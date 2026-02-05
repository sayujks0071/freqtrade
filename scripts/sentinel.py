#!/usr/bin/env python3
"""
Sentinel: Circuit Breaker for Freqtrade
Monitors live logs/status and triggers emergency stops.
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


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Sentinel")


class Sentinel:
    def __init__(self, config_path: Path, interval: int = 300):
        self.config_path = config_path
        self.interval = interval
        self.rpc_url = ""
        self.rpc_token = ""
        self.balance_history: list[tuple[datetime, float]] = []  # List of (timestamp, balance)
        self.btc_exchange = ccxt.gateio()  # Public access is enough for OHLCV

        self.config = self.load_config()
        self.setup_rpc()

    def load_config(self):
        if not self.config_path.exists():
            logger.error(f"Config file not found: {self.config_path}")
            sys.exit(1)

        with self.config_path.open() as f:
            return json.load(f)

    def setup_rpc(self):
        api_config = self.config.get("api_server", {})
        if not api_config.get("enabled", False):
            logger.error("API Server is not enabled in config.")
            sys.exit(1)

        ip = api_config.get("listen_ip_address", "127.0.0.1")
        port = api_config.get("listen_port", 8080)
        username = api_config.get("username")
        password = api_config.get("password")

        if ip == "0.0.0.0":  # noqa: S104
            ip = "127.0.0.1"

        self.rpc_url = f"http://{ip}:{port}/api/v1"

        # Authenticate
        try:
            auth_url = f"{self.rpc_url}/token/login"
            resp = requests.post(
                auth_url,
                data={"username": username, "password": password},
                timeout=10,
            )
            resp.raise_for_status()
            self.rpc_token = resp.json().get("access_token")
            logger.info("Successfully authenticated with Freqtrade RPC.")
        except Exception as e:
            logger.error(f"Failed to authenticate with RPC: {e}")
            sys.exit(1)

    def get_headers(self):
        return {"Authorization": f"Bearer {self.rpc_token}"}

    def get_current_balance(self):
        try:
            resp = requests.get(f"{self.rpc_url}/balance", headers=self.get_headers(), timeout=10)
            resp.raise_for_status()
            data = resp.json()
            # Return total balance in stake currency
            # Usually 'total' field implies the estimated total
            return data.get("total", 0.0)
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return None

    def check_drawdown(self):
        current_balance = self.get_current_balance()
        if current_balance is None:
            return False

        now = datetime.now()
        self.balance_history.append((now, current_balance))

        # Prune old history (> 1 hour)
        cutoff = now - timedelta(hours=1)
        self.balance_history = [(t, b) for t, b in self.balance_history if t > cutoff]

        if not self.balance_history:
            return False

        max_balance = max(b for t, b in self.balance_history)

        # Avoid division by zero
        if max_balance == 0:
            return False

        drawdown = (max_balance - current_balance) / max_balance

        if drawdown > 0.05:
            logger.warning(
                f"Drawdown Alert: {drawdown:.2%} in last hour "
                f"(Max: {max_balance}, Current: {current_balance})"
            )
            return True

        return False

    def check_btc_drop(self):
        try:
            # Fetch last 4 hours of 1h candles
            # limit=5 ensures we have enough coverage
            ohlcv = self.btc_exchange.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=5)

            if not ohlcv:
                return False

            # ohlcv is list of [timestamp, open, high, low, close, volume]
            relevant_candles = ohlcv[-5:]  # Just to be safe

            max_price = 0.0
            current_price = relevant_candles[-1][4]  # Close of last candle (current)

            # Check Highs of relevant period
            for candle in relevant_candles:
                if candle[2] > max_price:
                    max_price = candle[2]

            if max_price == 0:
                return False

            drop = (max_price - current_price) / max_price

            if drop > 0.10:
                logger.warning(
                    f"BTC Drop Alert: {drop:.2%} in last 4h "
                    f"(Max: {max_price}, Current: {current_price})"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking BTC price: {e}")
            return False

    def trigger_emergency(self, reason):
        logger.critical(f"TRIGGERING EMERGENCY PROTOCOL: {reason}")

        # 1. Alert OpenClaw
        self.send_alert(f"CRITICAL ALERT: {reason}. Triggering Kill Switch.")

        # 2. Liquidation (Panic Sell)
        self.liquidation()

        # 3. Kill Switch
        self.kill_switch()

    def send_alert(self, message):
        logger.info(f"Sending Alert: {message}")
        # Placeholder for OpenClaw
        print(f"OPENCLAW >> {message}")

    def liquidation(self):
        logger.info("Attempting Global Liquidation...")
        try:
            resp = requests.post(
                f"{self.rpc_url}/forceexit",
                headers=self.get_headers(),
                json={"all": True},
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("Liquidation signal sent successfully.")
            else:
                logger.error(f"Liquidation failed: {resp.text}")
        except Exception as e:
            logger.error(f"Liquidation error: {e}")

    def kill_switch(self):
        logger.info("Engaging Kill Switch (Stopping Bot)...")
        try:
            resp = requests.post(f"{self.rpc_url}/stop", headers=self.get_headers(), timeout=10)
            if resp.status_code == 200:
                logger.info("Bot stopped successfully.")
            else:
                logger.error(f"Kill switch failed: {resp.text}")
        except Exception as e:
            logger.error(f"Kill switch error: {e}")

    def run_once(self):
        logger.info("Running checks...")
        triggered = False
        reason = ""

        if self.check_drawdown():
            triggered = True
            reason = "Drawdown > 5% in 1h"
        elif self.check_btc_drop():
            triggered = True
            reason = "BTC Drop > 10% in 4h"

        if triggered:
            self.trigger_emergency(reason)
            return True
        return False

    def run(self):
        logger.info(f"Sentinel started. Monitoring every {self.interval} seconds.")
        while True:
            if self.run_once():
                logger.info("Emergency triggered. Sentinel exiting.")
                break
            time.sleep(self.interval)


def main():
    parser = argparse.ArgumentParser(description="Sentinel Circuit Breaker")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("user_data/configs/config.delta.dryrun.json"),
        help="Path to Freqtrade config file",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Check interval in seconds (default: 300)",
    )

    args = parser.parse_args()

    sentinel = Sentinel(args.config, args.interval)
    sentinel.run()


if __name__ == "__main__":
    main()
