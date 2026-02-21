#!/usr/bin/env python3
"""
Sentinel: Real-time crisis management to protect capital.
Monitors drawdown and BTC market crashes, triggering a kill switch if necessary.
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
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
    def __init__(self, config_path: Path, state_path: Path):
        self.config_path = config_path
        self.state_path = state_path
        self.api_url = "http://127.0.0.1:8080"
        self.api_user = ""
        self.api_pass = ""
        self.state: dict[str, Any] = {"balance_history": []}
        self.access_token = None
        self.token_expiry = 0

        self.load_config()
        self.load_state()

    def load_config(self):
        """Loads configuration from file."""
        try:
            with self.config_path.open("r") as f:
                config = json.load(f)
                api_config = config.get("api_server", {})

                # Check if API is enabled
                if not api_config.get("enabled", False):
                    logger.warning("API Server is not enabled in config!")

                ip = api_config.get("listen_ip_address", "127.0.0.1")
                if ip == "0.0.0.0":  # noqa: S104
                    ip = "127.0.0.1"
                port = api_config.get("listen_port", 8080)
                self.api_url = f"http://{ip}:{port}"
                self.api_user = api_config.get("username", "")
                self.api_pass = api_config.get("password", "")

                logger.info(f"Loaded config from {self.config_path}. API URL: {self.api_url}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            sys.exit(1)

    def load_state(self):
        """Loads state from file."""
        try:
            with self.state_path.open("r") as f:
                self.state = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.info("No valid state file found, starting fresh.")
            self.state = {"balance_history": []}

    def save_state(self):
        """Saves state to file."""
        try:
            with self.state_path.open("w") as f:
                json.dump(self.state, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def get_api_token(self):
        """Authenticates with Freqtrade API to get a JWT token."""
        if self.access_token:
            return self.access_token

        try:
            auth_data = {"username": self.api_user, "password": self.api_pass}
            resp = requests.post(f"{self.api_url}/api/v1/token/login", data=auth_data, timeout=10)
            if resp.status_code == 200:
                self.access_token = resp.json().get("access_token")
                return self.access_token
            else:
                logger.error(f"Failed to authenticate: {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return None

    def get_headers(self):
        token = self.get_api_token()
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    def get_current_balance(self) -> float:
        """Fetches current total balance (in stake currency) from API."""
        try:
            headers = self.get_headers()
            if not headers:
                return 0.0

            resp = requests.get(f"{self.api_url}/api/v1/balance", headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return float(data.get("total", 0.0))
            else:
                logger.error(f"Failed to fetch balance: {resp.text}")
                return 0.0
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return 0.0

    def check_drawdown(self) -> bool:
        """Checks if drawdown > 5% in the last hour."""
        current_time = datetime.now(timezone.utc).timestamp()  # noqa: UP017
        current_balance = self.get_current_balance()

        # Update history
        self.state["balance_history"].append((current_time, current_balance))

        # Prune history > 1 hour (3600 seconds)
        cutoff_time = current_time - 3600
        self.state["balance_history"] = [
            (t, b) for t, b in self.state["balance_history"] if t >= cutoff_time
        ]
        self.save_state()

        if not self.state["balance_history"]:
            return False

        # Calculate Max Balance in last hour
        max_balance = max(b for t, b in self.state["balance_history"])

        if max_balance <= 0:
            return False

        drawdown = (max_balance - current_balance) / max_balance
        logger.info(
            f"Current Balance: {current_balance}, Max (1h): {max_balance}, Drawdown: {drawdown:.2%}"
        )

        if drawdown > 0.05:
            logger.critical(f"CRITICAL: Drawdown {drawdown:.2%} exceeds 5% limit!")
            return True
        return False

    def check_btc_crash(self) -> bool:
        """Checks if Bitcoin drops > 10% in the last 4 hours."""
        try:
            exchange = ccxt.binance()
            # Fetch OHLCV for last 4 hours
            ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=5)

            if not ohlcv:
                logger.warning("Failed to fetch BTC OHLCV data.")
                return False

            highs = [candle[2] for candle in ohlcv]
            current_price = ohlcv[-1][4]

            max_high_4h = max(highs)

            if max_high_4h <= 0:
                return False

            drop = (max_high_4h - current_price) / max_high_4h
            logger.info(
                f"BTC Price: {current_price}, Max High (4h): {max_high_4h}, Drop: {drop:.2%}"
            )

            if drop > 0.10:
                logger.critical(f"CRITICAL: Bitcoin drop {drop:.2%} exceeds 10% limit!")
                return True
            return False

        except Exception as e:
            logger.error(f"Error checking BTC crash: {e}")
            return False

    def trigger_emergency(self, reason: str):
        """Executes emergency protocols."""
        logger.critical(f"Triggering Emergency Protocol: {reason}")

        headers = self.get_headers()
        if not headers:
            logger.error("Cannot authenticate to trigger emergency actions!")
            return

        # 1. Force Exit (Liquidation)
        try:
            logger.info("Executing Force Exit (Liquidation)...")
            resp = requests.post(
                f"{self.api_url}/api/v1/forceexit",
                headers=headers,
                json={"trade_id": "all"},
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("Force Exit executed successfully.")
            else:
                logger.error(f"Force Exit failed: {resp.text}")
        except Exception as e:
            logger.error(f"Force Exit error: {e}")

        # 2. Kill Switch (Stop Bot)
        try:
            logger.info("Executing Kill Switch (Stop Bot)...")
            resp = requests.post(f"{self.api_url}/api/v1/stop", headers=headers, timeout=10)
            if resp.status_code == 200:
                logger.info("Bot stopped successfully.")
            else:
                logger.error(f"Kill Switch failed: {resp.text}")
        except Exception as e:
            logger.error(f"Kill Switch error: {e}")

        # 3. Alert
        self.send_alert(f"CRITICAL ALERT: {reason}. Bot stopped and positions liquidated.")

        # 4. Journal
        self.log_to_journal(reason)

    def send_alert(self, message: str):
        """Sends an alert (Mock/Placeholder)."""
        logger.info(f"ALERT SENT: {message}")
        # Placeholder for OpenClaw / WhatsApp integration

    def log_to_journal(self, reason: str):
        """Logs the event to the Sentinel journal."""
        journal_path = Path(".jules/sentinel.md")
        try:
            timestamp = datetime.now(timezone.utc).isoformat()  # noqa: UP017
            entry = (
                f"\n## Emergency Triggered: {timestamp}\n"
                f"- **Reason**: {reason}\n"
                f"- **Action**: Kill Switch & Liquidation executed.\n"
            )
            with journal_path.open("a") as f:
                f.write(entry)
            logger.info("Event logged to journal.")
        except Exception as e:
            logger.error(f"Failed to log to journal: {e}")

    def run(self):
        """Main monitoring loop."""
        logger.info("Sentinel started. Monitoring every 5 minutes...")
        while True:
            try:
                drawdown_alert = self.check_drawdown()
                btc_alert = self.check_btc_crash()

                if drawdown_alert:
                    self.trigger_emergency("Drawdown > 5% in last hour")
                    break

                if btc_alert:
                    self.trigger_emergency("Bitcoin drop > 10% in last 4 hours")
                    break

            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")

            time.sleep(300)  # 5 minutes


def main():
    parser = argparse.ArgumentParser(description="Sentinel: Freqtrade Circuit Breaker")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("user_data/configs/config.delta.live.json"),
        help="Path to config file",
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=Path("user_data/sentinel_state.json"),
        help="Path to state file",
    )
    args = parser.parse_args()

    if not args.config.exists():
        logger.error(f"Config file not found: {args.config}")
        sys.exit(1)

    sentinel = Sentinel(args.config, args.state)
    sentinel.run()


if __name__ == "__main__":
    main()
