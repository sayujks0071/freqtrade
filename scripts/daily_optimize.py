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
DEFAULT_SPACES = ["buy", "roi", "stoploss", "trailing"]
HYPEROPT_LOSS = "SharpeHyperOptLoss"


def run_command(cmd, capture=True):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"Error running command: {result.stderr}")
    return result


def get_timerange(days=30):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
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
            for fname in json_files:
                if "backtest-result" in fname:
                    target_file = fname
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


def find_available_strategies():
    """Finds all available strategy files in the user_data/strategies directory."""
    files = list(STRATEGIES_DIR.glob("*.py"))
    strategies = []
    for f in files:
        if f.stem != "__init__" and not f.stem.startswith("_"):
            strategies.append(f.stem)
    return strategies


def run_backtest_job(strategy_name_or_list, extra_config=None):
    """Runs a backtest job for a single strategy or a list of strategies."""
    timerange = get_timerange()

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
    ]

    if extra_config:
        cmd.extend(["--config", str(extra_config)])

    if isinstance(strategy_name_or_list, list):
        print(f"Running backtest for {len(strategy_name_or_list)} strategies over {timerange}...")
        cmd.append("--strategy-list")
        cmd.extend(strategy_name_or_list)
    else:
        print(f"Running backtest for {strategy_name_or_list} over {timerange}...")
        cmd.extend(["--strategy", strategy_name_or_list])

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


def extract_hyperopt_params(output: str) -> dict:
    """
    Extracts the JSON parameters from the hyperopt output.
    """
    lines = output.splitlines()
    json_str = ""
    started = False

    for line in reversed(lines):
        stripped = line.strip()
        # Check for single-line JSON first
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                params = json.loads(stripped)
                if "params" in params or "minimal_roi" in params:
                    return params
            except json.JSONDecodeError:
                pass

        # Check for multi-line JSON
        if stripped == "}":
            started = True

        if started:
            json_str = line + "\n" + json_str
            if stripped == "{":
                try:
                    params = json.loads(json_str)
                    if "params" in params or "minimal_roi" in params:
                        return params
                except json.JSONDecodeError:
                    continue
    return {}


def strategy_has_parameters(strategy_name: str) -> bool:
    """
    Checks if the strategy file has parameter definitions (IntParameter, DecimalParameter, etc.).
    """
    strategy_file = STRATEGIES_DIR / f"{strategy_name}.py"
    if not strategy_file.exists():
        return False

    with strategy_file.open() as f:
        content = f.read()
        if (
            "IntParameter" in content
            or "DecimalParameter" in content
            or "CategoricalParameter" in content
        ):
            return True
        if "RealParameter" in content or "BooleanParameter" in content:
            return True

    return False


def main():  # noqa: C901
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
        default="main",
        help=("Target branch for pushing changes (default: main)"),
    )
    parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation prompts before pushing"
    )

    args = parser.parse_args()

    if not args.dry_run:
        if not check_git_status():
            print("\nPlease commit or stash your changes before running this script.")
            print("Or use --dry-run to test without making git changes.")
            sys.exit(1)

    # 1. Establish Baseline
    latest_file = get_latest_backtest_file()
    backtest_data = None

    if latest_file:
        mtime = datetime.fromtimestamp(latest_file.stat().st_mtime)
        if (datetime.now() - mtime) < timedelta(days=1):
            print(f"Using recent backtest file: {latest_file}")
            backtest_data = read_backtest_result(latest_file)
        else:
            print(f"Latest backtest file {latest_file} is older than 1 day.")

    if not backtest_data:
        print("No recent baseline found. Running initial backtest...")
        strategies = find_available_strategies()
        if not strategies:
            print("No strategy file found.")
            sys.exit(1)
        backtest_data = run_backtest_job(strategies)

    if not backtest_data:
        print("Failed to produce backtest baseline.")
        sys.exit(1)

    worst_strategy, current_sharpe, current_stats = find_worst_strategy(backtest_data)
    if not worst_strategy:
        print("No strategy found in backtest results.")
        sys.exit(1)

    current_drawdown = current_stats.get("max_drawdown_account", 1.0)
    # Removed unused variable: current_profit_pct

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

    # Determine spaces
    spaces = list(DEFAULT_SPACES)
    if "buy" in spaces and not strategy_has_parameters(worst_strategy):
        print(f"Strategy {worst_strategy} has no parameters defined. Excluding 'buy' space.")
        spaces.remove("buy")

    print(f"Running Hyperopt for {worst_strategy} with spaces {spaces}...")
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
        *spaces,
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

    new_params = extract_hyperopt_params(result_hyperopt.stdout)

    if not new_params:
        print("Could not extract new parameters from hyperopt output.")
        if strategy_json.exists() and not created_new:
            shutil.move(backup_json, strategy_json)
        elif created_new and strategy_json.exists():
            strategy_json.unlink()
        sys.exit(1)

    stoploss = new_params.get("stoploss")
    if stoploss is not None and stoploss < -0.10:
        print(f"Start Optimization Failed: Stoploss {stoploss} is less than -0.10 limit.")
        if strategy_json.exists() and not created_new:
            shutil.move(backup_json, strategy_json)
        elif created_new and strategy_json.exists():
            strategy_json.unlink()
        sys.exit(1)

    print(f"Applying new parameters to {strategy_json}")
    with strategy_json.open("w") as f:
        json.dump(new_params, f, indent=4)

    # 3. Evaluation
    print("Running verification backtest with new parameters...")
    new_backtest_data = run_backtest_job(worst_strategy, extra_config=strategy_json)

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
    new_profit_pct = new_stats.get("profit_total_pct", 0.0) * 100

    print(f"New Sharpe: {new_sharpe}")
    print(f"New Drawdown: {new_drawdown}")

    sharpe_improved = new_sharpe > (current_sharpe * 1.05)
    drawdown_improved = new_drawdown < current_drawdown

    print(f"Sharpe Improved: {sharpe_improved}")
    print(f"Drawdown Improved: {drawdown_improved}")

    if sharpe_improved and drawdown_improved:
        print("Evaluation PASSED. Committing changes.")
        msg = f"perf: optimized {worst_strategy} (+{new_profit_pct:.2f}% ROI)"

        if args.dry_run:
            print("\n[DRY-RUN MODE] Would have committed and pushed:")
            print(f"  File: {strategy_json}")
            print(f"  Message: {msg}")
            print(f"  Branch: {args.branch}")
        else:
            target_branch = args.branch
            run_command(["git", "add", "-f", str(strategy_json)])
            run_command(["git", "commit", "-m", msg])

            if not args.yes:
                print(f"\nReady to push changes to branch '{target_branch}'")
                response = input("\nProceed with push? [y/N]: ").strip().lower()
                if response not in ["y", "yes"]:
                    print("Push cancelled. Changes are committed locally.")
                    if backup_json.exists():
                        backup_json.unlink()
                    return

            print(f"\nPushing to {target_branch}...")
            push_cmd = ["git", "push", "origin"]
            if target_branch == "main":
                push_cmd.append("HEAD:main")
            else:
                push_cmd.append(target_branch)

            result = run_command(push_cmd, capture=True)
            if result.returncode == 0:
                print(f"\n✓ Successfully pushed optimized strategy to branch: {target_branch}")
            else:
                print(f"\nFailed to push to {target_branch}")
                print(result.stderr)

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
