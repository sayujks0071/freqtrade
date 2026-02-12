#!/usr/bin/env python3
"""
Weekly Reporting Script
Generates WEEKLY_REPORT.md based on git log and optimization_log.txt
"""

import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


# Configuration
USER_DATA_DIR = Path("user_data")
LOG_FILE = USER_DATA_DIR / "logs/optimization_log.txt"
REPORT_FILE = Path("WEEKLY_REPORT.md")


def run_command(cmd, capture=True):
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"Error running command: {result.stderr}")
    return result


def get_git_log_updates(days=7):
    """
    Get strategies updated in the last N days from git log.
    Returns a list of dicts: {'strategy': str, 'roi_change': float, 'message': str, 'date': str}
    """
    # Use format: hash|date|subject
    # We use --since to filter by time
    cmd = [
        "git",
        "log",
        f"--since={days} days ago",
        "--pretty=format:%h|%ad|%s",
        "--date=short",
    ]
    result = run_command(cmd)

    updates = []
    if result.returncode == 0 and result.stdout:
        lines = result.stdout.splitlines()
        for line in lines:
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue

            commit_hash, date, subject = parts

            # Pattern: perf: optimized {strategy} (+{roi}% ROI)
            # Example: perf: optimized MyStrategy (+2.50% ROI)
            match = re.search(r"perf: optimized\s+(\w+)\s+\(\+?([0-9.-]+)% ROI\)", subject)
            if match:
                strategy = match.group(1)
                roi_change = float(match.group(2))
                updates.append(
                    {
                        "strategy": strategy,
                        "roi_change": roi_change,
                        "message": subject,
                        "date": date,
                        "hash": commit_hash,
                    }
                )
    return updates


def _process_log_line(line, strategies_status, cutoff_date):
    """
    Helper function to process a single line from the optimization log.
    """
    line = line.strip()
    if not line:
        return

    # Format: TIMESTAMP|STRATEGY|STATUS|ROI_IMPROVEMENT|SHARPE_OLD|SHARPE_NEW|DD_OLD|DD_NEW
    parts = line.split("|")
    if len(parts) < 3:
        return

    try:
        timestamp_str = parts[0]
        strategy = parts[1]
        status = parts[2]

        timestamp = datetime.fromisoformat(timestamp_str)

        if timestamp >= cutoff_date:
            if strategy not in strategies_status:
                strategies_status[strategy] = {"success": False, "failed": False}

            if status == "SUCCESS":
                strategies_status[strategy]["success"] = True
            elif status == "FAILED":
                strategies_status[strategy]["failed"] = True
    except ValueError:
        return


def parse_optimization_log(days=7):
    """
    Parse optimization_log.txt to find stuck strategies.
    Stuck = Failed in the last N days and NO success in the last N days.
    Returns a list of stuck strategy names.
    """
    if not LOG_FILE.exists():
        print(f"Log file not found: {LOG_FILE}")
        return []

    cutoff_date = datetime.now() - timedelta(days=days)

    strategies_status = {}  # strategy -> {'success': bool, 'failed': bool}

    with LOG_FILE.open("r") as f:
        for line in f:
            _process_log_line(line, strategies_status, cutoff_date)

    stuck_strategies = []
    for strategy, status in strategies_status.items():
        if status["failed"] and not status["success"]:
            stuck_strategies.append(strategy)

    return stuck_strategies


def generate_report(updates, stuck_strategies):
    """Generates the Markdown report."""

    total_roi_improvement = sum(u["roi_change"] for u in updates)

    content = [
        f"# Weekly Strategy Report - {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "## 1. Updated Strategies",
        "",
    ]

    if updates:
        content.append("| Date | Strategy | ROI Improvement | Commit |")
        content.append("|---|---|---|---|")
        for u in updates:
            content.append(
                f"| {u['date']} | {u['strategy']} | {u['roi_change']:+.2f}% | {u['hash']} |"
            )
    else:
        content.append("No strategies were updated this week.")

    content.append("")
    content.append("## 2. Total Estimated Improvement in Portfolio ROI")
    content.append("")
    content.append(f"**Total Improvement: {total_roi_improvement:+.2f}%**")

    content.append("")
    content.append("## 3. Stuck Strategies (Candidates for Deletion)")
    content.append("")
    content.append("Strategies that failed to improve despite optimization attempts this week:")
    content.append("")

    if stuck_strategies:
        for s in stuck_strategies:
            content.append(f"- {s}")
    else:
        content.append("No stuck strategies found.")

    content.append("")

    with REPORT_FILE.open("w") as f:
        f.write("\n".join(content))

    print(f"Report generated: {REPORT_FILE}")


def main():
    print("Generating weekly report...")
    updates = get_git_log_updates()
    stuck_strategies = parse_optimization_log()
    generate_report(updates, stuck_strategies)
    print("Done.")


if __name__ == "__main__":
    main()
