#!/usr/bin/env python3
"""
Weekly Reporting Script
Generates WEEKLY_REPORT.md from git logs and optimization logs.
"""

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


OPTIMIZATION_LOG = Path("optimization_log.txt")
REPORT_FILE = Path("WEEKLY_REPORT.md")


def run_command(cmd, capture=True):
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"Error running command: {' '.join(cmd)}")
        print(result.stderr)
    return result


def get_git_updates(days=7):
    """
    Parses git log for successful optimization commits in the last N days.
    Returns a list of dicts: {'strategy': str, 'roi_change': float, 'date': str, 'hash': str}
    """
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    cmd = [
        "git",
        "log",
        f"--since={since_date}",
        "--grep=perf: optimized",
        "--pretty=format:%H|%cd|%s",
        "--date=iso",
    ]

    result = run_command(cmd)
    if result.returncode != 0:
        return []

    updates = []
    # Regex to capture strategy name and ROI from commit message
    # Message format: "perf: optimized StrategyName (+1.23% ROI)"
    # Also handle negative ROI or other variations if possible, though daily_optimize
    # formats it strictly.
    # The regex needs to handle the literal plus sign if present.
    pattern = r"perf: optimized (\w+) \(\+?([+-]?[\d.]+)% ROI\)"

    for line in result.stdout.splitlines():
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 3:
            continue

        commit_hash = parts[0]
        date_str = parts[1]
        message = parts[2]

        match = re.search(pattern, message)
        if match:
            strategy = match.group(1)
            roi_change = float(match.group(2))
            updates.append(
                {
                    "strategy": strategy,
                    "roi_change": roi_change,
                    "date": date_str,
                    "hash": commit_hash,
                    "message": message,
                }
            )

    return updates


def get_optimization_attempts(days=7):
    """
    Parses optimization_log.txt for attempts in the last N days.
    Returns a list of dicts (the log entries).
    """
    if not OPTIMIZATION_LOG.exists():
        return []

    attempts = []
    cutoff_date = datetime.now() - timedelta(days=days)

    with OPTIMIZATION_LOG.open("r") as f:
        for line in f:
            try:
                entry = json.loads(line)
                timestamp_str = entry.get("timestamp")
                if timestamp_str:
                    # Handle ISO format
                    dt = datetime.fromisoformat(timestamp_str)
                    # Make dt naive for comparison with datetime.now()
                    if dt.tzinfo is not None:
                        dt = dt.replace(tzinfo=None)

                    if dt >= cutoff_date:
                        attempts.append(entry)
            except json.JSONDecodeError:
                continue
            except ValueError:
                continue  # parsing date error

    return attempts


def synthesize_report(updates, attempts):
    """
    Generates the markdown report content.
    """
    report_lines = []
    report_lines.append("# Weekly Strategy Optimization Report")
    report_lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}")
    report_lines.append("")

    # Section 1: Updated Strategies
    report_lines.append("## 1. Updated Strategies")
    if updates:
        report_lines.append("| Strategy | ROI Change | Date | Commit |")
        report_lines.append("|---|---|---|---|")
        for u in updates:
            # Format date for brevity
            short_date = u["date"].split("T")[0]
            report_lines.append(
                f"| {u['strategy']} | {u['roi_change']:+.2f}% | {short_date} | `{u['hash'][:7]}` |"
            )
    else:
        report_lines.append("No strategies were successfully updated this week.")
    report_lines.append("")

    # Section 2: Total ROI Improvement
    report_lines.append("## 2. Total Estimated Improvement in Portfolio ROI")
    total_roi = sum(u["roi_change"] for u in updates)
    report_lines.append(f"**Total ROI Improvement:** {total_roi:+.2f}%")
    report_lines.append(
        "> Note: This is the sum of estimated ROI improvements from "
        "individual strategy optimizations."
    )
    report_lines.append("")

    # Section 3: Stuck Strategies
    report_lines.append("## 3. Stuck Strategies (Candidates for Deletion)")

    # Identify strategies that failed to improve
    # We look at 'attempts' where status='failed'
    # Check if they had ANY success in 'updates' or 'attempts' with status='success'

    # Map strategy -> {'success': int, 'failed': int}
    strategy_stats = {}

    for a in attempts:
        strat = a.get("strategy")
        status = a.get("status")
        if strat not in strategy_stats:
            strategy_stats[strat] = {"success": 0, "failed": 0}

        if status == "success":
            strategy_stats[strat]["success"] += 1
        else:
            strategy_stats[strat]["failed"] += 1

    # Also verify against git updates (source of truth for success)
    for u in updates:
        strat = u["strategy"]
        if strat not in strategy_stats:
            strategy_stats[strat] = {"success": 0, "failed": 0}
        # If it's in git updates, it counts as a success, but might duplicate log
        # if log exists.
        # We rely on log if available, but if log is missing entries (e.g. older runs),
        # git log helps.
        # But 'attempts' comes from log file. If log file was just created, it might
        # be empty for past events.
        # So we just trust what we have.

    stuck_strategies = []
    for strat, stats in strategy_stats.items():
        if stats["failed"] > 0 and stats["success"] == 0:
            stuck_strategies.append((strat, stats["failed"]))

    if stuck_strategies:
        report_lines.append(
            "The following strategies failed to improve despite optimization attempts:"
        )
        report_lines.append("| Strategy | Failed Attempts |")
        report_lines.append("|---|---|")
        for strat, count in stuck_strategies:
            report_lines.append(f"| {strat} | {count} |")
    else:
        report_lines.append(
            "No completely stuck strategies detected this week (all attempted "
            "strategies had at least one success or were not attempted)."
        )

    report_lines.append("")
    return "\n".join(report_lines)


def main():
    print("Generating Weekly Report...")

    # 1. Parse Git Log
    updates = get_git_updates(days=7)
    print(f"Found {len(updates)} updates in git log.")

    # 2. Parse Optimization Log
    attempts = get_optimization_attempts(days=7)
    print(f"Found {len(attempts)} attempts in optimization log.")

    # 3. Synthesize Report
    content = synthesize_report(updates, attempts)

    # 4. Write Report
    with REPORT_FILE.open("w") as f:
        f.write(content)

    print(f"Report written to {REPORT_FILE}")

    # 5. Commit and Push
    # Check if file changed
    run_command(["git", "add", str(REPORT_FILE)])

    # Check if there are changes to commit
    status = run_command(["git", "status", "--porcelain"])
    if not status.stdout.strip():
        print("No changes to report.")
        return

    print("Committing and pushing report...")
    run_command(["git", "commit", "-m", "docs: update weekly report"])

    # Pull rebase to avoid conflicts
    current_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    run_command(["git", "pull", "--rebase", "origin", current_branch])

    push_cmd = ["git", "push", "origin", current_branch]
    if current_branch == "HEAD":
        # Likely in detached HEAD, push to main
        push_cmd = ["git", "push", "origin", "HEAD:main"]

    result = run_command(push_cmd)
    if result.returncode == 0:
        print("Successfully pushed report.")
    else:
        print("Failed to push report.")
        sys.exit(1)


if __name__ == "__main__":
    main()
