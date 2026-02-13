#!/usr/bin/env python3
"""
Weekly Reporting Script
Aggregates optimization logs and git history to generate a weekly report.
"""

import subprocess
from datetime import datetime, timedelta
from pathlib import Path


# Configuration
USER_DATA_DIR = Path("user_data")
OPTIMIZATION_LOG_FILE = USER_DATA_DIR / "logs/optimization_log.txt"
WEEKLY_REPORT_FILE = Path("WEEKLY_REPORT.md")


def run_command(cmd, capture=True):
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"Warning running command: {' '.join(cmd)}")
        print(result.stderr)
    return result


def get_git_commits(days=7):
    """
    Get git commits from the last N days.
    Returns a list of dicts: {'hash': str, 'subject': str, 'date': str}
    """
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    cmd = [
        "git",
        "log",
        f"--since={since_date}",
        "--pretty=format:%h|%s|%ad",
        "--date=short",
    ]
    result = run_command(cmd)
    commits = []
    if result.returncode == 0 and result.stdout:
        for line in result.stdout.splitlines():
            try:
                parts = line.split("|")
                if len(parts) >= 3:
                    commits.append({"hash": parts[0], "subject": parts[1], "date": parts[2]})
            except Exception as e:
                print(f"Error parsing git log line: {line}. Error: {e}")
                continue
    return commits


def parse_optimization_log(days=7):
    """
    Parse the optimization log for the last N days.
    Returns a list of entries.
    """
    entries = []
    if not OPTIMIZATION_LOG_FILE.exists():
        return entries

    cutoff_date = datetime.now() - timedelta(days=days)

    with OPTIMIZATION_LOG_FILE.open("r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            parts = line.split("|")
            # Format: TIMESTAMP|STRATEGY|STATUS|ROI_IMPROVEMENT|...
            # ...|SHARPE_OLD|SHARPE_NEW|DD_OLD|DD_NEW
            if len(parts) < 8:
                continue

            try:
                timestamp_str = parts[0]
                timestamp = datetime.fromisoformat(timestamp_str)

                if timestamp < cutoff_date:
                    continue

                entry = {
                    "timestamp": timestamp,
                    "strategy": parts[1],
                    "status": parts[2],
                    "roi_improvement": float(parts[3]),
                    "sharpe_old": float(parts[4]),
                    "sharpe_new": float(parts[5]),
                    "dd_old": float(parts[6]),
                    "dd_new": float(parts[7]),
                }
                entries.append(entry)
            except ValueError:
                continue

    return entries


def generate_updated_strategies_section(commits, log_entries):
    lines = []
    lines.append("## 1. Updated Strategies")

    updated_strategies = set()

    # From log
    for entry in log_entries:
        if entry["status"] == "PASS":
            updated_strategies.add(entry["strategy"])

    commits_listed = False
    for commit in commits:
        subject = commit["subject"]
        if "perf:" in subject:
            lines.append(f"- {commit['date']}: {subject} ({commit['hash']})")
            commits_listed = True
        elif "optimize" in subject.lower():
            lines.append(f"- {commit['date']}: {subject} ({commit['hash']})")
            commits_listed = True

    if updated_strategies:
        lines.append("")
        lines.append("**Successfully Optimized via Daily Job:**")
        for strategy in sorted(updated_strategies):
            lines.append(f"- {strategy}")

    if not updated_strategies and not commits_listed:
        lines.append("No strategies were updated this week.")

    return lines


def generate_roi_section(log_entries):
    lines = []
    lines.append("## 2. Total Estimated Improvement in Portfolio ROI")

    total_roi = 0.0
    for entry in log_entries:
        if entry["status"] == "PASS":
            total_roi += entry["roi_improvement"]

    lines.append(f"**Total ROI Improvement:** +{total_roi:.2f}%")
    lines.append("")
    lines.append(
        "> Note: This metric sums the estimated ROI improvement from individual "
        "backtests and may not directly translate to live portfolio performance."
    )
    return lines


def generate_stuck_strategies_section(log_entries):
    lines = []
    lines.append("## 3. Stuck Strategies (Candidates for Review)")

    strategies_with_failures = set()
    strategies_with_successes = set()

    for entry in log_entries:
        if entry["status"] == "FAIL":
            strategies_with_failures.add(entry["strategy"])
        elif entry["status"] == "PASS":
            strategies_with_successes.add(entry["strategy"])

    stuck_strategies = strategies_with_failures - strategies_with_successes

    if stuck_strategies:
        for strategy in sorted(stuck_strategies):
            fail_count = sum(
                1 for e in log_entries if e["strategy"] == strategy and e["status"] == "FAIL"
            )
            lines.append(f"- **{strategy}**: {fail_count} failed optimization attempts this week.")
    else:
        lines.append("No stuck strategies detected.")

    return lines


def generate_report(commits, log_entries):
    """
    Generate the markdown report.
    """
    lines = []
    lines.append(f"# Weekly Strategy Report ({datetime.now().strftime('%Y-%m-%d')})")
    lines.append("")

    lines.extend(generate_updated_strategies_section(commits, log_entries))
    lines.append("")

    lines.extend(generate_roi_section(log_entries))
    lines.append("")

    lines.extend(generate_stuck_strategies_section(log_entries))

    return "\n".join(lines)


def main():
    print("Generating Weekly Report...")

    commits = get_git_commits()
    log_entries = parse_optimization_log()

    report_content = generate_report(commits, log_entries)

    with WEEKLY_REPORT_FILE.open("w") as f:
        f.write(report_content)

    print(f"Report written to {WEEKLY_REPORT_FILE}")


if __name__ == "__main__":
    main()
