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
    Finds the last JSON object in the output which typically contains the best parameters.
    """
    lines = output.splitlines()
    json_str = ""
    started = False

    # Iterate backwards to find the last JSON block
    # Freqtrade prints the params in json format at the end when --print-json is used
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
                    # Sometimes it returns the strategy config object directly
                    return params
                except json.JSONDecodeError:
                    continue  # Keep looking if this wasn't valid JSON or not the right one
    return {}


def main():
    parser = argparse.ArgumentParser(
        description="Daily Optimization Routine for Freqtrade strategies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry-run mode (no git operations):
  %(prog)s --dry-run

  # Push to a feature branch instead of main:
  %(prog)s --branch optimize-strategy-$(date +%%Y%%m%%d)

  # Skip confirmation prompts:
  %(prog)s --yes
        """
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run optimization without committing or pushing changes"
    )
    parser.add_argument(
        "--branch",
        type=str,
        default=None,
        help=(
            "Target branch for pushing changes "
            "(default: 'main')"
        )
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompts before pushing"
    )

    args = parser.parse_args()

    # Check git status before starting (unless in dry-run mode)
    if not args.dry_run:
        if not check_git_status():
            print("\nPlease commit or stash your changes before running this script.")
            print("Or use --dry-run to test without making git changes.")
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
    strategy_json = STRATEGIES_DIR / f"{worst_strategy}.json"
    backup_json = strategy_json.with_suffix(".json.bak")
    created_new = False

    if strategy_json.exists():
        print(f"Backing up {strategy_json} to {backup_json}")
        shutil.copy(strategy_json, backup_json)
    else:
        created_new = True

    print(f"Running Hyperopt for {worst_strategy}...")
    cmd_hyperopt = [
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
        print(result_hyperopt.stderr)  # Print stderr on failure
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
    else:
        print("Could not extract new parameters from hyperopt output.")
        # We might want to fail here, or just continue and let the verification fail
        # if no file was written
        # But if no file written, verification will use default/old params.

        # If capture failed to get json, we should probably revert and exit
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
            print(f"  File: {strategy_json}")
            print(f"  Message: {msg}")
            if args.branch:
                print(f"  Branch: {args.branch}")
            else:
                print(f"  Branch: main")
            print("\nNo changes were made. Use without --dry-run to apply changes.")
        else:
            # Determine target branch
            if args.branch:
                target_branch = args.branch
            else:
                target_branch = "main"

            current_branch = get_current_branch()

            # Create and switch to feature branch if not already on it
            if current_branch != target_branch:
                print(f"\nSwitching to target branch: {target_branch}")
                # Check if branch already exists
                check_result = subprocess.run(
                    ["git", "rev-parse", "--verify", target_branch],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if check_result.returncode == 0:
                    # Branch exists, just switch to it
                    print(f"Branch '{target_branch}' already exists, switching to it...")
                    result = run_command(["git", "checkout", target_branch], capture=True)
                else:
                    # Branch doesn't exist, create it
                    result = run_command(["git", "checkout", "-b", target_branch], capture=True)

                if result.returncode != 0:
                    print("Failed to create or switch to target branch.")
                    if result.stderr:
                        print(f"Git error: {result.stderr}")
                    print("Reverting changes...")
                    if not created_new:
                        shutil.move(backup_json, strategy_json)
                    else:
                        if strategy_json.exists():
                            strategy_json.unlink()
                    sys.exit(1)

            # Use -f to force add in case user_data is gitignored
            run_command(["git", "add", "-f", str(strategy_json)])
            run_command(["git", "commit", "-m", msg])

            # Confirm before pushing
            if not args.yes:
                print(f"\nReady to push changes to branch '{target_branch}'")
                print("This will:")
                print(f"  - Push optimized strategy parameters for {worst_strategy}")
                print(f"  - Create/update remote branch: {target_branch}")
                print("\nYou can then create a pull request to review and merge these changes.")
                response = input("\nProceed with push? [y/N]: ").strip().lower()
                if response not in ['y', 'yes']:
                    print("Push cancelled. Changes are committed locally.")
                    print(f"You can manually push later with: git push origin {target_branch}")
                    if backup_json.exists():
                        backup_json.unlink()
                    return

            print(f"\nPushing to {target_branch}...")
            result = run_command(["git", "push", "origin", target_branch], capture=True)

            if result.returncode == 0:
                print(f"\n✓ Successfully pushed optimized strategy to branch: {target_branch}")
                print("\nNext steps:")
                print(f"  1. Create a pull request from '{target_branch}' to your main branch")
                print("  2. Review the changes and test the optimized strategy")
                print("  3. Merge the pull request after verification")
            else:
                print(f"\nFailed to push to {target_branch}")
                print("Changes are committed locally. You can manually push later.")

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
