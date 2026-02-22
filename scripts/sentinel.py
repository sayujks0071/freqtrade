#!/usr/bin/env python3
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add ft_client to sys.path
sys.path.append(str(Path(__file__).parent.parent / "ft_client"))
try:
    from freqtrade_client.ft_rest_client import FtRestClient
except ImportError:
    print("Could not import FtRestClient. Make sure ft_client is in the path.")
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

STATE_FILE = Path("user_data/sentinel_state.json")
# Default config, can be overridden or logic improved to find active config
CONFIG_FILE = Path("user_data/configs/config.delta.live.json")


def load_config():
    if not CONFIG_FILE.exists():
        logger.error(f"Config file not found: {CONFIG_FILE}")
        sys.exit(1)
    with CONFIG_FILE.open() as f:
        return json.load(f)


def load_state():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open() as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning("State file corrupted, starting fresh.")
    return {"balance_history": [], "btc_history": []}


def save_state(state):
    with STATE_FILE.open("w") as f:
        json.dump(state, f)


def get_btc_price():
    try:
        import ccxt
        exchange = ccxt.kraken()  # Reliable public API
        ticker = exchange.fetch_ticker("BTC/USDT")
        return ticker["last"]
    except Exception as e:
        logger.error(f"Error fetching BTC price: {e}")
        return None


def prune_history(history, max_age_seconds):
    # Use datetime.UTC if available (Python 3.11+), otherwise datetime.timezone.utc
    utc_tz = getattr(datetime, 'UTC', timezone.utc)
    now = datetime.now(utc_tz).timestamp()
    return [entry for entry in history if now - entry["timestamp"] < max_age_seconds]


def check_drawdown(history, current_value, threshold, window_seconds):
    # History is list of {"timestamp": ts, "value": val}
    # Check drop from MAX in window
    if not history:
        return False

    # Prune first to ensure we only look at the window
    relevant = prune_history(history, window_seconds)
    if not relevant:
        return False

    max_val = max(entry["value"] for entry in relevant)
    if max_val == 0:
        return False

    drawdown = (current_value - max_val) / max_val
    return drawdown < threshold


def send_alert(message):
    logger.critical(f"ALERT: {message}")
    # Placeholder for OpenClaw / Webhook
    webhook_url = os.environ.get("OPENCLAW_URL")
    if webhook_url:
        try:
            import requests
            requests.post(webhook_url, json={"text": message}, timeout=10)
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")


def execute_emergency_measures(client):
    """Executes liquidation and stops the bot."""
    # Liquidation
    logger.info("Panic selling all positions...")
    try:
        trades = client.status()  # Returns list of open trades
        if isinstance(trades, list):
            for trade in trades:
                trade_id = trade.get("trade_id")
                if trade_id:
                    logger.info(f"Force exiting trade {trade_id}")
                    try:
                        client.forceexit(trade_id)
                    except Exception as e:
                        logger.error(f"Failed to exit trade {trade_id}: {e}")
        else:
            logger.error("Unexpected response from client.status()")
    except Exception as e:
        logger.error(f"Failed to get trades for liquidation: {e}")

    # Kill Switch
    logger.info("Stopping Freqtrade...")
    try:
        client.stop()
    except Exception as e:
        logger.error(f"Failed to stop bot: {e}")

    logger.info("Sentinel triggered and executed protective measures. Exiting.")
    sys.exit(0)


def monitor_loop(client, state):
    """Single iteration of monitoring logic."""
    # 1. Check Balance
    try:
        balance_data = client.balance()
        # Freqtrade balance response has "value" for total estimated value in stake currency
        current_balance = balance_data.get("value", 0.0)
    except Exception as e:
        logger.error(f"Failed to fetch balance: {e}")
        current_balance = 0.0

    # 2. Check BTC
    current_btc = get_btc_price()

    utc_tz = getattr(datetime, 'UTC', timezone.utc)
    now_ts = datetime.now(utc_tz).timestamp()

    # Update State
    if current_balance > 0:
        state["balance_history"].append({"timestamp": now_ts, "value": current_balance})
    if current_btc:
        state["btc_history"].append({"timestamp": now_ts, "value": current_btc})

    # Prune
    state["balance_history"] = prune_history(state["balance_history"], 3600 * 4)  # Keep 4h
    state["btc_history"] = prune_history(state["btc_history"], 3600 * 4)

    save_state(state)

    # Check Triggers
    triggered = False
    reason = ""

    # Drawdown > 5% in 1h
    if check_drawdown(state["balance_history"], current_balance, -0.05, 3600):
        triggered = True
        reason = f"Drawdown > 5% in last hour! Current: {current_balance}"

    # BTC Drop > 10% in 4h
    if current_btc and check_drawdown(state["btc_history"], current_btc, -0.10, 3600 * 4):
        triggered = True
        reason = f"Bitcoin crash > 10% in last 4 hours! Current: {current_btc}"

    if triggered:
        send_alert(f"CRITICAL ALERT: {reason}")
        execute_emergency_measures(client)

    logger.info(f"Status Normal. Balance: {current_balance:.2f}, BTC: {current_btc}")


def main():
    logger.info("Sentinel starting...")
    config = load_config()
    api_config = config.get("api_server", {})

    # Default to localhost if not specified
    ip = api_config.get('listen_ip_address', '127.0.0.1')
    port = api_config.get('listen_port', 8080)
    url = f"http://{ip}:{port}"
    user = api_config.get("username")
    password = api_config.get("password")

    client = FtRestClient(url, username=user, password=password)

    state = load_state()

    while True:
        try:
            monitor_loop(client, state)
            time.sleep(300)  # 5 minutes
        except KeyboardInterrupt:
            logger.info("Sentinel stopped by user.")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Error in Sentinel loop: {e}")
            time.sleep(60)  # Retry after 1 minute on error


if __name__ == "__main__":
    main()
