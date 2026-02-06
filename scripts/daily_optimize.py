#!/usr/bin/env python3
"""
Daily Optimization Routine
"""

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path


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
        with last_result_file.open() as f:
            data = json.load(f)
            filename = data.get("latest_backtest")
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
    if filepath.suffix == ".zip":
        with zipfile.ZipFile(filepath, "r") as z:
            json_files = [f for f in z.namelist() if f.endswith(".json")]
            target_file = None
            for f in json_files:
                if "backtest-result" in f:
                    target_file = f
                    break
            if not target_file and json_files:
                target_file = json_files[0]

            if target_file:
                with z.open(target_file) as f:
                    data = json.load(f)
    else:
        with filepath.open() as f:
            data = json.load(f)
    return data


def find_worst_strategy(backtest_data):
    strategies = backtest_data.get("strategy", {})
    if not strategies:
        return None, None, None

    worst_strategy = None
    min_sharpe = float("inf")
    worst_stats = None

    for strategy_name, stats in strategies.items():
        sharpe = stats.get("sharpe", -float("inf"))
        if sharpe is None:
            sharpe = -float("inf")

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
        "freqtrade",
        "backtesting",
        "--config",
        str(CONFIG_FILE),
        "--timerange",
        timerange,
        "--timeframe",
        "1h",
        "--cache",
        "none",
        "--strategy",
        strategy_name,
    ]

    run_command(cmd, capture=True)

    latest = get_latest_backtest_file()
    if latest:
        return read_backtest_result(latest)
    return None


def check_git_status():
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False
    )
    if result.returncode != 0:
        print("Warning: Could not check git status")
        return False

    if result.stdout.strip():
        print("Error: Repository has uncommitted changes:")
        print(result.stdout)
        return False

    return True


def get_current_branch():
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def extract_hyperopt_params(output: str) -> dict:
    lines = output.splitlines()
    json_str = ""
    started = False

    for line in reversed(lines):
        if line.strip() == "}":
            started = True
        if started:
            json_str = line + "\n" + json_str
            if line.strip() == "{":
                try:
                    params = json.loads(json_str)
                    if "params" in params:
                        return params["params"]
                    return params
                except json.JSONDecodeError:
                    continue
    return {}


def establish_baseline():
    latest_file = get_latest_backtest_file()
    backtest_data = None
    if latest_file:
        print(f"Using latest backtest file: {latest_file}")
        backtest_data = read_backtest_result(latest_file)

    if not backtest_data:
        print("No valid baseline found. Running initial backtest...")
        fallback = find_available_strategy()
        if not fallback:
            print("No strategy file found.")
            sys.exit(1)
        backtest_data = run_backtest_job(fallback)

    if not backtest_data:
        print("Failed to produce backtest baseline.")
        sys.exit(1)

    worst_strategy, current_sharpe, current_stats = find_worst_strategy(backtest_data)
    if not worst_strategy:
        print("No strategy found in backtest results.")
        sys.exit(1)

    current_drawdown = current_stats.get("max_drawdown_account", 1.0)
    print(f"Selected Strategy: {worst_strategy}")
    print(f"Current Sharpe: {current_sharpe}")
    print(f"Current Drawdown: {current_drawdown}")

    return worst_strategy, current_sharpe, current_drawdown


def run_hyperopt(strategy_name):
    print(f"Running Hyperopt for {strategy_name}...")
    cmd = [
        "freqtrade",
        "hyperopt",
        "--config",
        str(CONFIG_FILE),
        "--strategy",
        strategy_name,
        "--epochs",
        str(EPOCHS),
        "--spaces",
        *SPACES,
        "--hyperopt-loss",
        HYPEROPT_LOSS,
        "--min-trades",
        "1",
        "--timerange",
        get_timerange(),
        "--no-color",
        "--print-json",
        "-j",
        "1",
    ]
    return run_command(cmd, capture=True)


def verify_results(strategy_name, current_sharpe, current_drawdown):
    print("Running verification backtest with new parameters...")
    new_data = run_backtest_job(strategy_name)

    if not new_data:
        print("Failed to run verification backtest.")
        return False, 0.0

    new_stats = new_data["strategy"][strategy_name]
    new_sharpe = new_stats.get("sharpe", -float("inf"))
    if new_sharpe is None:
        new_sharpe = -float("inf")
    new_drawdown = new_stats.get("max_drawdown_account", 1.0)
    profit = new_stats.get("profit_total_pct", 0.0) * 100

    print(f"New Sharpe: {new_sharpe}")
    print(f"New Drawdown: {new_drawdown}")

    improved = (new_sharpe > (current_sharpe * 1.05)) and (new_drawdown < current_drawdown)
    print(f"Improvement: {improved}")

    return improved, profit


def git_commit_push(args, strategy_name, avg_profit, strategy_file):
    msg = f"perf: optimized {strategy_name} (+{avg_profit:.2f}% ROI)"
    target_branch = args.branch or f"optimize-{datetime.now().strftime('%Y%m%d')}"

    if args.dry_run:
        print(f"\n[DRY-RUN] Would commit to {target_branch}: {msg}")
        return

    current = get_current_branch()
    if current != target_branch:
        print(f"Switching to {target_branch}...")
        res = subprocess.run(
            ["git", "rev-parse", "--verify", target_branch],
            capture_output=True, check=False
        )
        cmd = ["git", "checkout"]
        if res.returncode == 0:
            cmd.append(target_branch)
        else:
            cmd.extend(["-b", target_branch])
        run_command(cmd)

    run_command(["git", "add", "-f", str(strategy_file)])
    run_command(["git", "commit", "-m", msg])

    if not args.yes:
        if input(f"Push to {target_branch}? [y/N]: ").lower() not in ["y", "yes"]:
            return

    run_command(["git", "push", "origin", target_branch])


def parse_args():
    parser = argparse.ArgumentParser(
        description="Daily Optimization Routine",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true", help="No git ops")
    parser.add_argument("--branch", type=str, help="Target branch")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    return parser.parse_args()


def restore_backup(strat_json, backup, created_new):
    if not created_new:
        if backup.exists():
            shutil.move(backup, strat_json)
    elif strat_json.exists():
        strat_json.unlink()


def main():
    args = parse_args()

    if not args.dry_run and not check_git_status():
        sys.exit(1)

    worst_strat, curr_sharpe, curr_dd = establish_baseline()

    strat_json = STRATEGIES_DIR / f"{worst_strat}.json"
    backup = strat_json.with_suffix(".json.bak")
    created_new = False

    if strat_json.exists():
        shutil.copy(strat_json, backup)
    else:
        created_new = True

    res = run_hyperopt(worst_strat)
    if res.returncode != 0:
        print("Hyperopt failed.")
        restore_backup(strat_json, backup, created_new)
        sys.exit(1)

    new_params = extract_hyperopt_params(res.stdout)
    if new_params:
        with strat_json.open("w") as f:
            json.dump(new_params, f, indent=4)
    else:
        print("No params found.")
        restore_backup(strat_json, backup, created_new)
        sys.exit(1)

    success, profit = verify_results(worst_strat, curr_sharpe, curr_dd)

    if success:
        git_commit_push(args, worst_strat, profit, strat_json)
        if backup.exists():
            backup.unlink()
    else:
        print("Reverting changes.")
        restore_backup(strat_json, backup, created_new)


if __name__ == "__main__":
    main()
