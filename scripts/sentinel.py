#!/usr/bin/env python3
"""
Sentinel (Circuit Breaker) Script
Monitors Freqtrade bot and market conditions to protect capital.

Features:
- Monitors Drawdown > 5% in the last hour.
- Monitors Bitcoin drops > 10% in the last 4 hours.
- Actions: Alert (OpenClaw), Liquidation (optional), Kill Switch (stop bot).
"""

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ccxt
import requests


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("user_data/logs/sentinel.log"),
    ],
)
logger = logging.getLogger("Sentinel")


class Sentinel:
    def __init__(self, config_path: str, state_path: str = "user_data/sentinel_state.json"):
        self.config_path = Path(config_path)
        self.state_path = Path(state_path)
        self.config = self._load_config()
        self.api_url = self._get_api_url()
        self.auth_token = None

        # Load state
        self.state = self._load_state()

        # Initialize CCXT exchange for price monitoring
        self.exchange_id = self.config.get("exchange", {}).get("name", "binance").lower()
        try:
            exchange_class = getattr(ccxt, self.exchange_id)
            self.exchange = exchange_class()
        except AttributeError:
            logger.warning(f"Exchange {self.exchange_id} not found in ccxt. Fallback to binance.")
            self.exchange = ccxt.binance()
            self.exchange_id = "binance"

        # Configuration for thresholds
        self.drawdown_threshold = 0.05  # 5%
        self.btc_drop_threshold = 0.10  # 10%
        self.openclaw_url = "http://localhost:5000/send"

        # Operational flags
        self.liquidate_on_trigger = True  # Can be made configurable

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            logger.error(f"Config file not found: {self.config_path}")
            sys.exit(1)

        with self.config_path.open() as f:
            return json.load(f)

    def _load_state(self) -> dict[str, Any]:
        if self.state_path.exists():
            try:
                with self.state_path.open() as f:
                    state = json.load(f)
                    # Clean up old data on load
                    return self._prune_state(state)
            except json.JSONDecodeError:
                logger.warning("State file corrupted. Starting fresh.")
        return {
            "balance_history_1h": [],  # List of [timestamp, balance]
            "btc_price_history_4h": [],  # List of [timestamp, price]
        }

    def _save_state(self):
        with self.state_path.open("w") as f:
            json.dump(self.state, f, indent=4)

    def _prune_state(self, state: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).timestamp()

        # Prune balance history (> 1 hour)
        one_hour_ago = now - 3600
        state["balance_history_1h"] = [
            x for x in state.get("balance_history_1h", []) if x[0] >= one_hour_ago
        ]

        # Prune BTC price history (> 4 hours)
        four_hours_ago = now - (4 * 3600)
        state["btc_price_history_4h"] = [
            x for x in state.get("btc_price_history_4h", []) if x[0] >= four_hours_ago
        ]
        return state

    def _get_api_url(self) -> str:
        api_config = self.config.get("api_server", {})
        if not api_config.get("enabled", False):
            logger.error("API Server not enabled in config.")
            sys.exit(1)

        ip = api_config.get("listen_ip_address", "127.0.0.1")
        if ip == "0.0.0.0":  # noqa: S104
            ip = "127.0.0.1"
        port = api_config.get("listen_port", 8080)
        return f"http://{ip}:{port}/api/v1"

    def login(self):
        api_config = self.config.get("api_server", {})
        username = api_config.get("username")
        password = api_config.get("password")

        try:
            response = requests.post(
                f"{self.api_url}/token/login",
                data={"username": username, "password": password},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            self.auth_token = data["access_token"]
            logger.info("Successfully authenticated with Freqtrade API.")
        except requests.RequestException as e:
            logger.error(f"Failed to login to Freqtrade API: {e}")
            # We don't exit here, as we might retry later or valid token exists?
            # Actually, without token we can't fetch balance.
            pass

    def _get_headers(self):
        if not self.auth_token:
            self.login()
        return {"Authorization": f"Bearer {self.auth_token}"}

    def fetch_balance(self) -> float | None:
        try:
            url = f"{self.api_url}/balance"
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            if response.status_code == 401:
                logger.info("Token expired, re-logging in...")
                self.login()
                response = requests.get(url, headers=self._get_headers(), timeout=10)

            response.raise_for_status()
            data = response.json()
            # Total balance in stake currency
            return data.get("total", 0.0)
        except requests.RequestException as e:
            logger.error(f"Error fetching balance: {e}")
            return None

    def fetch_btc_price(self) -> float | None:
        try:
            # Try to fetch BTC/USDT as market health indicator.
            ticker = self.exchange.fetch_ticker("BTC/USDT")
            return ticker["last"]
        except Exception as e:
            logger.warning(f"Error fetching BTC price from {self.exchange_id}: {e}")
            # Fallback: check config stake currency against BTC?
            return None

    def check_drawdown(self, current_balance: float) -> bool:
        now = datetime.now(UTC).timestamp()

        # Update history
        self.state["balance_history_1h"].append([now, current_balance])
        self.state = self._prune_state(self.state)

        history = self.state["balance_history_1h"]
        if not history:
            return False

        max_balance = max(x[1] for x in history)
        if max_balance == 0:
            return False

        drawdown = (max_balance - current_balance) / max_balance

        if drawdown > self.drawdown_threshold:
            logger.warning(
                f"Drawdown trigger: Current {current_balance}, Max {max_balance}, "
                f"Drawdown {drawdown:.2%}"
            )
            return True
        return False

    def check_btc_drop(self, current_price: float) -> bool:
        now = datetime.now(UTC).timestamp()

        # Update history
        self.state["btc_price_history_4h"].append([now, current_price])
        self.state = self._prune_state(self.state)

        history = self.state["btc_price_history_4h"]
        if not history:
            return False

        max_price = max(x[1] for x in history)
        if max_price == 0:
            return False

        drop = (max_price - current_price) / max_price

        if drop > self.btc_drop_threshold:
            logger.warning(
                f"BTC Drop trigger: Current {current_price}, Max {max_price}, Drop {drop:.2%}"
            )
            return True
        return False

    def trigger_emergency(self, reason: str):
        logger.critical(f"EMERGENCY TRIGGERED: {reason}")

        # 1. Alert (OpenClaw)
        try:
            requests.post(
                self.openclaw_url,
                json={"message": f"CRITICAL ALERT: Sentinel Triggered! Reason: {reason}"},
                timeout=5,
            )
            logger.info("Sent OpenClaw alert.")
        except requests.RequestException as e:
            logger.error(f"Failed to send OpenClaw alert: {e}")

        # 2. Liquidation (Force Exit All)
        if self.liquidate_on_trigger:
            logger.info("Initiating Liquidation (Force Exit All)...")
            try:
                # Get open trades
                response = requests.get(
                    f"{self.api_url}/status", headers=self._get_headers(), timeout=10
                )
                if response.status_code == 200:
                    trades = response.json()
                    for trade in trades:
                        trade_id = trade["trade_id"]
                        logger.info(f"Force exiting trade {trade_id} ({trade['pair']})")
                        try:
                            res = requests.post(
                                f"{self.api_url}/forceexit",
                                headers=self._get_headers(),
                                json={"tradeid": trade_id},
                                timeout=5,
                            )
                            logger.info(f"Exit result for {trade_id}: {res.text}")
                        except requests.RequestException as e:
                            logger.error(f"Failed to force exit trade {trade_id}: {e}")

                    # Wait a moment for orders to be processed
                    time.sleep(5)
                else:
                    logger.error(f"Failed to fetch trades for liquidation: {response.text}")
            except requests.RequestException as e:
                logger.error(f"Liquidation failed: {e}")

        # 3. Kill Switch (Stop Bot)
        logger.info("Engaging Kill Switch (Stopping Freqtrade)...")
        try:
            requests.post(f"{self.api_url}/stop", headers=self._get_headers(), timeout=5)
            logger.info("Freqtrade stop command sent.")
        except requests.RequestException as e:
            logger.error(f"Failed to stop Freqtrade: {e}")

        # Exit script? Or just stop monitoring?
        # The prompt says "Resume: Do not restart trading until I manually approve it."
        # If the bot is stopped, monitoring is moot (can't fetch balance).
        logger.info("Sentinel actions complete. Exiting.")
        sys.exit(0)

    def run(self):
        logger.info("Sentinel started monitoring...")

        while True:
            try:
                # 1. Check Balance Drawdown
                balance = self.fetch_balance()
                if balance is not None:
                    if self.check_drawdown(balance):
                        self.trigger_emergency("Drawdown limit exceeded (>5% in 1h)")

                # 2. Check BTC Drop
                btc_price = self.fetch_btc_price()
                if btc_price is not None:
                    if self.check_btc_drop(btc_price):
                        self.trigger_emergency("Bitcoin crash detected (>10% drop in 4h)")

                # Save state
                self._save_state()

                # Sleep 5 minutes
                time.sleep(300)

            except KeyboardInterrupt:
                logger.info("Sentinel stopped by user.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                time.sleep(60)  # Sleep a bit before retrying


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Freqtrade Sentinel")
    parser.add_argument(
        "--config",
        "-c",
        help="Path to config file",
        default="user_data/configs/config.delta.live.json",
    )
    args = parser.parse_args()

    sentinel = Sentinel(args.config)
    sentinel.run()
