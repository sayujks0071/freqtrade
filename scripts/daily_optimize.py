#!/usr/bin/env python3
"""
Daily Optimization Routine
"""

import argparse
import json
import re
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
        check=False
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
        check=False
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


def update_strategy_content(content: str, params: dict) -> str:
    """
    Updates the strategy content with new parameters.
    """
    new_content = content

    # 1. Update IntParameter/DecimalParameter defaults
    # params structure: {'buy': {'buy_rsi': 25}, 'sell': {'sell_rsi': 75}, ...}
    for space, space_params in params.items():
        if isinstance(space_params, dict):
            for param_name, param_value in space_params.items():
                # Regex to find: param_name = IntParameter(..., default=XXX, ...)
                # matches: buy_rsi = IntParameter(10, 40, default=30, space="buy")
                pattern = fr"({param_name}\s*=\s*(?:Int|Decimal)Parameter\(.*default=)([\d\.]+)(.*)"

                # Check if param_value is numeric
                if isinstance(param_value, (int, float)):
                    # Replace the default value
                    new_content = re.sub(pattern, fr"\g<1>{param_value}\g<3>", new_content)

    # 2. Update minimal_roi
    if "roi" in params:
        roi_params = params["roi"]
        # roi is usually a dict like {"0": 0.1, "10": 0.05}
        # We need to format it nicely
        roi_str = json.dumps(roi_params, indent=4).replace("\n", "\n    ")
        # Regex to find minimal_roi = { ... }
        # Using DOTALL to match across lines
        pattern = r"(minimal_roi\s*=\s*)\{.*?\}"
        new_content = re.sub(pattern, fr"\1{roi_str}", new_content, flags=re.DOTALL)

    # 3. Update stoploss
    if "stoploss" in params:
        stoploss_val = params["stoploss"]
        if isinstance(stoploss_val, dict):
            stoploss_val = stoploss_val.get("stoploss", -0.10)

        # Regex to find stoploss = XXX
        pattern = r"(stoploss\s*=\s*)-?[\d\.]+"
        new_content = re.sub(pattern, fr"\1{stoploss_val}", new_content)

    # 4. Update trailing stop
    if "trailing" in params:
        trailing = params["trailing"]
        # Keys: trailing_stop, trailing_stop_positive, trailing_stop_positive_offset, trailing_only_offset_is_reached
        for key, value in trailing.items():
            # Boolean needs python format (True/False) not json (true/false)
            if isinstance(value, bool):
                val_str = str(value)
            else:
                val_str = str(value)

            pattern = fr"({key}\s*=\s*).*"
            new_content = re.sub(pattern, fr"\1{val_str}", new_content)

    return new_content


