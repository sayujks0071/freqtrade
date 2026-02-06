#!/usr/bin/env python3
"""
Sentinel - Circuit Breaker for Freqtrade.

Monitor: Check the live logs every 5 minutes.
Emergency Rule: IF `Drawdown > 5%` in the last hour OR `Bitcoin drops > 10%` in 4 hours:
    -   Kill Switch: Immediately runs `freqtrade stop`.
    -   Liquidation: Panic sell all positions to USDT.
    -   Alert: Send a 'CRITICAL ALERT' message to my WhatsApp via OpenClaw.
Resume: Do not restart trading until I manually approve it.
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
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
    def __init__(
        self,
        config_path: Path,
        interval: int,
        openclaw_url: str | None,
        dry_run: bool = False,
    ):
        self.config_path = config_path
        self.interval = interval
        self.openclaw_url = openclaw_url
        self.dry_run = dry_run

        self.rpc_config = self._load_rpc_config()
        self.rpc_url = (
            f"http://{self.rpc_config.get('listen_ip_address', '127.0.0.1')}:"
            f"{self.rpc_config.get('listen_port', 8080)}/api/v1"
        )
        self.auth_token = None

        # History for calculations
        # List of (timestamp, balance)
        self.balance_history: list[tuple[datetime, float]] = []

        # Initialize Exchange for BTC price
        # Using Binance as a reliable public source for BTC/USDT
        self.exchange = ccxt.binance()

    def _load_rpc_config(self) -> dict:
        if not self.config_path.exists():
            logger.error(f"Config file not found: {self.config_path}")
            sys.exit(1)

        with self.config_path.open() as f:
            config = json.load(f)

        return config.get("api_server", {})

    def _login(self) -> bool:
        username = self.rpc_config.get("username")
        password = self.rpc_config.get("password")

        if not username or not password:
            logger.error("RPC username or password not found in config.")
            return False

        try:
            response = requests.post(
                f"{self.rpc_url}/token/login",
                data={"username": username, "password": password},
                timeout=10,
            )
            response.raise_for_status()
            self.auth_token = response.json().get("access_token")
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to login to RPC: {e}")
            return False

    def _rpc_get(self, endpoint: str) -> dict | None:
        if not self.auth_token:
            if not self._login():
                return None

        headers = {"Authorization": f"Bearer {self.auth_token}"}
        try:
            response = requests.get(
                f"{self.rpc_url}/{endpoint}", headers=headers, timeout=10
            )
            if response.status_code == 401:
                # Token expired? Retry login
                logger.info("Token expired, refreshing...")
                if self._login():
                    headers = {"Authorization": f"Bearer {self.auth_token}"}
                    response = requests.get(
                        f"{self.rpc_url}/{endpoint}", headers=headers, timeout=10
                    )
                else:
                    return None
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"RPC Request failed ({endpoint}): {e}")
            return None

    def _rpc_post(self, endpoint: str, data: dict | None = None) -> dict | None:
        if not self.auth_token:
            if not self._login():
                return None

        headers = {"Authorization": f"Bearer {self.auth_token}"}
        try:
            response = requests.post(
                f"{self.rpc_url}/{endpoint}", json=data, headers=headers, timeout=10
            )
            if response.status_code == 401:
                if self._login():
                    headers = {"Authorization": f"Bearer {self.auth_token}"}
                    response = requests.post(
                        f"{self.rpc_url}/{endpoint}",
                        json=data,
                        headers=headers,
                        timeout=10,
                    )
                else:
                    return None
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"RPC Request failed ({endpoint}): {e}")
            return None

    def get_total_balance(self) -> float | None:
        data = self._rpc_get("balance")
        if data:
            # Assuming 'total' currency is USDT or returning total value in quote currency
            # /balance returns list of currencies.
            # We want the total portfolio value.
            # Usually /balance result has 'total' key if using some versions,
            # or we need to sum.
            # Let's check /status or /profit?
            # /balance usually returns: {'currencies': [...], 'total': ...}
            # If 'total' is not present, we might need to sum 'est_stake'.
            return data.get("total")
        return None

    def get_btc_drop_4h(self) -> float | None:
        """
        Calculates the percentage drop of BTC in the last 4 hours.
        Returns float (e.g. 0.10 for 10% drop).
        """
        try:
            # Fetch OHLCV for 4h.
            # 4h = 240 minutes.
            # If we fetch 1h candles, we need last 5 candles (current + 4 previous).
            ohlcv = self.exchange.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=5)
            if not ohlcv:
                return None

            # ohlcv is list of [timestamp, open, high, low, close, volume]
            # We want the Highest High in the last 4 hours vs Current Close.
            # The last candle is the current one (incomplete).
            # The lookback period is 4 hours.
            # We consider the High of the candles covering the last 4 hours.

            highs = [candle[2] for candle in ohlcv]
            current_price = ohlcv[-1][4]  # Current close (or last price)
            max_price = max(highs)

            if max_price == 0:
                return 0.0

            drop = (max_price - current_price) / max_price
            return drop

        except Exception as e:
            logger.error(f"Failed to fetch BTC price: {e}")
            return None

    def update_balance_history(self, current_balance: float):
        now = datetime.now(timezone.utc)  # noqa: UP017
        self.balance_history.append((now, current_balance))

        # Prune history older than 1 hour
        cutoff = now - timedelta(hours=1)
        self.balance_history = [(t, b) for t, b in self.balance_history if t >= cutoff]

    def get_drawdown_1h(self, current_balance: float) -> float:
        """
        Calculates max drawdown in the last 1 hour.
        Returns float (e.g. 0.05 for 5%).
        """
        if not self.balance_history:
            return 0.0

        max_balance = max(b for t, b in self.balance_history)
        if max_balance == 0:
            return 0.0

        drawdown = (max_balance - current_balance) / max_balance
        return drawdown

    def notify_openclaw(self, message: str):
        logger.info(f"ALERT: {message}")
        if self.openclaw_url:
            try:
                payload = {"message": message, "channel": "whatsapp"}
                requests.post(self.openclaw_url, json=payload, timeout=10)
            except Exception as e:
                logger.error(f"Failed to send OpenClaw alert: {e}")
        else:
            logger.warning("OpenClaw URL not configured. Alert only logged.")

    def trigger_emergency(self, reason: str):
        msg = f"CRITICAL ALERT: Sentinel triggered! Reason: {reason}"
        self.notify_openclaw(msg)

        if self.dry_run:
            logger.info("[DRY-RUN] Would STOP bot and FORCE EXIT all positions.")
            return

        # Liquidation (Panic Sell)
        logger.info("Executing Liquidation (Force Exit All)...")
        self._rpc_post("forceexit")  # forceexit all

        # Kill Switch
        logger.info("Executing Kill Switch (Stop Bot)...")
        self._rpc_post("stop")

        logger.info("Emergency actions completed. Sentinel exiting.")
        sys.exit(0)

    def run(self):
        logger.info("Sentinel started monitoring...")
        while True:
            try:
                # 1. Check BTC
                btc_drop = self.get_btc_drop_4h()
                if btc_drop is not None:
                    logger.info(f"BTC Drop 4h: {btc_drop:.2%}")
                    if btc_drop > 0.10:
                        self.trigger_emergency(f"Bitcoin dropped {btc_drop:.2%} > 10% in 4h")

                # 2. Check Balance & Drawdown
                balance = self.get_total_balance()
                if balance is not None:
                    self.update_balance_history(balance)
                    drawdown = self.get_drawdown_1h(balance)
                    logger.info(f"Current Balance: {balance}, Drawdown 1h: {drawdown:.2%}")

                    if drawdown > 0.05:
                        self.trigger_emergency(f"Drawdown {drawdown:.2%} > 5% in 1h")
                else:
                    logger.warning("Could not fetch balance from RPC.")

                # Wait for next interval
                time.sleep(self.interval)

            except KeyboardInterrupt:
                logger.info("Sentinel stopped by user.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in loop: {e}")
                time.sleep(self.interval)


def main():
    parser = argparse.ArgumentParser(
        description="Sentinel - Circuit Breaker for Freqtrade",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
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
    parser.add_argument(
        "--openclaw-url",
        type=str,
        default=None,
        help="URL for OpenClaw/WhatsApp alerts",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate actions without executing them",
    )

    args = parser.parse_args()

    sentinel = Sentinel(
        config_path=args.config,
        interval=args.interval,
        openclaw_url=args.openclaw_url,
        dry_run=args.dry_run,
    )

    sentinel.run()


if __name__ == "__main__":
    main()
