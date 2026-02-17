#!/usr/bin/env python3
import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import ccxt
import requests


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Sentinel")

STATE_FILE = Path("user_data/sentinel_state.json")


class Sentinel:
    def __init__(self, config_path: str, panic_sell: bool, openclaw_url: str | None):
        self.config_path = Path(config_path)
        self.panic_sell_enabled = panic_sell
        self.openclaw_url = openclaw_url
        self.config = self.load_config()
        self.api_url = (
            f"http://{self.config['api_server']['listen_ip_address']}:"
            f"{self.config['api_server']['listen_port']}/api/v1"
        )
        self.auth_token = None
        self.headers: dict[str, str] = {}

        # Initialize CCXT (Kraken)
        self.exchange = ccxt.kraken()

        # Initialize state
        self.state = self.load_state()

    def load_config(self) -> dict:
        if not self.config_path.exists():
            logger.error(f"Config file not found: {self.config_path}")
            sys.exit(1)
        with self.config_path.open() as f:
            return json.load(f)

    def load_state(self) -> dict:
        if STATE_FILE.exists():
            try:
                with STATE_FILE.open() as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.warning("State file corrupted, starting fresh.")
        return {"balance_history": []}

    def save_state(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with STATE_FILE.open("w") as f:
            json.dump(self.state, f)

    def authenticate(self):
        username = self.config["api_server"]["username"]
        password = self.config["api_server"]["password"]
        try:
            resp = requests.post(
                f"{self.api_url}/token/login", auth=(username, password), timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            self.auth_token = data["access_token"]
            self.headers = {"Authorization": f"Bearer {self.auth_token}"}
            logger.info("Authenticated successfully.")
        except requests.RequestException as e:
            logger.error(f"Authentication failed: {e}")
            sys.exit(1)

    def check_btc_crash(self) -> bool:
        """Check if BTC crashed > 10% in last 4 hours."""
        try:
            # Fetch OHLCV for last 4 hours (1h timeframe, limit 5 to capture sufficient history)
            ohlcv = self.exchange.fetch_ohlcv("BTC/USD", timeframe="1h", limit=5)
            if not ohlcv:
                logger.warning("No OHLCV data fetched.")
                return False

            ticker = self.exchange.fetch_ticker("BTC/USD")
            current_price = ticker["last"]

            # Use High of the candles in the 4h window as the reference max
            highs = [candle[2] for candle in ohlcv]
            max_price_4h = max(highs)

            drop = (current_price - max_price_4h) / max_price_4h
            logger.info(
                f"BTC Check: Current={current_price}, Max4h={max_price_4h}, Drop={drop:.2%}"
            )

            if drop < -0.10:
                logger.critical(f"BTC CRASH DETECTED: {drop:.2%} drop in 4h!")
                return True
            return False
        except Exception as e:
            logger.error(f"Error checking BTC price: {e}")
            return False

    def check_drawdown(self) -> bool:
        """Check if account drawdown > 5% in last 1 hour."""
        try:
            resp = requests.get(f"{self.api_url}/balance", headers=self.headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            current_balance = data.get("total")
            if current_balance is None:
                logger.warning("Could not retrieve total balance from API.")
                return False

            now = datetime.now(UTC).timestamp()
            self.state["balance_history"].append({"timestamp": now, "balance": current_balance})

            # Prune old entries (> 1h)
            one_hour_ago = now - 3600
            self.state["balance_history"] = [
                entry
                for entry in self.state["balance_history"]
                if entry["timestamp"] >= one_hour_ago
            ]
            self.save_state()

            if not self.state["balance_history"]:
                return False

            # Max balance in last 1 hour
            max_balance = max(e["balance"] for e in self.state["balance_history"])

            if max_balance == 0:
                return False

            drawdown = (current_balance - max_balance) / max_balance
            logger.info(
                f"Drawdown Check: Current={current_balance}, Max1h={max_balance}, DD={drawdown:.2%}"
            )

            if drawdown < -0.05:
                logger.critical(f"DRAWDOWN ALERT: {drawdown:.2%} in last 1h!")
                return True
            return False

        except Exception as e:
            logger.error(f"Error checking balance: {e}")
            return False

    def trigger_emergency(self, reason: str):
        logger.critical(f"TRIGGERING EMERGENCY: {reason}")

        # 1. Alert
        if self.openclaw_url:
            try:
                requests.post(
                    self.openclaw_url,
                    json={"message": f"CRITICAL ALERT: {reason}"},
                    timeout=5,
                )
                logger.info("Alert sent to OpenClaw.")
            except Exception as e:
                logger.error(f"Failed to send alert: {e}")

        # 2. Panic Sell (Liquidation)
        if self.panic_sell_enabled:
            logger.info("Panic Sell ENABLED. Liquidating all positions...")
            try:
                # Get open trades
                resp = requests.get(f"{self.api_url}/status", headers=self.headers, timeout=10)
                trades = resp.json()
                for trade in trades:
                    trade_id = trade["trade_id"]
                    logger.info(f"Force exiting trade {trade_id} ({trade['pair']})...")
                    requests.post(
                        f"{self.api_url}/forceexit",
                        headers=self.headers,
                        json={"tradeid": trade_id},
                        timeout=5,
                    )
            except Exception as e:
                logger.error(f"Failed to liquidate positions: {e}")

        # 3. Kill Switch (Stop Bot)
        logger.info("Stopping Freqtrade bot...")
        try:
            requests.post(f"{self.api_url}/stop", headers=self.headers, timeout=5)
            logger.info("Bot stopped.")
        except Exception as e:
            logger.error(f"Failed to stop bot: {e}")

        logger.info("Emergency procedure completed. Exiting.")
        sys.exit(0)

    def run(self):
        logger.info("Sentinel started. Monitoring...")
        self.authenticate()

        while True:
            try:
                btc_crashed = self.check_btc_crash()
                drawdown_hit = self.check_drawdown()

                if btc_crashed:
                    self.trigger_emergency("Bitcoin crashed > 10% in 4h")
                elif drawdown_hit:
                    self.trigger_emergency("Account drawdown > 5% in 1h")

                time.sleep(300)  # 5 minutes
            except KeyboardInterrupt:
                logger.info("Sentinel stopped by user.")
                sys.exit(0)
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                time.sleep(60)  # Retry after 1 min


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Freqtrade Sentinel (Circuit Breaker)")
    parser.add_argument(
        "--config",
        default="user_data/configs/config.delta.live.json",
        help="Path to config file",
    )
    parser.add_argument(
        "--panic-sell",
        action="store_true",
        help="Enable panic sell (liquidation) on trigger",
    )
    parser.add_argument("--openclaw-url", help="Webhook URL for OpenClaw alerts")

    args = parser.parse_args()

    sentinel = Sentinel(args.config, args.panic_sell, args.openclaw_url)
    sentinel.run()
