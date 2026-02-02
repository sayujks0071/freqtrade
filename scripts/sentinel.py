#!/usr/bin/env python3
"""
The "Sentinel" (Circuit Breaker)
Goal: Real-time crisis management to protect capital.
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import ccxt
import requests


# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("sentinel.log")],
)
logger = logging.getLogger("Sentinel")

# Constants
CHECK_INTERVAL = 300  # 5 minutes
BTC_DROP_THRESHOLD = 0.10  # 10%
BTC_DROP_WINDOW_HOURS = 4
DRAWDOWN_THRESHOLD = 0.05  # 5%
DRAWDOWN_WINDOW_MINUTES = 60


class Sentinel:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = self._load_config()

        # API Configuration
        api_config = self.config.get("api_server", {})
        self.api_ip = api_config.get("listen_ip_address", "127.0.0.1")
        if self.api_ip == "0.0.0.0":  # noqa: S104
            self.api_ip = "127.0.0.1"
        self.api_port = api_config.get("listen_port", 8080)
        self.username = api_config.get("username")
        self.password = api_config.get("password")
        self.base_url = f"http://{self.api_ip}:{self.api_port}/api/v1"

        self.token = None

        # State
        self.balance_history: list[
            tuple[datetime, float]
        ] = []  # List of (timestamp, total_balance)

        # Gate.io for BTC monitoring (Reliable Source)
        self.exchange = ccxt.gateio({"enableRateLimit": True})

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            logger.error(f"Config file not found: {self.config_path}")
            sys.exit(1)

        try:
            with self.config_path.open("r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            sys.exit(1)

    def login(self):
        """Authenticate with Freqtrade API"""
        try:
            logger.info("Authenticating with Freqtrade API...")
            auth = (self.username, self.password)
            response = requests.post(f"{self.base_url}/login", auth=auth, timeout=10)

            if response.status_code == 200:
                self.token = response.json().get("access_token")
                logger.info("Authentication successful.")
            else:
                logger.error(f"Authentication failed: {response.status_code} {response.text}")
                self.token = None
        except requests.RequestException as e:
            logger.error(f"Connection error during login: {e}")
            self.token = None

    def get_headers(self) -> dict:
        if not self.token:
            self.login()
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def get_balance(self) -> float | None:
        """Fetch current total balance (stake currency)"""
        if not self.token:
            self.login()
            if not self.token:
                return None

        try:
            response = requests.get(
                f"{self.base_url}/balance", headers=self.get_headers(), timeout=10
            )

            if response.status_code == 401:  # Unauthorized (Token expired?)
                logger.warning("Token expired, re-authenticating...")
                self.login()
                response = requests.get(
                    f"{self.base_url}/balance", headers=self.get_headers(), timeout=10
                )

            if response.status_code == 200:
                data = response.json()
                # 'total' is the total value in stake currency
                return data.get("total")
            else:
                logger.error(f"Failed to get balance: {response.status_code} {response.text}")
                return None
        except requests.RequestException as e:
            logger.error(f"Connection error fetching balance: {e}")
            return None

    def check_drawdown(self, current_balance: float) -> bool:
        """
        Check if drawdown > 5% in the last hour.
        Returns True if triggered.
        """
        now = datetime.now()
        self.balance_history.append((now, current_balance))

        # Prune history older than window
        cutoff = now - timedelta(minutes=DRAWDOWN_WINDOW_MINUTES)
        self.balance_history = [x for x in self.balance_history if x[0] >= cutoff]

        if not self.balance_history:
            return False

        # Calculate Max Balance in the window
        max_balance = max(x[1] for x in self.balance_history)

        if max_balance <= 0:
            return False

        drawdown = (max_balance - current_balance) / max_balance

        if drawdown > DRAWDOWN_THRESHOLD:
            logger.critical(
                f"DRAWDOWN TRIGGERED: {drawdown:.2%} in last hour. "
                f"Max: {max_balance}, Current: {current_balance}"
            )
            return True
        return False

    def check_btc_crash(self) -> bool:
        """
        Check if Bitcoin dropped > 10% in the last 4 hours.
        Returns True if triggered.
        """
        try:
            # Fetch last 5 candles (1h timeframe) to cover 4 hours history + current
            ohlcv = self.exchange.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=6)
            if not ohlcv:
                logger.warning("No BTC data fetched.")
                return False

            # ohlcv format: [timestamp, open, high, low, close, volume]
            # We want the highest high in the window vs current close

            # The last candle is current/incomplete.
            current_close = ohlcv[-1][4]

            # Use Highs of all fetched candles as the reference peak
            highs = [candle[2] for candle in ohlcv]
            max_high = max(highs)

            if max_high <= 0:
                return False

            drop = (max_high - current_close) / max_high

            if drop > BTC_DROP_THRESHOLD:
                logger.critical(
                    f"BTC CRASH TRIGGERED: {drop:.2%} drop in 4h. "
                    f"High: {max_high}, Current: {current_close}"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking BTC price: {e}")
            return False

    def trigger_emergency(self):
        """Execute Kill Switch and Liquidation"""
        logger.critical("!!! EMERGENCY PROTOCOL INITIATED !!!")
        self.send_alert("CRITICAL ALERT: Sentinel triggered! Executing emergency procedures.")

        headers = self.get_headers()

        # 1. Panic Sell (Liquidation)
        logger.info("Attempting to liquidate all positions (Force Exit)...")
        try:
            # forceexit with tradeid="all"
            payload = {"tradeid": "all"}
            response = requests.post(
                f"{self.base_url}/forceexit", json=payload, headers=headers, timeout=10
            )
            if response.status_code == 200:
                logger.info("Force exit command sent successfully.")
            else:
                logger.error(f"Force exit failed: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"Exception during force exit: {e}")

        # 2. Kill Switch (Stop Bot)
        logger.info("Attempting to STOP the trading bot...")
        try:
            response = requests.post(f"{self.base_url}/stop", headers=headers, timeout=10)
            if response.status_code == 200:
                logger.info("Bot stop command sent successfully.")
            else:
                logger.error(f"Bot stop command failed: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"Exception during bot stop: {e}")

    def send_alert(self, message: str):
        """Send alert via OpenClaw/WhatsApp (Placeholder)"""
        # Placeholder for actual integration
        logger.info(f"Adding to alert queue (OpenClaw/WhatsApp): {message}")
        # In a real implementation, you would call the OpenClaw API here.
        # print(f"OpenClaw: {message}")

    def run(self):
        logger.info("Sentinel started monitoring.")
        logger.info(f"Drawdown Threshold: {DRAWDOWN_THRESHOLD * 100}% / {DRAWDOWN_WINDOW_MINUTES}m")
        logger.info(f"BTC Drop Threshold: {BTC_DROP_THRESHOLD * 100}% / {BTC_DROP_WINDOW_HOURS}h")

        while True:
            try:
                # 1. Check Balance & Drawdown
                current_balance = self.get_balance()
                if current_balance is not None:
                    if self.check_drawdown(current_balance):
                        self.trigger_emergency()
                        logger.info("Sentinel stopping after emergency trigger.")
                        sys.exit(0)
                    logger.info(f"Balance Check: {current_balance:.2f} (OK)")

                # 2. Check BTC Crash
                if self.check_btc_crash():
                    self.trigger_emergency()
                    logger.info("Sentinel stopping after emergency trigger.")
                    sys.exit(0)
                logger.info("BTC Check: Market Stable (OK)")

            except KeyboardInterrupt:
                logger.info("Sentinel stopped by user.")
                sys.exit(0)
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")

            time.sleep(CHECK_INTERVAL)


def main():
    parser = argparse.ArgumentParser(description="Sentinel: Freqtrade Circuit Breaker")
    parser.add_argument(
        "--config",
        type=str,
        default="user_data/configs/config.delta.dryrun.json",
        help="Path to Freqtrade config file",
    )
    args = parser.parse_args()

    config_path = Path(args.config)

    sentinel = Sentinel(config_path)
    sentinel.run()


if __name__ == "__main__":
    main()
