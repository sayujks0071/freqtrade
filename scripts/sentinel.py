#!/usr/bin/env python3
"""
Sentinel (Circuit Breaker)
Real-time crisis management to protect capital.
"""

import argparse
import json
import logging
import os
import sys
import time
from collections import deque

import ccxt
import requests
import schedule


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Sentinel")


class Sentinel:
    def __init__(self, config_path: str | None = None):
        self.config: dict = {}
        self.api_url = os.getenv("FREQTRADE_API_URL", "http://127.0.0.1:8080")
        self.api_username = os.getenv("FREQTRADE_API_USERNAME", "freqtrader")
        self.api_password = os.getenv("FREQTRADE_API_PASSWORD", "SuperSecurePassword123!")
        self.exchange_id = os.getenv("SENTINEL_EXCHANGE", "binance")
        self.openclaw_url = os.getenv("OPENCLAW_URL")
        self.openclaw_token = os.getenv("OPENCLAW_TOKEN")

        # Load config if provided
        if config_path:
            self.load_config(config_path)

        # Initialize exchange for market data
        try:
            self.exchange = getattr(ccxt, self.exchange_id)()
        except AttributeError:
            logger.error(f"Exchange '{self.exchange_id}' not found in ccxt. Defaulting to binance.")
            self.exchange = ccxt.binance()

        # State for drawdown check
        self.balance_history: deque[tuple[float, float]] = deque()  # (timestamp, total_balance)
        self.history_window = 3600  # 1 hour in seconds

        # State
        self.is_running = True

    def load_config(self, path: str):
        try:
            with open(path) as f:  # noqa: PTH123
                config = json.load(f)
                self.config = config

                # Extract API config
                api = config.get("api_server", {})
                if api.get("listen_ip_address") and api.get("listen_port"):
                    host = api.get("listen_ip_address", "127.0.0.1")
                    if host == "0.0.0.0":  # noqa: S104
                        host = "127.0.0.1"
                    self.api_url = f"http://{host}:{api.get('listen_port')}"

                self.api_username = api.get("username", self.api_username)
                self.api_password = api.get("password", self.api_password)

        except Exception as e:
            logger.error(f"Error loading config from {path}: {e}")

    def _get_api_auth(self):
        return (self.api_username, self.api_password)

    def fetch_btc_price_data(self):
        """Fetches OHLCV for BTC/USDT to check for crash."""
        try:
            # 1h candles, need last 5 to cover 4h window + current
            ohlcv = self.exchange.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=5)
            return ohlcv
        except Exception as e:
            logger.error(f"Error fetching BTC data: {e}")
            return None

    def check_market_crash(self):
        """Check if Bitcoin drops > 10% in 4 hours."""
        ohlcv = self.fetch_btc_price_data()
        if not ohlcv:
            return False

        # ohlcv format: [timestamp, open, high, low, close, volume]
        # We want the highest high in the last 4 completed candles + current
        current_close = ohlcv[-1][4]
        highs = [candle[2] for candle in ohlcv]
        max_high = max(highs)

        drop_pct = (max_high - current_close) / max_high

        if drop_pct > 0.10:
            logger.critical(
                f"BTC CRASH DETECTED: {drop_pct * 100:.2f}% drop from {max_high} to {current_close}"
            )
            return True
        return False

    def fetch_portfolio_value(self):
        """Fetches current portfolio value from Freqtrade API."""
        try:
            resp = requests.get(
                f"{self.api_url}/api/v1/balance",
                auth=self._get_api_auth(),
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                # data format: {"currencies": [...], "total": ..., "value": ...}
                return data.get("total")
            else:
                logger.error(f"API Error /balance: {resp.status_code} {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Error fetching portfolio value: {e}")
            return None

    def check_portfolio_drawdown(self):
        """Check if Drawdown > 5% in the last hour."""
        current_value = self.fetch_portfolio_value()
        if current_value is None:
            return False

        now = time.time()
        self.balance_history.append((now, current_value))

        # Clean old history
        while self.balance_history and self.balance_history[0][0] < now - self.history_window:
            self.balance_history.popleft()

        if not self.balance_history:
            return False

        # Calculate max balance in the window
        max_balance = max(val for _, val in self.balance_history)

        if max_balance <= 0:
            return False

        drawdown = (max_balance - current_value) / max_balance

        if drawdown > 0.05:
            logger.critical(
                f"PORTFOLIO DRAWDOWN DETECTED: {drawdown * 100:.2f}% drop from "
                f"{max_balance} to {current_value}"
            )
            return True
        return False

    def _send_alert(self, message: str):
        if self.openclaw_url:
            try:
                payload = {"message": message, "token": self.openclaw_token}
                requests.post(self.openclaw_url, json=payload, timeout=5)
            except Exception as e:
                logger.error(f"Failed to send OpenClaw alert: {e}")
        else:
            logger.info(f"OpenClaw URL not configured. Alert: {message}")

    def _stop_buying(self):
        try:
            requests.post(
                f"{self.api_url}/api/v1/stopbuy",
                auth=self._get_api_auth(),
                timeout=10,
            )
            logger.info("Executed /stopbuy")
        except Exception as e:
            logger.error(f"Failed to execute /stopbuy: {e}")

    def _force_exit_all(self):
        """Panic sell all positions."""
        try:
            # Get open trades
            resp = requests.get(
                f"{self.api_url}/api/v1/status",
                auth=self._get_api_auth(),
                timeout=10,
            )
            if resp.status_code == 200:
                trades = resp.json()
                # trades is a list of open trades
                # Iterate and force exit
                for trade in trades:
                    trade_id = trade.get("trade_id")
                    if trade_id:
                        requests.post(
                            f"{self.api_url}/api/v1/forceexit",
                            json={"tradeid": trade_id},
                            auth=self._get_api_auth(),
                            timeout=10,
                        )
                        logger.info(f"Executed /forceexit for trade {trade_id}")
            else:
                logger.error(f"Failed to get status for force exit: {resp.status_code}")
        except Exception as e:
            logger.error(f"Failed to execute force exit: {e}")

    def _stop_bot(self):
        try:
            requests.post(
                f"{self.api_url}/api/v1/stop",
                auth=self._get_api_auth(),
                timeout=10,
            )
            logger.info("Executed /stop (Kill Switch)")
        except Exception as e:
            logger.error(f"Failed to execute /stop: {e}")

    def trigger_emergency(self, reason: str):
        msg = f"CRITICAL ALERT: Sentinel triggered due to {reason}. Engaging Emergency Protocol."
        logger.critical(msg)

        self._send_alert(msg)
        self._stop_buying()
        self._force_exit_all()

        # Give the bot a moment to process exit orders before killing it
        time.sleep(5)

        self._stop_bot()

        logger.critical(
            "Emergency Protocol Completed. Sentinel Entering Standby (Manual Restart Required)."
        )
        self.is_running = False
        sys.exit(1)

    def run_checks(self):
        if not self.is_running:
            return

        logger.info("Sentinel checking status...")

        if self.check_market_crash():
            self.trigger_emergency("Bitcoin Crash (>10% drop in 4h)")
            return

        if self.check_portfolio_drawdown():
            self.trigger_emergency("Portfolio Drawdown (>5% in 1h)")
            return

    def start(self):
        logger.info("Sentinel started. Monitoring every 5 minutes.")
        schedule.every(5).minutes.do(self.run_checks)

        # Initial check
        self.run_checks()

        while self.is_running:
            schedule.run_pending()
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="Sentinel: Freqtrade Circuit Breaker")
    parser.add_argument("--config", "-c", help="Path to Freqtrade config file", default=None)
    args = parser.parse_args()

    sentinel = Sentinel(config_path=args.config)
    sentinel.start()


if __name__ == "__main__":
    main()
