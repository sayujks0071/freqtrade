#!/usr/bin/env python3
"""
The Sentinel (Circuit Breaker)
Real-time crisis management to protect capital.

Monitors account drawdown and Bitcoin price drops.
Triggers emergency liquidation and kill switch if thresholds are breached.
"""

import base64
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Sentinel")


class Sentinel:
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.api_url = "http://127.0.0.1:8080"
        self.username = ""
        self.password = ""
        self.jwt_token = None
        self.balance_history: list[tuple[float, float]] = []  # List of (timestamp, balance)
        self.is_dry_run = True

        self._load_config()

    def _load_config(self):
        """Load API credentials from config file."""
        if not self.config_path.exists():
            logger.error(f"Config file not found: {self.config_path}")
            sys.exit(1)

        try:
            with self.config_path.open("r") as f:
                config = json.load(f)
                api_config = config.get("api_server", {})
                self.api_url = (
                    f"http://{api_config.get('listen_ip_address', '127.0.0.1')}:"
                    f"{api_config.get('listen_port', 8080)}"
                )
                self.username = api_config.get("username", "")
                self.password = api_config.get("password", "")
                self.is_dry_run = config.get("dry_run", True)

                # Handle 0.0.0.0 binding
                if "0.0.0.0" in self.api_url:  # noqa: S104
                    self.api_url = self.api_url.replace("0.0.0.0", "127.0.0.1")  # noqa: S104

        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            sys.exit(1)

    def _get_headers(self, auth=False):
        """Get headers for requests."""
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if auth:
            if not self.jwt_token:
                self.authenticate()
            if self.jwt_token:
                headers["Authorization"] = f"Bearer {self.jwt_token}"
        return headers

    def authenticate(self):
        """Authenticate with the API to get a JWT token."""
        auth_url = f"{self.api_url}/api/v1/token/login"
        # Basic Auth for login
        auth_str = f"{self.username}:{self.password}"
        auth_bytes = auth_str.encode("ascii")
        base64_bytes = base64.b64encode(auth_bytes)
        base64_str = base64_bytes.decode("ascii")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {base64_str}",
        }

        try:
            req = urllib.request.Request(auth_url, headers=headers, method="POST")  # noqa: S310
            with urllib.request.urlopen(req) as response:  # noqa: S310
                data = json.loads(response.read().decode())
                self.jwt_token = data.get("access_token")
                logger.info("Successfully authenticated with Freqtrade API")
        except urllib.error.URLError as e:
            logger.error(f"Authentication failed: {e}")
            # If authentication fails, we might not be able to do anything.
            # But we should retry or exit.
            pass

    def _request(self, method, endpoint, data=None):
        """Make a request to the API."""
        url = f"{self.api_url}/api/v1/{endpoint}"
        headers = self._get_headers(auth=True)

        json_data = None
        if data:
            json_data = json.dumps(data).encode("utf-8")

        try:
            req = urllib.request.Request(url, data=json_data, headers=headers, method=method)  # noqa: S310
            with urllib.request.urlopen(req) as response:  # noqa: S310
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                logger.warning("Token expired, re-authenticating...")
                self.jwt_token = None
                self.authenticate()
                # Retry once
                return self._request(method, endpoint, data)
            logger.error(f"API request failed ({method} {endpoint}): {e}")
            return None
        except urllib.error.URLError as e:
            logger.error(f"Connection error ({url}): {e}")
            return None

    def get_balance(self):
        """Fetch current total balance."""
        data = self._request("GET", "balance")
        if data:
            # Total balance in stake currency is usually what we care about
            # The structure depends on the exchange/response.
            # Freqtrade /balance returns:
            # { "currencies": [...], "total": ..., "symbol": "USDT", "value": ... }
            # "total" is the total balance in stake currency.
            return data.get("total", 0.0)
        return None

    def get_btc_price_drop(self):
        """Check BTC price drop over last 4 hours."""
        # Fetch last 5 candles (4 hours history + current)
        # timeframe='1h', limit=5
        # Endpoint: /pair_candles?pair=BTC/USDT&timeframe=1h&limit=5
        # Query params need to be encoded if using standard lib, but here manual string is easy
        endpoint = "pair_candles?pair=BTC/USDT&timeframe=1h&limit=5"
        data = self._request("GET", endpoint)

        if not data or not isinstance(data, list) or len(data) < 2:
            logger.warning("Could not fetch BTC candles or insufficient data.")
            return 0.0

        # Data structure: [timestamp, open, high, low, close, volume]
        # We want the max High of the last 4 hours vs current Close.
        # If we have 5 candles, the last one is current (open), previous 4 are closed.
        # Actually, if we want "in 4 hours", we look at the window of 4h.

        highs = [candle[2] for candle in data]
        current_close = data[-1][4]  # Current candle close (or current price if live)
        max_high = max(highs)

        if max_high == 0:
            return 0.0

        drop = (current_close - max_high) / max_high
        return drop

    def check_drawdown(self, current_balance):
        """Check if drawdown > 5% in last hour."""
        now = time.time()
        self.balance_history.append((now, current_balance))

        # Prune old history (> 1 hour = 3600 seconds)
        one_hour_ago = now - 3600
        self.balance_history = [(t, b) for t, b in self.balance_history if t >= one_hour_ago]

        if not self.balance_history:
            return 0.0

        max_balance = max(b for t, b in self.balance_history)
        if max_balance == 0:
            return 0.0

        drawdown = (current_balance - max_balance) / max_balance
        return drawdown

    def emergency_stop(self, reason):
        """Trigger emergency stop sequence."""
        logger.critical(f"EMERGENCY STOP TRIGGERED: {reason}")

        # 1. Liquidation (Panic sell)
        logger.info("Attempting to panic sell all positions...")
        status = self._request("GET", "status")
        if status and isinstance(status, list):
            for trade in status:
                trade_id = trade.get("trade_id")
                if trade_id:
                    logger.info(f"Force exiting trade {trade_id}")
                    self._request("POST", "forceexit", {"tradeid": trade_id})

        # 2. Alert
        self.send_alert(f"CRITICAL ALERT: {reason}. Bot stopped and positions liquidated.")

        # 3. Kill Switch
        logger.info("Stopping the bot...")
        self._request("POST", "stop")

        logger.info("Sentinel has performed emergency shutdown. Exiting.")
        sys.exit(0)

    def send_alert(self, message):
        """Send alert via OpenClaw (Placeholder)."""
        logger.critical(f"OpenClaw Alert: {message}")
        # TODO: Implement OpenClaw / WhatsApp integration here.
        # For now, just logging is the action.

    def run(self):
        """Main monitoring loop."""
        logger.info("Sentinel started monitoring...")

        # Initial authentication
        self.authenticate()

        while True:
            try:
                # 1. Check Balance / Drawdown
                balance = self.get_balance()
                if balance is not None:
                    drawdown = self.check_drawdown(balance)
                    logger.info(f"Current Balance: {balance:.2f}, 1h Drawdown: {drawdown:.2%}")

                    if drawdown < -0.05:
                        self.emergency_stop(f"Drawdown {drawdown:.2%} exceeds limit of 5% in 1h")

                # 2. Check Bitcoin Drop
                btc_drop = self.get_btc_price_drop()
                logger.info(f"BTC 4h Drop: {btc_drop:.2%}")

                if btc_drop < -0.10:
                    self.emergency_stop(f"Bitcoin drop {btc_drop:.2%} exceeds limit of 10% in 4h")

                # Sleep 5 minutes
                time.sleep(300)

            except KeyboardInterrupt:
                logger.info("Sentinel stopped by user.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                time.sleep(60)  # Sleep a bit before retrying


if __name__ == "__main__":
    # Determine config path
    # Default to user_data/configs/config.delta.live.json
    default_config = Path("user_data/configs/config.delta.live.json")
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    elif default_config.exists():
        config_file = str(default_config)
    else:
        # Fallback to config.json if exists
        fallback = Path("config.json")
        if fallback.exists():
            config_file = str(fallback)
        else:
            print("Error: No configuration file found.")
            sys.exit(1)

    sentinel = Sentinel(config_file)
    sentinel.run()
