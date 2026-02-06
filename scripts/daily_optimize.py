#!/usr/bin/env python3
"""
Daily Optimization Routine.
"""

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone
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


def get_timerange() -> str:
    """Get the timerange for the last 30 days."""
    end_date = datetime.now(tz=timezone.utc)  # noqa: UP017
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
    """Read backtest results from a file."""
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
                with z.open(target_file) as f_obj:
                    data = json.load(f_obj)
    else:
        with filepath.open() as f_obj:
            data = json.load(f_obj)
    return data


def find_all_strategies() -> list[str]:
    """Find all strategy names in the user_data/strategies directory."""
    files = list(STRATEGIES_DIR.glob("*.py"))
    strategies = []
    for f in files:
        if f.stem != "__init__" and not f.stem.startswith("_"):
            strategies.append(f.stem)
    return strategies


def run_backtest_job(strategies: list[str]) -> dict | None:
    """Run a backtest for the specified strategies."""
    timerange = get_timerange()
    strategy_args = strategies
    print(f"Running backtest for {strategy_args} over {timerange}...")

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
        "--strategy-list",
        *strategy_args,
    ]

    result = run_command(cmd, capture=True)
    if result.returncode != 0:
        print("Backtest failed.")
        print(result.stderr)
        return None

    latest = get_latest_backtest_file()
    if latest:
        return read_backtest_result(latest)
    return None


def establish_baseline() -> dict | None:
    """Establish a baseline backtest covering all available strategies."""
    available_strategies = find_all_strategies()
    if not available_strategies:
        print("No strategy files found.")
        return None

    latest_file = get_latest_backtest_file()
    backtest_data = None

    if latest_file:
        print(f"Checking latest backtest file: {latest_file}")
        backtest_data = read_backtest_result(latest_file)

    # Check if all strategies are in the baseline
    missing_strategies = []
    if backtest_data:
        # Use .keys() directly on the dictionary if 'strategy' key exists, else empty
        ran_strategies = list(backtest_data.get("strategy", {}).keys())
        missing_strategies = [s for s in available_strategies if s not in ran_strategies]
    else:
        missing_strategies = available_strategies

    if missing_strategies:
        print(f"Baseline incomplete. Missing: {missing_strategies}. Running full backtest...")
        return run_backtest_job(available_strategies)

    return backtest_data


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


def extract_hyperopt_params(output: str) -> dict:
    """Extract JSON parameters from hyperopt output."""
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


def run_hyperopt(strategy_name: str) -> dict | None:
    """Run hyperopt for the specified strategy."""
    print(f"Running Hyperopt for {strategy_name}...")
    cmd_hyperopt = [
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

    result = run_command(cmd_hyperopt, capture=True)
    if result.returncode != 0:
        print("Hyperopt failed.")
        print(result.stderr)
        return None

    return extract_hyperopt_params(result.stdout)


def verify_improvement(
    strategy_name: str, current_sharpe: float, current_drawdown: float
) -> tuple[bool, float, float]:
    """Verify if the new parameters improve the strategy."""
    print("Running verification backtest with new parameters...")
    new_backtest_data = run_backtest_job([strategy_name])

    if not new_backtest_data:
        return False, -float("inf"), 1.0

    new_stats = new_backtest_data["strategy"][strategy_name]
    new_sharpe = new_stats.get("sharpe", -float("inf"))
    if new_sharpe is None:
        new_sharpe = -float("inf")
    new_drawdown = new_stats.get("max_drawdown_account", 1.0)

    profit_pct = new_stats.get("profit_total_pct", 0.0) * 100

    print(f"New Sharpe: {new_sharpe} (Target: > {current_sharpe * 1.05})")
    print(f"New Drawdown: {new_drawdown} (Target: < {current_drawdown})")

    sharpe_improved = new_sharpe > (current_sharpe * 1.05)
    drawdown_improved = new_drawdown < current_drawdown

    if sharpe_improved and drawdown_improved:
        return True, profit_pct, new_sharpe

    return False, profit_pct, new_sharpe


def commit_and_push(strategy_file: Path, msg: str, dry_run: bool) -> None:
    """Commit and push changes to git."""
    if dry_run:
        print("\n[DRY-RUN MODE] Would have committed and pushed:")
        print(f"  File: {strategy_file}")
        print(f"  Message: {msg}")
        return

    # Use -f to force add in case user_data is gitignored
    run_command(["git", "add", "-f", str(strategy_file)])

    # Commit only the strategy file to avoid committing unrelated staged changes
    run_command(["git", "commit", "-m", msg, str(strategy_file)])

    print("\nPushing to origin main...")
    # Use HEAD:main to handle detached HEAD state in CI
    result = run_command(["git", "push", "origin", "HEAD:main"], capture=True)

    if result.returncode == 0:
        print("\n✓ Successfully pushed optimized strategy to main.")
    else:
        print("\nFailed to push to main.")
        print(result.stderr)


def process_strategy_optimization(
    worst_strategy: str, current_sharpe: float, current_drawdown: float, dry_run: bool
) -> None:
    """Orchestrate the optimization process for a single strategy."""
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

    improved, profit_pct, _ = verify_improvement(worst_strategy, current_sharpe, current_drawdown)

    if improved:
        print("Evaluation PASSED. Committing changes.")
        msg = f"perf: optimized {worst_strategy} (+{profit_pct:.2f}% ROI)"
        commit_and_push(strategy_json, msg, dry_run)
        if backup_json.exists():
            backup_json.unlink()
    else:
        print("Evaluation FAILED. Reverting changes.")
        if not created_new:
            shutil.move(backup_json, strategy_json)
        else:
            if strategy_json.exists():
                strategy_json.unlink()


def main() -> None:
    """Main execution entry point."""
    parser = argparse.ArgumentParser(description="Daily Optimization Routine")
    parser.add_argument("--dry-run", action="store_true", help="Run without pushing")
    args = parser.parse_args()

    backtest_data = establish_baseline()
    if not backtest_data:
        print("Failed to establish baseline.")
        sys.exit(1)

    worst_strategy, current_sharpe, current_stats = find_worst_strategy(backtest_data)
    if not worst_strategy or not current_stats:
        print("No strategy found in baseline.")
        sys.exit(1)

    current_drawdown = current_stats.get("max_drawdown_account", 1.0)
    print(f"Selected Strategy: {worst_strategy}")
    print(f"Current Sharpe: {current_sharpe}")
    print(f"Current Drawdown: {current_drawdown}")

    process_strategy_optimization(worst_strategy, current_sharpe, current_drawdown, args.dry_run)


if __name__ == "__main__":
    main()
