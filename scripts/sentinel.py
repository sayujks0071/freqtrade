#!/usr/bin/env python3
"""
Sentinel (Circuit Breaker) Script
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

import ccxt
import requests


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


# Helper to read from env or config
def get_env_var(name, default=None):
    return os.environ.get(name, default)


# Freqtrade API Connection
FREQTRADE_API_URL = get_env_var("FREQTRADE_API_URL", "http://127.0.0.1:8080")
FREQTRADE_API_USERNAME = get_env_var("FREQTRADE_API_USERNAME", "freqtrader")
FREQTRADE_API_PASSWORD = get_env_var("FREQTRADE_API_PASSWORD", "SuperSecurePassword123!")

# OpenClaw / Alerting
OPENCLAW_URL = get_env_var("OPENCLAW_URL", "https://api.openclaw.com/v1/send")  # Example URL
OPENCLAW_TOKEN = get_env_var("OPENCLAW_TOKEN", "")
WHATSAPP_NUMBER = get_env_var("WHATSAPP_NUMBER", "")

# Thresholds
DRAWDOWN_THRESHOLD_PCT = 5.0  # 5%
BTC_DROP_THRESHOLD_PCT = 10.0  # 10%
BTC_DROP_TIMEFRAME_HOURS = 4

# Exchange for Market Data (BTC check)
EXCHANGE_ID = "gate"  # Using Gate.io for market data check
# Gate.io futures or spot. Using spot for global check is fine too, but futures more liquid.
MARKET_SYMBOL = "BTC/USDT:USDT"

# State persistence
STATE_FILE = Path("user_data/sentinel_state.json")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("user_data/logs/sentinel.log"),
    ],
)
logger = logging.getLogger("Sentinel")


# ---------------------------------------------------------------------------
# Freqtrade API Client
# ---------------------------------------------------------------------------


class FreqtradeClient:
    def __init__(self, url, username, password):
        self.url = url
        self.username = username
        self.password = password
        self.access_token = None
        self.session = requests.Session()

    def login(self):
        """
        Logs in to Freqtrade API to get an access token.
        """
        auth_data = {"username": self.username, "password": self.password}
        try:
            resp = self.session.post(f"{self.url}/api/v1/token/login", data=auth_data, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self.access_token = data.get("access_token")
            logger.info("Successfully logged in to Freqtrade API.")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Error logging in to Freqtrade API: {e}")
            return False

    def _get_headers(self):
        if not self.access_token:
            return {}
        return {"Authorization": f"Bearer {self.access_token}"}

    def _request(self, method, endpoint, **kwargs):
        """
        Wrapper for requests to handle token expiration/login.
        """
        if not self.access_token:
            if not self.login():
                return None

        url = f"{self.url}/api/v1/{endpoint}"
        headers = self._get_headers()

        # Merge headers if provided in kwargs
        if "headers" in kwargs:
            headers.update(kwargs["headers"])
            del kwargs["headers"]

        try:
            resp = self.session.request(method, url, headers=headers, **kwargs)
            if resp.status_code == 401:
                logger.warning("Token expired or invalid. Re-logging in...")
                if self.login():
                    # Retry request with new token
                    headers = self._get_headers()
                    resp = self.session.request(method, url, headers=headers, **kwargs)
                else:
                    return None

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling Freqtrade API ({endpoint}): {e}")
            return None

    def get_balance(self):
        return self._request("GET", "balance")

    def get_status(self):
        return self._request("GET", "status")

    def stop_bot(self):
        return self._request("POST", "stop")

    def start_bot(self):
        return self._request("POST", "start")

    def kill_switch(self):
        """Stops the bot immediately."""
        logger.warning("Executing KILL SWITCH...")
        return self.stop_bot()


# ---------------------------------------------------------------------------
# Market Data Client
# ---------------------------------------------------------------------------


class MarketData:
    def __init__(self, exchange_id="gate"):
        try:
            self.exchange = getattr(ccxt, exchange_id)()
        except Exception as e:
            logger.error(f"Error initializing CCXT exchange {exchange_id}: {e}")
            self.exchange = None

    def get_price_drop(self, symbol, hours=4):
        if not self.exchange:
            return 0.0

        try:
            # Fetch OHLCV for the lookback period
            # We need the open price from 'hours' ago and current price
            # 1h candles.
            # We need at least hours+1 candles to get the open of the candle 'hours' ago.
            # If hours=4, we need 5 candles (0, 1, 2, 3, 4).
            # Index -1 is current/latest.
            # Index -5 is 4 hours ago.
            limit = hours + 2
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe="1h", limit=limit)

            if not ohlcv or len(ohlcv) < hours + 1:
                logger.warning("Insufficient OHLCV data to calculate drop.")
                return 0.0

            # Current price (close of last candle or current ticker)
            current_price = ohlcv[-1][4]

            # Price 'hours' ago (Open of the candle 'hours' ago)
            # If we want a 4h window, we compare current price with the Open of the candle 4h ago.
            # Example: 12:00, 13:00, 14:00, 15:00, 16:00 (current)
            # We want price at 12:00.
            # OHLCV list is sorted oldest to newest.
            # If len is 5. -1 is 16:00. -5 is 12:00.
            # So index should be -(hours + 1).

            if len(ohlcv) >= hours + 1:
                # Use -(hours + 1) to get the candle starting 'hours' ago
                past_candle = ohlcv[-(hours + 1)]
                past_open = past_candle[1]  # Open price

                if past_open == 0:
                    return 0.0

                drop_pct = (past_open - current_price) / past_open * 100
                return drop_pct

            return 0.0

        except Exception as e:
            logger.error(f"Error fetching market data: {e}")
            return 0.0


# ---------------------------------------------------------------------------
# Sentinel Logic
# ---------------------------------------------------------------------------


class Sentinel:
    def __init__(self):
        self.ft_client = FreqtradeClient(
            FREQTRADE_API_URL, FREQTRADE_API_USERNAME, FREQTRADE_API_PASSWORD
        )
        self.market = MarketData(EXCHANGE_ID)
        self.state = self.load_state()

    def load_state(self):
        if STATE_FILE.exists():
            try:
                with STATE_FILE.open("r") as f:
                    return json.load(f)
            except Exception:  # noqa: S110
                pass
        return {"balance_history": [], "triggered": False}

    def save_state(self):
        with STATE_FILE.open("w") as f:
            json.dump(self.state, f)

    def update_balance_history(self, current_balance):
        # Store balance with timestamp
        now = time.time()
        history = self.state.get("balance_history", [])

        # Add new record
        history.append({"ts": now, "balance": current_balance})

        # Prune old records (older than 1 hour + buffer)
        cutoff = now - 3600 - 600  # 1h 10m
        history = [x for x in history if x["ts"] > cutoff]

        self.state["balance_history"] = history
        self.save_state()

    def calculate_drawdown(self, current_balance):
        history = self.state.get("balance_history", [])
        if not history:
            return 0.0

        # Max balance in the last hour
        # Filter for last hour
        now = time.time()
        cutoff = now - 3600
        relevant_history = [x for x in history if x["ts"] >= cutoff]

        if not relevant_history:
            return 0.0

        max_balance = max(x["balance"] for x in relevant_history)
        max_balance = max(max_balance, current_balance)  # Compare with current too

        if max_balance == 0:
            return 0.0

        drawdown = (max_balance - current_balance) / max_balance * 100
        return drawdown

    def alert(self, message):
        logger.critical(f"ALERT: {message}")
        print(f"--> SENT ALERT TO WHATSAPP: {message}")

        if not OPENCLAW_URL or not WHATSAPP_NUMBER:
            logger.warning("OpenClaw URL or WhatsApp number not configured. Skipping alert.")
            return

        payload = {"token": OPENCLAW_TOKEN, "to": WHATSAPP_NUMBER, "message": message}
        try:
            resp = requests.post(OPENCLAW_URL, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info("Alert sent successfully via OpenClaw.")
            else:
                logger.error(f"Failed to send alert: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.error(f"Exception sending alert: {e}")

    def run_check(self):
        if self.state.get("triggered"):
            logger.info("Sentinel already triggered. Waiting for manual reset.")
            return

        # 1. Check Drawdown
        balance_data = self.ft_client.get_balance()
        current_balance = None

        if balance_data:
            total_balance = balance_data.get("total")

            if isinstance(total_balance, (int, float)):
                current_balance = float(total_balance)
            elif isinstance(balance_data, dict) and "currencies" in balance_data:
                # Fallback logic if needed, but 'total' should be there for overall balance
                # If we can't determine balance, we MUST skip to avoid false positives.
                pass

        if current_balance is None:
            logger.error(
                "Could not determine current balance from Freqtrade API. Skipping drawdown check."
            )
        else:
            self.update_balance_history(current_balance)
            drawdown = self.calculate_drawdown(current_balance)

            logger.info(f"Current Balance: {current_balance}, 1h Drawdown: {drawdown:.2f}%")

            if drawdown > DRAWDOWN_THRESHOLD_PCT:
                self.trigger_emergency(f"Drawdown {drawdown:.2f}% > {DRAWDOWN_THRESHOLD_PCT}%")
                return

        # 2. Check Bitcoin Drop
        btc_drop = self.market.get_price_drop(MARKET_SYMBOL, BTC_DROP_TIMEFRAME_HOURS)
        logger.info(f"BTC {BTC_DROP_TIMEFRAME_HOURS}h Drop: {btc_drop:.2f}%")

        if btc_drop > BTC_DROP_THRESHOLD_PCT:
            msg = f"Bitcoin dropped {btc_drop:.2f}% in {BTC_DROP_TIMEFRAME_HOURS}h"
            self.trigger_emergency(msg)
            return

    def trigger_emergency(self, reason):
        msg = f"CRITICAL ALERT: Sentinel Triggered! Reason: {reason}"
        self.alert(msg)

        # Kill Switch
        self.ft_client.kill_switch()

        # Optional: Liquidation (Panic Sell)
        # self.ft_client.force_exit_all() # Not implemented in client yet

        # Mark as triggered
        self.state["triggered"] = True
        self.save_state()


def main():
    logger.info("Starting Sentinel...")
    sentinel = Sentinel()
    sentinel.run_check()


if __name__ == "__main__":
    main()
