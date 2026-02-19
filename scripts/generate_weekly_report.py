#!/usr/bin/env python3
"""
Generate Weekly Report
"""

import json
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


def run_command(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip().splitlines()
    except subprocess.CalledProcessError:
        return []


def get_git_commits(days=7):
    # Get commits from the last X days
    cmd = ["git", "log", f"--since={days} days ago", "--pretty=format:%s"]
    return run_command(cmd)


def parse_commits(commits):
    """
    Parse commit messages to find updated strategies.
    Example message: perf: optimized DeltaSafeStrategy (+12.81% ROI)
    """
    updated_strategies = []

    # Regex for "perf: optimized [StrategyName] (+X% ROI)"
    pattern = re.compile(r"perf: optimized (\w+) \(\+([+-]?[\d.]+)% ROI\)")

    for commit in commits:
        match = pattern.search(commit)
        if match:
            strategy = match.group(1)
            # The percentage in commit is Total ROI, not improvement.
            # But we can list it.
            roi = match.group(2)
            updated_strategies.append(f"{strategy} (Total ROI: {roi}%)")

    return updated_strategies


def parse_optimization_log(days=7):
    """
    Parse optimization_log.txt to calculate ROI improvement and find stuck strategies.
    """
    log_file = Path("optimization_log.txt")

    successful_strategies = set()
    failed_counts = {}
    total_roi_improvement = 0.0

    if log_file.exists():
        cutoff_date = datetime.now() - timedelta(days=days)

        with log_file.open("r") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    timestamp = datetime.fromisoformat(entry["timestamp"])
                    if timestamp < cutoff_date:
                        continue

                    strategy = entry["strategy"]
                    status = entry["status"]

                    if status == "success":
                        successful_strategies.add(strategy)
                        # Sum up ROI change (improvement)
                        roi_change = entry.get("roi_change", 0.0)
                        total_roi_improvement += roi_change
                    elif status == "failed":
                        failed_counts[strategy] = failed_counts.get(strategy, 0) + 1

                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

    # Identify stuck strategies: failures > 0 and NO success in the period?
    # Or maybe failures > 0 regardless of success?
    # "stuck strategies that failed to improve despite optimization attempts"
    # If it succeeded once, it improved.
    # So we check if it is NOT in successful_strategies.

    stuck_strategies = []
    for strat, count in failed_counts.items():
        if strat not in successful_strategies:
            stuck_strategies.append(f"{strat} ({count} failed attempts)")

    return total_roi_improvement, stuck_strategies


def main():
    commits = get_git_commits()
    updated_from_git = parse_commits(commits)

    total_roi_improvement, stuck_strategies = parse_optimization_log()

    # Build report content
    report_lines = [
        "# Weekly Optimization Report",
        "",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "## 1. Updated Strategies",
    ]

    if updated_from_git:
        for s in updated_from_git:
            report_lines.append(f"- {s}")
    else:
        report_lines.append("No strategies updated this week.")

    report_lines.append("")
    report_lines.append("## 2. Portfolio ROI Improvement")
    report_lines.append(f"**Total Estimated Improvement:** {total_roi_improvement:+.2f}%")

    report_lines.append("")
    report_lines.append("## 3. Stuck Strategies")
    if stuck_strategies:
        report_lines.append(
            "The following strategies failed to improve despite optimization "
            "attempts (candidates for deletion):"
        )
        for s in stuck_strategies:
            report_lines.append(f"- {s}")
    else:
        report_lines.append("No stuck strategies detected.")

    report_content = "\n".join(report_lines) + "\n"

    output_file = Path("WEEKLY_REPORT.md")
    with output_file.open("w") as f:
        f.write(report_content)

    print(f"Generated {output_file}")


if __name__ == "__main__":
    main()
