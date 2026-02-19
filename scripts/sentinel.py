#!/usr/bin/env python3
"""
Sentinel Script (Circuit Breaker)
Monitors Freqtrade bot status and market conditions to protect capital.
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import ccxt
import requests


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Sentinel")


class Sentinel:
    def __init__(self, config_path: str, state_file: str, dry_run: bool = False):
        self.config_path = Path(config_path)
        self.state_file = Path(state_file)
        self.dry_run = dry_run
        self.config = self._load_config()
        self.api_url = self._get_api_url()
        self.api_auth = self._get_api_auth()
        self.jwt_token: str | None = None
        self.exchange = self._init_exchange()
        self.balance_history: list[tuple[float, float]] = []  # List of (timestamp, balance)
        self.openclaw_url = os.getenv("OPENCLAW_URL", "http://localhost:5000/send")
        self.liquidate_on_trigger = os.getenv("SENTINEL_LIQUIDATE", "false").lower() == "true"

    def _load_config(self) -> dict[str, Any]:
        """Loads the Freqtrade configuration file."""
        try:
            with self.config_path.open("r") as f:
                # Freqtrade configs can contain comments, so we use json.load
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load config from {self.config_path}: {e}")
            sys.exit(1)

    def _get_api_url(self) -> str:
        api_config = self.config.get("api_server", {})
        if not api_config.get("enabled", False):
            logger.error("API Server is not enabled in configuration.")
            sys.exit(1)
        ip = api_config.get("listen_ip_address", "127.0.0.1")
        if ip == "0.0.0.0":  # noqa: S104
            ip = "127.0.0.1"
        port = api_config.get("listen_port", 8080)
        return f"http://{ip}:{port}/api/v1"

    def _get_api_auth(self) -> tuple[str, str]:
        api_config = self.config.get("api_server", {})
        username = api_config.get("username")
        password = api_config.get("password")
        if not username or not password:
            logger.error("API credentials missing in configuration.")
            sys.exit(1)
        return (username, password)

    def _init_exchange(self) -> ccxt.Exchange:
        """Initialize CCXT exchange for market data (BTC/USDT)."""
        # We use Binance for reliable market data, or fallback to the configured exchange if needed.
        # The prompt implies watching "Bitcoin" globally.
        try:
            return ccxt.binance()
        except Exception as e:
            logger.warning(f"Failed to initialize Binance: {e}. Falling back to generic CCXT.")
            return ccxt.binance()

    def _authenticate(self):
        """Authenticate with Freqtrade API to get JWT token."""
        try:
            response = requests.post(
                f"{self.api_url}/token/login",
                auth=self.api_auth,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            self.jwt_token = data.get("access_token")
            logger.info("Successfully authenticated with Freqtrade API.")
        except requests.RequestException as e:
            logger.error(f"Authentication failed: {e}")
            # Don't exit, retry later? For now, we need auth to work.
            pass

    def _get_headers(self) -> dict[str, str]:
        if not self.jwt_token:
            self._authenticate()
        return {"Authorization": f"Bearer {self.jwt_token}"}

    def _get_balance(self) -> float | None:
        """Fetch current total balance from Freqtrade API."""
        try:
            response = requests.get(
                f"{self.api_url}/balance",
                headers=self._get_headers(),
                timeout=10
            )
            if response.status_code == 401:  # Token expired
                self._authenticate()
                response = requests.get(
                    f"{self.api_url}/balance",
                    headers=self._get_headers(),
                    timeout=10
                )
            response.raise_for_status()
            data = response.json()
            # Depending on the response structure, usually 'total' or similar.
            # freqtrade /balance returns: {'currencies': [...], 'total': ..., ...}
            # We want the total value in stake currency (usually USDT).
            return data.get("total")
        except requests.RequestException as e:
            logger.error(f"Failed to fetch balance: {e}")
            return None

    def _get_btc_price_drop(self) -> float:
        """
        Check if BTC dropped > 10% in the last 4 hours.
        Returns the drop percentage (positive value = drop).
        """
        try:
            # Fetch OHLCV for last 4 hours (1h candles)
            ohlcv = self.exchange.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=5)
            if not ohlcv:
                return 0.0

            # ohlcv is list of [timestamp, open, high, low, close, volume]
            # We want the High of the last 4 hours (excluding current partially complete candle
            # if we want strict 4h, but usually "last 4h" means window).
            # Let's take the max High from the last 4 completed candles + current.
            highs = [candle[2] for candle in ohlcv]
            current_close = ohlcv[-1][4]
            max_high = max(highs)

            if max_high == 0:
                return 0.0

            drop = (max_high - current_close) / max_high
            return drop
        except Exception as e:
            logger.error(f"Failed to fetch BTC price: {e}")
            return 0.0

    def load_state(self):
        """Load balance history from state file."""
        try:
            with self.state_file.open("r") as f:
                data = json.load(f)
                self.balance_history = data.get("balance_history", [])
        except (FileNotFoundError, json.JSONDecodeError):
            logger.info("No valid state file found, starting fresh.")
            self.balance_history = []

    def save_state(self):
        """Save balance history to state file."""
        try:
            # Prune entries older than 1 hour
            cutoff = time.time() - 3600
            self.balance_history = [
                entry for entry in self.balance_history if entry[0] > cutoff
            ]

            with self.state_file.open("w") as f:
                json.dump({"balance_history": self.balance_history}, f)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def check_drawdown(self, current_balance: float) -> float:
        """
        Check drawdown in the last hour.
        Returns drawdown percentage (positive value = loss).
        """
        now = time.time()
        self.balance_history.append((now, current_balance))

        # Calculate max balance in history
        if not self.balance_history:
            return 0.0

        max_balance = max(entry[1] for entry in self.balance_history)
        if max_balance == 0:
            return 0.0

        drawdown = (max_balance - current_balance) / max_balance
        return drawdown

    def trigger_emergency(self, reason: str):
        """Execute emergency actions."""
        logger.critical(f"EMERGENCY TRIGGERED: {reason}")

        # 1. Alert
        self._send_alert(f"CRITICAL ALERT: {reason}")

        # 2. Liquidation (Optional)
        if self.liquidate_on_trigger:
            self._liquidate()

        # 3. Kill Switch
        self._stop_bot()

    def _send_alert(self, message: str):
        try:
            payload = {"message": message}
            response = requests.post(self.openclaw_url, json=payload, timeout=5)
            if response.status_code != 200:
                logger.error(
                    f"Failed to send alert to OpenClaw: {response.status_code} {response.text}"
                )
            else:
                logger.info("Alert sent via OpenClaw.")
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")

    def _liquidate(self):
        logger.warning("Attempting to liquidate all positions...")
        try:
            response = requests.post(
                f"{self.api_url}/forceexit",
                headers=self._get_headers(),
                timeout=10
            )
            if response.status_code == 200:
                logger.info("Liquidation command sent successfully.")
            else:
                logger.error(f"Liquidation failed: {response.text}")
        except Exception as e:
            logger.error(f"Liquidation request failed: {e}")

    def _stop_bot(self):
        logger.critical("Stopping Freqtrade bot...")
        try:
            response = requests.post(
                f"{self.api_url}/stop",
                headers=self._get_headers(),
                timeout=10
            )
            if response.status_code == 200:
                logger.info("Bot stopped successfully.")
            else:
                logger.error(f"Failed to stop bot: {response.text}")
        except Exception as e:
            logger.error(f"Stop request failed: {e}")

        # Exit the sentinel script as well
        sys.exit(0)

    def run(self):
        logger.info("Sentinel started monitoring...")
        while True:
            try:
                self.load_state()

                # Check BTC
                btc_drop = self._get_btc_price_drop()
                logger.info(f"BTC Drop (4h): {btc_drop * 100:.2f}%")
                if btc_drop > 0.10:
                    self.trigger_emergency(f"Bitcoin dropped {btc_drop * 100:.2f}% in last 4 hours")

                # Check Balance / Drawdown
                current_balance = self._get_balance()
                if current_balance is not None:
                    drawdown = self.check_drawdown(current_balance)
                    logger.info(
                        f"Current Balance: {current_balance}, Drawdown (1h): {drawdown * 100:.2f}%"
                    )
                    if drawdown > 0.05:
                        self.trigger_emergency(
                            f"Drawdown {drawdown * 100:.2f}% exceeds 5% limit in last hour"
                        )

                self.save_state()

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")

            time.sleep(300)  # 5 minutes


def main():
    parser = argparse.ArgumentParser(description="Freqtrade Sentinel")
    parser.add_argument(
        "--config",
        default="user_data/configs/config.delta.live.json",
        help="Path to config file"
    )
    parser.add_argument(
        "--state",
        default="user_data/sentinel_state.json",
        help="Path to state file"
    )
    args = parser.parse_args()

    sentinel = Sentinel(args.config, args.state)
    sentinel.run()


if __name__ == "__main__":
    main()
