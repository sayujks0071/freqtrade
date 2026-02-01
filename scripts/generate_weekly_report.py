#!/usr/bin/env python3
"""
Weekly Reporting Script
Aggregates Git logs and optimization logs to generate a weekly report.
"""

import argparse
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


REPORT_FILE = Path("WEEKLY_REPORT.md")
LOG_FILE = Path("optimization_log.txt")


def run_command(cmd, capture=True):
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"Error running command: {' '.join(cmd)}")
        if result.stderr:
            print(result.stderr)
    return result


def get_git_commits(days=7):
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    cmd = [
        "git", "log",
        f"--since={since}",
        "--pretty=format:%s"
    ]
    result = run_command(cmd)
    if result.returncode == 0:
        return result.stdout.splitlines()
    return []


def get_optimization_logs(days=7):
    if not LOG_FILE.exists():
        return []

    cutoff = datetime.now() - timedelta(days=days)
    logs = []

    with LOG_FILE.open("r") as f:
        for line in f:
            try:
                entry = json.loads(line)
                entry_date = datetime.fromisoformat(entry["timestamp"])
                if entry_date >= cutoff:
                    logs.append(entry)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return logs


def generate_report(commits, logs):
    # Section 1: Strategies Updated
    updated_strategies = set()

    # From Git
    for commit in commits:
        if commit.startswith("perf: optimized"):
            # Extract strategy name "perf: optimized StrategyName (+...)"
            parts = commit.split()
            if len(parts) >= 3:
                updated_strategies.add(parts[2])

    # From Logs (Success)
    success_logs = [log_entry for log_entry in logs if log_entry.get("status") == "SUCCESS"]
    for log_entry in success_logs:
        updated_strategies.add(log_entry.get("strategy"))

    # Section 2: Portfolio ROI Improvement
    total_roi_improvement = 0.0
    for log_entry in success_logs:
        metrics = log_entry.get("metrics", {})
        total_roi_improvement += metrics.get("profit_pct", 0.0)

    # Section 3: Stuck Strategies
    # Failed attempts in the last week, AND no success in the last week.
    failed_logs = [log_entry for log_entry in logs if log_entry.get("status") == "FAILURE"]
    failed_strategies = set(log_entry.get("strategy") for log_entry in failed_logs)
    successful_strategies_week = set(log_entry.get("strategy") for log_entry in success_logs)

    stuck_strategies = failed_strategies - successful_strategies_week

    # Generate Markdown
    lines = []
    lines.append("# Weekly Optimization Report")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")

    lines.append("## 1. Strategies Updated")
    if updated_strategies:
        for s in sorted(list(updated_strategies)):
            lines.append(f"- {s}")
    else:
        lines.append("No strategies updated this week.")
    lines.append("")

    lines.append("## 2. Total Estimated Improvement in Portfolio ROI")
    lines.append(f"**{total_roi_improvement:.2f}%**")
    lines.append("")

    lines.append("## 3. Stuck Strategies (Candidates for Deletion)")
    lines.append("Strategies that failed to improve despite optimization attempts this week:")
    if stuck_strategies:
        for s in sorted(list(stuck_strategies)):
            # Count failures
            count = len([log_entry for log_entry in failed_logs if log_entry.get("strategy") == s])
            lines.append(f"- {s} ({count} failed attempts)")
    else:
        lines.append("None.")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate Weekly Optimization Report")
    parser.add_argument("--push", action="store_true", help="Commit and push the report")
    args = parser.parse_args()

    commits = get_git_commits()
    logs = get_optimization_logs()

    report_content = generate_report(commits, logs)

    with REPORT_FILE.open("w") as f:
        f.write(report_content)

    print(f"Report generated at {REPORT_FILE}")

    if args.push:
        # Check if file changed
        run_command(["git", "add", str(REPORT_FILE)])
        status = run_command(["git", "status", "--porcelain"])
        if str(REPORT_FILE) in status.stdout:
            print("Committing and pushing report...")
            run_command(["git", "commit", "-m", "docs: generate weekly optimization report"])
            run_command(["git", "push"])
        else:
            print("No changes to report.")


if __name__ == "__main__":
    main()
