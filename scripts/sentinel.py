#!/usr/bin/env python3
"""
Sentinel: Crisis Management & Circuit Breaker for Freqtrade
Goal: Real-time monitoring to protect capital.

This script monitors:
1. Account Drawdown (> 5% in 1 hour)
2. Bitcoin Price Drop (> 10% in 4 hours)

Actions on Trigger:
- Kill Switch: Stop the bot (RPC /stop)
- Liquidation: Sell all positions (RPC /forceexit)
- Alert: Send critical alert to OpenClaw via Webhook
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import ccxt
import requests


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path("user_data/logs/sentinel.log")),
    ],
)
logger = logging.getLogger("Sentinel")


class Sentinel:
    def __init__(self, config_path: Path, openclaw_url: str | None, dry_run: bool = False):
        self.config_path = config_path
        self.openclaw_url = openclaw_url
        self.dry_run = dry_run
        self.state_file = Path("user_data/sentinel_state.json")
        self.rpc_url = None
        self.rpc_token = None
        self.headers = {}

        # Load config
        self.config = self._load_config()
        self._setup_rpc()

        # Initialize state
        self.state = self._load_state()

    def _load_config(self) -> dict:
        try:
            with self.config_path.open("r") as f:
                config = json.load(f)
            return config
        except Exception as e:
            logger.error(f"Failed to load config file: {e}")
            sys.exit(1)

    def _setup_rpc(self):
        api_config = self.config.get("api_server", {})
        if not api_config.get("enabled", False):
            logger.warning("API Server is not enabled in config. RPC commands will fail.")

        ip = api_config.get("listen_ip_address", "127.0.0.1")
        port = api_config.get("listen_port", 8080)
        self.rpc_url = f"http://{ip}:{port}/api/v1"
        self.username = api_config.get("username")
        self.password = api_config.get("password")

    def _login(self) -> bool:
        if not self.username or not self.password:
            logger.error("API credentials missing in config.")
            return False

        try:
            response = requests.post(
                f"{self.rpc_url}/login",
                data={"username": self.username, "password": self.password},
                timeout=10,
            )
            response.raise_for_status()
            token = response.json().get("access_token")
            if token:
                self.rpc_token = token
                self.headers = {"Authorization": f"Bearer {token}"}
                return True
        except requests.RequestException as e:
            logger.error(f"Login failed: {e}")
            return False
        return False

    def _api_request(
        self, method: str, endpoint: str, json_data: dict | None = None
    ) -> dict:
        if self.dry_run and method != "GET":
            logger.info(f"[DRY-RUN] API Request: {method} {endpoint} Payload: {json_data}")
            return {}

        if not self.rpc_token:
            if not self._login():
                return {}

        url = f"{self.rpc_url}/{endpoint}"
        try:
            if method == "GET":
                response = requests.get(url, headers=self.headers, timeout=10)
            elif method == "POST":
                response = requests.post(
                    url, headers=self.headers, json=json_data, timeout=10
                )
            else:
                return {}

            if response.status_code == 401:  # Token expired
                logger.info("Token expired, refreshing...")
                if self._login():
                    return self._api_request(method, endpoint, json_data)  # Retry once
                else:
                    return {}

            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"API Request failed ({endpoint}): {e}")
            return {}

    def _load_state(self) -> dict:
        if self.state_file.exists():
            try:
                with self.state_file.open("r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass
        return {
            "balance_history": [],
            "price_history": [],
            "triggered": False,
            "last_trigger_time": None,
        }

    def _save_state(self):
        try:
            with self.state_file.open("w") as f:
                json.dump(self.state, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def get_balance(self) -> float | None:
        # Calls /balance to get total balance in stake currency (USDT)
        data = self._api_request("GET", "balance")
        if not data:
            return None
        return data.get("total")

    def get_btc_price(self) -> float | None:
        # Use CCXT to fetch BTC/USDT price from Gate.io or Kraken
        try:
            # Fallback to Kraken if Gate.io fails or just use Kraken as primary reference
            exchange = ccxt.kraken()
            ticker = exchange.fetch_ticker("BTC/USDT")
            return ticker["last"]
        except Exception as e:
            logger.error(f"Failed to fetch BTC price: {e}")
            return None

    def update_history(self, balance: float, price: float):
        now = time.time()

        # Update Balance History (1 hour window)
        self.state["balance_history"].append([now, balance])
        # Prune older than 1 hour (3600 seconds)
        self.state["balance_history"] = [
            x for x in self.state["balance_history"] if now - x[0] <= 3600
        ]

        # Update Price History (4 hour window)
        self.state["price_history"].append([now, price])
        # Prune older than 4 hours (14400 seconds)
        self.state["price_history"] = [
            x for x in self.state["price_history"] if now - x[0] <= 14400
        ]

        self._save_state()

    def check_triggers(self) -> str | None:
        if not self.state["balance_history"] or not self.state["price_history"]:
            return None

        current_balance = self.state["balance_history"][-1][1]
        max_balance = max(x[1] for x in self.state["balance_history"])

        if max_balance > 0:
            drawdown = (max_balance - current_balance) / max_balance
            if drawdown > 0.05:
                return f"Drawdown > 5% ({drawdown:.2%}) in last hour"

        current_price = self.state["price_history"][-1][1]
        max_price = max(x[1] for x in self.state["price_history"])

        if max_price > 0:
            drop = (max_price - current_price) / max_price
            if drop > 0.10:
                return f"Bitcoin Drop > 10% ({drop:.2%}) in last 4 hours"

        return None

    def execute_emergency(self, reason: str):
        logger.critical(f"EMERGENCY TRIGGERED: {reason}")

        # 1. Stop Bot
        logger.info("Executing Kill Switch (RPC /stop)...")
        self._api_request("POST", "stop")

        # 2. Liquidate
        logger.info("Executing Liquidation (RPC /forceexit all)...")
        self._api_request("POST", "forceexit", {"tradeid": "all"})

        # 3. Alert
        self.send_alert(
            f"CRITICAL ALERT: Sentinel triggered! Reason: {reason}. "
            "Bot stopped and positions liquidated."
        )

        # Update state
        self.state["triggered"] = True
        self.state["last_trigger_time"] = time.time()
        self._save_state()

    def send_alert(self, message: str):
        if not self.openclaw_url:
            logger.warning("OpenClaw URL not configured. Skipping alert.")
            return

        payload = {"message": message}
        if self.dry_run:
            logger.info(f"[DRY-RUN] Sending Alert to {self.openclaw_url}: {message}")
            return

        try:
            response = requests.post(self.openclaw_url, json=payload, timeout=10)
            if response.status_code != 200:
                logger.error(f"Failed to send alert: {response.text}")
            else:
                logger.info("Alert sent successfully.")
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")

    def run(self):
        logger.info("Sentinel started. Monitoring every 5 minutes...")
        while True:
            try:
                if self.state.get("triggered"):
                    logger.warning(
                        "Sentinel previously triggered. Waiting for manual reset "
                        "(delete state or reset 'triggered' flag)."
                    )
                    time.sleep(300)
                    continue

                balance = self.get_balance()
                price = self.get_btc_price()

                if balance is None or price is None:
                    logger.warning("Failed to fetch data. Skipping this interval.")
                    time.sleep(300)
                    continue

                if balance <= 0 or price <= 0:
                    logger.warning(
                        f"Invalid data received (Balance={balance}, BTC={price}). "
                        "Skipping this interval."
                    )
                    time.sleep(300)
                    continue

                logger.info(f"Status: Balance={balance:.2f}, BTC={price:.2f}")

                self.update_history(balance, price)

                reason = self.check_triggers()
                if reason:
                    self.execute_emergency(reason)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")

            time.sleep(300)


def main():
    parser = argparse.ArgumentParser(
        description="Sentinel: Crisis Management for Freqtrade"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("user_data/configs/config.delta.live.json"),
        help="Path to config file",
    )
    parser.add_argument(
        "--openclaw-url",
        type=str,
        default=os.getenv("OPENCLAW_URL"),
        help="OpenClaw Webhook URL",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Dry run mode (no actual API calls)"
    )

    args = parser.parse_args()

    if not args.config.exists():
        logger.error(f"Config file not found: {args.config}")
        sys.exit(1)

    sentinel = Sentinel(args.config, args.openclaw_url, args.dry_run)
    sentinel.run()


if __name__ == "__main__":
    main()
