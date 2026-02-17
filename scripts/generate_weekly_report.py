#!/usr/bin/env python3
"""
Weekly Reporting Script
Aggregates optimization logs and git commit history to generate a weekly report.
"""

import argparse
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


# Configuration
LOG_FILE = Path("optimization_log.txt")
REPORT_FILE = Path("WEEKLY_REPORT.md")
DAYS_LOOKBACK = 7

def run_command(cmd, capture=True):
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"Error running command: {result.stderr}")
    return result

def get_git_log(days=7):
    """
    Parses git log for 'perf: optimized' messages in the last N days.
    Returns a list of dicts: {'strategy': str, 'roi': float, 'hash': str, 'date': str}
    """
    since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    cmd = [
        "git", "log",
        f"--since={since_date}",
        "--pretty=format:%H|%ad|%s",
        "--date=short"
    ]
    result = run_command(cmd)
    commits = []

    if result.returncode == 0:
        for line in result.stdout.splitlines():
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue

            commit_hash, date, msg = parts
            # Match message: perf: optimized {StrategyName} (+{ROI}% ROI)
            match = re.search(r"perf: optimized\s+(\w+)\s+\(\+([\d\.]+)\%\s+ROI\)", msg)
            if match:
                strategy = match.group(1)
                roi = float(match.group(2))
                commits.append({
                    "strategy": strategy,
                    "roi": roi,
                    "hash": commit_hash,
                    "date": date
                })
    return commits

def parse_optimization_log(days=7):
    """
    Parses optimization_log.txt for entries in the last N days.
    Returns a list of dicts: {'timestamp': dt, 'strategy': str, 'status': str}
    """
    if not LOG_FILE.exists():
        return []

    entries = []
    cutoff_date = datetime.now() - timedelta(days=days)

    with LOG_FILE.open("r") as f:
        for line in f:
            # Format: YYYY-MM-DD HH:MM:SS | Strategy: <Name> | Status: <Success/Fail> | ...
            parts = line.split("|")
            if len(parts) < 3:
                continue

            try:
                timestamp_str = parts[0].strip()
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")

                if timestamp < cutoff_date:
                    continue

                strategy_part = parts[1].strip()
                status_part = parts[2].strip()

                strategy = strategy_part.split(": ")[1]
                status = status_part.split(": ")[1]

                entries.append({
                    "timestamp": timestamp,
                    "strategy": strategy,
                    "status": status
                })
            except (ValueError, IndexError):
                continue

    return entries

def generate_report():
    print(f"Generating report for last {DAYS_LOOKBACK} days...")

    # 1. Gather Data
    git_updates = get_git_log(DAYS_LOOKBACK)
    log_entries = parse_optimization_log(DAYS_LOOKBACK)

    # 2. Analyze Updates
    updated_strategies = {} # strategy -> total_roi_improvement
    total_roi_improvement = 0.0

    for commit in git_updates:
        strat = commit["strategy"]
        roi = commit["roi"]
        updated_strategies[strat] = updated_strategies.get(strat, 0.0) + roi
        total_roi_improvement += roi

    # 3. Analyze Stuck Strategies
    strategies_attempted = set()
    strategies_succeeded = set()
    strategies_failed = set()

    for entry in log_entries:
        strat = entry["strategy"]
        strategies_attempted.add(strat)
        if entry["status"] == "Success":
            strategies_succeeded.add(strat)
        else:
            strategies_failed.add(strat)

    # Also check git updates as successes (source of truth for committed changes)
    for commit in git_updates:
        strategies_succeeded.add(commit["strategy"])

    stuck_candidates = []
    for strat in strategies_failed:
        if strat not in strategies_succeeded:
            stuck_candidates.append(strat)

    # 4. Synthesize Report
    report_lines = []
    report_lines.append("# Weekly Strategy Optimization Report")
    report_lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}")
    report_lines.append(f"**Period:** Last {DAYS_LOOKBACK} days\n")

    report_lines.append("## 1. Updated Strategies")
    if updated_strategies:
        report_lines.append("| Strategy | Est. ROI Improvement |")
        report_lines.append("| :--- | :--- |")
        for strat, roi in updated_strategies.items():
            report_lines.append(f"| {strat} | +{roi:.2f}% |")
    else:
        report_lines.append("No strategies were updated this week.")
    report_lines.append("")

    report_lines.append("## 2. Portfolio Improvement")
    report_lines.append(f"**Total Estimated ROI Improvement:** +{total_roi_improvement:.2f}%")
    report_lines.append("")

    report_lines.append("## 3. Stuck Strategies (Candidates for Deletion)")
    report_lines.append("> Strategies that failed to improve despite optimization attempts.")
    if stuck_candidates:
        for strat in stuck_candidates:
            report_lines.append(f"- {strat}")
    else:
        report_lines.append("No stuck strategies detected.")
    report_lines.append("")

    report_content = "\n".join(report_lines)

    # Write Report
    with REPORT_FILE.open("w") as f:
        f.write(report_content)

    print(f"Report generated: {REPORT_FILE}")
    print(report_content)

    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Do not commit or push")
    args = parser.parse_args()

    if generate_report():
        # Check if there are changes to commit
        status = run_command(["git", "status", "--porcelain"])
        if not status.stdout.strip() and REPORT_FILE.exists():
            # If REPORT_FILE exists and git status says clean, then no change.
            # But generate_report rewrote it. If content is same, git status is clean.
            print("No changes to report.")
            return

        if args.dry_run:
            print("Dry run: skipping commit and push.")
            return

        # Commit and Push
        run_command(["git", "add", str(REPORT_FILE)])
        run_command(["git", "commit", "-m", "docs: update weekly report"])

        # Push
        # We target develop as per context
        target_ref = "HEAD:develop"

        # Check if we are on a branch that maps to develop
        branch_cmd = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        current_branch = branch_cmd.stdout.strip()

        # If explicitly on develop, just push to develop
        if current_branch == "develop":
            target_ref = "develop"

        print(f"Pushing to {target_ref}...")
        push_result = run_command(["git", "push", "origin", target_ref])

        if push_result.returncode == 0:
            print("Successfully pushed report.")
        else:
            print("Failed to push report.")

if __name__ == "__main__":
    main()
