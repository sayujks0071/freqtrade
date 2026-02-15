#!/usr/bin/env python3
"""
Sentinel (Circuit Breaker) Script for Freqtrade.

Monitors portfolio drawdown and Bitcoin price crashes to trigger emergency stops.
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import ccxt
import requests

# Adjust path to import ft_client
# Assuming script is in scripts/ and ft_client is in ft_client/ relative to repo root
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root / "ft_client"))

try:
    from freqtrade_client.ft_client import load_config
    from freqtrade_client.ft_rest_client import FtRestClient
except ImportError:
    print(
        "Error: ft_client not found. Ensure you are running from the repo root "
        "or ft_client is installed."
    )
    sys.exit(1)

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(project_root / "user_data/logs/sentinel.log")
        if (project_root / "user_data/logs").exists()
        else logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("sentinel")


class Sentinel:
    def __init__(
        self, config_path, interval=300, dry_run=False, one_shot=False, panic_sell=False
    ):
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            logger.warning(
                f"Config file {self.config_path} not found. Some settings might be missing."
            )
            self.config = {}
        else:
            self.config = load_config(str(self.config_path))

        self.interval = interval
        self.dry_run = dry_run
        self.one_shot = one_shot
        self.panic_sell = panic_sell

        # API Connection
        api_config = self.config.get("api_server", {})
        self.api_url = api_config.get("listen_ip_address", "127.0.0.1")
        self.api_port = api_config.get("listen_port", "8080")
        self.username = api_config.get("username")
        self.password = api_config.get("password")
        self.server_url = f"http://{self.api_url}:{self.api_port}"

        self.client = FtRestClient(self.server_url, self.username, self.password)

        # State Management
        self.user_data_dir = project_root / "user_data"
        self.state_file = self.user_data_dir / "sentinel_state.json"

        # Create user_data if not exists (though usually it should)
        if not self.user_data_dir.exists():
            try:
                self.user_data_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"Could not create user_data directory: {e}")

        self.load_state()

        # OpenClaw / Webhook
        # Config key 'sentinel' -> 'openclaw_url'
        self.openclaw_url = self.config.get("sentinel", {}).get("openclaw_url")

        # Market Data (CCXT)
        # Default to Binance
        self.exchange = ccxt.binance()

    def load_state(self):
        if self.state_file.exists():
            try:
                with self.state_file.open("r") as f:
                    self.state = json.load(f)
            except json.JSONDecodeError:
                logger.error("Corrupt state file, resetting state.")
                self.state = {"balance_history": [], "triggered": False}
        else:
            self.state = {"balance_history": [], "triggered": False}

    def save_state(self):
        try:
            with self.state_file.open("w") as f:
                json.dump(self.state, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def log(self, message, level=logging.INFO):
        if level == logging.ERROR:
            logger.error(message)
        else:
            logger.info(message)

    def alert(self, message):
        self.log(f"ALERT: {message}", level=logging.ERROR)
        if self.openclaw_url:
            try:
                if not self.dry_run:
                    requests.post(
                        self.openclaw_url,
                        json={"message": message, "priority": "high"},
                        timeout=10,
                    )
                else:
                    self.log(f"Dry Run: Would post to OpenClaw: {message}")
            except Exception as e:
                self.log(f"Failed to send alert: {e}", level=logging.ERROR)
        else:
            self.log("No OpenClaw URL configured. Alert skipped.")

    def get_btc_drop(self):
        """
        Check if Bitcoin dropped > 10% in last 4 hours using CCXT.
        """
        try:
            # Fetch 1h candles, last 5 to cover 4h window + current incomplete candle
            ohlcv = self.exchange.fetch_ohlcv("BTC/USDT", "1h", limit=5)
            if not ohlcv or len(ohlcv) < 2:
                return 0.0

            # Use the highest High in the window as the reference peak
            highs = [x[2] for x in ohlcv]
            current_price = ohlcv[-1][4]  # Close of current/last candle

            max_high = max(highs)

            if max_high == 0:
                return 0.0

            drop = (max_high - current_price) / max_high
            return drop
        except Exception as e:
            self.log(f"Error fetching BTC price from CCXT: {e}", level=logging.ERROR)
            return 0.0

    def check_drawdown(self, current_balance):
        """
        Check if Drawdown > 5% in last hour.
        Updates balance history in state.
        """
        now_ts = datetime.now().timestamp()

        # Add current balance
        self.state["balance_history"].append(
            {"timestamp": now_ts, "balance": current_balance}
        )

        # Prune old history (> 1 hour = 3600 seconds)
        cutoff = now_ts - 3600
        self.state["balance_history"] = [
            x for x in self.state["balance_history"] if x["timestamp"] >= cutoff
        ]
        self.save_state()

        if not self.state["balance_history"]:
            return 0.0

        # Max balance in the last hour
        max_balance = max(x["balance"] for x in self.state["balance_history"])

        if max_balance == 0:
            return 0.0

        drawdown = (max_balance - current_balance) / max_balance
        return drawdown

    def emergency_stop(self, reason):
        """
        Executes the kill switch and optional liquidation.
        """
        msg = f"CRITICAL ALERT: {reason}. Initiating Kill Switch."
        self.alert(msg)

        if self.dry_run:
            self.log("Dry Run: Would stop bot now.")
        else:
            try:
                self.client.stop()
                self.log("Bot stopped via API.")
            except Exception as e:
                self.log(f"Failed to stop bot: {e}", level=logging.ERROR)

        if self.panic_sell:
            self.alert("Initiating Emergency Liquidation (Panic Sell).")
            if self.dry_run:
                self.log("Dry Run: Would liquidate all positions.")
            else:
                try:
                    # Get open trades
                    trades = self.client.status()
                    for trade in trades:
                        trade_id = trade.get("trade_id")
                        if trade_id:
                            self.log(f"Force exiting trade {trade_id}")
                            self.client.forceexit(str(trade_id))
                            # Small delay to ensure order submission
                            time.sleep(1)
                except Exception as e:
                    self.log(f"Failed to liquidate positions: {e}", level=logging.ERROR)

        self.state["triggered"] = True
        self.save_state()

    def fetch_current_balance(self):
        """
        Fetch the current balance from the Freqtrade API.
        """
        try:
            balance_data = self.client.balance()
            if balance_data:
                # balance_data is a dict (json response) matching Balances schema
                # 'total' is the estimated total value in stake currency
                current_balance = balance_data.get("total", 0.0)
                self.log(
                    f"Current Balance: {current_balance:.2f} "
                    f"{balance_data.get('stake', 'Units')}"
                )
                return current_balance
            else:
                self.log(
                    "Failed to fetch balance data (API returned None).", level=logging.ERROR
                )
        except Exception as e:
            self.log(f"Error fetching balance from API: {e}", level=logging.ERROR)
            # If API is down, we can't check drawdown, but we CAN check BTC crash via CCXT
        return 0.0

    def run_check_cycle(self):
        """
        Run a single iteration of checks.
        Returns True if the script should stop (e.g. one_shot finished), False otherwise.
        """
        # Reload state in case it was modified externally (unlikely but safe)
        self.load_state()

        if self.state.get("triggered"):
            self.log(
                "Sentinel previously triggered. Waiting for manual reset. "
                "(Set 'triggered': false in state file to resume)"
            )
            return True if self.one_shot else False

        # 1. Get Current Balance from API
        current_balance = self.fetch_current_balance()

        # 2. Check Drawdown
        if current_balance > 0:
            dd = self.check_drawdown(current_balance)
            self.log(f"Portfolio Drawdown (1h): {dd * 100:.2f}%")

            if dd > 0.05:
                self.emergency_stop(f"Drawdown {dd * 100:.2f}% > 5%")
                return True
        else:
            self.log("Skipping Drawdown check due to missing balance data.")

        # 3. Check Bitcoin Drop
        btc_drop = self.get_btc_drop()
        self.log(f"BTC Drop (4h): {btc_drop * 100:.2f}%")

        if btc_drop > 0.10:
            self.emergency_stop(f"Bitcoin Drop {btc_drop * 100:.2f}% > 10%")
            return True

        if self.one_shot:
            return True

        return False

    def loop(self):
        self.log(
            f"Sentinel started. Interval: {self.interval}s. Dry Run: {self.dry_run}"
        )
        while True:
            try:
                should_stop = self.run_check_cycle()
                if should_stop:
                    break

                time.sleep(self.interval)

            except KeyboardInterrupt:
                self.log("Sentinel stopped by user.")
                break
            except Exception as e:
                self.log(f"Unexpected error in main loop: {e}", level=logging.ERROR)
                if self.one_shot:
                    break
                time.sleep(60)  # Retry delay


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Freqtrade Sentinel")
    parser.add_argument(
        "-c", "--config", help="Config file", default="config.json"
    )
    parser.add_argument(
        "--interval", help="Check interval in seconds", type=int, default=300
    )
    parser.add_argument("--oneshot", help="Run once and exit", action="store_true")
    parser.add_argument("--dryrun", help="Dry run (no actions)", action="store_true")
    parser.add_argument(
        "--panic-sell",
        help="Liquidate all positions on trigger",
        action="store_true",
    )

    args = parser.parse_args()

    sentinel = Sentinel(
        args.config, args.interval, args.dryrun, args.oneshot, args.panic_sell
    )
    sentinel.loop()
