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
OPTIMIZATION_LOG = Path(__file__).resolve().parent.parent / "optimization_log.txt"

# Optimization Parameters
EPOCHS = 200
SPACES = ["buy", "roi", "stoploss", "trailing"]
HYPEROPT_LOSS = "SharpeHyperOptLoss"


def log_optimization_attempt(strategy, status, details):
    """Logs optimization attempt to optimization_log.txt."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"{timestamp} | {strategy} | {status} | {details}\n"
    try:
        with OPTIMIZATION_LOG.open("a") as f:
            f.write(log_entry)
        print(f"Logged: {log_entry.strip()}")
    except Exception as e:
        print(f"Failed to write to log: {e}")


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
        sys.executable,
        "-m",
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
    """
    Check if the repository is in a clean state before making changes.
    Returns True if clean, False otherwise.
    """
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
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
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
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


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Daily Optimization Routine for Freqtrade strategies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run optimization without committing or pushing changes",
    )
    parser.add_argument(
        "--branch",
        type=str,
        default=None,
        help="Target branch for pushing changes",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompts before pushing",
    )
    return parser.parse_args()


def establish_baseline():
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
            return None, None, None, None
        backtest_data = run_backtest_job(fallback_strategy)

    if not backtest_data:
        print("Failed to produce backtest baseline.")
        return None, None, None, None

    worst_strategy, current_sharpe, current_stats = find_worst_strategy(backtest_data)
    if not worst_strategy:
        print("No strategy found in backtest results.")
        return None, None, None, None

    current_drawdown = current_stats.get("max_drawdown_account", 1.0)
    return worst_strategy, current_sharpe, current_drawdown, current_stats


def run_hyperopt(strategy):
    strategy_json = STRATEGIES_DIR / f"{strategy}.json"
    backup_json = strategy_json.with_suffix(".json.bak")
    created_new = False

    if strategy_json.exists():
        print(f"Backing up {strategy_json} to {backup_json}")
        shutil.copy(strategy_json, backup_json)
    else:
        created_new = True

    print(f"Running Hyperopt for {strategy}...")
    cmd_hyperopt = [
        sys.executable,
        "-m",
        "freqtrade",
        "hyperopt",
        "--config",
        str(CONFIG_FILE),
        "--strategy",
        strategy,
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
    return result_hyperopt, strategy_json, backup_json, created_new


def ensure_feature_branch(target_branch):
    current_branch = get_current_branch()
    if current_branch != target_branch:
        print(f"\nCreating feature branch: {target_branch}")
        check_result = subprocess.run(
            ["git", "rev-parse", "--verify", target_branch],
            capture_output=True,
            text=True,
            check=False,
        )
        if check_result.returncode == 0:
            print(f"Branch '{target_branch}' already exists, switching...")
            result = run_command(["git", "checkout", target_branch], capture=True)
        else:
            result = run_command(["git", "checkout", "-b", target_branch], capture=True)

        if result.returncode != 0:
            print("Failed to create or switch to feature branch.")
            return False
    return True


def commit_and_push_stuck(strategy, details, args):
    """Commits and pushes the optimization log when a strategy is stuck."""
    msg = f"chore: update optimization log (stuck strategy {strategy})"
    print(f"Committing log update: {msg}")

    if args.dry_run:
        print("[DRY-RUN] Would git add optimization_log.txt, commit, and push.")
        return

    run_command(["git", "add", "-f", str(OPTIMIZATION_LOG)])
    run_command(["git", "commit", "-m", msg])

    # Push to current branch (likely main or develop if not feature branch)
    current_branch = get_current_branch()
    if current_branch:
        print(f"Pushing log update to {current_branch}...")
        run_command(["git", "push", "origin", current_branch], capture=True)


def commit_and_push(strategy, strategy_json, backup_json, avg_profit_pct, args):
    msg = f"perf: optimized {strategy} (+{avg_profit_pct:.2f}% ROI)"

    if args.dry_run:
        print("\n[DRY-RUN MODE] Would have committed and pushed:")
        print(f"  File: {strategy_json}")
        print(f"  Message: {msg}")
        if backup_json.exists():
            backup_json.unlink()
        return

    if args.branch:
        target_branch = args.branch
    else:
        target_branch = f"optimize-{datetime.now().strftime('%Y%m%d')}"

    if not ensure_feature_branch(target_branch):
        print("Reverting changes...")
        if backup_json.exists():
            shutil.move(backup_json, strategy_json)
        sys.exit(1)

    # Add strategy file AND optimization log
    run_command(["git", "add", "-f", str(strategy_json)])
    run_command(["git", "add", "-f", str(OPTIMIZATION_LOG)])
    run_command(["git", "commit", "-m", msg])

    if not args.yes:
        print(f"\nReady to push changes to branch '{target_branch}'")
        response = input("\nProceed with push? [y/N]: ").strip().lower()
        if response not in ["y", "yes"]:
            print("Push cancelled.")
            if backup_json.exists():
                backup_json.unlink()
            return

    print(f"\nPushing to {target_branch}...")
    result = run_command(["git", "push", "origin", target_branch], capture=True)

    if result.returncode == 0:
        print(f"\n✓ Successfully pushed optimized strategy to: {target_branch}")
    else:
        print(f"\nFailed to push to {target_branch}")

    if backup_json.exists():
        backup_json.unlink()


def handle_optimization_result(
    worst_strategy,
    current_sharpe,
    current_drawdown,
    strategy_json,
    backup_json,
    created_new,
    args,
):
    print("Running verification backtest...")
    new_backtest_data = run_backtest_job(worst_strategy)

    if not new_backtest_data:
        print("Failed to run verification backtest.")
        log_optimization_attempt(worst_strategy, "Failed", "Verification backtest failed")
        commit_and_push_stuck(worst_strategy, "Verification backtest failed", args)
        if strategy_json.exists() and not created_new:
            shutil.move(backup_json, strategy_json)
        elif created_new and strategy_json.exists():
            strategy_json.unlink()
        sys.exit(1)

    new_stats = new_backtest_data["strategy"][worst_strategy]
    new_sharpe = new_stats.get("sharpe", -float("inf")) or -float("inf")
    new_drawdown = new_stats.get("max_drawdown_account", 1.0)
    avg_profit_pct = new_stats.get("profit_total_pct", 0.0) * 100

    print(f"New Sharpe: {new_sharpe}")
    print(f"New Drawdown: {new_drawdown}")

    sharpe_improved = new_sharpe > (current_sharpe * 1.05)
    drawdown_improved = new_drawdown < current_drawdown

    details = (
        f"Sharpe: {current_sharpe:.2f}->{new_sharpe:.2f}, "
        f"Drawdown: {current_drawdown:.2f}->{new_drawdown:.2f}"
    )

    if sharpe_improved and drawdown_improved:
        print("Evaluation PASSED. Committing changes.")
        log_optimization_attempt(worst_strategy, "Success", details)
        commit_and_push(worst_strategy, strategy_json, backup_json, avg_profit_pct, args)
    else:
        print("Evaluation FAILED. Reverting changes.")
        log_optimization_attempt(worst_strategy, "Stuck", f"No improvement ({details})")
        commit_and_push_stuck(worst_strategy, f"No improvement ({details})", args)

        if not created_new:
            shutil.move(backup_json, strategy_json)
        else:
            if strategy_json.exists():
                strategy_json.unlink()


def main():
    args = parse_arguments()

    if not args.dry_run:
        if not check_git_status():
            print("\nPlease commit or stash your changes first.")
            sys.exit(1)

    # 1. Establish Baseline
    worst_strategy, current_sharpe, current_drawdown, _ = establish_baseline()
    if not worst_strategy:
        sys.exit(1)

    print(f"Selected Strategy: {worst_strategy}")
    print(f"Current Sharpe: {current_sharpe}")
    print(f"Current Drawdown: {current_drawdown}")

    # 2. Hyperopt Execution
    res_hyperopt, strategy_json, backup_json, created_new = run_hyperopt(worst_strategy)

    if res_hyperopt.returncode != 0:
        print("Hyperopt failed.")
        log_optimization_attempt(worst_strategy, "Failed", "Hyperopt process failed")
        commit_and_push_stuck(worst_strategy, "Hyperopt failed", args)
        if strategy_json.exists() and not created_new:
            shutil.move(backup_json, strategy_json)
        elif created_new and strategy_json.exists():
            strategy_json.unlink()
        sys.exit(1)

    new_params = extract_hyperopt_params(res_hyperopt.stdout)
    if new_params:
        print(f"Applying new parameters to {strategy_json}")
        with strategy_json.open("w") as f:
            json.dump(new_params, f, indent=4)
    else:
        print("Could not extract new parameters.")
        log_optimization_attempt(worst_strategy, "Failed", "No params extracted")
        commit_and_push_stuck(worst_strategy, "No params extracted", args)
        if strategy_json.exists() and not created_new:
            shutil.move(backup_json, strategy_json)
        elif created_new and strategy_json.exists():
            strategy_json.unlink()
        sys.exit(1)

    # 3. Handle Result
    handle_optimization_result(
        worst_strategy,
        current_sharpe,
        current_drawdown,
        strategy_json,
        backup_json,
        created_new,
        args,
    )


if __name__ == "__main__":
    main()
