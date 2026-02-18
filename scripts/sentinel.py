#!/usr/bin/env python3
"""
Sentinel (Circuit Breaker) Script
Monitors for market crashes or account drawdowns and triggers emergency actions.
"""

import argparse
import json
import logging
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
    def __init__(self, config_path: Path, openclaw_url: str, panic_sell: bool, dry_run: bool):
        self.config_path = config_path
        self.openclaw_url = openclaw_url
        self.panic_sell = panic_sell
        self.dry_run = dry_run

        self.config = self.load_config(config_path)

        # API Configuration
        api_config = self.config.get("api_server", {})
        ip = api_config.get("listen_ip_address", "127.0.0.1")
        port = api_config.get("listen_port", 8080)
        self.api_url = f"http://{ip}:{port}/api/v1"
        self.api_auth = (
            api_config.get("username", ""),
            api_config.get("password", ""),
        )
        self.access_token = None

        self.state_file = Path("user_data/sentinel_state.json")
        self.state = self.load_state()

    def load_config(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            logger.error(f"Config file not found: {path}")
            sys.exit(1)
        with path.open("r") as f:
            return json.load(f)

    def load_state(self) -> dict[str, Any]:
        if self.state_file.exists():
            try:
                with self.state_file.open("r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass
        return {"balance_history": [], "triggered": False}

    def save_state(self):
        # Ensure directory exists
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with self.state_file.open("w") as f:
            json.dump(self.state, f, indent=4)

    def get_token(self):
        # Initial login to get token
        try:
            resp = requests.post(f"{self.api_url}/token/login", auth=self.api_auth, timeout=10)
            resp.raise_for_status()
            self.access_token = resp.json().get("access_token")
            logger.info("Successfully authenticated with Freqtrade API")
        except Exception as e:
            logger.error(f"Failed to authenticate: {e}")

    def get_headers(self):
        if not self.access_token:
            self.get_token()
        return {"Authorization": f"Bearer {self.access_token}"}

    def check_btc_crash(self) -> bool:
        """Check if Bitcoin dropped > 10% in last 4 hours."""
        try:
            # Using Binance as a reference
            exchange = ccxt.binance()
            # 1h candles, last 5 (4 hours history + current)
            ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=5)
            if not ohlcv:
                return False

            # ohlcv is [timestamp, open, high, low, close, volume]
            # Max high in the last 4 completed candles + current partial
            highs = [x[2] for x in ohlcv]
            current_price = ohlcv[-1][4]  # Current close
            max_high = max(highs)

            if max_high == 0:
                return False

            drop = (max_high - current_price) / max_high

            if drop > 0.10:
                logger.warning(f"BTC Crash detected! Drop: {drop:.2%}")
                return True
            else:
                logger.info(f"BTC Drop (4h): {drop:.2%}")

        except Exception as e:
            logger.error(f"Error checking BTC price: {e}")

        return False

    def check_drawdown(self) -> bool:
        """Check if account drawdown > 5% in last 1 hour."""
        try:
            resp = requests.get(f"{self.api_url}/balance", headers=self.get_headers(), timeout=10)
            if resp.status_code == 401:
                # Token might be expired, retry once
                self.get_token()
                resp = requests.get(
                    f"{self.api_url}/balance", headers=self.get_headers(), timeout=10
                )

            resp.raise_for_status()
            data = resp.json()

            # Use total value in stake currency
            current_balance = data.get("total", 0.0)

            now = time.time()
            # Append current balance
            self.state["balance_history"].append([now, current_balance])

            # Prune > 1h (3600 seconds)
            one_hour_ago = now - 3600
            self.state["balance_history"] = [
                x for x in self.state["balance_history"] if x[0] >= one_hour_ago
            ]
            self.save_state()

            if not self.state["balance_history"]:
                return False

            max_balance = max(x[1] for x in self.state["balance_history"])
            if max_balance == 0:
                return False

            drawdown = (max_balance - current_balance) / max_balance

            if drawdown > 0.05:
                logger.warning(f"High Drawdown detected! {drawdown:.2%}")
                return True
            else:
                logger.info(f"Account Drawdown (1h): {drawdown:.2%}")

        except Exception as e:
            logger.error(f"Error checking drawdown: {e}")

        return False

    def trigger_emergency(self, reason: str):
        logger.critical(f"TRIGGERING EMERGENCY: {reason}")

        # 1. Alert
        if self.openclaw_url:
            try:
                requests.post(
                    self.openclaw_url,
                    json={"message": f"CRITICAL ALERT: {reason}"},
                    timeout=10,
                )
                logger.info("Alert sent to OpenClaw")
            except Exception as e:
                logger.error(f"Failed to send alert: {e}")

        if self.dry_run:
            logger.info("Dry Run: Skipping Kill Switch and Liquidation")
            # Mark as triggered so we don't spam alerts in dry run loop
            self.state["triggered"] = True
            self.save_state()
            return

        # 2. Liquidation (Optional)
        if self.panic_sell:
            try:
                # Get open trades
                resp = requests.get(
                    f"{self.api_url}/status", headers=self.get_headers(), timeout=10
                )
                resp.raise_for_status()
                trades = resp.json()

                for trade in trades:
                    trade_id = trade["trade_id"]
                    logger.info(f"Panic selling trade {trade_id}")
                    # Using forceexit
                    requests.post(
                        f"{self.api_url}/forceexit",
                        headers=self.get_headers(),
                        json={"tradeid": trade_id},
                        timeout=10,
                    )
            except Exception as e:
                logger.error(f"Failed to panic sell: {e}")

        # 3. Kill Switch
        try:
            requests.post(f"{self.api_url}/stop", headers=self.get_headers(), timeout=10)
            logger.critical("Bot Stopped via API.")
        except Exception as e:
            logger.error(f"Failed to stop bot: {e}")

        self.state["triggered"] = True
        self.save_state()

    def run(self):
        logger.info("Sentinel started monitoring...")

        # Initial Auth check
        self.get_token()

        while True:
            # Reload state in case it was modified externally (e.g. manual reset)
            self.state = self.load_state()

            if self.state.get("triggered"):
                logger.warning(
                    "Sentinel already triggered. "
                    "Waiting for manual reset (delete or update state file)."
                )
                time.sleep(300)
                continue

            btc_crash = self.check_btc_crash()
            drawdown = self.check_drawdown()

            if btc_crash:
                self.trigger_emergency("Bitcoin Crash > 10% in 4h")
            elif drawdown:
                self.trigger_emergency("Account Drawdown > 5% in 1h")

            time.sleep(300)


def main():
    parser = argparse.ArgumentParser(description="Sentinel Circuit Breaker")
    parser.add_argument("--config", "-c", required=True, type=Path, help="Path to Freqtrade config")
    parser.add_argument("--openclaw-url", help="OpenClaw Webhook URL")
    parser.add_argument(
        "--panic-sell", action="store_true", help="Liquidate all positions on trigger"
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not execute stop/sell commands")

    args = parser.parse_args()

    sentinel = Sentinel(args.config, args.openclaw_url, args.panic_sell, args.dry_run)
    sentinel.run()


if __name__ == "__main__":
    main()
