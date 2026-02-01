#!/usr/bin/env python3
"""
Daily Optimization Routine
"""

import sys
import json
import subprocess
import shutil
import csv
import zipfile
from pathlib import Path
from datetime import datetime, timedelta

# Configuration
USER_DATA_DIR = Path("user_data")
BACKTEST_RESULTS_DIR = USER_DATA_DIR / "backtest_results"
STRATEGIES_DIR = USER_DATA_DIR / "strategies"
CONFIG_FILE = USER_DATA_DIR / "configs/config_daily_opt.json"

# Optimization Parameters
EPOCHS = 200
SPACES = ["buy", "roi", "stoploss", "trailing"]
HYPEROPT_LOSS = "SharpeHyperOptLoss"

def run_command(cmd, capture=True):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"Error running command: {result.stderr}")
        if not capture:
             pass
    return result

def get_timerange():
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    return f"{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}"

def get_latest_backtest_file():
    if not BACKTEST_RESULTS_DIR.exists():
        return None
    last_result_file = BACKTEST_RESULTS_DIR / ".last_result.json"
    if last_result_file.exists():
        with open(last_result_file, 'r') as f:
            data = json.load(f)
            filename = data.get('latest_backtest')
            if filename:
                return BACKTEST_RESULTS_DIR / filename

    files = list(BACKTEST_RESULTS_DIR.glob("backtest-result-*.zip"))
    if not files:
        files = list(BACKTEST_RESULTS_DIR.glob("backtest-result-*.json"))

    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)

def read_backtest_result(filepath):
    data = None
    if filepath.suffix == '.zip':
        with zipfile.ZipFile(filepath, 'r') as z:
            json_files = [f for f in z.namelist() if f.endswith('.json')]
            target_file = None
            for f in json_files:
                if 'backtest-result' in f:
                    target_file = f
                    break
            if not target_file and json_files:
                target_file = json_files[0]

            if target_file:
                with z.open(target_file) as f:
                    data = json.load(f)
    else:
        with open(filepath, 'r') as f:
            data = json.load(f)
    return data

def find_worst_strategy(backtest_data):
    strategies = backtest_data.get('strategy', {})
    if not strategies:
        return None, None, None

    worst_strategy = None
    min_sharpe = float('inf')
    worst_stats = None

    for strategy_name, stats in strategies.items():
        sharpe = stats.get('sharpe', -float('inf'))
        if sharpe is None:
             sharpe = -float('inf')

        if sharpe < min_sharpe:
            min_sharpe = sharpe
            worst_strategy = strategy_name
            worst_stats = stats

    return worst_strategy, min_sharpe, worst_stats

def find_available_strategy():
    files = list(STRATEGIES_DIR.glob("*.py"))
    for f in files:
        if f.stem != "__init__" and not f.stem.startswith("_"):
            return f.stem
    return None

def run_backtest_job(strategy_name):
    timerange = get_timerange()
    print(f"Running backtest for {strategy_name} over {timerange}...")
    cmd = [
        "freqtrade", "backtesting",
        "--config", str(CONFIG_FILE),
        "--timerange", timerange,
        "--timeframe", "1h",
        "--cache", "none",
        "--strategy", strategy_name
    ]

    run_command(cmd, capture=True)

    latest = get_latest_backtest_file()
    if latest:
        return read_backtest_result(latest)
    return None

def main():
    # 1. Establish Baseline
    latest_file = get_latest_backtest_file()

    backtest_data = None
    if latest_file:
        print(f"Using latest backtest file: {latest_file}")
        backtest_data = read_backtest_result(latest_file)

    if not backtest_data:
        print("No valid baseline found. Running initial backtest...")
        fallback_strategy = find_available_strategy()
        if not fallback_strategy:
            print("No strategy file found.")
            sys.exit(1)
        backtest_data = run_backtest_job(fallback_strategy)

    if not backtest_data:
        print("Failed to produce backtest baseline.")
        sys.exit(1)

    worst_strategy, current_sharpe, current_stats = find_worst_strategy(backtest_data)
    if not worst_strategy:
        print("No strategy found in backtest results.")
        sys.exit(1)

    current_drawdown = current_stats.get('max_drawdown_account', 1.0)

    print(f"Selected Strategy: {worst_strategy}")
    print(f"Current Sharpe: {current_sharpe}")
    print(f"Current Drawdown: {current_drawdown}")

    # 2. Hyperopt Execution
    strategy_json = STRATEGIES_DIR / f"{worst_strategy}.json"
    backup_json = strategy_json.with_suffix('.json.bak')
    created_new = False

    if strategy_json.exists():
        print(f"Backing up {strategy_json} to {backup_json}")
        shutil.copy(strategy_json, backup_json)
    else:
        created_new = True

    print(f"Running Hyperopt for {worst_strategy}...")
    cmd_hyperopt = [
        "freqtrade", "hyperopt",
        "--config", str(CONFIG_FILE),
        "--strategy", worst_strategy,
        "--epochs", str(EPOCHS),
        "--spaces", *SPACES,
        "--hyperopt-loss", HYPEROPT_LOSS,
        "--min-trades", "1",
        "--timerange", get_timerange(),
        "--no-color",
        "-j", "1"
    ]

    result_hyperopt = run_command(cmd_hyperopt, capture=False)

    if result_hyperopt.returncode != 0:
        print("Hyperopt failed.")
        if strategy_json.exists() and not created_new:
             shutil.move(backup_json, strategy_json)
        elif created_new and strategy_json.exists():
             strategy_json.unlink()
        sys.exit(1)

    # 3. Evaluation (Verification Backtest)
    print("Running verification backtest with new parameters...")
    new_backtest_data = run_backtest_job(worst_strategy)

    if not new_backtest_data:
        print("Failed to run verification backtest.")
        if strategy_json.exists() and not created_new:
             shutil.move(backup_json, strategy_json)
        elif created_new and strategy_json.exists():
             strategy_json.unlink()
        sys.exit(1)

    new_stats = new_backtest_data['strategy'][worst_strategy]
    new_sharpe = new_stats.get('sharpe', -float('inf'))
    if new_sharpe is None:
        new_sharpe = -float('inf')
    new_drawdown = new_stats.get('max_drawdown_account', 1.0)

    # Get profit % for commit message
    avg_profit_pct = new_stats.get('profit_total_pct', 0.0) * 100

    print(f"New Sharpe: {new_sharpe}")
    print(f"New Drawdown: {new_drawdown}")

    sharpe_improved = new_sharpe > (current_sharpe * 1.05)
    drawdown_improved = new_drawdown < current_drawdown

    print(f"Sharpe Improved: {sharpe_improved}")
    print(f"Drawdown Improved: {drawdown_improved}")

    if sharpe_improved and drawdown_improved:
        print("Evaluation PASSED. Committing changes.")
        msg = f"perf: optimized {worst_strategy} (+{avg_profit_pct:.2f}% ROI)"

        # Use -f to force add in case user_data is gitignored
        run_command(["git", "add", "-f", str(strategy_json)])
        run_command(["git", "commit", "-m", msg])
        run_command(["git", "push", "origin", "main"])

        if backup_json.exists():
            backup_json.unlink()

    else:
        print("Evaluation FAILED. Reverting changes.")
        if not created_new:
            shutil.move(backup_json, strategy_json)
        else:
            if strategy_json.exists():
                strategy_json.unlink()

if __name__ == "__main__":
    main()
