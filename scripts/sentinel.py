#!/usr/bin/env python3
"""
Sentinel (Circuit Breaker) Script for Freqtrade
Monitors account drawdown and BTC price drops to trigger emergency stop and liquidation.
"""

import argparse
import base64
import json
import logging
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Sentinel")


class Sentinel:
    def __init__(self, config_path: str, dry_run: bool = False):
        self.config_path = config_path
        self.dry_run = dry_run
        self.config = self._load_config()
        self.api_url = self._get_api_url()
        self.auth_token = None
        self.balance_history: list[tuple[datetime, float]] = []
        self.btc_price_history: list[tuple[datetime, float]] = []

        # Thresholds
        self.drawdown_threshold = 0.05  # 5%
        self.btc_drop_threshold = 0.10  # 10%
        self.monitor_interval = 300  # 5 minutes

        # History windows
        self.balance_window = timedelta(hours=1)
        self.btc_window = timedelta(hours=4)

    def _load_config(self) -> dict[str, Any]:
        try:
            with open(self.config_path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config file: {e}")
            sys.exit(1)

    def _get_api_url(self) -> str:
        api_config = self.config.get("api_server", {})
        if not api_config.get("enabled", False):
            logger.error("API Server is not enabled in configuration.")
            sys.exit(1)

        ip = api_config.get("listen_ip_address", "127.0.0.1")
        if ip == "0.0.0.0":
            ip = "127.0.0.1"
        port = api_config.get("listen_port", 8080)
        return f"http://{ip}:{port}/api/v1"

    def _get_auth_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def _request(
        self, method: str, endpoint: str, data: dict | None = None, auth: bool = True
    ) -> dict[str, Any]:
        url = f"{self.api_url}{endpoint}"
        headers = self._get_auth_headers() if auth else {}

        if endpoint == "/token/login":
            # Use Basic Auth
            api_config = self.config.get("api_server", {})
            username = api_config.get("username")
            password = api_config.get("password")
            auth_str = f"{username}:{password}"
            b64_auth = base64.b64encode(auth_str.encode()).decode()
            headers = {"Authorization": f"Basic {b64_auth}"}

        try:
            if data:
                json_data = json.dumps(data).encode("utf-8")
                headers["Content-Type"] = "application/json"
                req = urllib.request.Request(
                    url, data=json_data, headers=headers, method=method
                )  # noqa: S310
            else:
                req = urllib.request.Request(url, headers=headers, method=method)  # noqa: S310

            with urllib.request.urlopen(req) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401 and auth and endpoint != "/token/login":
                logger.info("Token expired, refreshing...")
                self.login()
                return self._request(method, endpoint, data, auth)
            logger.error(f"HTTP Error {e.code}: {e.reason}")
            try:
                logger.error(e.read().decode())
            except Exception:
                pass
            raise
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise

    def login(self):
        try:
            response = self._request("POST", "/token/login", auth=False)
            self.auth_token = response.get("access_token")
            logger.info("Successfully authenticated with Freqtrade API")
        except Exception as e:
            logger.error(f"Login failed: {e}")
            if not self.dry_run:
                sys.exit(1)

    def get_balance(self) -> float:
        """Returns total USDT value of the account (balance + open positions)"""
        try:
            data = self._request("GET", "/balance")
            # API response: {"total": 1234.5, "symbol": "USDT", ...}
            return float(data.get("total", 0.0))
        except Exception:
            return 0.0

    def get_btc_price(self) -> float:
        """Returns current BTC price from Freqtrade API"""
        stake_currency = self.config.get("stake_currency", "USDT")
        pair = f"BTC/{stake_currency}"

        # Try /pair_candles first (lightweight) if whitelisted
        try:
            query = urllib.parse.urlencode({"pair": pair, "timeframe": "1h", "limit": 1})
            data = self._request("GET", f"/pair_candles?{query}")
            if data and "data" in data and len(data["data"]) > 0:
                return float(data["data"][-1][4])
        except Exception:
            pass

        # Try /pair_history with live_mode=True
        try:
            # Need to get strategy name if not in config
            strategy = self.config.get("strategy")
            if not strategy:
                # Attempt to fetch from config
                try:
                    config_resp = self._request("GET", "/show_config")
                    strategy = config_resp.get("strategy")
                except Exception:
                    pass

            if not strategy:
                logger.warning("Strategy not found for pair_history call.")
                return 0.0

            payload = {
                "pair": pair,
                "timeframe": "1h",
                "timerange": f"{datetime.now().strftime('%Y%m%d')}-",
                "strategy": strategy,
                "live_mode": True
            }

            data = self._request("POST", "/pair_history", data=payload)
            if data and "data" in data and len(data["data"]) > 0:
                return float(data["data"][-1][4])
        except Exception as e:
            logger.warning(f"Failed to fetch BTC price: {e}")
            return 0.0

        return 0.0

    def check_drawdown(self, current_balance: float) -> bool:
        if current_balance <= 0:
            return False

        now = datetime.now()
        self.balance_history.append((now, current_balance))

        # Prune old history
        self.balance_history = [
            (t, b) for t, b in self.balance_history if now - t <= self.balance_window
        ]

        if not self.balance_history:
            return False

        max_balance = max(b for t, b in self.balance_history)
        if max_balance == 0:
            return False

        drawdown = (max_balance - current_balance) / max_balance
        if drawdown > self.drawdown_threshold:
            logger.warning(
                f"Drawdown Alert: Current {drawdown:.2%} > Threshold {self.drawdown_threshold:.2%}"
            )
            return True
        return False

    def check_btc_drop(self, current_price: float) -> bool:
        if current_price <= 0:
            return False

        now = datetime.now()
        self.btc_price_history.append((now, current_price))

        # Prune old history
        self.btc_price_history = [
            (t, p) for t, p in self.btc_price_history if now - t <= self.btc_window
        ]

        if not self.btc_price_history:
            return False

        max_price = max(p for t, p in self.btc_price_history)
        if max_price == 0:
            return False

        drop = (max_price - current_price) / max_price
        if drop > self.btc_drop_threshold:
            logger.warning(
                f"BTC Drop Alert: Current {drop:.2%} > Threshold {self.btc_drop_threshold:.2%}"
            )
            return True
        return False

    def emergency_stop(self):
        logger.critical("TRIGGERING EMERGENCY STOP!")
        if self.dry_run:
            logger.info("[DRY RUN] Would call /stop")
            return

        try:
            self._request("POST", "/stop")
            logger.info("Bot stopped successfully.")
        except Exception as e:
            logger.error(f"Failed to stop bot: {e}")

    def emergency_liquidate(self):
        logger.critical("TRIGGERING EMERGENCY LIQUIDATION!")
        if self.dry_run:
            logger.info("[DRY RUN] Would call /forceexit trade_id='all'")
            return

        try:
            self._request("POST", "/forceexit", data={"tradeid": "all"})
            logger.info("Liquidation request sent.")
        except Exception as e:
            logger.error(f"Failed to liquidate: {e}")

    def run(self):
        logger.info(f"Starting Sentinel (Dry Run: {self.dry_run})")
        logger.info(
            f"Monitoring: Drawdown > {self.drawdown_threshold:.0%}, "
            f"BTC Drop > {self.btc_drop_threshold:.0%}"
        )

        if not self.dry_run:
            self.login()
        else:
            # Try login but don't fail hard if dry-run (e.g. testing logic without running bot)
            try:
                self.login()
            except SystemExit:
                logger.warning(
                    "[DRY RUN] Login failed. Proceeding with mock data or limited functionality."
                )

        while True:
            try:
                # 1. Check Balance
                balance = self.get_balance()
                logger.info(f"Current Balance: {balance:.2f}")

                # 2. Check BTC Price
                btc_price = self.get_btc_price()
                logger.info(f"Current BTC Price: {btc_price:.2f}")

                # 3. Evaluate Rules
                drawdown_alert = self.check_drawdown(balance)
                btc_alert = self.check_btc_drop(btc_price)

                if drawdown_alert or btc_alert:
                    reason = "Drawdown" if drawdown_alert else "BTC Drop"
                    logger.critical(f"EMERGENCY TRIGGERED: {reason}")

                    self.emergency_stop()
                    self.emergency_liquidate()

                    logger.info("Sentinel Actions Complete. Exiting.")
                    break

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")

            logger.info(f"Sleeping for {self.monitor_interval} seconds...")
            time.sleep(self.monitor_interval)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sentinel Circuit Breaker for Freqtrade")
    parser.add_argument(
        "--config",
        default="user_data/configs/config.delta.live.json",
        help="Path to config file",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Run without executing emergency actions"
    )
    args = parser.parse_args()

    sentinel = Sentinel(args.config, args.dry_run)
    sentinel.run()
