#!/usr/bin/env python3
import argparse
import json
import logging
import sys
import time
from pathlib import Path


# Ensure we can import ft_client
repo_root = Path(__file__).resolve().parent.parent
sys.path.append(str(repo_root / "ft_client"))

try:
    from freqtrade_client.ft_rest_client import FtRestClient
except ImportError as e:
    print(
        f"Error: Could not import freqtrade_client. "
        f"Make sure ft_client is in the path. Details: {e}"
    )
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("sentinel")


class Sentinel:
    def __init__(self, config_path, interval, dry_run, btc_pair):
        self.config_path = Path(config_path)
        self.interval = interval
        self.dry_run = dry_run
        self.btc_pair = btc_pair
        self.history_file = repo_root / "user_data" / "sentinel_history.json"

        self.config = self._load_config()
        self.client = self._init_client()
        self.balance_history = self._load_history()

    def _load_config(self):
        if not self.config_path.exists():
            logger.error(f"Config file not found: {self.config_path}")
            sys.exit(1)
        with self.config_path.open("r") as f:
            return json.load(f)

    def _init_client(self):
        api_config = self.config.get("api_server", {})
        if not api_config.get("enabled", False):
            logger.error("API Server is not enabled in the configuration.")
            sys.exit(1)

        ip = api_config.get("listen_ip_address", "127.0.0.1")
        port = api_config.get("listen_port", 8080)
        username = api_config.get("username")
        password = api_config.get("password")

        url = f"http://{ip}:{port}"
        return FtRestClient(url, username=username, password=password)

    def _load_history(self):
        if self.history_file.exists():
            try:
                with self.history_file.open("r") as f:
                    data = json.load(f)
                    return data
            except json.JSONDecodeError:
                logger.warning("History file corrupted, starting fresh.")
                return []
        return []

    def _save_history(self):
        with self.history_file.open("w") as f:
            json.dump(self.balance_history, f)

    def update_balance_history(self):
        try:
            balance_data = self.client.balance()
            # freqtrade `balance` endpoint returns:
            # { "currencies": [...], "total": 1234.5, "symbol": "USDT", ... }
            # Use 'total' if available.
            total_balance = balance_data.get("total")
            if total_balance is None:
                # If total is not directly available, try to sum up.
                # But without prices, we can't sum easily.
                # Assuming 'total' is present in standard Freqtrade API.
                logger.warning("Could not find 'total' in balance response. Using 0.")
                total_balance = 0.0

            now_ts = time.time()
            self.balance_history.append({"ts": now_ts, "balance": total_balance})

            # Prune history older than 1 hour + margin (e.g. 70 mins)
            cutoff = now_ts - 3600 - 600
            self.balance_history = [x for x in self.balance_history if x["ts"] > cutoff]
            self._save_history()

            return total_balance
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return None

    def check_drawdown(self):
        # Drawdown > 5% in the last hour
        if not self.balance_history:
            return False

        now_ts = time.time()
        one_hour_ago = now_ts - 3600

        # Filter entries within the last hour
        recent_history = [x for x in self.balance_history if x["ts"] >= one_hour_ago]

        if not recent_history:
            return False

        max_balance = max(x["balance"] for x in recent_history)
        current_balance = recent_history[-1]["balance"]

        if max_balance == 0:
            return False

        drawdown = (max_balance - current_balance) / max_balance

        if drawdown > 0.05:
            logger.info(
                f"Drawdown detected: {drawdown * 100:.2f}% "
                f"(Max: {max_balance}, Curr: {current_balance})"
            )
            return True
        return False

    def check_btc_crash(self):
        # Bitcoin drops > 10% in 4 hours
        try:
            # Get 1h candles, last 5 to cover 4 hours
            candles_data = self.client.pair_candles(self.btc_pair, "1h", limit=5)

            if not candles_data:
                logger.debug(f"No candle data received for {self.btc_pair}")
                return False

            if isinstance(candles_data, dict) and "error" in candles_data:
                logger.warning(f"Error getting candles: {candles_data['error']}")
                return False

            # Check structure: list of lists [timestamp, open, high, low, close, volume]
            if len(candles_data) > 0 and isinstance(candles_data[0], list):
                now_ms = time.time() * 1000
                four_hours_ago_ms = now_ms - (4 * 3600 * 1000)

                # Filter relevant candles (timestamp >= 4 hours ago)
                relevant_candles = [c for c in candles_data if c[0] >= four_hours_ago_ms]

                if not relevant_candles:
                    relevant_candles = candles_data

                # Use Highs for peak price reference
                highs = [c[2] for c in relevant_candles]
                current_price = relevant_candles[-1][4]  # Close of latest

                max_high = max(highs)

                if max_high == 0:
                    return False

                drop = (max_high - current_price) / max_high

                if drop > 0.10:
                    logger.info(
                        f"BTC Crash detected: {drop * 100:.2f}% "
                        f"(High: {max_high}, Curr: {current_price})"
                    )
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking BTC price: {e}")
            return False

    def trigger_emergency(self, reason):
        msg = f"CRITICAL ALERT: {reason}"
        self.alert(msg)

        if self.dry_run:
            logger.info("DRY RUN: Would trigger Panic Sell and Kill Switch now.")
            return

        logger.info("Engaging Kill Switch and Liquidation...")
        self.panic_sell()

        logger.info("Stopping Bot...")
        try:
            self.client.stop()
        except Exception as e:
            logger.error(f"Failed to stop bot: {e}")

    def panic_sell(self):
        try:
            open_trades = self.client.status()
            if not open_trades:
                logger.info("No open trades to sell.")
                return

            for trade in open_trades:
                trade_id = trade["trade_id"]
                pair = trade["pair"]
                logger.info(f"Panic selling {pair} (ID: {trade_id})...")
                try:
                    self.client.forceexit(trade_id, ordertype="market")
                except Exception as e:
                    logger.error(f"Failed to sell {pair}: {e}")

        except Exception as e:
            logger.error(f"Error during panic sell: {e}")

    def alert(self, msg):
        logger.critical(msg)
        print(f"OPENCLAW: {msg}")

    def run(self):
        logger.info(f"Sentinel started. Monitoring {self.btc_pair}. Interval: {self.interval}s")
        while True:
            try:
                self.update_balance_history()

                if self.check_drawdown():
                    self.trigger_emergency("Drawdown > 5% in last hour")
                    logger.info("Emergency triggered. Sentinel exiting.")
                    sys.exit(0)

                if self.check_btc_crash():
                    self.trigger_emergency(f"{self.btc_pair} drop > 10% in 4 hours")
                    logger.info("Emergency triggered. Sentinel exiting.")
                    sys.exit(0)

            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")

            time.sleep(self.interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sentinel: Freqtrade Circuit Breaker")
    parser.add_argument(
        "--config",
        default="user_data/configs/config.delta.live.json",
        help="Path to config file",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Check interval in seconds (default: 300)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (do not actually stop/sell)",
    )
    parser.add_argument(
        "--pair", default="BTC/USDT", help="BTC pair to monitor (default: BTC/USDT)"
    )

    args = parser.parse_args()

    sentinel = Sentinel(args.config, args.interval, args.dry_run, args.pair)
    sentinel.run()
