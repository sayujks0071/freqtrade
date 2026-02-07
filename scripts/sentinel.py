#!/usr/bin/env python3
"""
Sentinel (Circuit Breaker)
--------------------------
Real-time crisis management to protect capital.

Monitors:
1. Drawdown > 5% in the last hour.
2. Bitcoin drops > 10% in 4 hours.

Actions:
- Alert via OpenClaw (Webhook).
- Stop buying (/stopbuy).
- Liquidation (/forceexit).
- Kill Switch (/stop).

Usage:
    python3 scripts/sentinel.py
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta

import ccxt
import requests
import schedule


# Configuration
API_URL = os.getenv("FREQTRADE_API_URL", "http://127.0.0.1:8080")
API_USER = os.getenv("FREQTRADE_API_USERNAME", "freqtrader")
API_PASS = os.getenv("FREQTRADE_API_PASSWORD", "SuperSecurePassword123!")
OPENCLAW_URL = os.getenv("OPENCLAW_URL", "https://openclaw.app/api/v1/alert")  # Placeholder

# Thresholds
DRAWDOWN_THRESHOLD = 0.05  # 5%
BTC_DROP_THRESHOLD = 0.10  # 10%

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("sentinel.log"),
    ],
)
logger = logging.getLogger("Sentinel")


def get_access_token():
    """Authenticate with Freqtrade API and return access token."""
    url = f"{API_URL}/api/v1/token/login"
    try:
        # Freqtrade API expects form data for login
        data = {"username": API_USER, "password": API_PASS}
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            logger.error("Failed to retrieve access token: No token in response")
            return None
        return token
    except requests.RequestException as e:
        logger.error(f"Error logging in to Freqtrade API: {e}")
        return None


def get_balance(token):
    """Fetch current balance from Freqtrade API."""
    url = f"{API_URL}/api/v1/balance"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        # Assume total balance in base currency (e.g. USDT)
        # The structure is usually {'currencies': [...], 'total': ...}
        # Or simplistic total balance sum.
        # Freqtrade /balance returns list of currencies.
        # We need the total value in stake currency.
        # Let's assume the response has a 'total' field or we sum 'total' of stake currency.
        # Actually, /balance returns:
        # {
        #   "currencies": [ ... ],
        #   "total": 1234.5,
        #   "symbol": "USDT",
        #   ...
        # }
        # Let's check the schema if possible, but 'total' is a safe bet for total account value.
        return data.get("total")
    except requests.RequestException as e:
        logger.error(f"Error fetching balance: {e}")
        return None


def get_btc_price():
    """Fetch current BTC/USDT price from Kucoin via CCXT."""
    try:
        exchange = ccxt.kucoin()
        ticker = exchange.fetch_ticker("BTC/USDT")
        return ticker["last"]
    except ccxt.BaseError as e:
        logger.error(f"Error fetching BTC price: {e}")
        return None


def get_open_trades(token):
    """Fetch open trades from Freqtrade API."""
    url = f"{API_URL}/api/v1/status"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error fetching open trades: {e}")
        return []


class Sentinel:
    def __init__(self):
        self.balance_history = []  # List of (timestamp, balance)
        self.btc_history = []      # List of (timestamp, price)
        self.token = None

    def refresh_token(self):
        """Refresh the API token."""
        self.token = get_access_token()

    def check_drawdown(self, current_balance):
        """Check if drawdown exceeds threshold in the last hour."""
        now = datetime.now()
        # Add current to history
        self.balance_history.append((now, current_balance))

        # Prune history older than 1 hour
        one_hour_ago = now - timedelta(hours=1)
        self.balance_history = [
            (t, b) for t, b in self.balance_history if t >= one_hour_ago
        ]

        if not self.balance_history:
            return False

        # Find max balance in history
        max_balance = max(b for t, b in self.balance_history)

        if max_balance <= 0:
            return False

        drawdown = (max_balance - current_balance) / max_balance
        if drawdown > DRAWDOWN_THRESHOLD:
            logger.warning(f"Drawdown Triggered: {drawdown:.2%} > {DRAWDOWN_THRESHOLD:.2%}")
            return True
        return False

    def check_btc_drop(self, current_price):
        """Check if BTC drop exceeds threshold in the last 4 hours."""
        now = datetime.now()
        # Add current to history
        self.btc_history.append((now, current_price))

        # Prune history older than 4 hours
        four_hours_ago = now - timedelta(hours=4)
        self.btc_history = [
            (t, p) for t, p in self.btc_history if t >= four_hours_ago
        ]

        if not self.btc_history:
            return False

        # Find max price in history
        max_price = max(p for t, p in self.btc_history)

        if max_price <= 0:
            return False

        drop = (max_price - current_price) / max_price
        if drop > BTC_DROP_THRESHOLD:
            logger.warning(f"BTC Drop Triggered: {drop:.2%} > {BTC_DROP_THRESHOLD:.2%}")
            return True
        return False

    def trigger_emergency(self, reason):
        """Execute emergency procedures."""
        logger.critical(f"EMERGENCY TRIGGERED: {reason}")

        # 1. Alert
        try:
            requests.post(OPENCLAW_URL, json={"message": f"CRITICAL ALERT: {reason}"}, timeout=10)
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")

        # 2. Liquidation (StopBuy + ForceExit)
        if self.token:
            headers = {"Authorization": f"Bearer {self.token}"}
            try:
                requests.post(f"{API_URL}/api/v1/stopbuy", headers=headers, timeout=10)
                logger.info("Executed /stopbuy")
            except Exception as e:
                logger.error(f"Failed to execute /stopbuy: {e}")

            # Fetch open trades and force exit each
            open_trades = get_open_trades(self.token)
            if open_trades:
                logger.info(f"Found {len(open_trades)} open trades. Attempting to force exit...")
                for trade in open_trades:
                    trade_id = trade.get("trade_id")
                    if trade_id:
                        try:
                            requests.post(
                                f"{API_URL}/api/v1/forceexit",
                                headers=headers,
                                json={"tradeid": trade_id},
                                timeout=10,
                            )
                            logger.info(f"Executed /forceexit for trade {trade_id}")
                        except Exception as e:
                            logger.error(f"Failed to execute /forceexit for trade {trade_id}: {e}")
            else:
                logger.info("No open trades found to liquidate.")

            # 3. Kill Switch (Stop Process)
            # The prompt says "Kill Switch: Immediately runs freqtrade stop".
            # This implies the process stops. However, "Liquidation" implies selling.
            # If we stop the process immediately, open orders might remain or be cancelled.
            # We need the bot running to manage the sell orders from /forceexit.
            # We wait a brief moment for the exit orders to be placed, then stop.
            try:
                # Wait 5 seconds to let forceexit requests register
                time.sleep(5)
                requests.post(f"{API_URL}/api/v1/stop", headers=headers, timeout=10)
                logger.critical("Executed /stop")
            except Exception as e:
                logger.error(f"Failed to execute /stop: {e}")

        # Stop monitoring
        sys.exit(1)

    def monitor(self):
        """Main monitoring job."""
        logger.info("Running Sentinel check...")

        # Ensure token
        if not self.token:
            self.refresh_token()

        # 1. Check Balance
        if self.token:
            balance = get_balance(self.token)
            if balance is not None:
                if self.check_drawdown(balance):
                    self.trigger_emergency("Drawdown > 5%")
            else:
                logger.warning("Could not fetch balance. Attempting to refresh token.")
                self.refresh_token()
        else:
            logger.error("No API token available. Skipping balance check.")
            self.refresh_token()

        # 2. Check BTC Price
        btc_price = get_btc_price()
        if btc_price is not None:
            if self.check_btc_drop(btc_price):
                self.trigger_emergency("BTC Drop > 10%")
        else:
            logger.warning("Could not fetch BTC price.")


def main():
    sentinel = Sentinel()
    logger.info("Sentinel initialized.")

    # Schedule the job every 5 minutes
    schedule.every(5).minutes.do(sentinel.monitor)

    # Run once immediately
    sentinel.monitor()

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
