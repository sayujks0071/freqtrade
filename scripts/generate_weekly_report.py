#!/usr/bin/env python3
"""
Weekly Report Generator
"""

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


LOG_FILE = Path("optimization_log.txt")
REPORT_FILE = Path("WEEKLY_REPORT.md")


def get_git_log(days=7):
    # git log --since="7 days ago" --pretty=format:"%s"
    cmd = ["git", "log", f"--since={days} days ago", "--pretty=format:%s"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.splitlines()
    except subprocess.CalledProcessError:
        print("Error reading git log")
        return []


def parse_optimization_log(days=7):
    logs = []
    if not LOG_FILE.exists():
        return logs

    since_date = datetime.now() - timedelta(days=days)

    with LOG_FILE.open("r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entry_date = datetime.fromisoformat(entry["timestamp"])
                if entry_date >= since_date:
                    logs.append(entry)
            except (json.JSONDecodeError, ValueError):
                continue
    return logs


def get_updated_strategies(git_commits, opt_logs):
    updated = set()
    for msg in git_commits:
        if "perf: optimized" in msg:
            parts = msg.split()
            if len(parts) >= 3:
                updated.add(parts[2])
    for entry in opt_logs:
        if entry.get("status") == "success":
            updated.add(entry.get("strategy"))
    return updated


def get_stuck_candidates(opt_logs):
    failed_counts = {}
    for entry in opt_logs:
        if entry.get("status") == "failed":
            strat = entry.get("strategy")
            failed_counts[strat] = failed_counts.get(strat, 0) + 1

    stuck = []
    for strat, count in failed_counts.items():
        succeeded = any(
            e.get("status") == "success" and e.get("strategy") == strat for e in opt_logs
        )
        if not succeeded:
            stuck.append(f"{strat} ({count} failed attempts)")
    return stuck


def calculate_roi_improvement(opt_logs):
    total = 0.0
    for entry in opt_logs:
        if entry.get("status") == "success":
            total += entry.get("roi_change", 0.0)
    return total


def main():
    git_commits = get_git_log()
    opt_logs = parse_optimization_log()

    updated_strategies = get_updated_strategies(git_commits, opt_logs)
    total_roi_improvement = calculate_roi_improvement(opt_logs)
    stuck_candidates = get_stuck_candidates(opt_logs)

    # Generate Report
    report_lines = []
    report_lines.append("# Weekly Strategy Optimization Report")
    report_lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    report_lines.append("")

    report_lines.append("## 1. Updated Strategies")
    if updated_strategies:
        for s in sorted(updated_strategies):
            report_lines.append(f"- {s}")
    else:
        report_lines.append("No strategies updated this week.")
    report_lines.append("")

    report_lines.append("## 2. Total Estimated Improvement in Portfolio ROI")
    report_lines.append(f"Total ROI Improvement: {total_roi_improvement * 100:.2f}%")
    report_lines.append("")

    report_lines.append("## 3. Stuck Strategies (Candidates for Deletion)")
    if stuck_candidates:
        report_lines.append(
            "The following strategies failed to improve despite optimization attempts:"
        )
        for s in stuck_candidates:
            report_lines.append(f"- {s}")
    else:
        report_lines.append("No stuck strategies identified.")

    with REPORT_FILE.open("w") as f:
        f.write("\n".join(report_lines) + "\n")

    print(f"Generated {REPORT_FILE}")


if __name__ == "__main__":
    main()
