#!/usr/bin/env python3
"""
Generate Weekly Optimization Report
"""

import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


# Configuration
REPO_ROOT = Path(__file__).resolve().parent.parent
OPTIMIZATION_LOG = REPO_ROOT / "optimization_log.txt"
REPORT_FILE = REPO_ROOT / "WEEKLY_REPORT.md"


def get_git_log(days=7):
    """Fetches git commit messages from the last N days."""
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    cmd = [
        "git",
        "log",
        f"--since={since_date}",
        "--pretty=format:%s",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"Error fetching git log: {result.stderr}")
        return []
    return result.stdout.splitlines()


def parse_optimization_log(days=7):
    """Parses optimization_log.txt for stuck strategies in the last N days."""
    if not OPTIMIZATION_LOG.exists():
        return []

    stuck_strategies = []
    cutoff_date = datetime.now() - timedelta(days=days)

    with OPTIMIZATION_LOG.open("r") as f:
        for line in f:
            parts = line.strip().split(" | ")
            if len(parts) < 4:
                continue

            timestamp_str, strategy, status, details = parts
            try:
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

            if timestamp < cutoff_date:
                continue

            if status != "Success":
                stuck_strategies.append({
                    "timestamp": timestamp_str,
                    "strategy": strategy,
                    "status": status,
                    "details": details,
                })

    return stuck_strategies


def generate_report():
    print("Generating Weekly Report...")

    # 1. Parse Git Log
    commits = get_git_log()
    updated_strategies = []
    total_roi_improvement = 0.0

    # Regex to match: perf: optimized StrategyName (+1.23% ROI)
    pattern = re.compile(r"perf: optimized\s+(\w+)\s+\(\+([\d\.]+)\%\s+ROI\)")

    for commit in commits:
        match = pattern.search(commit)
        if match:
            strategy = match.group(1)
            roi = float(match.group(2))
            updated_strategies.append((strategy, roi))
            total_roi_improvement += roi

    # 2. Parse Optimization Log
    stuck_strategies = parse_optimization_log()

    # 3. Generate Markdown
    lines = []
    lines.append(
        f"# Weekly Optimization Report ({datetime.now().strftime('%Y-%m-%d')})"
    )
    lines.append("")

    lines.append("## 1. Updated Strategies")
    if updated_strategies:
        for strategy, roi in updated_strategies:
            lines.append(f"- **{strategy}**: +{roi:.2f}% ROI")
    else:
        lines.append("No strategies were successfully optimized this week.")
    lines.append("")

    lines.append("## 2. Total Estimated Improvement")
    lines.append(
        f"**Total Portfolio ROI Improvement:** +{total_roi_improvement:.2f}%"
    )
    lines.append("")

    lines.append("## 3. Stuck Strategies (Candidates for Deletion)")
    if stuck_strategies:
        lines.append("| Timestamp | Strategy | Status | Reason |")
        lines.append("|---|---|---|---|")
        for s in stuck_strategies:
            lines.append(
                f"| {s['timestamp']} | {s['strategy']} | {s['status']} | {s['details']} |"
            )
    else:
        lines.append("No stuck strategies detected this week.")
    lines.append("")

    # Write to file
    with REPORT_FILE.open("w") as f:
        f.write("\n".join(lines))

    print(f"Report generated: {REPORT_FILE}")


if __name__ == "__main__":
    generate_report()
