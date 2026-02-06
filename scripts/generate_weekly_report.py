#!/usr/bin/env python3
"""
Weekly Reporting Script
Aggregates optimization results and generates a weekly report.
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


# Configuration
REPO_ROOT = Path(__file__).resolve().parent.parent
OPTIMIZATION_LOG_FILE = REPO_ROOT / "optimization_log.txt"
REPORT_FILE = REPO_ROOT / "WEEKLY_REPORT.md"


def run_command(cmd, capture=True):
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"Error running command: {' '.join(cmd)}")
        print(result.stderr)
    return result


def get_weekly_commits():
    """
    Get commits from the last 7 days that improved performance.
    """
    # Look for commits starting with "perf: optimized" in the last 7 days
    cmd = [
        "git",
        "log",
        "--since=7 days ago",
        "--grep=perf: optimized",
        "--pretty=format:%h|%cd|%s",
        "--date=short",
    ]

    result = run_command(cmd)
    if result.returncode != 0:
        return []

    commits = []
    if not result.stdout.strip():
        return []

    for line in result.stdout.splitlines():
        parts = line.split("|")
        if len(parts) >= 3:
            commit_hash = parts[0]
            date = parts[1]
            message = parts[2]

            # Extract strategy name and ROI
            # Message format: perf: optimized {strategy} (+{roi}% ROI)
            match = re.search(r"perf: optimized\s+(\w+)\s+\(\+([\d\.]+)\%\s+ROI\)", message)
            if match:
                strategy = match.group(1)
                roi = float(match.group(2))
                commits.append(
                    {
                        "hash": commit_hash,
                        "date": date,
                        "strategy": strategy,
                        "roi": roi,
                        "message": message,
                    }
                )
            else:
                # Fallback if format is slightly different
                commits.append(
                    {
                        "hash": commit_hash,
                        "date": date,
                        "strategy": "Unknown",
                        "roi": 0.0,
                        "message": message,
                    }
                )

    return commits


def get_stuck_strategies():
    """
    Find strategies that failed optimization attempts in the last 7 days.
    """
    if not OPTIMIZATION_LOG_FILE.exists():
        return {}

    stuck_strategies = {}
    cutoff_date = datetime.now() - timedelta(days=7)

    with OPTIMIZATION_LOG_FILE.open("r") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 6:
                continue

            # Format: timestamp,strategy,outcome,sharpe,drawdown,message
            ts_str = parts[0]
            strategy = parts[1]
            outcome = parts[2]
            message = parts[5]

            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                continue

            if ts < cutoff_date:
                continue

            if outcome == "failure":
                if strategy not in stuck_strategies:
                    stuck_strategies[strategy] = []
                stuck_strategies[strategy].append(message)

    return stuck_strategies


def generate_report(commits, stuck_strategies):
    """
    Generate the Markdown report.
    """
    lines = []
    lines.append("# Weekly Strategy Optimization Report")
    lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n")

    # Section 1: Updated Strategies
    lines.append("## 1. Updated Strategies")
    if commits:
        lines.append("| Date | Strategy | ROI Improvement | Commit |")
        lines.append("|---|---|---|---|")
        for c in commits:
            lines.append(f"| {c['date']} | {c['strategy']} | +{c['roi']:.2f}% | {c['hash']} |")
    else:
        lines.append("No strategies were updated this week.")
    lines.append("")

    # Section 2: Total Estimated Improvement
    lines.append("## 2. Total Estimated Improvement")
    total_roi = sum(c["roi"] for c in commits)
    lines.append(f"**Total Portfolio ROI Improvement:** +{total_roi:.2f}%")
    lines.append("")

    # Section 3: Stuck Strategies
    lines.append("## 3. Stuck Strategies (Candidates for Deletion)")
    if stuck_strategies:
        lines.append("The following strategies failed to improve despite optimization attempts:")
        lines.append("")
        for strategy, reasons in stuck_strategies.items():
            unique_reasons = set(reasons)
            lines.append(
                f"- **{strategy}**: Failed {len(reasons)} times. "
                f"Reasons: {', '.join(unique_reasons)}"
            )
    else:
        lines.append("No stuck strategies detected this week.")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate weekly optimization report")
    parser.add_argument("--dry-run", action="store_true", help="Do not commit or push changes")
    args = parser.parse_args()

    print("Generating weekly report...")

    # Gather data
    commits = get_weekly_commits()
    stuck_strategies = get_stuck_strategies()

    # Generate content
    report_content = generate_report(commits, stuck_strategies)

    # Write file
    with REPORT_FILE.open("w") as f:
        f.write(report_content)

    print(f"Report written to {REPORT_FILE}")

    if args.dry_run:
        print("Dry run: Skipping git operations.")
        return

    # Commit and Push
    # Check if there are changes
    run_command(["git", "add", str(REPORT_FILE)])

    status = run_command(["git", "status", "--porcelain"])
    if not status.stdout.strip():
        print("No changes to report. Skipping commit.")
        return

    # Configure git identity for the commit
    run_command(["git", "config", "user.name", "github-actions[bot]"])
    run_command(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"])

    commit_msg = f"docs: update weekly report {datetime.now().strftime('%Y-%m-%d')}"
    run_command(["git", "commit", "-m", commit_msg])

    # Push to main
    print("Pushing report...")
    push_result = run_command(["git", "push", "origin", "HEAD:main"])

    if push_result.returncode == 0:
        print("Report pushed successfully.")
    else:
        print("Failed to push report.")
        sys.exit(1)


if __name__ == "__main__":
    main()
