#!/usr/bin/env python3
"""
Sentinel: Circuit Breaker for Freqtrade.
Monitors the bot and triggers emergency shutdown if thresholds are breached.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import requests


# Add ft_client to path
current_dir = Path(__file__).resolve().parent
ft_client_dir = current_dir.parent / "ft_client"
sys.path.append(str(ft_client_dir))

from freqtrade_client.ft_rest_client import FtRestClient


logger = logging.getLogger("sentinel")


class Sentinel:
    def __init__(self, config_path, interval=300):
        self.config_path = Path(config_path)
        self.interval = interval
        self.balance_history = []  # List of (timestamp, balance)
        self.client = self._connect_client()
        self.setup_logging()

    def setup_logging(self):
        log_file = Path("user_data/sentinel_alert.log")
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)],
        )

    def _connect_client(self):
        if not self.config_path.exists():
            # If the provided path doesn't exist, try defaulting to config.json
            # But if the user explicitly provided a path, we should respect it
            # The default is user_data/configs/config.delta.live.json
            logger.error(f"Config file not found: {self.config_path}")
            sys.exit(1)

        with self.config_path.open("r") as f:
            # simple load, comments are not handled by standard json
            # ft_client uses rapidjson or json with comment stripping usually
            # But config.delta.live.json is standard JSON usually.
            # If not, I should use rapidjson or a robust loader.
            # ft_client uses rapidjson.
            try:
                import rapidjson

                config = rapidjson.load(
                    f, parse_mode=rapidjson.PM_COMMENTS | rapidjson.PM_TRAILING_COMMAS
                )
            except ImportError:
                config = json.load(f)

        api_config = config.get("api_server", {})
        url = api_config.get("listen_ip_address", "127.0.0.1")
        port = api_config.get("listen_port", "8080")
        username = api_config.get("username")
        password = api_config.get("password")

        server_url = f"http://{url}:{port}"
        return FtRestClient(server_url, username, password)

    def get_balance(self):
        try:
            data = self.client.balance()
            if "total" in data:
                return float(data["total"])
            return 0.0
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return None

    def get_btc_price_drop(self):
        try:
            pair = "BTC/USDT"
            # Get 5 candles for 1h timeframe to cover 4 hours ago
            candles = self.client.pair_candles(pair, "1h", limit=5)
            if not candles or len(candles) < 5:
                return 0.0

            # candles is list of lists [time, open, high, low, close, volume]
            current_price = candles[-1][4]
            price_4h_ago = candles[0][4]

            if price_4h_ago == 0:
                return 0.0

            drop = (price_4h_ago - current_price) / price_4h_ago
            return drop
        except Exception as e:
            logger.error(f"Error fetching BTC price: {e}")
            return 0.0

    def update_balance_history(self, current_balance):
        now = time.time()
        self.balance_history.append((now, current_balance))
        # Remove entries older than 1 hour
        one_hour_ago = now - 3600
        self.balance_history = [(t, b) for t, b in self.balance_history if t >= one_hour_ago]

    def check_drawdown(self, current_balance):
        if not self.balance_history:
            return False

        max_balance = max(b for t, b in self.balance_history)
        if max_balance == 0:
            return False

        drawdown = (max_balance - current_balance) / max_balance
        if drawdown > 0.05:
            logger.warning(f"Drawdown detected: {drawdown:.2%}")
            return True
        return False

    def check_btc_crash(self):
        drop = self.get_btc_price_drop()
        if drop > 0.10:
            logger.warning(f"BTC Crash detected: {drop:.2%}")
            return True
        return False

    def alert(self, message):
        logger.critical(message)
        try:
            requests.post("http://localhost:5000/send", json={"message": message}, timeout=5)
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")

    def emergency_shutdown(self, reason):
        msg = f"CRITICAL ALERT: {reason}. Initiating Kill Switch."
        self.alert(msg)

        try:
            logger.info("Stopping buy...")
            self.client.stopbuy()

            logger.info("Liquidating all positions...")
            trades = self.client.status()
            if trades:
                for trade in trades:
                    logger.info(f"Force exiting trade {trade['trade_id']}")
                    self.client.forceexit(trade["trade_id"])

            # Wait for sales to process
            time.sleep(5)

            logger.info("Stopping bot...")
            self.client.stop()

        except Exception as e:
            logger.error(f"Error during emergency shutdown: {e}")

        sys.exit(0)

    def run(self):
        logger.info("Sentinel started monitoring...")
        while True:
            try:
                balance = self.get_balance()
                if balance is not None:
                    self.update_balance_history(balance)

                    if self.check_drawdown(balance):
                        self.emergency_shutdown("Drawdown > 5% in last hour")

                if self.check_btc_crash():
                    self.emergency_shutdown("Bitcoin drops > 10% in 4 hours")

            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")

            time.sleep(self.interval)


def main():
    parser = argparse.ArgumentParser(description="Sentinel for Freqtrade")
    parser.add_argument(
        "--config", help="Config file path", default="user_data/configs/config.delta.live.json"
    )
    parser.add_argument("--interval", help="Check interval in seconds", type=int, default=300)
    args = parser.parse_args()

    sentinel = Sentinel(args.config, args.interval)
    sentinel.run()


if __name__ == "__main__":
    main()
