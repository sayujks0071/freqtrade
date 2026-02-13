#!/usr/bin/env python3
"""
Sentinel - Circuit Breaker for Freqtrade
"""

import sys
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path to allow importing freqtrade_client
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR / "ft_client"))

try:
    from freqtrade_client.ft_client import FtRestClient, load_config
    import ccxt
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    print("Please ensure freqtrade-client and ccxt are installed or available.")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Sentinel")


class Sentinel:
    def __init__(self, config_file, liquidate=False, dry_run=False):
        self.config_file = config_file
        self.liquidate_on_crash = liquidate
        self.dry_run = dry_run  # If true, don't actually stop/liquidate, just log
        self.config = load_config(config_file)

        # API Client Setup
        self.api_url = self.config.get("api_server", {}).get("listen_ip_address", "127.0.0.1")
        self.api_port = self.config.get("api_server", {}).get("listen_port", "8080")
        self.username = self.config.get("api_server", {}).get("username")
        self.password = self.config.get("api_server", {}).get("password")
        self.server_url = f"http://{self.api_url}:{self.api_port}"

        self.client = FtRestClient(self.server_url, self.username, self.password)

        # Balance History for Drawdown Calculation
        # List of tuples: (timestamp, total_balance)
        self.balance_history = []

        # Exchange Setup for BTC Price Check
        # Default to Gate.io based on memory if not specified, but CCXT supports many.
        # We use a public instance for market data.
        self.exchange = ccxt.gateio()

    def check_btc_crash(self):
        """
        Check if Bitcoin dropped > 10% in the last 4 hours.
        Logic: Compare current price against max high of last 4 hourly candles.
        """
        try:
            # Fetch last 5 candles (4 hours + current incomplete candle)
            ohlcv = self.exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=5)
            if not ohlcv:
                logger.warning("Could not fetch BTC/USDT OHLCV data.")
                return False

            # Candles are [timestamp, open, high, low, close, volume]
            # We want the high of the last 4 *completed* candles + current high
            # Actually, just take max high of all fetched candles.
            highs = [candle[2] for candle in ohlcv]
            max_high = max(highs)

            current_price = ohlcv[-1][4] # Close of last candle (current price)

            if max_high == 0:
                return False

            drop = (max_high - current_price) / max_high

            if drop > 0.10:
                logger.warning(f"BTC Crash Detected! Drop: {drop:.2%}, Max High: {max_high}, Current: {current_price}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking BTC crash: {e}")
            return False

    def check_drawdown(self):
        """
        Check if Account Drawdown > 5% in the last hour.
        """
        try:
            # Fetch current balance
            balance_data = self.client.balance()
            if not balance_data:
                logger.warning("Could not fetch balance data.")
                return False

            # Assuming 'total' is the total balance in stake currency or USDT
            # The structure of balance() response depends on Freqtrade version.
            # Usually it returns a dict with 'currencies' list and 'total' (total in quote currency)
            # We'll use 'total' from the response if available, or sum 'total' of currencies.

            current_balance = balance_data.get('total')

            # If total is missing or 0 (which might happen if structure is different), try to calculate
            if current_balance is None or current_balance == 0:
                 currencies = balance_data.get('currencies', [])
                 if currencies:
                     # Some versions return list of dicts
                     # We might need to know the stake currency to sum correctly, or just trust 'total'
                     # If 'total' is present but 0, maybe account is empty.
                     pass

            if current_balance is None:
                logger.warning("Could not determine total balance.")
                return False

            now = datetime.now()
            self.balance_history.append((now, current_balance))

            # Prune history older than 1 hour
            one_hour_ago = now - timedelta(hours=1)
            self.balance_history = [x for x in self.balance_history if x[0] > one_hour_ago]

            if not self.balance_history:
                return False

            max_balance_last_hour = max(x[1] for x in self.balance_history)

            if max_balance_last_hour == 0:
                return False

            drawdown = (max_balance_last_hour - current_balance) / max_balance_last_hour

            if drawdown > 0.05:
                logger.warning(f"Drawdown Detected! Drawdown: {drawdown:.2%}, Max Balance (1h): {max_balance_last_hour}, Current: {current_balance}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking drawdown: {e}")
            return False

    def emergency_action(self, reason):
        """
        Execute emergency actions: Stop bot, Liquidate (optional), Alert.
        """
        logger.critical(f"EMERGENCY ACTION TRIGGERED: {reason}")

        if self.dry_run:
            logger.info("[DRY-RUN] Would have stopped bot and liquidated.")
            return

        # 1. Alert (Placeholder for OpenClaw)
        self.send_alert(f"CRITICAL ALERT: {reason}. Stopping Bot.")

        # 2. Liquidate (Optional)
        if self.liquidate_on_crash:
            logger.info("Liquidating all positions...")
            try:
                # Get open trades to verify
                trades = self.client.status()
                if trades:
                    for trade in trades:
                        trade_id = trade['trade_id']
                        logger.info(f"Force exiting trade {trade_id}")
                        self.client.forceexit(trade_id)
            except Exception as e:
                logger.error(f"Error liquidating positions: {e}")

        # 3. Kill Switch
        logger.info("Stopping Freqtrade...")
        try:
            self.client.stop()
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")

        # Exit script
        sys.exit(0)

    def send_alert(self, message):
        """
        Send alert via OpenClaw (Placeholder).
        """
        logger.info(f"Sending Alert: {message}")
        # TODO: Implement OpenClaw integration here
        # Example: requests.post("https://api.openclaw.com/send", json={"message": message})
        pass

    def run(self):
        logger.info("Sentinel started. Monitoring...")
        while True:
            try:
                # Check BTC Crash
                if self.check_btc_crash():
                    self.emergency_action("Bitcoin Crash > 10% in 4h")

                # Check Drawdown
                if self.check_drawdown():
                    self.emergency_action("Account Drawdown > 5% in 1h")

                # Sleep 5 minutes
                time.sleep(300)

            except KeyboardInterrupt:
                logger.info("Sentinel stopped by user.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in monitor loop: {e}")
                time.sleep(60) # Retry after 1 min on error

def main():
    parser = argparse.ArgumentParser(description="Sentinel - Circuit Breaker for Freqtrade")
    parser.add_argument("-c", "--config", required=True, help="Path to config file")
    parser.add_argument("--liquidate", action="store_true", help="Liquidate all positions on trigger")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without executing them")

    args = parser.parse_args()

    sentinel = Sentinel(args.config, args.liquidate, args.dry_run)
    sentinel.run()

if __name__ == "__main__":
    main()
