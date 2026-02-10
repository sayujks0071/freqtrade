#!/usr/bin/env python3
"""
Weekly Reporting Script
Generates WEEKLY_REPORT.md from git log and optimization_log.txt
"""

import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


# Configuration
REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = REPO_ROOT / "optimization_log.txt"
REPORT_FILE = REPO_ROOT / "WEEKLY_REPORT.md"


def get_git_log_since(days=7):
    """
    Get git log messages since N days ago.
    Returns a list of commit messages.
    """
    # Use git log to get commits. We use --since="7 days ago" which is more robust than
    # manual date calculation but specific date format is fine too.
    # Note: running in CI might have shallow clone.
    # Checkout step usually handles this with fetch-depth: 0.

    cmd = ["git", "log", f"--since={days} days ago", "--pretty=format:%s", "--no-merges"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running git log: {result.stderr}")
        return []
    return result.stdout.splitlines()


def parse_updated_strategies(commit_messages):
    """
    Parses commit messages to find updated strategies and ROI improvements.
    Format expected: "perf: optimized {strategy} (+{roi}% ROI)"
    Returns: List of dicts with 'strategy' and 'roi_change'
    """
    updates = []
    # Regex to match: perf: optimized StrategyName (+5.20% ROI improvement)
    # capturing group 1: StrategyName
    # capturing group 2: +5.20 or -1.5 etc.
    pattern = re.compile(r"perf: optimized\s+(\w+)\s+\(([\+\-]?[\d\.]+)[%]?\s+ROI\s+improvement\)")

    for msg in commit_messages:
        match = pattern.search(msg)
        if match:
            strategy = match.group(1)
            try:
                roi_change = float(match.group(2))
                updates.append({"strategy": strategy, "roi_change": roi_change})
            except ValueError:
                continue
    return updates


def parse_stuck_strategies(log_file, days=7):
    """
    Parses optimization_log.txt to find strategies that failed optimization.
    Returns a set of strategy names.
    """
    if not log_file.exists():
        return set()

    stuck = set()
    cutoff_date = datetime.now() - timedelta(days=days)

    # Format: Date | Strategy | Outcome | ...
    # 2023-10-27 10:00:00 | Strategy: MyStrat | Outcome: FAILURE | ...

    with log_file.open("r") as f:
        for line in f:
            # Robust parsing using substring search
            if not line.strip():
                continue

            # Parse Date
            try:
                # Date is usually at the start, up to first pipe
                date_str = line.split("|")[0].strip()
                entry_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            except (ValueError, IndexError):
                continue

            if entry_date < cutoff_date:
                continue

            # Parse Strategy
            strategy_match = re.search(r"Strategy:\s*([^|]+)", line)
            if not strategy_match:
                continue
            strategy = strategy_match.group(1).strip()

            # Parse Outcome
            outcome_match = re.search(r"Outcome:\s*([^|]+)", line)
            if not outcome_match:
                continue
            outcome = outcome_match.group(1).strip()

            if outcome == "FAILURE":
                stuck.add(strategy)
            elif outcome == "SUCCESS":
                # If it succeeded later in the week, remove it from stuck
                if strategy in stuck:
                    stuck.remove(strategy)

    return stuck


def generate_report(updates, stuck_strategies):
    """Generates the Markdown report."""
    total_roi_improvement = sum(u["roi_change"] for u in updates)

    lines = []
    lines.append("# Weekly Strategy Optimization Report")
    lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")

    lines.append("## Section 1: Updated Strategies")
    if updates:
        for u in updates:
            lines.append(f"- **{u['strategy']}**: {u['roi_change']:+.2f}% ROI")
    else:
        lines.append("No strategies were updated this week.")
    lines.append("")

    lines.append("## Section 2: Total Estimated Improvement")
    lines.append(f"**Total Portfolio ROI Improvement:** {total_roi_improvement:+.2f}%")
    lines.append("")

    lines.append("## Section 3: Stuck Strategies")
    lines.append(
        "Strategies that failed to improve despite optimization attempts (candidates for deletion):"
    )
    if stuck_strategies:
        for s in sorted(stuck_strategies):
            lines.append(f"- {s}")
    else:
        lines.append("No strategies are currently stuck.")
    lines.append("")

    return "\n".join(lines)


def main():
    print("Generating Weekly Report...")

    # 1. Parse Git Log
    git_commits = get_git_log_since(days=7)
    updates = parse_updated_strategies(git_commits)

    # 2. Parse Optimization Log
    stuck_strategies = parse_stuck_strategies(LOG_FILE, days=7)

    # 3. Generate Report
    report_content = generate_report(updates, stuck_strategies)

    # 4. Write to file
    with REPORT_FILE.open("w") as f:
        f.write(report_content)

    print(f"Report generated at {REPORT_FILE}")


if __name__ == "__main__":
    main()
