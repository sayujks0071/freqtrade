#!/usr/bin/env python3
"""
Sentinel (Circuit Breaker) Script
Monitors live logs/state and triggers emergency actions.
"""

import argparse
import logging
import sys
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import ccxt
import requests


# Try to import freqtrade for config loading, else fallback to json
try:
    from freqtrade.configuration.load_config import load_config_file
except ImportError:
    load_config_file = None  # type: ignore
    import json
    import re

    def _strip_comments(text: str) -> str:
        return re.sub(r"//.*", "", text)


logger = logging.getLogger("Sentinel")


class Sentinel:
    def __init__(self, config_path: Path, api_url: str, api_user: str, api_pass: str):
        self.config_path = config_path
        self.api_url = api_url.rstrip("/")
        self.api_user = api_user
        self.api_pass = api_pass
        self.access_token: str | None = None
        self.refresh_token: str | None = None

        # History for Drawdown Calculation (1 hour)
        # Stores (timestamp, total_balance)
        self.balance_history: deque[tuple[datetime, float]] = deque()

        # Exchange for BTC price monitoring
        self.exchange_id = "binance"
        self.exchange: ccxt.Exchange | None = None

        self.setup_exchange()

    def setup_exchange(self):
        """Initialize CCXT exchange for BTC monitoring."""
        try:
            # Attempt to load exchange from config if available
            config = self._load_config()
            if config:
                self.exchange_id = config.get("exchange", {}).get("name", "binance")

            exchange_class = getattr(ccxt, self.exchange_id)
            self.exchange = exchange_class({"enableRateLimit": True})
            logger.info(f"Initialized exchange: {self.exchange_id}")
        except Exception as e:
            logger.error(f"Failed to initialize exchange {self.exchange_id}: {e}")
            # Fallback to binance if configured one fails
            if self.exchange_id != "binance":
                logger.info("Falling back to binance for BTC monitoring.")
                self.exchange_id = "binance"
                self.exchange = ccxt.binance({"enableRateLimit": True})

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from file."""
        if not self.config_path.exists():
            return {}

        if load_config_file:  # type: ignore
            return load_config_file(str(self.config_path))  # type: ignore

        try:
            with self.config_path.open("r") as f:
                content = _strip_comments(f.read())
                return json.loads(content)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

    def authenticate(self) -> bool:
        """Authenticate with Freqtrade RPC."""
        try:
            auth_url = f"{self.api_url}/api/v1/token/login"
            response = requests.post(auth_url, auth=(self.api_user, self.api_pass), timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get("access_token")
                self.refresh_token = data.get("refresh_token")
                return True
            else:
                logger.error(f"Authentication failed: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False

    def get_auth_header(self) -> dict[str, str]:
        """Return Authorization header."""
        if not self.access_token:
            self.authenticate()
        return {"Authorization": f"Bearer {self.access_token}"}

    def get_balance(self) -> float | None:
        """Get current total balance from RPC."""
        try:
            url = f"{self.api_url}/api/v1/balance"
            response = requests.get(url, headers=self.get_auth_header(), timeout=10)

            if response.status_code == 401:
                # Token expired, re-auth and retry
                if self.authenticate():
                    response = requests.get(url, headers=self.get_auth_header(), timeout=10)

            if response.status_code == 200:
                data = response.json()
                # 'total' field usually contains total balance in stake currency
                # Freqtrade API /balance returns 'total' at top level
                return float(data.get("total", 0.0))
            else:
                logger.error(f"Failed to get balance: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return None

    def get_btc_price_drop(self) -> float:
        """
        Calculate BTC price drop percentage over last 4 hours.
        Returns drop as positive float (e.g. 0.12 for 12% drop).
        """
        if not self.exchange:
            return 0.0

        try:
            # Fetch OHLCV for BTC/USDT (1h candles, last 5 candles to cover 4h + current)
            symbol = "BTC/USDT"
            timeframe = "1h"
            limit = 5
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

            if not ohlcv:
                return 0.0

            # Highs of the last candles
            highs = [candle[2] for candle in ohlcv]
            current_close = ohlcv[-1][4]

            max_high = max(highs)
            if max_high == 0:
                return 0.0

            drop = (max_high - current_close) / max_high
            return drop

        except Exception as e:
            logger.error(f"Error getting BTC price: {e}")
            return 0.0

    def check_drawdown(self) -> bool:
        """
        Check if drawdown > 5% in the last hour.
        """
        current_balance = self.get_balance()
        if current_balance is None:
            return False

        now = datetime.now(UTC)
        self.balance_history.append((now, current_balance))

        # Prune history older than 1 hour
        one_hour_ago = now - timedelta(hours=1)
        while self.balance_history and self.balance_history[0][0] < one_hour_ago:
            self.balance_history.popleft()

        if not self.balance_history:
            return False

        max_balance = max(b for t, b in self.balance_history)
        if max_balance == 0:
            return False

        drawdown = (max_balance - current_balance) / max_balance

        logger.info(
            f"Current Balance: {current_balance:.2f} | "
            f"Max (1h): {max_balance:.2f} | "
            f"Drawdown: {drawdown:.2%}"
        )

        return drawdown > 0.05

    def check_btc_crash(self) -> bool:
        """
        Check if Bitcoin drops > 10% in 4 hours.
        """
        drop = self.get_btc_price_drop()
        logger.info(f"BTC Drop (4h): {drop:.2%}")
        return drop > 0.10

    def emergency_stop(self, reason: str):
        """
        Execute Kill Switch, Liquidation, and Alert.
        """
        logger.critical(f"EMERGENCY STOP TRIGGERED: {reason}")
        self.send_alert(f"CRITICAL ALERT: {reason}. Executing Emergency Stop.")

        headers = self.get_auth_header()

        # 1. Liquidation (Panic Sell)
        try:
            logger.info("Executing Force Exit (Panic Sell)...")
            url = f"{self.api_url}/api/v1/forceexit"
            # Payload for 'all' trades
            payload = {"tradeid": "all"}
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            logger.info(f"Force Exit Response: {response.text}")
        except Exception as e:
            logger.error(f"Failed to force exit: {e}")

        # 2. Kill Switch (Stop Bot)
        try:
            logger.info("Stopping Bot...")
            url = f"{self.api_url}/api/v1/stop"
            response = requests.post(url, headers=headers, timeout=10)
            logger.info(f"Stop Response: {response.text}")
        except Exception as e:
            logger.error(f"Failed to stop bot: {e}")

    def send_alert(self, message: str):
        """
        Send alert via OpenClaw (Placeholder).
        """
        # Placeholder for OpenClaw integration
        # TODO: Implement actual OpenClaw / WhatsApp integration
        print(f"!!! ALERT: {message} !!!")
        logger.critical(message)

    def run(self):
        """Main monitoring loop."""
        logger.info("Sentinel started. Monitoring...")
        if not self.authenticate():
            logger.error("Initial authentication failed. Exiting.")
            sys.exit(1)

        while True:
            try:
                drawdown_trigger = self.check_drawdown()
                btc_crash_trigger = self.check_btc_crash()

                if drawdown_trigger:
                    self.emergency_stop("Drawdown > 5% in last hour")
                    # Stop monitoring after trigger? Or keep alerting?
                    # "Resume: Do not restart trading until I manually approve it."
                    # The bot is stopped, so Sentinel can likely exit or just wait.
                    logger.info("Emergency actions taken. Sentinel exiting.")
                    sys.exit(0)

                if btc_crash_trigger:
                    self.emergency_stop("Bitcoin drops > 10% in 4 hours")
                    logger.info("Emergency actions taken. Sentinel exiting.")
                    sys.exit(0)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")

            # Sleep 5 minutes
            time.sleep(300)


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="Sentinel: Freqtrade Circuit Breaker")
    parser.add_argument("--config", type=Path, help="Path to config file")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8080", help="API URL")
    parser.add_argument("--user", type=str, help="API Username")
    parser.add_argument("--password", type=str, help="API Password")

    args = parser.parse_args()

    # Try to load credentials from config if not provided
    config_path = args.config
    if not config_path:
        # Default config path
        default_path = Path("user_data/configs/config.delta.live.json")
        if default_path.exists():
            config_path = default_path

    api_user = args.user
    api_pass = args.password
    api_url = args.url

    if config_path and config_path.exists():
        try:
            # Quick load to get API creds
            if load_config_file:  # type: ignore
                config = load_config_file(str(config_path))  # type: ignore
            else:
                with config_path.open("r") as f:
                    # simplistic load
                    import json
                    import re

                    content = re.sub(r"//.*", "", f.read())
                    config = json.loads(content)

            api_server = config.get("api_server", {})
            if not api_user:
                api_user = api_server.get("username")
            if not api_pass:
                api_pass = api_server.get("password")
            if (
                not args.url
                and api_server.get("listen_ip_address")
                and api_server.get("listen_port")
            ):
                api_url = f"http://{api_server['listen_ip_address']}:{api_server['listen_port']}"

        except Exception as e:
            logger.warning(f"Failed to load credentials from config: {e}")

    if not api_user or not api_pass:
        logger.error("API credentials not provided and could not be loaded from config.")
        sys.exit(1)

    sentinel = Sentinel(config_path or Path("config.json"), api_url, api_user, api_pass)
    sentinel.run()


if __name__ == "__main__":
    main()
