#!/usr/bin/env python3
"""
Sentinel Script
Monitors Freqtrade for emergency conditions:
1. Drawdown > 5% in 1h
2. Bitcoin Crash > 10% in 4h
Triggers: Panic Sell, Kill Switch, Alert.
"""

import argparse
import json
import logging
import time
from pathlib import Path

import ccxt
import requests
from requests.auth import HTTPBasicAuth


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Sentinel")


class Sentinel:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = self._load_config()

        # Ensure api_server config exists
        if "api_server" not in self.config:
            raise ValueError("Config file missing 'api_server' section.")

        ip = self.config["api_server"].get("listen_ip_address", "127.0.0.1")
        port = self.config["api_server"].get("listen_port", 8080)
        self.api_url = f"http://{ip}:{port}/api/v1"
        self.username = self.config["api_server"].get("username")
        self.password = self.config["api_server"].get("password")

        if not self.username or not self.password:
            raise ValueError("API username or password missing in config.")

        self.access_token = None
        self.refresh_token = None

        self.state_file = Path("user_data/sentinel_state.json")
        self.balance_history = self._load_state()  # List of [timestamp, balance]

    def _load_config(self) -> dict:
        with self.config_path.open() as f:
            return json.load(f)

    def _load_state(self) -> list:
        if self.state_file.exists():
            try:
                with self.state_file.open() as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except json.JSONDecodeError:
                pass
        return []

    def _save_state(self):
        # Create directory if it doesn't exist (though user_data usually exists)
        self.state_file.parent.mkdir(exist_ok=True, parents=True)
        with self.state_file.open("w") as f:
            json.dump(self.balance_history, f)

    def login(self):
        """Authenticates with the API and retrieves tokens."""
        try:
            response = requests.post(
                f"{self.api_url}/token/login",
                auth=HTTPBasicAuth(self.username, self.password),
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            self.access_token = data["access_token"]
            self.refresh_token = data["refresh_token"]
            logger.info("Successfully authenticated with API.")
        except requests.RequestException as e:
            logger.error(f"Login failed: {e}")
            raise

    def refresh_access_token(self):
        """Refreshes the access token using the refresh token."""
        if not self.refresh_token:
            self.login()
            return

        try:
            headers = {"Authorization": f"Bearer {self.refresh_token}"}
            response = requests.post(
                f"{self.api_url}/token/refresh",
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            self.access_token = data["access_token"]
            logger.info("Refreshed access token.")
        except requests.RequestException as e:
            logger.error(f"Token refresh failed: {e}")
            # If refresh fails, try full login
            self.login()

    def api_request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Wrapper for API requests with automatic authentication handling."""
        if not self.access_token:
            self.login()

        url = f"{self.api_url}{endpoint}"
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.access_token}"

        kwargs.setdefault("timeout", 10)
        try:
            response = requests.request(method, url, headers=headers, **kwargs)  # noqa: S113

            if response.status_code == 401:
                # Token expired, refresh and retry
                logger.info("Token expired, refreshing...")
                self.refresh_access_token()
                headers["Authorization"] = f"Bearer {self.access_token}"
                response = requests.request(method, url, headers=headers, **kwargs)  # noqa: S113

            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"API request failed ({method} {endpoint}): {e}")
            raise

    def get_total_balance(self) -> float:
        """Fetches total account balance in stake currency."""
        data = self.api_request("GET", "/balance")
        # The balance endpoint returns a 'total' field which is the total value in stake currency
        # Structure: {"currencies": [...], "total": 123.45, ...}
        return float(data.get("total", 0.0))

    def check_drawdown(self):
        """Checks if drawdown exceeds 5% in the last hour."""
        try:
            current_balance = self.get_total_balance()
            now = time.time()
            self.balance_history.append([now, current_balance])

            # Prune older than 1 hour (3600s)
            cutoff = now - 3600
            self.balance_history = [x for x in self.balance_history if x[0] > cutoff]
            self._save_state()

            if not self.balance_history:
                return

            # Max balance in the window
            max_balance = max(x[1] for x in self.balance_history)

            if max_balance == 0:
                return

            drawdown = (max_balance - current_balance) / max_balance

            if drawdown > 0.05:
                msg = (
                    f"Drawdown Alert: {drawdown:.2%} in last hour! "
                    f"(Max: {max_balance}, Current: {current_balance})"
                )
                logger.critical(msg)
                self.trigger_emergency(msg)
            else:
                logger.debug(f"Current Drawdown: {drawdown:.2%}")

        except Exception as e:
            logger.error(f"Error checking drawdown: {e}")

    def check_btc_crash(self):
        """Checks if Bitcoin dropped > 10% in the last 4 hours."""
        try:
            exchange = ccxt.gateio()
            # Fetch 1h candles, limit=5 (Current + 4 previous)
            # Gate.io usually supports 1h
            candles = exchange.fetch_ohlcv("BTC/USDT", "1h", limit=5)

            if not candles:
                logger.warning("No candle data returned for BTC/USDT")
                return

            # Candle format: [timestamp, open, high, low, close, volume]
            # Max High in the window
            max_high = max(c[2] for c in candles)
            # Current Close (latest candle's close price)
            current_price = candles[-1][4]

            if max_high == 0:
                return

            drop = (max_high - current_price) / max_high

            if drop > 0.10:
                msg = (
                    f"Bitcoin Crash Alert: {drop:.2%} drop in last 4 hours! "
                    f"(High: {max_high}, Current: {current_price})"
                )
                logger.critical(msg)
                self.trigger_emergency(msg)
            else:
                logger.debug(f"BTC Drop: {drop:.2%}")

        except Exception as e:
            logger.error(f"Error checking BTC crash: {e}")

    def trigger_emergency(self, reason: str):
        """Triggers emergency actions: Panic Sell, Stop Bot, Alert."""
        logger.critical(f"TRIGGERING EMERGENCY: {reason}")

        # 1. Panic Sell (Force Exit All)
        try:
            logger.info("Attempting to liquidate all positions...")
            self.api_request("POST", "/forceexit", json={"tradeid": "all"})
            logger.info("Force Exit command sent successfully.")
        except Exception:
            logger.error("Failed to execute Force Exit command.")

        # 2. Kill Switch (Stop Bot)
        try:
            logger.info("Attempting to stop the bot...")
            self.api_request("POST", "/stop")
            logger.info("Stop command sent successfully.")
        except Exception:
            logger.error("Failed to execute Stop command.")

        # 3. Alert (Logged as CRITICAL above)
        # Assuming external log monitoring picks up CRITICAL logs

    def run(self):
        logger.info("Sentinel started monitoring...")
        while True:
            self.check_drawdown()
            self.check_btc_crash()
            time.sleep(300)


def main():
    parser = argparse.ArgumentParser(description="Freqtrade Sentinel (Circuit Breaker)")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("user_data/configs/config.delta.live.json"),
        help="Path to config file",
    )
    args = parser.parse_args()

    if not args.config.exists():
        logger.error(f"Config file not found: {args.config}")
        return

    sentinel = Sentinel(args.config)
    sentinel.run()


if __name__ == "__main__":
    main()
