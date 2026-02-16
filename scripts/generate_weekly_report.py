#!/usr/bin/env python3
"""
Weekly Reporting Script
Parses optimization logs and git commit history to generate a weekly report.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


# Configuration
REPO_ROOT = Path(__file__).resolve().parent.parent
OPTIMIZATION_LOG = REPO_ROOT / "optimization_log.txt"
REPORT_FILE = REPO_ROOT / "WEEKLY_REPORT.md"


def run_command(cmd, capture=True, check=True):
    # print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=capture, text=True, check=False)
    if check and result.returncode != 0:
        print(f"Error running command: {' '.join(cmd)}")
        print(result.stderr)
        sys.exit(result.returncode)
    return result


def get_git_log(days=7):
    """
    Get git log messages for the last N days.
    """
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    cmd = ["git", "log", f"--since={since_date}", "--pretty=format:%s"]
    result = run_command(cmd)
    return result.stdout.splitlines()


def parse_optimization_log(days=7):
    """
    Parse the optimization log file for entries in the last N days.
    """
    if not OPTIMIZATION_LOG.exists():
        return []

    cutoff_date = datetime.now() - timedelta(days=days)
    entries = []

    with OPTIMIZATION_LOG.open("r") as f:
        for line in f:
            try:
                entry = json.loads(line)
                timestamp = datetime.fromisoformat(entry["timestamp"])
                if timestamp > cutoff_date:
                    entries.append(entry)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return entries


def parse_git_updates(log_lines):
    """
    Parse git log lines for optimization commits.
    Format: perf: optimized {Strategy} (+{ROI}% ROI)
    """
    updates = []
    # Regex to match: perf: optimized StrategyName (+12.34% ROI)
    pattern = re.compile(r"perf: optimized\s+([\w\s-]+?)\s+\(\+([\d.]+)%\s+ROI\)")

    for line in log_lines:
        match = pattern.search(line)
        if match:
            strategy = match.group(1).strip()
            roi = float(match.group(2))
            updates.append({"strategy": strategy, "roi_improvement": roi, "line": line})
    return updates


def identify_stuck_strategies(log_entries, successful_updates):
    """
    Identify strategies that were attempted but not successfully updated.
    """
    attempted_strategies = set()
    for entry in log_entries:
        attempted_strategies.add(entry["strategy"])

    successful_strategies = set(u["strategy"] for u in successful_updates)

    stuck = []
    for strategy in attempted_strategies:
        if strategy not in successful_strategies:
            # Check if it failed multiple times?
            # For now, if it was attempted and not updated, it's stuck or failed.
            # We can count failures.
            failures = [
                e for e in log_entries if e["strategy"] == strategy and not e.get("success", False)
            ]
            if failures:
                stuck.append({"strategy": strategy, "attempts": len(failures)})
    return stuck


def generate_report(updates, stuck, total_roi):
    """
    Generate the Markdown report content.
    """
    report = []
    report.append("# Weekly Strategy Optimization Report")
    report.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}")
    report.append("")

    report.append("## 1. Updated Strategies")
    if updates:
        for u in updates:
            report.append(f"- **{u['strategy']}**: +{u['roi_improvement']:.2f}% ROI")
    else:
        report.append("No strategies were updated this week.")
    report.append("")

    report.append("## 2. Total Estimated Improvement")
    report.append(f"- **Total Portfolio ROI Improvement:** +{total_roi:.2f}%")
    report.append("")

    report.append("## 3. Stuck Strategies (Candidates for Deletion)")
    if stuck:
        report.append("The following strategies failed to improve despite optimization attempts:")
        for s in stuck:
            report.append(f"- **{s['strategy']}** ({s['attempts']} failed attempts)")
    else:
        report.append("No stuck strategies detected.")

    return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description="Generate Weekly Optimization Report")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print report to stdout instead of file"
    )
    parser.add_argument("--push", action="store_true", help="Commit and push the report")
    parser.add_argument(
        "--branch", type=str, default="main", help="Target branch to push to (default: main)"
    )
    args = parser.parse_args()

    # 1. Gather Data
    print("Fetching git log...")
    git_log_lines = get_git_log()

    print("Parsing optimization log...")
    log_entries = parse_optimization_log()

    # 2. Analyze
    updates = parse_git_updates(git_log_lines)
    total_roi = sum(u["roi_improvement"] for u in updates)
    stuck = identify_stuck_strategies(log_entries, updates)

    # 3. Generate Report
    content = generate_report(updates, stuck, total_roi)

    if args.dry_run:
        print("\n--- REPORT PREVIEW ---\n")
        print(content)
        print("\n----------------------\n")
        return

    print(f"Writing report to {REPORT_FILE}...")
    with REPORT_FILE.open("w") as f:
        f.write(content)

    # 4. Commit and Push
    if args.push:
        # Check for changes
        run_command(["git", "status", "--porcelain"], capture=True)
        # If file changed or verify if untracked...
        # simpler to just try adding

        print("Committing and pushing report...")
        run_command(["git", "add", str(REPORT_FILE)])

        # Check if there are changes to commit
        diff = run_command(["git", "diff", "--cached", "--name-only"], capture=True)
        if REPORT_FILE.name in diff.stdout:
            run_command(["git", "commit", "-m", "docs: update weekly report"])
            # Push to target branch
            run_command(["git", "push", "origin", f"HEAD:{args.branch}"])
            print(f"Report pushed to {args.branch}.")
        else:
            print("No changes to report.")


if __name__ == "__main__":
    main()