def main():
    parser = argparse.ArgumentParser(
        description="Daily Optimization Routine for Freqtrade strategies",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run optimization without committing or pushing changes"
    )
    parser.add_argument(
        "--branch",
        type=str,
        default="main",
        help="Target branch for pushing changes (default: main)"
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompts before pushing"
    )

    args = parser.parse_args()

    if not args.dry_run:
        if not check_git_status():
            print("\nPlease commit or stash your changes before running this script.")
            sys.exit(1)

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

    current_drawdown = current_stats.get("max_drawdown_account", 1.0)

    print(f"Selected Strategy: {worst_strategy}")
    print(f"Current Sharpe: {current_sharpe}")
    print(f"Current Drawdown: {current_drawdown}")

    # 2. Hyperopt Execution
    strategy_file = STRATEGIES_DIR / f"{worst_strategy}.py"
    backup_file = strategy_file.with_suffix(".py.bak")

    if not strategy_file.exists():
        print(f"Strategy file not found: {strategy_file}")
        sys.exit(1)

    print(f"Backing up {strategy_file} to {backup_file}")
    shutil.copy(strategy_file, backup_file)

    print(f"Running Hyperopt for {worst_strategy}...")
    cmd_hyperopt = [
        sys.executable,
        "-m",
        "freqtrade",
        "hyperopt",
        "--config",
        str(CONFIG_FILE),
        "--strategy",
        worst_strategy,
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
        shutil.move(backup_file, strategy_file)
        sys.exit(1)

    # Apply new parameters
    new_params = extract_hyperopt_params(result_hyperopt.stdout)
    if new_params:
        print(f"Applying new parameters to {strategy_file}")
        try:
            with strategy_file.open("r") as f:
                content = f.read()

            new_content = update_strategy_content(content, new_params)

            with strategy_file.open("w") as f:
                f.write(new_content)
        except Exception as e:
            print(f"Error updating strategy file: {e}")
            shutil.move(backup_file, strategy_file)
            sys.exit(1)
    else:
        print("Could not extract new parameters from hyperopt output.")
        shutil.move(backup_file, strategy_file)
        sys.exit(1)

    # 3. Evaluation (Verification Backtest)
    print("Running verification backtest with new parameters...")
    new_backtest_data = run_backtest_job(worst_strategy)

    if not new_backtest_data:
        print("Failed to run verification backtest.")
        shutil.move(backup_file, strategy_file)
        sys.exit(1)

    new_stats = new_backtest_data["strategy"][worst_strategy]
    new_sharpe = new_stats.get("sharpe", -float("inf"))
    if new_sharpe is None:
        new_sharpe = -float("inf")
    new_drawdown = new_stats.get("max_drawdown_account", 1.0)

    # Get profit % for commit message
    avg_profit_pct = new_stats.get("profit_total_pct", 0.0) * 100

    print(f"New Sharpe: {new_sharpe}")
    print(f"New Drawdown: {new_drawdown}")

    sharpe_improved = new_sharpe > (current_sharpe * 1.05)
    drawdown_improved = new_drawdown < current_drawdown

    print(f"Sharpe Improved: {sharpe_improved}")
    print(f"Drawdown Improved: {drawdown_improved}")

    if sharpe_improved and drawdown_improved:
        print("Evaluation PASSED. Committing changes.")
        msg = f"perf: optimized {worst_strategy} (+{avg_profit_pct:.2f}% ROI)"

        if args.dry_run:
            print("\n[DRY-RUN MODE] Would have committed and pushed:")
            print(f"  File: {strategy_file}")
            print(f"  Message: {msg}")
            print(f"  Branch: {args.branch}")
            print("\nReverting changes for dry-run...")
            shutil.move(backup_file, strategy_file)
        else:
            target_branch = args.branch
            current_branch = get_current_branch()

            if current_branch != target_branch:
                print(f"Switching to branch {target_branch}...")
                # This logic is simplified; in a real CI/CD or user machine we need to be careful
                # If target branch doesn't exist, create it. If it does, check it out.
                # Assuming 'main' exists.
                result = run_command(["git", "checkout", target_branch], capture=True)
                if result.returncode != 0:
                     # Try creating it if it doesn't exist (though strictly for main it should exist)
                     result = run_command(["git", "checkout", "-b", target_branch], capture=True)

            run_command(["git", "add", "-f", str(strategy_file)])
            run_command(["git", "commit", "-m", msg])

            if not args.yes:
                print(f"\nReady to push changes to branch '{target_branch}'")
                response = input("\nProceed with push? [y/N]: ").strip().lower()
                if response not in ['y', 'yes']:
                    print("Push cancelled.")
                    if backup_file.exists():
                        backup_file.unlink()
                    return

            print(f"\nPushing to {target_branch}...")
            # We assume origin exists.
            result = run_command(["git", "push", "origin", target_branch], capture=True)

            if result.returncode == 0:
                print(f"\n✓ Successfully pushed optimized strategy to branch: {target_branch}")
            else:
                print(f"\nFailed to push to {target_branch}")

            if backup_file.exists():
                backup_file.unlink()

    else:
        print("Evaluation FAILED. Reverting changes.")
        shutil.move(backup_file, strategy_file)


if __name__ == "__main__":
    main()
