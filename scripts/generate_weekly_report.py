#!/usr/bin/env python3
"""
Weekly Reporting Script
Aggregates optimization logs and git commit history to generate a weekly report.
"""

import re
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


# Configuration
USER_DATA_DIR = Path("user_data")
OPTIMIZATION_LOG = USER_DATA_DIR / "optimization_log.txt"
REPORT_FILE = Path("WEEKLY_REPORT.md")


def run_command(cmd, capture=True):
    """Run a shell command."""
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"Error running command: {' '.join(cmd)}\n{result.stderr}")
    return result


def parse_git_log(days=7):
    """
    Parses git log for the last `days` days.
    Returns a list of commit messages.
    """
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    cmd = ["git", "log", f"--since={since_date}", "--pretty=format:%s"]
    result = run_command(cmd)
    if result.returncode == 0:
        return result.stdout.splitlines()
    return []


def parse_optimization_log(days=7):
    """
    Parses the optimization log file.
    Returns a dictionary of strategy statuses.
    """
    if not OPTIMIZATION_LOG.exists():
        return {}

    content = OPTIMIZATION_LOG.read_text(encoding="utf-8")

    # Pattern to match the start of a log entry
    # Group 1: Timestamp
    entry_pattern = re.compile(
        r"^--- Optimization Run Started: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ---", re.MULTILINE
    )

    matches = list(entry_pattern.finditer(content))
    cutoff_date = datetime.now() - timedelta(days=days)

    strategy_status = defaultdict(list)

    for i, match in enumerate(matches):
        timestamp_str = match.group(1)
        try:
            block_date = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

        if block_date < cutoff_date:
            continue

        # Extract content for this block
        start_idx = match.end()  # Start after the matched header

        if i + 1 < len(matches):
            end_idx = matches[i + 1].start()
        else:
            end_idx = len(content)

        block_content = content[start_idx:end_idx]

        # Analyze block content
        match_strategy = re.search(r"Selected Strategy: (.+)", block_content)
        if match_strategy:
            strategy_name = match_strategy.group(1).strip()

            # Check for failure or success
            if "Evaluation FAILED" in block_content:
                strategy_status[strategy_name].append("FAILED")
            elif "Evaluation PASSED" in block_content:
                strategy_status[strategy_name].append("PASSED")

    return strategy_status


def generate_report():
    """Generates the WEEKLY_REPORT.md file."""
    print("Generating Weekly Report...")

    commits = parse_git_log()
    strategy_logs = parse_optimization_log()

    # Section 1: Updated Strategies & ROI
    updated_strategies = []
    total_roi = 0.0

    # Regex to match: perf: optimized <strategy> (+<roi>% ROI)
    roi_pattern = re.compile(r"perf: optimized (.+) \(\+([\d.]+)% ROI\)")

    for msg in commits:
        match = roi_pattern.search(msg)
        if match:
            strategy = match.group(1)
            roi = float(match.group(2))
            updated_strategies.append((strategy, roi))
            total_roi += roi

    # Section 3: Stuck Strategies
    stuck_strategies = []
    for strategy, statuses in strategy_logs.items():
        # Definition of stuck: > 3 failures and NO passes in the last week
        failures = statuses.count("FAILED")
        passes = statuses.count("PASSED")

        if failures > 3 and passes == 0:
            stuck_strategies.append(strategy)

    # Write Report
    with REPORT_FILE.open("w", encoding="utf-8") as f:
        f.write(f"# Weekly Strategy Report ({datetime.now().strftime('%Y-%m-%d')})\n\n")

        f.write("## 1. Updated Strategies\n")
        if updated_strategies:
            f.write("| Strategy | ROI Improvement |\n")
            f.write("| :--- | :--- |\n")
            for strategy, roi in updated_strategies:
                f.write(f"| {strategy} | +{roi:.2f}% |\n")
        else:
            f.write("No strategies were updated this week.\n")
        f.write("\n")

        f.write("## 2. Total Estimated Improvement\n")
        f.write(f"**Total Portfolio ROI Improvement:** +{total_roi:.2f}%\n\n")

        f.write("## 3. Stuck Strategies\n")
        if stuck_strategies:
            f.write(
                "The following strategies have failed optimization repeatedly (>3 times) "
                "without success and are candidates for deletion:\n\n"
            )
            for strategy in stuck_strategies:
                f.write(f"- {strategy}\n")
        else:
            f.write("No stuck strategies identified.\n")

    print(f"Report generated: {REPORT_FILE}")


def commit_and_push():
    """Commits and pushes the report."""
    if not REPORT_FILE.exists():
        print("Report file not found. Skipping commit.")
        return

    print("Committing and pushing report...")

    # Git add
    run_command(["git", "add", str(REPORT_FILE)])

    # Git commit
    msg = f"docs: generate weekly report for {datetime.now().strftime('%Y-%m-%d')}"
    run_command(["git", "commit", "-m", msg])

    # Git push
    # We push to the current branch. In CI, this might be detached HEAD, so we need to be careful.
    # We assume we are pushing to origin main.
    run_command(["git", "push", "origin", "HEAD:main"])


if __name__ == "__main__":
    generate_report()
    commit_and_push()
