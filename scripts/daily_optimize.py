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


def run_command(cmd: list[str], capture: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess command."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=capture, text=True, check=False)
    if result.returncode != 0:
        print(f"Error running command: {result.stderr}")
    return result


def get_freqtrade_cmd() -> list[str]:
    """Return the base command to run freqtrade."""
    return [sys.executable, "-m", "freqtrade"]


def get_timerange() -> str:
    """Get the timerange for the last 30 days."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    return f"{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}"


def get_latest_backtest_file() -> Path | None:
    """Find the latest backtest result file."""
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


def read_backtest_result(filepath: Path) -> dict | None:
    """Read backtest result from a JSON or ZIP file."""
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


def find_worst_strategy(backtest_data: dict) -> tuple[str | None, float, dict | None]:
    """Find the strategy with the lowest Sharpe ratio."""
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


def get_all_strategy_names() -> list[str]:
    """Get all available strategy names from the strategies directory."""
    files = list(STRATEGIES_DIR.glob("*.py"))
    strategies = []
    for f in files:
        if f.stem != "__init__" and not f.stem.startswith("_"):
            strategies.append(f.stem)
    return strategies


def run_backtest_job(strategy_names: list[str]) -> dict | None:
    """Run backtest for the given strategies."""
    if not strategy_names:
        return None

    timerange = get_timerange()
    print(f"Running backtest for {strategy_names} over {timerange}...")
    cmd = get_freqtrade_cmd() + [
        "backtesting",
        "--config",
        str(CONFIG_FILE),
        "--timerange",
        timerange,
        "--timeframe",
        "1h",
        "--cache",
        "none",
        "--strategy-list",
        *strategy_names,
    ]

    run_command(cmd, capture=True)

    latest = get_latest_backtest_file()
    if latest:
        return read_backtest_result(latest)
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


def evaluate_improvement(
    current_sharpe: float, current_drawdown: float, new_sharpe: float, new_drawdown: float
) -> bool:
    """
    Evaluate if the new metrics are improved based on the rule:
    New_Sharpe > (Current_Sharpe * 1.05) AND New_Drawdown < Current_Drawdown.
    """
    sharpe_improved = new_sharpe > (current_sharpe * 1.05)
    drawdown_improved = new_drawdown < current_drawdown

    print(f"Sharpe: {current_sharpe:.4f} -> {new_sharpe:.4f} (Improved: {sharpe_improved})")
    print(f"Drawdown: {current_drawdown:.4f} -> {new_drawdown:.4f} (Improved: {drawdown_improved})")

    return sharpe_improved and drawdown_improved


def run_hyperopt(strategy_name: str) -> dict | None:
    """Run hyperopt for the strategy and return extracted params."""
    print(f"Running Hyperopt for {strategy_name}...")
    cmd_hyperopt = get_freqtrade_cmd() + [
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
        return None

    return extract_hyperopt_params(result_hyperopt.stdout)


def check_git_status() -> bool:
    """Check if the repository is in a clean state."""
    result = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, check=False
    )
    return result.returncode == 0 and not result.stdout.strip()


def commit_and_push(
    strategy_name: str, profit_pct: float, dry_run: bool = False, yes: bool = False
):
    """Commit changes and push to main."""
    msg = f"perf: optimized {strategy_name} (+{profit_pct:.2f}% ROI)"
    strategy_json = STRATEGIES_DIR / f"{strategy_name}.json"

    if dry_run:
        print("\n[DRY-RUN] Would commit and push:")
        print(f"  Files: {strategy_json}")
        print(f"  Message: {msg}")
        print("  Branch: HEAD:main")
        return

    # Git Add
    run_command(["git", "add", "-f", str(strategy_json)])

    # Git Commit
    run_command(["git", "commit", "-m", msg])

    # Git Push
    if not yes:
        response = input("\nProceed with push to main? [y/N]: ").strip().lower()
        if response not in ["y", "yes"]:
            print("Push cancelled.")
            return

    print("Pushing to origin main...")
    result = run_command(["git", "push", "origin", "HEAD:main"], capture=True)

    if result.returncode == 0:
        print("Successfully pushed to main.")
    else:
        print("Failed to push to main.")


def establish_baseline() -> tuple[str | None, float, float]:
    """
    Establish baseline metrics.
    Returns: (worst_strategy_name, current_sharpe, current_drawdown)
    """
    latest_file = get_latest_backtest_file()
    backtest_data = None
    all_strategies = get_all_strategy_names()

    if latest_file:
        print(f"Checking latest backtest file: {latest_file}")
        data = read_backtest_result(latest_file)
        if data:
            strategies_in_file = list(data.get("strategy", {}).keys())
            # Check if this is a partial result (e.g. from verification)
            if len(strategies_in_file) < len(all_strategies):
                print(
                    f"Latest file contains {len(strategies_in_file)} strategies, "
                    f"but {len(all_strategies)} are available."
                )
                print("Considering it a partial result. Ignoring.")
            else:
                print("Latest file covers all strategies. Using it as baseline.")
                backtest_data = data

    if not backtest_data:
        print("No valid full baseline found. Running initial backtest on all strategies...")
        if not all_strategies:
            print("No strategies found.")
            return None, 0.0, 0.0

        backtest_data = run_backtest_job(all_strategies)

    if not backtest_data:
        print("Failed to produce backtest baseline.")
        return None, 0.0, 0.0

    worst_strategy, current_sharpe, stats = find_worst_strategy(backtest_data)

    if not worst_strategy or stats is None:
        return None, 0.0, 0.0

    current_drawdown = stats.get("max_drawdown_account", 1.0)
    return worst_strategy, current_sharpe, current_drawdown


def process_optimization_result(
    worst_strategy: str,
    current_sharpe: float,
    current_drawdown: float,
    strategy_json: Path,
    backup_json: Path,
    created_new: bool,
    dry_run: bool,
    yes: bool,
):
    """Verify optimization results and commit if successful."""
    print("Running verification backtest...")
    new_backtest_data = run_backtest_job([worst_strategy])

    passed = False
    avg_profit_pct = 0.0

    if new_backtest_data:
        new_stats = new_backtest_data["strategy"].get(worst_strategy, {})
        new_sharpe = new_stats.get("sharpe", -float("inf"))
        new_drawdown = new_stats.get("max_drawdown_account", 1.0)
        avg_profit_pct = new_stats.get("profit_total_pct", 0.0) * 100

        if new_sharpe is not None:
            passed = evaluate_improvement(
                current_sharpe, current_drawdown, new_sharpe, new_drawdown
            )

    if passed:
        print("Evaluation PASSED. Committing changes.")
        commit_and_push(worst_strategy, avg_profit_pct, dry_run, yes)
        if backup_json.exists():
            backup_json.unlink()
    else:
        print("Evaluation FAILED. Reverting changes.")
        if not created_new:
            shutil.move(backup_json, strategy_json)
        elif created_new:
            if strategy_json.exists():
                strategy_json.unlink()


def main():
    parser = argparse.ArgumentParser(description="Daily Optimization Routine")
    parser.add_argument("--dry-run", action="store_true", help="Run without git changes")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    if not args.dry_run and not check_git_status():
        print("Repo has uncommitted changes. Commit or stash them first.")
        sys.exit(1)

    worst_strategy, current_sharpe, current_drawdown = establish_baseline()
    if not worst_strategy:
        print("Could not find a strategy to optimize.")
        sys.exit(1)

    print(f"Selected Strategy: {worst_strategy}")
    print(f"Current Sharpe: {current_sharpe}")
    print(f"Current Drawdown: {current_drawdown}")

    strategy_json = STRATEGIES_DIR / f"{worst_strategy}.json"
    backup_json = strategy_json.with_suffix(".json.bak")
    created_new = False

    if strategy_json.exists():
        shutil.copy(strategy_json, backup_json)
    else:
        created_new = True

    new_params = run_hyperopt(worst_strategy)

    if not new_params:
        if strategy_json.exists() and not created_new:
            shutil.move(backup_json, strategy_json)
        elif created_new and strategy_json.exists():
            strategy_json.unlink()
        sys.exit(1)

    print(f"Applying new parameters to {strategy_json}")
    with strategy_json.open("w") as f:
        json.dump(new_params, f, indent=4)

    process_optimization_result(
        worst_strategy,
        current_sharpe,
        current_drawdown,
        strategy_json,
        backup_json,
        created_new,
        args.dry_run,
        args.yes,
    )


if __name__ == "__main__":
    main()
