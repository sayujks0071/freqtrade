#!/usr/bin/env python3
"""
Generate Weekly Report
"""

import argparse
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


# Configuration
REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = REPO_ROOT / "optimization_log.txt"
REPORT_FILE = REPO_ROOT / "WEEKLY_REPORT.md"


def run_command(cmd, capture=True):
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"Error running command: {' '.join(cmd)}\n{result.stderr}")
    return result


def get_weekly_updates(days=7):
    """
    Parse git log for successful optimizations in the last N days.
    Returns a list of dicts: {'strategy': name, 'roi': float}
    """
    cmd = ["git", "log", f"--since={days} days ago", "--pretty=format:%s"]
    result = run_command(cmd)
    if result.returncode != 0:
        return []

    updates = []
    # Regex to match: perf: optimized StrategyName (+1.23% ROI)
    pattern = re.compile(r"perf: optimized\s+(\w+)\s+\(\+([\d\.]+)\%\s+ROI\)")

    for line in result.stdout.splitlines():
        match = pattern.match(line.strip())
        if match:
            strategy = match.group(1)
            roi = float(match.group(2))
            updates.append({"strategy": strategy, "roi": roi})

    return updates


def get_stuck_strategies(days=7, successful_strategies=None):
    """
    Identify strategies that failed optimization and were not successful in the last N days.
    """
    if successful_strategies is None:
        successful_strategies = set()

    if not LOG_FILE.exists():
        print(f"Warning: {LOG_FILE} not found.")
        return []

    cutoff_date = datetime.now() - timedelta(days=days)
    failed_strategies = set()

    # Format: 2024-05-22T10:00:00.000000 | StrategyName | STATUS | Details
    with LOG_FILE.open() as f:
        for line in f:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue

            timestamp_str = parts[0]
            strategy = parts[1]
            status = parts[2]

            try:
                # Isoformat parsing
                entry_date = datetime.fromisoformat(timestamp_str)
            except ValueError:
                continue

            if entry_date >= cutoff_date:
                if status == "FAILED":
                    failed_strategies.add(strategy)

    # "Stuck" means failed at least once and NOT in successful list
    stuck = [s for s in failed_strategies if s not in successful_strategies]
    return sorted(stuck)


def generate_report(updates, stuck, total_roi):
    lines = []
    lines.append("# Weekly Optimization Report")
    lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")

    lines.append("## 1. Updated Strategies")
    if updates:
        for up in updates:
            lines.append(f"- **{up['strategy']}**: +{up['roi']:.2f}% ROI")
    else:
        lines.append("No strategies updated this week.")
    lines.append("")

    lines.append("## 2. Total Estimated Improvement")
    lines.append(f"**Total ROI Improvement:** +{total_roi:.2f}%")
    lines.append("")

    lines.append("## 3. Stuck Strategies")
    lines.append("(Strategies that failed optimization attempts and were not updated)")
    if stuck:
        for s in stuck:
            lines.append(f"- {s}")
    else:
        lines.append("No stuck strategies detected.")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate Weekly Report")
    parser.add_argument("--push", action="store_true", help="Commit and push the report")
    args = parser.parse_args()

    print("Collecting data...")
    updates = get_weekly_updates()
    successful_strategies = {u["strategy"] for u in updates}

    stuck = get_stuck_strategies(successful_strategies=successful_strategies)

    total_roi = sum(u["roi"] for u in updates)

    print(f"Found {len(updates)} updates and {len(stuck)} stuck strategies.")

    report_content = generate_report(updates, stuck, total_roi)

    with REPORT_FILE.open("w") as f:
        f.write(report_content)

    print(f"Report generated at {REPORT_FILE}")

    if args.push:
        print("Committing and pushing report...")
        run_command(["git", "add", str(REPORT_FILE)])
        run_command(["git", "commit", "-m", "docs: update weekly report"])

        # Get current branch
        res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True
        )
        current_branch = res.stdout.strip()

        run_command(["git", "push", "origin", current_branch])
        print("Done.")


if __name__ == "__main__":
    main()
