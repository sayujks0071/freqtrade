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
BASELINE_METRICS_FILE = Path("baseline_metrics.json")

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
        sys.executable,
        "-m",
        "freqtrade.main",
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
    """
    Check if the repository is in a clean state before making changes.
    Returns True if clean, False otherwise.
    """
    result = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        print("Warning: Could not check git status")
        if result.stderr:
            print(f"Error: {result.stderr}")
        return False

    # If there's any output, there are uncommitted changes
    if result.stdout.strip():
        print("Error: Repository has uncommitted changes:")
        print(result.stdout)
        return False

    return True


def get_current_branch():
    """Get the current git branch name."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=False
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def extract_hyperopt_params(output: str) -> dict:
    """
    Extracts the JSON parameters from the hyperopt output.
    """
    lines = output.splitlines()
    json_str = ""
    started = False

    # Iterate backwards to find the last JSON block
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


def _get_fallback_strategy_from_backtest():
    """
    Helper to find the worst performing strategy from the latest backtest result.
    """
    selected_strategy = None
    latest_file = get_latest_backtest_file()
    if latest_file:
        print(f"Checking latest backtest file: {latest_file}")
        data = read_backtest_result(latest_file)
        if data and "strategy" in data:
            strategies = data["strategy"]
            # Find worst by Sharpe
            worst_sharpe = float("inf")
            for s_name, stats in strategies.items():
                sharpe = stats.get("sharpe", -float("inf"))
                if sharpe is None:
                    sharpe = -float("inf")
                if sharpe < worst_sharpe:
                    worst_sharpe = sharpe
                    selected_strategy = s_name
            if selected_strategy:
                print(
                    f"Selected worst strategy from backtest (Sharpe {worst_sharpe}): "
                    f"{selected_strategy}"
                )
    return selected_strategy


def establish_baseline():
    """
    Identifies the strategy to optimize and establishes its current baseline metrics.
    Prioritizes reading from baseline_metrics.json.
    """
    selected_strategy = None

    # 1. Try to pick from baseline_metrics.json
    if BASELINE_METRICS_FILE.exists():
        try:
            with BASELINE_METRICS_FILE.open() as f:
                metrics = json.load(f)
                if isinstance(metrics, list) and metrics:
                    # Sort by ROI (ascending), assuming lowest ROI needs most help
                    # If ROI is missing, assume 0
                    metrics.sort(key=lambda x: x.get("roi", 0))
                    selected_strategy = metrics[0].get("strategy")
                    print(f"Selected strategy from {BASELINE_METRICS_FILE}: {selected_strategy}")
        except json.JSONDecodeError:
            print(f"Warning: Could not parse {BASELINE_METRICS_FILE}")

    # 2. Fallback to latest backtest results
    if not selected_strategy:
        selected_strategy = _get_fallback_strategy_from_backtest()

    # 3. Fallback to scanning folder
    if not selected_strategy:
        print("Falling back to discovering available strategies...")
        selected_strategy = find_available_strategy()

    if not selected_strategy:
        print("No strategies found.")
        sys.exit(1)

    print(f"Establishing baseline for {selected_strategy}...")
    backtest_data = run_backtest_job(selected_strategy)

    if not backtest_data:
        print("Failed to run baseline backtest.")
        sys.exit(1)

    stats = backtest_data["strategy"][selected_strategy]
    current_sharpe = stats.get("sharpe", -float("inf"))
    if current_sharpe is None:
        current_sharpe = -float("inf")
    current_drawdown = stats.get("max_drawdown_account", 1.0)

    return selected_strategy, current_sharpe, current_drawdown


def run_hyperopt_execution(strategy_name):
    """
    Runs hyperopt and updates the strategy json file.
    Returns path to backup file if created, else None.
    """
    strategy_json = STRATEGIES_DIR / f"{strategy_name}.json"
    backup_json = strategy_json.with_suffix(".json.bak")
    created_new = False

    if strategy_json.exists():
        print(f"Backing up {strategy_json} to {backup_json}")
        shutil.copy(strategy_json, backup_json)
    else:
        created_new = True

    print(f"Running Hyperopt for {strategy_name}...")
    cmd_hyperopt = [
        sys.executable,
        "-m",
        "freqtrade.main",
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

    result_hyperopt = run_command(cmd_hyperopt, capture=True)

    if result_hyperopt.returncode != 0:
        print("Hyperopt failed.")
        print(result_hyperopt.stderr)
        if strategy_json.exists() and not created_new:
            shutil.move(backup_json, strategy_json)
        elif created_new and strategy_json.exists():
            strategy_json.unlink()
        sys.exit(1)

    # Apply new parameters
    new_params = extract_hyperopt_params(result_hyperopt.stdout)
    if new_params:
        print(f"Applying new parameters to {strategy_json}")
        with strategy_json.open("w") as f:
            json.dump(new_params, f, indent=4)
        return backup_json if not created_new else "CREATED_NEW"
    else:
        print("Could not extract new parameters from hyperopt output.")
        if strategy_json.exists() and not created_new:
            shutil.move(backup_json, strategy_json)
        elif created_new and strategy_json.exists():
            strategy_json.unlink()
        sys.exit(1)


def evaluate_results(strategy_name, current_sharpe, current_drawdown):
    """
    Runs verification backtest and checks against 'The Gatekeeper' rules.
    """
    print("Running verification backtest with new parameters...")
    new_backtest_data = run_backtest_job(strategy_name)

    if not new_backtest_data:
        print("Failed to run verification backtest.")
        return False, 0.0

    new_stats = new_backtest_data["strategy"][strategy_name]
    new_sharpe = new_stats.get("sharpe", -float("inf"))
    if new_sharpe is None:
        new_sharpe = -float("inf")
    new_drawdown = new_stats.get("max_drawdown_account", 1.0)
    profit_pct = new_stats.get("profit_total_pct", 0.0) * 100

    print(f"Baseline Sharpe: {current_sharpe:.4f}, New Sharpe: {new_sharpe:.4f}")
    print(f"Baseline Drawdown: {current_drawdown:.4f}, New Drawdown: {new_drawdown:.4f}")

    # Rule: New_Sharpe > (Current_Sharpe * 1.05) AND New_Drawdown < Current_Drawdown

    sharpe_improved = new_sharpe > (current_sharpe * 1.05)
    drawdown_improved = new_drawdown < current_drawdown

    print(f"Sharpe Improved (> {current_sharpe * 1.05:.4f}): {sharpe_improved}")
    print(f"Drawdown Improved (< {current_drawdown:.4f}): {drawdown_improved}")

    if sharpe_improved and drawdown_improved:
        return True, profit_pct
    return False, profit_pct


def git_push_workflow(strategy_name, profit_pct, dry_run=False, branch=None, yes=False):
    strategy_json = STRATEGIES_DIR / f"{strategy_name}.json"
    msg = f"perf: optimized {strategy_name} (+{profit_pct:.2f}% ROI)"
    target_branch = branch if branch else "main"

    if dry_run:
        print("\n[DRY-RUN MODE] Would have committed and pushed:")
        print(f"  File: {strategy_json}")
        print(f"  Message: {msg}")
        print(f"  Branch: {target_branch}")
        return

    # Simplified git flow for "Push to origin main"
    # 1. Add file
    run_command(["git", "add", "-f", str(strategy_json)])
    # 2. Commit
    run_command(["git", "commit", "-m", msg])

    # 3. Push
    if not yes:
        print(f"\nReady to push changes to {target_branch}")
        response = input(f"Proceed with push to origin {target_branch}? [y/N]: ").strip().lower()
        if response not in ["y", "yes"]:
            print("Push cancelled. Changes are committed locally.")
            return

    print(f"Pushing to origin {target_branch}...")
    result = run_command(["git", "push", "origin", target_branch], capture=True)
    if result.returncode == 0:
        print(f"✓ Successfully pushed to origin {target_branch}")
    else:
        print(f"Failed to push: {result.stderr}")


def main():
    parser = argparse.ArgumentParser(description="Daily Optimization Routine")
    parser.add_argument("--dry-run", action="store_true", help="Run without committing/pushing")
    parser.add_argument("--branch", type=str, default="main", help="Target branch (default: main)")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    if not args.dry_run and not check_git_status():
        print("Repo not clean. Commit/stash changes or use --dry-run.")
        sys.exit(1)

    # 1. Selection & Baseline
    strategy_name, current_sharpe, current_drawdown = establish_baseline()
    print(f"Selected Strategy: {strategy_name}")
    print(f"Baseline Sharpe: {current_sharpe}")
    print(f"Baseline Drawdown: {current_drawdown}")

    # 2. Action (Hyperopt)
    backup_file = run_hyperopt_execution(strategy_name)

    # 3. Evaluation
    success, profit_pct = evaluate_results(strategy_name, current_sharpe, current_drawdown)

    strategy_json = STRATEGIES_DIR / f"{strategy_name}.json"

    if success:
        print("Evaluation PASSED. Committing...")
        # Clean up backup
        if backup_file and backup_file != "CREATED_NEW" and backup_file.exists():
            backup_file.unlink()

        git_push_workflow(
            strategy_name, profit_pct, dry_run=args.dry_run, branch=args.branch, yes=args.yes
        )
    else:
        print("Evaluation FAILED. Reverting changes.")
        # Revert
        if backup_file == "CREATED_NEW":
            if strategy_json.exists():
                strategy_json.unlink()
        elif backup_file and backup_file.exists():
            shutil.move(backup_file, strategy_json)


if __name__ == "__main__":
    main()
