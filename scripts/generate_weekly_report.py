#!/usr/bin/env python3
"""
Weekly Report Generator
"""

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

USER_DATA_DIR = Path("user_data")
LOG_FILE = USER_DATA_DIR / "optimization_log.txt"
REPORT_FILE = Path("WEEKLY_REPORT.md")


def get_git_commits(days=7):
    """Get git commits from the last N days."""
    # Use git log to find commits since N days ago
    # We use relative date for simplicity with git log
    cmd = [
        "git",
        "log",
        f"--since={days}.days.ago",
        "--pretty=format:%h|%ad|%s",
        "--date=iso",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        commits = []
        for line in result.stdout.splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append(
                    {"hash": parts[0], "date": parts[1], "message": parts[2]}
                )
        return commits
    except subprocess.CalledProcessError as e:
        print(f"Error getting git log: {e}")
        return []


def parse_optimization_log(days=7):
    """Parse the optimization log file."""
    if not LOG_FILE.exists():
        return []

    entries = []
    # Use naive datetime for comparison as daily_optimize.py uses datetime.now() (naive)
    cutoff_date = datetime.now() - timedelta(days=days)

    with LOG_FILE.open("r") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                ts_str = entry.get("timestamp")
                if ts_str:
                    # fromisoformat handles simple ISO strings
                    ts = datetime.fromisoformat(ts_str)
                    # If ts is aware (unlikely from daily_optimize), make cutoff aware or strip tz
                    if ts.tzinfo is not None and cutoff_date.tzinfo is None:
                        ts = ts.replace(tzinfo=None)

                    if ts >= cutoff_date:
                        entries.append(entry)
            except json.JSONDecodeError:
                continue
    return entries


def generate_report():
    commits = get_git_commits()
    log_entries = parse_optimization_log()

    # Section 1: Updated Strategies
    updated_strategies = set()

    # From log
    for entry in log_entries:
        if entry.get("status") == "success":
            updated_strategies.add(entry.get("strategy"))

    # From git (fallback or cross-check)
    for commit in commits:
        msg = commit["message"]
        if msg.startswith("perf: optimized"):
            # Extract strategy name: "perf: optimized StrategyName (+...)"
            parts = msg.split(" ")
            if len(parts) >= 3:
                updated_strategies.add(parts[2])

    # Section 2: Total ROI Improvement
    total_roi_improvement = 0.0
    for entry in log_entries:
        if entry.get("status") == "success":
            total_roi_improvement += entry.get("roi_change", 0.0)

    # Section 3: Stuck Strategies
    # Strategies that failed and never succeeded in the period
    failed_attempts = set()
    successful_attempts = set()

    for entry in log_entries:
        strategy = entry.get("strategy")
        if entry.get("status") == "success":
            successful_attempts.add(strategy)
        elif entry.get("status") == "failed":
            failed_attempts.add(strategy)

    stuck_strategies = failed_attempts - successful_attempts

    # Generate Markdown
    report_lines = [
        "# Weekly Strategy Report",
        f"\n**Date:** {datetime.now().strftime('%Y-%m-%d')}",
        "\n## 1. Updated Strategies",
    ]

    if updated_strategies:
        for s in sorted(updated_strategies):
            report_lines.append(f"- {s}")
    else:
        report_lines.append("No strategies were updated this week.")

    report_lines.append("\n## 2. Total Estimated Improvement in Portfolio ROI")
    # Convert raw decimal to percentage
    report_lines.append(f"**{total_roi_improvement * 100:+.2f}%**")

    report_lines.append("\n## 3. Stuck Strategies (Candidates for Deletion)")
    if stuck_strategies:
        report_lines.append("The following strategies failed to improve despite optimization attempts:")
        for s in sorted(stuck_strategies):
            report_lines.append(f"- {s}")
    else:
        report_lines.append("No stuck strategies identified.")

    with REPORT_FILE.open("w") as f:
        f.write("\n".join(report_lines) + "\n")

    print(f"Report generated: {REPORT_FILE}")


if __name__ == "__main__":
    generate_report()
