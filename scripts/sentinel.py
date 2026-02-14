#!/usr/bin/env python3
"""
The "Sentinel" (Circuit Breaker)
Monitor: Check the live logs every 5 minutes.
Emergency Rule: IF Drawdown > 5% in the last hour OR Bitcoin drops > 10% in 4 hours:
    - Kill Switch: Immediately runs freqtrade stop.
    - Liquidation: (Optional) Panic sell all positions to USDT.
    - Alert: Send a 'CRITICAL ALERT' message to my WhatsApp via OpenClaw.
Resume: Do not restart trading until I manually approve it.
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import ccxt
from freqtrade_client.ft_rest_client import FtRestClient


# Configuration
# Default config to check if user_data/config.json is missing
CONFIG_PATH = Path("user_data/configs/config.delta.dryrun.json")
SENTINEL_STATE_FILE = Path("user_data/sentinel_state.json")

logger = logging.getLogger("sentinel")


def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


def load_config(config_path):
    with Path(config_path).open() as f:
        try:
            import rapidjson

            return rapidjson.load(
                f, parse_mode=rapidjson.PM_COMMENTS | rapidjson.PM_TRAILING_COMMAS
            )
        except ImportError:
            return json.load(f)


def get_rpc_client(config):
    api_config = config.get("api_server", {})
    if not api_config.get("enabled", False):
        logger.error("API Server not enabled in config.")
        sys.exit(1)

    ip = api_config.get("listen_ip_address", "127.0.0.1")
    port = api_config.get("listen_port", 8080)
    server_url = f"http://{ip}:{port}"
    username = api_config.get("username")
    password = api_config.get("password")

    return FtRestClient(server_url, username, password)


def send_alert(message):
    logger.critical(f"ALERT: {message}")
    openclaw_url = os.getenv("OPENCLAW_URL")
    if openclaw_url:
        try:
            import requests

            requests.post(
                openclaw_url, json={"message": message, "priority": "critical"}, timeout=10
            )
        except Exception as e:
            logger.error(f"Failed to send OpenClaw alert: {e}")
    else:
        logger.warning("OpenClaw URL not configured. (Set OPENCLAW_URL env var)")


def load_state():
    if SENTINEL_STATE_FILE.exists():
        try:
            with SENTINEL_STATE_FILE.open() as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {"balance_history": []}
    return {"balance_history": []}


def save_state(state):
    # Ensure directory exists
    SENTINEL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SENTINEL_STATE_FILE.open("w") as f:
        json.dump(state, f)


def check_drawdown(client, state):
    try:
        balance_data = client.balance()
        if not isinstance(balance_data, dict) or "total" not in balance_data:
            logger.error(f"Invalid balance response: {balance_data}")
            return False

        current_balance = balance_data.get("total")

        now_ts = time.time()
        state["balance_history"].append({"ts": now_ts, "balance": current_balance})

        cutoff = now_ts - 3600
        state["balance_history"] = [
            x for x in state["balance_history"] if x["ts"] >= cutoff
        ]

        save_state(state)

        if not state["balance_history"]:
            return False

        max_balance = max(x["balance"] for x in state["balance_history"])
        if max_balance == 0:
            return False

        drawdown = (max_balance - current_balance) / max_balance

        if drawdown > 0.05:
            return (
                f"Drawdown {drawdown * 100:.2f}% > 5% in last hour "
                f"(Max: {max_balance}, Curr: {current_balance})"
            )

        return False
    except Exception as e:
        logger.error(f"Error checking drawdown: {e}")
        return False


def check_btc_crash():
    try:
        exchange = ccxt.gateio()
        ohlcv = exchange.fetch_ohlcv("BTC/USDT", "1h", limit=5)
        if not ohlcv:
            logger.warning("No OHLCV data returned for BTC/USDT")
            return False

        current_close = ohlcv[-1][4]

        recent_candles = ohlcv
        max_high = max(c[2] for c in recent_candles)

        if max_high == 0:
            return False

        drop = (max_high - current_close) / max_high

        if drop > 0.10:
            return (
                f"Bitcoin drop {drop * 100:.2f}% > 10% in 4 hours "
                f"(High: {max_high}, Curr: {current_close})"
            )

        return False

    except Exception as e:
        logger.error(f"Error checking BTC price: {e}")
        return False


def emergency_liquidate(client):
    if os.getenv("SENTINEL_PANIC_SELL", "false").lower() == "true":
        logger.warning("Liquidating all positions...")
        trades = client.status()
        if isinstance(trades, list):
            for trade in trades:
                logger.info(f"Force exiting trade {trade['trade_id']}")
                client.forceexit(trade["trade_id"])

            # Wait for orders to be processed before stopping
            logger.info("Waiting for liquidation orders to be processed...")
            time.sleep(5)
        else:
            logger.error("Failed to get trades list for liquidation")


def run_once(config, client, state):
    """
    Runs a single check iteration.
    Returns True if an emergency action was taken (Sentinel triggered), False otherwise.
    """
    logger.info("Sentinel checking status...")

    try:
        ping = client.ping()
        if ping.get("status") != "pong":
            logger.info("Freqtrade not running (ping failed).")
            return False
    except Exception as e:
        logger.warning(f"Freqtrade not reachable ({e}).")
        return False

    reason = None

    dd_reason = check_drawdown(client, state)
    if dd_reason:
        reason = dd_reason

    if not reason:
        btc_reason = check_btc_crash()
        if btc_reason:
            reason = btc_reason

    if reason:
        msg = f"CRITICAL ALERT: {reason}. ENGAGING KILL SWITCH."
        send_alert(msg)

        try:
            emergency_liquidate(client)
            client.stop()
            logger.info("Freqtrade stopped.")
            return True
        except Exception as e:
            logger.error(f"Failed to execute kill switch: {e}")
            return True

    else:
        logger.info("All clear.")
        return False


def load_and_validate_config(config_arg):
    config_file = config_arg
    if not config_file:
        default_config = Path("user_data/config.json")
        if default_config.exists():
            config_file = default_config
        elif CONFIG_PATH.exists():
            logger.info(f"{default_config} not found, checking fallback {CONFIG_PATH}")
            config_file = CONFIG_PATH
        else:
            logger.error(f"No config file found at {default_config} or {CONFIG_PATH}")
            sys.exit(1)

    if not config_file.exists():
        logger.error(f"Config file not found at {config_file}")
        sys.exit(1)
    return config_file


def main():
    parser = argparse.ArgumentParser(description="Sentinel: Freqtrade Circuit Breaker")
    parser.add_argument("--config", type=Path, help="Path to config file")
    parser.add_argument("--oneshot", action="store_true", help="Run once and exit")
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Check interval in seconds (default: 300)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    setup_logging(args.verbose)

    config_file = load_and_validate_config(args.config)

    try:
        config = load_config(config_file)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)

    client = get_rpc_client(config)
    state = load_state()

    if args.oneshot:
        run_once(config, client, state)
    else:
        logger.info(f"Starting Sentinel loop (Interval: {args.interval}s)")
        while True:
            triggered = run_once(config, client, state)
            if triggered:
                logger.info("Emergency action taken. Sentinel stopping loop.")
                sys.exit(0)
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
