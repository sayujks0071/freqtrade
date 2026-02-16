#!/usr/bin/env python3
"""
Sentinel Script (Circuit Breaker)
Monitors account drawdown and Bitcoin crash to trigger emergency actions.
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
        logging.StreamHandler(),
        logging.FileHandler("user_data/logs/sentinel.log")
    ],
)
logger = logging.getLogger("Sentinel")


class Sentinel:
    def __init__(
        self,
        config_path: Path,
        panic_sell: bool,
        openclaw_url: str | None,
        dry_run: bool
    ):
        self.config_path = config_path
        self.panic_sell = panic_sell
        self.openclaw_url = openclaw_url
        self.dry_run = dry_run
        self.config = self.load_config()

        api_server = self.config.get("api_server", {})
        self.api_url = api_server.get("listen_ip_address", "127.0.0.1")
        self.api_port = api_server.get("listen_port", 8080)
        self.api_base = f"http://{self.api_url}:{self.api_port}/api/v1"
        self.api_username = api_server.get("username", "")
        self.api_password = api_server.get("password", "")

        self.jwt_token = None
        self.session = requests.Session()

        # Initialize Exchange for Market Data (BTC)
        try:
            self.exchange = ccxt.kraken()
        except Exception as e:
            logger.warning(f"Failed to initialize Kraken: {e}. Falling back to Binance.")
            self.exchange = ccxt.binance()

        self.state_file = Path("user_data/sentinel_state.json")
        self.state = self.load_state()

    def load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            logger.error(f"Config file not found: {self.config_path}")
            sys.exit(1)
        with self.config_path.open() as f:
            return json.load(f)

    def load_state(self) -> list[dict[str, Any]]:
        if self.state_file.exists():
            try:
                with self.state_file.open() as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return []
        return []

    def save_state(self):
        with self.state_file.open("w") as f:
            json.dump(self.state, f)

    def login(self):
        try:
            # First try ping to see if token is valid or needed
            res = self.session.get(f"{self.api_base}/ping", timeout=10)
            if res.status_code == 200:
                return  # Already authenticated or no auth needed

            # Login
            login_url = f"{self.api_base}/token/login"
            resp = self.session.post(
                login_url,
                auth=(self.api_username, self.api_password),
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                self.jwt_token = data.get("access_token")
                self.session.headers.update({"Authorization": f"Bearer {self.jwt_token}"})
                logger.info("Successfully logged in to Freqtrade API.")
            else:
                logger.error(f"Login failed: {resp.text}")
        except Exception as e:
            logger.error(f"Login exception: {e}")

    def get_balance_total(self) -> float | None:
        try:
            resp = self.session.get(f"{self.api_base}/balance", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # total is usually in stake currency
                return data.get("total")
            elif resp.status_code == 401:
                self.login()
                resp = self.session.get(f"{self.api_base}/balance", timeout=10)
                if resp.status_code == 200:
                    return resp.json().get("total")
                else:
                    logger.error(f"Failed to get balance after login: {resp.text}")
                    return None
            else:
                logger.error(f"Failed to get balance: {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Exception getting balance: {e}")
            return None

    def check_drawdown(self) -> bool:
        current_balance = self.get_balance_total()
        if current_balance is None:
            return False

        now = datetime.now(timezone.utc).timestamp()
        self.state.append({"timestamp": now, "balance": current_balance})

        # Prune older than 1 hour
        one_hour_ago = now - 3600
        self.state = [s for s in self.state if s["timestamp"] >= one_hour_ago]
        self.save_state()

        if not self.state:
            return False

        max_balance = max(s["balance"] for s in self.state)
        if max_balance == 0:
            return False

        drawdown = (max_balance - current_balance) / max_balance
        logger.info(
            f"Current Drawdown (1h): {drawdown:.2%} (Max: {max_balance}, Curr: {current_balance})"
        )

        if drawdown > 0.05:
            logger.warning(f"Drawdown {drawdown:.2%} > 5% threshold!")
            return True
        return False

    def check_btc_crash(self) -> bool:
        try:
            # Fetch OHLCV for BTC/USD or BTC/USDT. 1h timeframe, limit 5 (last 4 hours + current)
            symbol = "BTC/USD"

            # Check if symbol is supported, fallback to USDT
            try:
                if not self.exchange.markets:
                    self.exchange.load_markets()
                if symbol not in self.exchange.markets:
                    symbol = "BTC/USDT"
            except Exception as e:
                # If load_markets fails, try blind fetch
                logger.debug(f"Failed to load markets: {e}")

            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe="1h", limit=5)
            if not ohlcv:
                return False

            # ohlcv is [timestamp, open, high, low, close, volume]
            # Get max high of the previous 4 candles + current high
            highs = [candle[2] for candle in ohlcv]
            current_price = ohlcv[-1][4]
            max_high = max(highs)

            if max_high == 0:
                return False

            drop = (max_high - current_price) / max_high
            logger.info(f"BTC Drop (4h): {drop:.2%} (High: {max_high}, Curr: {current_price})")

            if drop > 0.10:
                logger.warning(f"BTC Drop {drop:.2%} > 10% threshold!")
                return True
            return False
        except Exception as e:
            logger.error(f"Error checking BTC crash: {e}")
            return False

    def trigger_emergency(self, reason: str):
        msg = f"CRITICAL ALERT: {reason}. Triggering Circuit Breaker."
        logger.critical(msg)
        self.send_alert(msg)

        if self.dry_run:
            logger.info("[DRY RUN] Would stop bot and optionally liquidate.")
            return

        # Stop Bot
        try:
            resp = self.session.post(f"{self.api_base}/stop", timeout=10)
            if resp.status_code == 200:
                logger.info("Bot stopped successfully.")
            else:
                logger.error(f"Failed to stop bot: {resp.text}")
        except Exception as e:
            logger.error(f"Exception stopping bot: {e}")

        # Panic Sell
        if self.panic_sell:
            self.liquidate_all()

    def liquidate_all(self):
        logger.info("Initiating Panic Sell (Liquidation)...")
        try:
            # Get open trades
            resp = self.session.get(f"{self.api_base}/status", timeout=10)
            if resp.status_code != 200:
                logger.error("Failed to get trade status for liquidation.")
                return

            trades = resp.json()
            for trade in trades:
                trade_id = trade["trade_id"]
                logger.info(f"Force exiting trade {trade_id} ({trade['pair']})...")
                res = self.session.post(
                    f"{self.api_base}/forceexit",
                    json={"tradeid": trade_id},
                    timeout=10
                )
                if res.status_code == 200:
                    logger.info(f"Trade {trade_id} exited.")
                else:
                    logger.error(f"Failed to exit trade {trade_id}: {res.text}")
        except Exception as e:
            logger.error(f"Exception during liquidation: {e}")

    def send_alert(self, message: str):
        if self.openclaw_url:
            try:
                # Assuming OpenClaw webhook accepts JSON with "message" or "text"
                requests.post(
                    self.openclaw_url,
                    json={"message": message, "text": message},
                    timeout=10
                )
                logger.info(f"Alert sent to OpenClaw: {self.openclaw_url}")
            except Exception as e:
                logger.error(f"Failed to send alert to OpenClaw: {e}")
        else:
            logger.info("No OpenClaw URL configured. Alert logged only.")

    def run(self):
        logger.info("Sentinel started. Monitoring...")
        self.login()

        while True:
            try:
                triggered = False
                if self.check_drawdown():
                    self.trigger_emergency("Drawdown > 5% in last hour")
                    triggered = True

                if not triggered and self.check_btc_crash():
                    self.trigger_emergency("Bitcoin drops > 10% in 4 hours")
                    triggered = True

                if triggered:
                    if not self.dry_run:
                        logger.info("Emergency triggered. Sentinel exiting.")
                        sys.exit(0)
                    else:
                        logger.info("[DRY RUN] Emergency triggered but continuing.")

            except KeyboardInterrupt:
                logger.info("Sentinel stopped by user.")
                sys.exit(0)
            except Exception as e:
                logger.error(f"Unexpected error in monitor loop: {e}")

            time.sleep(300)


def main():
    parser = argparse.ArgumentParser(description="Sentinel Circuit Breaker for Freqtrade")
    parser.add_argument(
        "--config", type=Path, default=Path("config.json"), help="Path to config file"
    )
    parser.add_argument(
        "--panic-sell",
        action="store_true",
        help="Enable panic sell (liquidation) on trigger"
    )
    parser.add_argument("--openclaw-url", type=str, help="OpenClaw Webhook URL for alerts")
    parser.add_argument(
        "--dry-run", action="store_true", help="Dry run mode (no actions taken)"
    )

    args = parser.parse_args()

    sentinel = Sentinel(args.config, args.panic_sell, args.openclaw_url, args.dry_run)
    sentinel.run()


if __name__ == "__main__":
    main()
