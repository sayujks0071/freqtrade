#!/usr/bin/env python3
"""
Weekly Reporting Script
Aggregates optimization logs and git commits to generate a weekly report.
"""

import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


USER_DATA_DIR = Path("user_data")
OPTIMIZATION_LOG_FILE = USER_DATA_DIR / "optimization_log.txt"
REPORT_FILE = Path("WEEKLY_REPORT.md")


def run_command(cmd, capture=True):
    # print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=capture, text=True)
    return result


def get_git_log(days=7):
    """
    Get git log for the last N days.
    Returns a list of commit messages.
    """
    # Calculate date
    since_date = (datetime.now(UTC) - timedelta(days=days)).strftime('%Y-%m-%d')

    cmd = [
        "git",
        "log",
        f"--since={since_date}",
        "--pretty=format:%s",  # Subject only
    ]

    result = run_command(cmd)
    if result.returncode != 0:
        print(f"Error getting git log: {result.stderr}")
        return []

    if not result.stdout.strip():
        return []

    return result.stdout.strip().split('\n')


def parse_git_commits(commits):
    """
    Parses commit messages for updated strategies and ROI.
    Format: perf: optimized {strategy} (+{roi}% ROI)
    """
    updated_strategies = []
    total_roi = 0.0

    # Regex to match: perf: optimized StrategyName (+1.23% ROI)
    # Note: Strategy name can be anything, ROI is float
    pattern = re.compile(r"perf: optimized\s+(\w+)\s+\(\+([\d\.]+)%\s+ROI\)")

    for commit in commits:
        match = pattern.search(commit)
        if match:
            strategy = match.group(1)
            roi = float(match.group(2))
            updated_strategies.append(strategy)
            total_roi += roi

    return updated_strategies, total_roi


def parse_optimization_log(days=7):
    """
    Parses optimization log for failures.
    """
    if not OPTIMIZATION_LOG_FILE.exists():
        return []

    stuck_strategies = set()
    cutoff_date = datetime.now(UTC) - timedelta(days=days)

    # Format in log: [YYYY-MM-DD HH:MM:SS] Selected Strategy: {strategy}
    # Followed eventually by: [YYYY-MM-DD HH:MM:SS] Evaluation FAILED.

    # We need to track the current strategy being processed in the log
    current_strategy = None

    with OPTIMIZATION_LOG_FILE.open() as f:
        for line in f:
            # Parse timestamp
            # [2024-05-20 12:00:00] ...
            match_ts = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", line)
            if match_ts:
                ts_str = match_ts.group(1)
                try:
                    ts = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC)
                except ValueError:
                    continue

                if ts < cutoff_date:
                    continue

                # Check for strategy selection
                # "Selected Strategy: StrategyName"
                if "Selected Strategy:" in line:
                    parts = line.split("Selected Strategy:")
                    if len(parts) > 1:
                        current_strategy = parts[1].strip()

                # Check for failure
                # "Evaluation FAILED"
                if "Evaluation FAILED" in line and current_strategy:
                    stuck_strategies.add(current_strategy)
                    # Don't reset current_strategy immediately, just in case?
                    # No, daily_optimize is sequential.
                    # But keeping it allows us to detect PASSED later if it retries immediately?
                    # daily_optimize runs once per execution.
                    pass

                # Check for success
                # "Evaluation PASSED"
                if "Evaluation PASSED" in line and current_strategy:
                    if current_strategy in stuck_strategies:
                        stuck_strategies.remove(current_strategy)
                    current_strategy = None  # Reset after success

    return list(stuck_strategies)


def generate_report_content(updated_strategies, total_roi, stuck_strategies):
    lines = []
    lines.append(f"# Weekly Strategy Report - {datetime.now(UTC).strftime('%Y-%m-%d')}")
    lines.append("")

    lines.append("## 1. Updated Strategies")
    if updated_strategies:
        # Deduplicate
        unique_strategies = sorted(list(set(updated_strategies)))
        for s in unique_strategies:
            lines.append(f"- {s}")
    else:
        lines.append("No strategies updated this week.")
    lines.append("")

    lines.append("## 2. Portfolio ROI Improvement")
    lines.append(f"**Total Estimated Improvement:** +{total_roi:.2f}%")
    lines.append("")

    lines.append("## 3. Stuck Strategies")
    if stuck_strategies:
        for s in sorted(stuck_strategies):
            lines.append(f"- {s}")
    else:
        lines.append("No stuck strategies found.")
    lines.append("")

    return "\n".join(lines)


def get_current_branch():
    """Get the current git branch name."""
    result = run_command(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"]
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return "main"


def main():
    print("Generating Weekly Report...")

    # 1. Parse Git Log
    commits = get_git_log()
    updated_strategies, total_roi = parse_git_commits(commits)

    # 2. Parse Optimization Log
    stuck_strategies = parse_optimization_log()

    # 3. Generate Content
    content = generate_report_content(updated_strategies, total_roi, stuck_strategies)

    # 4. Write File
    with REPORT_FILE.open('w') as f:
        f.write(content)

    print(f"Report generated at {REPORT_FILE}")

    # 5. Commit and Push
    run_command(["git", "add", str(REPORT_FILE)])

    # Check if diff
    status = run_command(["git", "status", "--porcelain"])
    if not status.stdout.strip():
        print("No changes to report.")
        return

    msg = "docs: weekly report"
    run_command(["git", "commit", "-m", msg])

    print("Pushing report...")

    branch = get_current_branch()

    # Pull before push to avoid conflicts
    print("Pulling latest changes...")
    # Assume main is the integration branch
    run_command(["git", "pull", "--rebase", "origin", "main"])

    push_cmd = ["git", "push", "origin"]
    # Handle detached HEAD (CI) or main branch
    if branch == "HEAD" or branch == "main":
        push_cmd.append("HEAD:main")
    else:
        push_cmd.append(branch)

    result = run_command(push_cmd)
    if result.returncode != 0:
        print(f"Error pushing report: {result.stderr}")
        sys.exit(1)

    print("Done.")


if __name__ == "__main__":
    main()
