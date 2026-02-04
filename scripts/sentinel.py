#!/usr/bin/env python3
import time
import sys
import logging
import argparse
import requests
import ccxt
from collections import deque
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Sentinel")

class Sentinel:
    def __init__(self, rpc_url, rpc_user, rpc_password, webhook_url, check_interval=300):
        self.rpc_url = rpc_url.rstrip('/')
        self.auth = (rpc_user, rpc_password)
        self.webhook_url = webhook_url
        self.check_interval = check_interval

        # History for Drawdown (1 hour window)
        self.balance_history = deque() # (timestamp, balance)

        # History for BTC Crash (4 hour window)
        self.price_history = deque() # (timestamp, price)

        # Initialize Exchange
        self.exchange = ccxt.gateio({'enableRateLimit': True})

        self.tripped = False

    def get_rpc_balance(self):
        try:
            response = requests.get(f"{self.rpc_url}/balance", auth=self.auth, timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Return total balance in stake currency (assuming USDT or similar total)
                # The endpoint returns a dict. 'total' is usually the key for total balance across all currencies in stake currency equivalent.
                # However, Freqtrade /balance response format:
                # { "currencies": [...], "total": 1234.5, ... }
                return data.get('total')
            else:
                logger.error(f"RPC Error: {response.status_code} {response.text}")
                return None
        except Exception as e:
            logger.error(f"RPC Connection Failed: {e}")
            return None

    def get_btc_price(self):
        try:
            ticker = self.exchange.fetch_ticker('BTC/USDT')
            return ticker['last']
        except Exception as e:
            logger.error(f"Exchange Connection Failed: {e}")
            return None

    def update_history(self, current_balance, current_price):
        now = datetime.now()

        # Balance History - 1 Hour
        if current_balance is not None:
            self.balance_history.append((now, current_balance))
            # Remove old
            while self.balance_history and (now - self.balance_history[0][0] > timedelta(hours=1)):
                self.balance_history.popleft()

        # Price History - 4 Hours
        if current_price is not None:
            self.price_history.append((now, current_price))
            # Remove old
            while self.price_history and (now - self.price_history[0][0] > timedelta(hours=4)):
                self.price_history.popleft()

    def check_drawdown(self):
        if not self.balance_history:
            return False, 0.0

        current_balance = self.balance_history[-1][1]
        # Find max balance in the window
        max_balance = max(b for t, b in self.balance_history)

        if max_balance == 0:
            return False, 0.0

        drawdown = (current_balance - max_balance) / max_balance

        if drawdown < -0.05: # > 5% drop
            return True, drawdown
        return False, drawdown

    def check_crash(self):
        if not self.price_history:
            return False, 0.0

        current_price = self.price_history[-1][1]
        # Find max price in the window (High water mark approach)
        max_price = max(p for t, p in self.price_history)

        if max_price == 0:
            return False, 0.0

        drop = (current_price - max_price) / max_price

        if drop < -0.10: # > 10% drop
            return True, drop
        return False, drop

    def trigger_emergency(self, reason):
        logger.critical(f"EMERGENCY TRIGGERED: {reason}")
        self.tripped = True

        # 1. Kill Switch
        try:
            logger.info("Sending /stop to RPC...")
            requests.post(f"{self.rpc_url}/stop", auth=self.auth, timeout=10)
        except Exception as e:
            logger.error(f"Failed to stop bot: {e}")

        # 2. Liquidation
        try:
            logger.info("Sending /forceexit to RPC...")
            requests.post(f"{self.rpc_url}/forceexit", auth=self.auth, timeout=10)
        except Exception as e:
            logger.error(f"Failed to force exit: {e}")

        # 3. Alert
        if self.webhook_url:
            try:
                logger.info("Sending Alert to OpenClaw...")
                requests.post(self.webhook_url, json={"content": f"CRITICAL ALERT: {reason}"}, timeout=10)
            except Exception as e:
                logger.error(f"Failed to send alert: {e}")
        else:
            logger.warning("No Webhook URL provided for alert.")

    def run(self):
        logger.info("Sentinel started. Monitoring...")
        while not self.tripped:
            try:
                balance = self.get_rpc_balance()
                price = self.get_btc_price()

                self.update_history(balance, price)

                # Check Rules
                is_dd, dd_val = self.check_drawdown()
                if is_dd:
                    self.trigger_emergency(f"Drawdown > 5% ({dd_val:.2%})")
                    break

                is_crash, crash_val = self.check_crash()
                if is_crash:
                    self.trigger_emergency(f"Bitcoin Drop > 10% ({crash_val:.2%})")
                    break

                logger.info(f"Status OK. Balance: {balance}, BTC: {price}, DD: {dd_val:.2%}, Drop: {crash_val:.2%}")

            except Exception as e:
                logger.error(f"Error in main loop: {e}")

            time.sleep(self.check_interval)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sentinel Circuit Breaker for Freqtrade")
    parser.add_argument("--rpc-url", default="http://127.0.0.1:8080/api/v1", help="Freqtrade RPC URL")
    parser.add_argument("--rpc-user", default="freqtrader", help="RPC Username")
    parser.add_argument("--rpc-password", default="SuperSecurePassword123!", help="RPC Password")
    parser.add_argument("--webhook-url", help="OpenClaw Webhook URL")
    parser.add_argument("--interval", type=int, default=300, help="Check interval in seconds")

    args = parser.parse_args()

    sentinel = Sentinel(
        args.rpc_url, args.rpc_user, args.rpc_password, args.webhook_url, args.check_interval
    )
    sentinel.run()
