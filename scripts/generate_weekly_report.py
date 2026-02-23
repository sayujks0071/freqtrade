#!/usr/bin/env python3
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


USER_DATA_DIR = Path("user_data")
LOG_FILE = USER_DATA_DIR / "optimization_log.txt"
REPORT_FILE = Path("WEEKLY_REPORT.md")


def get_reporting_period():
    today = datetime.now()
    # Align to the nearest past Sunday 00:00
    # weekday(): Mon=0, Sun=6.
    # (today.weekday() + 1) % 7 gives days since Sunday.
    days_since_sunday = (today.weekday() + 1) % 7

    end_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = end_date - timedelta(days=days_since_sunday)

    start_date = end_date - timedelta(days=7)

    return start_date, end_date


def run_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running command {' '.join(cmd)}: {result.stderr}")
        return ""
    return result.stdout


def get_git_changes(start_date, end_date):
    # Format dates for git
    since = start_date.strftime("%Y-%m-%d %H:%M:%S")
    until = end_date.strftime("%Y-%m-%d %H:%M:%S")

    cmd = [
        "git",
        "log",
        f"--since={since}",
        f"--until={until}",
        "--name-only",
        "--pretty=format:COMMIT:%H|%an|%s",
    ]

    output = run_command(cmd)

    changes = []
    current_commit = None

    for line in output.splitlines():
        if line.startswith("COMMIT:"):
            parts = line[7:].split("|", 2)
            if len(parts) == 3:
                current_commit = {
                    "hash": parts[0],
                    "author": parts[1],
                    "message": parts[2],
                    "files": [],
                }
                changes.append(current_commit)
        elif line.strip() and current_commit:
            current_commit["files"].append(line.strip())

    return changes


def _process_log_line(current_run, line):
    current_run["content"].append(line)
    strat_match = re.search(r"Selected Strategy: (\w+)", line)
    if strat_match:
        strategy = strat_match.group(1)
        current_run["current_strategy"] = strategy
        if strategy not in current_run["strategies"]:
            current_run["strategies"][strategy] = "UNKNOWN"

    if "Evaluation PASSED" in line:
        if "current_strategy" in current_run:
            current_run["strategies"][current_run["current_strategy"]] = "PASSED"
    elif "Evaluation FAILED" in line:
        if "current_strategy" in current_run:
            current_run["strategies"][current_run["current_strategy"]] = "FAILED"


def _extract_runs(content):
    runs = []
    current_run = {}
    # Regex for start of run
    # Matches: Running: ... --timerange 20231001-20231008 ...
    run_start_re = re.compile(r"Running: .*--timerange \d{8}-(\d{8})")

    for line in content.splitlines():
        match = run_start_re.search(line)
        if match:
            run_date_str = match.group(1)
            try:
                run_date = datetime.strptime(run_date_str, "%Y%m%d")
            except ValueError:
                continue

            current_run = {
                "date": run_date,
                "strategies": {},  # Map strategy -> status
                "content": [],
            }
            runs.append(current_run)

        if current_run:
            _process_log_line(current_run, line)
    return runs


def parse_optimization_log(start_date, end_date):
    if not LOG_FILE.exists():
        print(f"Log file {LOG_FILE} not found.")
        return {}

    content = LOG_FILE.read_text()
    runs = _extract_runs(content)

    # Filter runs within period
    relevant_runs = [r for r in runs if start_date <= r["date"] < end_date]

    strategy_status = {}

    for run in relevant_runs:
        for strat, status in run["strategies"].items():
            if strat not in strategy_status:
                strategy_status[strat] = {"PASSED": 0, "FAILED": 0}
            strategy_status[strat][status] += 1

    return strategy_status


def generate_report(start_date, end_date, git_changes, strategy_stats):
    updated_strategies = set()
    roi_improvements = []

    roi_re = re.compile(r"\+([\d.]+)% ROI")

    for commit in git_changes:
        # Check if strategy file modified
        is_strategy = False
        for f in commit["files"]:
            if f.startswith("user_data/strategies/") and (f.endswith(".json") or f.endswith(".py")):
                # Strategy param update
                updated_strategies.add(Path(f).stem)
                is_strategy = True

        if is_strategy:
            match = roi_re.search(commit["message"])
            if match:
                roi_improvements.append(float(match.group(1)))

    total_roi = sum(roi_improvements)

    # Stuck strategies: Failed at least once and Passed 0 times in this period.
    stuck_strategies = []
    for strat, stats in strategy_stats.items():
        if stats["FAILED"] > 0 and stats["PASSED"] == 0:
            stuck_strategies.append(strat)

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    report = "# Weekly Strategy Report\n\n"
    report += f"**Period:** {start_str} to {end_str}\n\n"

    report += "## 1. Updated Strategies\n"
    if updated_strategies:
        for s in sorted(updated_strategies):
            report += f"- {s}\n"
    else:
        report += "No strategies updated this week.\n"
    report += "\n"

    report += "## 2. Portfolio ROI Improvement\n"
    report += f"Total estimated improvement: **+{total_roi:.2f}%**\n\n"

    report += "## 3. Stuck Strategies (Candidates for Deletion)\n"
    if stuck_strategies:
        report += "The following strategies failed to improve despite optimization attempts:\n"
        for s in sorted(stuck_strategies):
            report += f"- {s} ({strategy_stats[s]['FAILED']} failures)\n"
    else:
        report += "No stuck strategies found.\n"

    return report


def main():
    start_date, end_date = get_reporting_period()
    print(f"Generating report for {start_date} to {end_date}")

    git_changes = get_git_changes(start_date, end_date)
    strategy_stats = parse_optimization_log(start_date, end_date)

    report_content = generate_report(start_date, end_date, git_changes, strategy_stats)

    with REPORT_FILE.open("w") as f:
        f.write(report_content)

    print(f"Report written to {REPORT_FILE}")


if __name__ == "__main__":
    main()
