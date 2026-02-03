#!/usr/bin/env python3
"""
Sentinel (Circuit Breaker) for Freqtrade.
Monitors portfolio drawdown and BTC crashes to trigger emergency stops.

Goal: Real-time crisis management to protect capital.
1. Monitor: Check the live logs (state) every 5 minutes.
2. Emergency Rule: IF Drawdown > 5% in the last hour OR Bitcoin drops > 10% in 4 hours:
    - Kill Switch: Immediately runs freqtrade stop.
    - Liquidation: Panic sell all positions to USDT.
    - Alert: Send a 'CRITICAL ALERT' message to my WhatsApp via OpenClaw.
3. Resume: Do not restart trading until I manually approve it.
"""

import logging
import os
import time
from datetime import UTC, datetime, timedelta

import ccxt
import requests


# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Sentinel")

# Configuration from Environment or Defaults
RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8080/api/v1")
RPC_USER = os.getenv("RPC_USER", "freqtrader")
RPC_PASSWORD = os.getenv("RPC_PASSWORD", "SuperSecurePassword123!")
OPENCLAW_URL = os.getenv("OPENCLAW_URL", "http://localhost:5000/webhook")  # Placeholder
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))  # 5 minutes
DRAWDOWN_THRESHOLD = 0.05  # 5%
BTC_DROP_THRESHOLD = 0.10  # 10%
BTC_PAIR = "BTC/USDT"


class Sentinel:
    def __init__(self):
        self.balance_history: list[tuple[datetime, float]] = []
        self.session = requests.Session()
        self.session.auth = (RPC_USER, RPC_PASSWORD)
        # Use Gate.io as fallback/primary for market data
        self.exchange = ccxt.gateio()

    def get_current_balance(self) -> float | None:
        """Fetch total balance from Freqtrade RPC."""
        try:
            # Let's try to get a token
            if "Authorization" not in self.session.headers:
                resp = self.session.post(f"{RPC_URL}/login", timeout=10)
                if resp.status_code == 200:
                    token = resp.json().get("access_token")
                    self.session.headers.update({"Authorization": f"Bearer {token}"})
                else:
                    logger.error(f"Failed to login to RPC: {resp.text}")
                    return None

            response = self.session.get(f"{RPC_URL}/balance", timeout=10)

            # Handle token expiration
            if response.status_code == 401:
                logger.info("Token expired. Re-authenticating...")
                self.session.headers.pop("Authorization", None)
                return None

            response.raise_for_status()
            data = response.json()
            return float(data.get("total", 0.0))
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return None

    def update_balance_history(self, current_balance: float):
        """Update history and prune entries older than 1 hour."""
        now = datetime.now(UTC)
        self.balance_history.append((now, current_balance))

        # Prune older than 1 hour
        one_hour_ago = now - timedelta(hours=1)
        self.balance_history = [(t, b) for t, b in self.balance_history if t > one_hour_ago]

    def check_drawdown(self, current_balance: float) -> bool:
        """Check if drawdown > 5% in the last hour."""
        if not self.balance_history:
            return False

        # Max balance in the last hour (including current if it's high, but we look for drop)
        # We want the max of previous entries to compare against current.
        max_balance = max(b for t, b in self.balance_history)

        if max_balance == 0:
            return False

        drawdown = (max_balance - current_balance) / max_balance
        if drawdown > DRAWDOWN_THRESHOLD:
            logger.warning(f"Drawdown detected: {drawdown:.2%} (Limit: {DRAWDOWN_THRESHOLD:.2%})")
            return True
        return False

    def check_btc_crash(self) -> bool:
        """Check if BTC drops > 10% in the last 4 hours."""
        try:
            # Fetch OHLCV for 4h timeframe? Or 1h and look back.
            # Using 1h candles, last 5 candles cover 4 hours ago to now.
            ohlcv = self.exchange.fetch_ohlcv(BTC_PAIR, timeframe="1h", limit=5)
            if not ohlcv:
                return False

            current_price = ohlcv[-1][4]  # Close of last candle (current)

            # Find the highest high in the last 4 hours
            # (excluding current candle potentially if it just started)
            # Actually, we want the drop from the high of the window.
            highs = [candle[2] for candle in ohlcv]  # Highs
            max_price = max(highs)

            drop = (max_price - current_price) / max_price
            if drop > BTC_DROP_THRESHOLD:
                logger.warning(f"BTC Crash detected: {drop:.2%} (Limit: {BTC_DROP_THRESHOLD:.2%})")
                return True
            return False
        except Exception as e:
            logger.error(f"Error checking BTC price: {e}")
            return False

    def send_alert(self, message: str):
        """Send alert to OpenClaw (Webhook)."""
        logger.info(f"Sending Alert: {message}")
        try:
            payload = {"message": message, "priority": "critical"}
            requests.post(OPENCLAW_URL, json=payload, timeout=5)
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")

    def trigger_emergency(self, reason: str):
        """Execute emergency procedures."""
        message = f"CRITICAL ALERT: {reason}. Initiating Kill Switch & Liquidation."
        self.send_alert(message)

        # 1. Force Exit (Liquidation)
        try:
            logger.info("Triggering Force Exit...")
            self.session.post(f"{RPC_URL}/forceexit", json={"tradeid": "all"}, timeout=10)
        except Exception as e:
            logger.error(f"Failed to force exit: {e}")

        # 2. Stop Bot (Kill Switch)
        try:
            logger.info("Triggering Stop...")
            self.session.post(f"{RPC_URL}/stop", timeout=10)
        except Exception as e:
            logger.error(f"Failed to stop bot: {e}")

    def run(self):
        logger.info("Sentinel started. Monitoring...")
        # Initial check to populate history
        current_balance = self.get_current_balance()
        if current_balance is not None:
            self.update_balance_history(current_balance)

        while True:
            try:
                # 1. Check Drawdown
                current_balance = self.get_current_balance()
                drawdown_trigger = False
                if current_balance is not None:
                    self.update_balance_history(current_balance)
                    drawdown_trigger = self.check_drawdown(current_balance)
                else:
                    logger.warning("Could not fetch balance. Skipping drawdown check.")

                # 2. Check BTC Crash
                btc_trigger = self.check_btc_crash()

                if drawdown_trigger or btc_trigger:
                    reason = []
                    if drawdown_trigger:
                        reason.append("Drawdown > 5% in 1h")
                    if btc_trigger:
                        reason.append("BTC Drop > 10% in 4h")

                    self.trigger_emergency(" & ".join(reason))

                    # Exit loop or wait for manual intervention?
                    # Prompt says: "Resume: Do not restart trading until I manually approve it."
                    # Since we called /stop, the bot is stopped. The Sentinel can continue running
                    # but maybe shouldn't keep triggering.
                    logger.info("Emergency procedures executed. Sentinel entering standby/exit.")
                    break

            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")

            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    sentinel = Sentinel()
    sentinel.run()
