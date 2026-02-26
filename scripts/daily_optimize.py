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
from datetime import UTC, datetime, timedelta
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


def run_command(cmd: list[str], capture: bool = True) -> subprocess.CompletedProcess:
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=capture, text=True, check=False)
        if result.returncode != 0:
            print(f"Error running command: {result.stderr}")
        return result
    except Exception as e:
        print(f"Exception running command: {e}")
        return subprocess.CompletedProcess(args=cmd, returncode=1, stderr=str(e))


def get_timerange() -> str:
    # Use UTC for consistency
    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=30)
    return f"{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}"


def get_latest_backtest_file() -> Path | None:
    if not BACKTEST_RESULTS_DIR.exists():
        return None
    last_result_file = BACKTEST_RESULTS_DIR / ".last_result.json"
    if last_result_file.exists():
        try:
            with last_result_file.open() as f:
                data = json.load(f)
                filename = data.get("latest_backtest")
                if filename:
                    return BACKTEST_RESULTS_DIR / filename
        except json.JSONDecodeError:
            pass

    files = list(BACKTEST_RESULTS_DIR.glob("backtest-result-*.zip"))
    if not files:
        files = list(BACKTEST_RESULTS_DIR.glob("backtest-result-*.json"))

    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)


def read_backtest_result(filepath: Path) -> dict | None:
    data = None
    try:
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
    except Exception as e:
        print(f"Error reading backtest result {filepath}: {e}")
        return None
    return data


def find_worst_strategy(backtest_data: dict) -> tuple[str | None, float, dict | None]:
    strategies = backtest_data.get("strategy", {})
    if not strategies:
        return None, -float("inf"), None

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


def find_available_strategies() -> list[str]:
    """Finds all available strategy files in the user_data/strategies directory."""
    files = list(STRATEGIES_DIR.glob("*.py"))
    strategies = []
    for f in files:
        if f.stem != "__init__" and not f.stem.startswith("_"):
            strategies.append(f.stem)
    return strategies


def run_backtest_job(
    strategy_name_or_list: str | list[str], extra_config: Path | None = None
) -> dict | None:
    """Runs a backtest job for a single strategy or a list of strategies."""
    timerange = get_timerange()

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


def check_git_status() -> bool:
    """
    Check if the repository is in a clean state before making changes.
    Returns True if clean, False otherwise.
    """
    result = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        print("Warning: Could not check git status")
        return False

    if result.stdout.strip():
        print("Error: Repository has uncommitted changes:")
        print(result.stdout)
        return False

    return True


def extract_hyperopt_params(output: str) -> dict:
    """
    Extracts the JSON parameters from the hyperopt output.
    Finds the last JSON object in the output which typically contains the best parameters.
    """
    lines = output.splitlines()
    json_str = ""
    started = False

    # Iterate backwards to find the last JSON block
    for line in reversed(lines):
        stripped = line.strip()
        if stripped == "}":
            started = True

        if started:
            json_str = line + "\n" + json_str
            if stripped == "{":
                try:
                    params = json.loads(json_str)
                    # We want the full config object (containing minimal_roi, params, etc.)
                    # Valid freqtrade hyperopt output should have 'params' or 'minimal_roi'
                    # or 'stoploss'
                    expected_keys = ("params", "minimal_roi", "stoploss", "trailing_stop")
                    if any(k in params for k in expected_keys):
                        return params
                except json.JSONDecodeError:
                    continue  # Keep looking if this wasn't valid JSON
    return {}


def main() -> None:  # noqa: C901
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
        help=("Target branch for pushing changes (default: main)"),
    )
    parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation prompts before pushing"
    )

    args = parser.parse_args()

    if not args.dry_run and not check_git_status():
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
        strategies = find_available_strategies()
        if not strategies:
            print("No strategy file found.")
            sys.exit(1)
        backtest_data = run_backtest_job(strategies)

    if not backtest_data:
        print("Failed to produce backtest baseline.")
        sys.exit(1)

    worst_strategy, current_sharpe, current_stats = find_worst_strategy(backtest_data)
    if not worst_strategy or not current_stats:
        print("No strategy found in backtest results.")
        sys.exit(1)

    current_drawdown = current_stats.get("max_drawdown_account", 1.0)
    current_trades = current_stats.get("total_trades", 0)

    print(f"Selected Strategy: {worst_strategy}")
    print(f"Current Sharpe: {current_sharpe}")
    print(f"Current Drawdown: {current_drawdown}")
    print(f"Current Trades: {current_trades}")

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
        if strategy_json.exists() and not created_new:
            shutil.move(backup_json, strategy_json)
        elif created_new and strategy_json.exists():
            strategy_json.unlink()
        sys.exit(1)

    # Apply new parameters
    # First check if Freqtrade generated the file (which it does in newer versions)
    file_updated_by_freqtrade = False
    if strategy_json.exists():
        try:
            with strategy_json.open() as f:
                json.load(f)
            file_updated_by_freqtrade = True
            print(f"Found updated parameter file at {strategy_json}")
        except Exception as e:
            print(f"Parameter file found but invalid: {e}")

    if not file_updated_by_freqtrade:
        # Fallback to extraction from stdout
        new_params = extract_hyperopt_params(result_hyperopt.stdout)
        if new_params:
            print(f"Applying new parameters to {strategy_json}")
            with strategy_json.open("w") as f:
                json.dump(new_params, f, indent=4)
        else:
            print("Could not extract new parameters from hyperopt output.")
            if strategy_json.exists() and not created_new:
                shutil.move(backup_json, strategy_json)
            elif created_new and strategy_json.exists():
                strategy_json.unlink()
            sys.exit(1)

    # 3. Evaluation (Verification Backtest)
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

    # Get profit % for commit message
    avg_profit_pct = new_stats.get("profit_total_pct", 0.0) * 100

    print(f"New Sharpe: {new_sharpe}")
    print(f"New Drawdown: {new_drawdown}")

    # Gatekeeper Logic
    if current_trades == 0:
        # If baseline had 0 trades, we accept if new sharpe is positive (profitable trades found)
        # We assume any profit is better than no trades.
        # We also check if drawdown is reasonable (e.g. not 100%)
        sharpe_improved = new_sharpe > 0
        drawdown_improved = new_drawdown < 1.0 # Reasonable sanity check
        print("Baseline had 0 trades. Using relaxed criteria.")
    else:
        sharpe_improved = new_sharpe > (current_sharpe * 1.05)
        # Relaxed drawdown check to allow same drawdown (e.g. 0 -> 0)
        drawdown_improved = new_drawdown <= current_drawdown

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
                print(f"  Branch: optimize-{datetime.now(UTC).strftime('%Y%m%d')}")
            print("\nNo changes were made. Use without --dry-run to apply changes.")
        else:
            target_branch = args.branch if args.branch else "main"

            run_command(["git", "add", "-f", str(strategy_json)])
            run_command(["git", "commit", "-m", msg])

            if args.yes:
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
                    print("Changes are committed locally.")
            else:
                 print("Skipping push (use --yes to push).")

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
