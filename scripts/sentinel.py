#!/usr/bin/env python3
"""
Sentinel Script
Monitors account drawdown and BTC price drops.
Triggers emergency stop and liquidation if thresholds are breached.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


# Add ft_client to path
# Assuming the script is in scripts/ and ft_client is in ft_client/ (sibling of scripts/ parent)
# scripts/ -> parent is root -> root/ft_client
sys.path.append(str(Path(__file__).parent.parent / "ft_client"))

try:
    from freqtrade_client.ft_rest_client import FtRestClient
except ImportError:
    print("Error: ft_client not found. Please ensure ft_client is in the correct path.")
    sys.exit(1)

try:
    import ccxt
except ImportError:
    print("Error: ccxt not found. Please install it using `pip install ccxt`.")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("user_data/sentinel.log"),
    ],
)
logger = logging.getLogger("Sentinel")

CONFIG_FILES = [
    "user_data/configs/config.delta.live.json",
    "user_data/configs/config_production.json",
    "user_data/config.json",
    "config.json",
]

STATE_FILE = Path("user_data/sentinel_state.json")


def load_config():
    for config_path in CONFIG_FILES:
        path = Path(config_path)
        if path.exists():
            try:
                with path.open("r") as f:
                    try:
                        import rapidjson

                        return rapidjson.load(
                            f, parse_mode=rapidjson.PM_COMMENTS | rapidjson.PM_TRAILING_COMMAS
                        )
                    except ImportError:
                        return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load config {path}: {e}")
    return None


def get_client(config):
    if not config:
        logger.error("No configuration found.")
        sys.exit(1)

    api_config = config.get("api_server", {})
    url = api_config.get("listen_ip_address", "127.0.0.1")
    port = api_config.get("listen_port", "8080")
    username = api_config.get("username")
    password = api_config.get("password")

    server_url = f"http://{url}:{port}"
    return FtRestClient(server_url, username, password)


def load_state():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
    return {"history": []}


def save_state(state):
    try:
        with STATE_FILE.open("w") as f:
            json.dump(state, f)
    except Exception as e:
        logger.error(f"Failed to save state: {e}")


def send_alert(message):
    logger.critical(f"ALERT: {message}")

    # Send to OpenClaw
    openclaw_url = os.environ.get("OPENCLAW_URL", "http://localhost:5000/send")
    try:
        response = requests.post(
            openclaw_url, json={"message": message, "priority": "critical"}, timeout=5
        )
        if response.status_code == 200:
            logger.info("Alert sent to OpenClaw.")
        else:
            logger.warning(f"Failed to send alert to OpenClaw: {response.status_code}")
    except Exception as e:
        logger.warning(f"Failed to connect to OpenClaw: {e}")

    # Also write to a specific alert file
    try:
        with Path("user_data/sentinel_alert.log").open("a") as f:
            f.write(f"{datetime.now(timezone.utc)} - {message}\n")  # noqa: UP017
    except Exception as e:
        logger.error(f"Failed to write alert log: {e}")


def check_drawdown(client, state):
    try:
        balance_data = client.balance()

        # Freqtrade API /balance returns 'total' field with total balance in stake currency
        current_balance = balance_data.get("total")

        if current_balance is None:
            logger.warning("Could not find 'total' in balance response. Skipping drawdown check.")
            return False

        now = datetime.now(timezone.utc).timestamp()  # noqa: UP017
        history = state.get("history", [])

        # Append current
        history.append({"timestamp": now, "balance": current_balance})

        # Prune older than 1 hour (3600 seconds)
        cutoff = now - 3600
        history = [entry for entry in history if entry["timestamp"] >= cutoff]

        state["history"] = history
        save_state(state)

        if not history:
            return False

        # Find max balance in history
        max_balance = max(entry["balance"] for entry in history)

        if max_balance == 0:
            return False

        drawdown = (current_balance - max_balance) / max_balance

        if drawdown < -0.05:
            logger.info(
                f"Drawdown triggered: Current {current_balance}, Max {max_balance}, "
                f"DD {drawdown:.2%}"
            )
            return True

    except Exception as e:
        logger.error(f"Error checking drawdown: {e}")

    return False


def check_btc_drop():
    try:
        # Use Binance via ccxt
        exchange = ccxt.binance()
        # Fetch OHLCV for BTC/USDT. 4 hours = 4 * 60 = 240 minutes.
        # Fetch 1h candles, last 5 candles to cover 4 hours fully
        ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=5)

        if not ohlcv:
            return False

        # ohlcv is list of [timestamp, open, high, low, close, volume]
        highs = [candle[2] for candle in ohlcv]
        max_high = max(highs)

        current_price = ohlcv[-1][4]  # Last close

        drop = (current_price - max_high) / max_high

        if drop < -0.10:
            logger.info(
                f"BTC Drop triggered: Current {current_price}, Max {max_high}, Drop {drop:.2%}"
            )
            return True

    except Exception as e:
        logger.error(f"Error checking BTC drop: {e}")

    return False


def trigger_emergency(client, reason):
    logger.critical(f"EMERGENCY TRIGGERED: {reason}")
    send_alert(f"EMERGENCY TRIGGERED: {reason}")

    # Liquidation
    try:
        logger.info("Liquidating positions...")
        trades = client.status()
        if trades:
            for trade in trades:
                trade_id = trade["trade_id"]
                logger.info(f"Force exiting trade {trade_id}")
                client.forceexit(trade_id)
    except Exception as e:
        logger.error(f"Failed to liquidate: {e}")

    # Kill Switch
    try:
        logger.info("Stopping bot...")
        client.stop()
    except Exception as e:
        logger.error(f"Failed to stop bot: {e}")

    logger.info("Sentinel actions complete. Exiting.")
    sys.exit(0)


def main():
    logger.info("Sentinel started.")
    config = load_config()
    client = get_client(config)

    # Initial verification
    try:
        client.ping()
        logger.info("Connected to Freqtrade API.")
    except Exception as e:
        logger.error(f"Could not connect to Freqtrade API: {e}")
        # Proceed even if API is down initially?
        # If API is down, we can't check drawdown but we can check BTC.
        # But we can't stop the bot via API if API is down.
        pass

    while True:
        try:
            state = load_state()

            # Check drawdown (needs API)
            try:
                if check_drawdown(client, state):
                    trigger_emergency(client, "Drawdown > 5% in 1 hour")
            except Exception as e:
                logger.debug(f"Drawdown check failed: {e}")

            # Check BTC drop (independent)
            if check_btc_drop():
                trigger_emergency(client, "Bitcoin drop > 10% in 4 hours")

            logger.info("Checks passed.")

        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")

        time.sleep(300)


if __name__ == "__main__":
    main()
