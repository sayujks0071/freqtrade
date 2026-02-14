#!/usr/bin/env python3
"""
Weekly Strategy Report Generator
Aggregates optimization logs and git commit history to produce a weekly report.
"""

import datetime
import subprocess
import sys
from pathlib import Path

# Configuration
REPO_ROOT = Path(".")
LOG_FILE = REPO_ROOT / "user_data/logs/optimization_log.txt"
REPORT_FILE = REPO_ROOT / "WEEKLY_REPORT.md"
DAYS = 7


def run_command(cmd, capture=True):
    """Runs a shell command."""
    try:
        result = subprocess.run(cmd, capture_output=capture, text=True, check=True)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error running command {' '.join(cmd)}: {e}")
        if capture:
            print(f"Stderr: {e.stderr}")
        return None


def get_git_updates(days):
    """
    Parses git log for strategy updates in the last N days.
    Looks for commit messages starting with 'perf: optimized'.
    """
    since_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    cmd = ["git", "log", f"--since={since_date}", "--pretty=format:%s"]

    result = run_command(cmd)
    if not result:
        return []

    updates = []
    for line in result.stdout.splitlines():
        if line.strip().startswith("perf: optimized"):
            # Extract strategy name if possible: "perf: optimized <Strategy> ..."
            parts = line.split()
            if len(parts) >= 3:
                updates.append(parts[2])
            else:
                updates.append(line)
    return sorted(list(set(updates)))


def parse_optimization_log(days):
    """
    Parses the optimization log file for entries in the last N days.
    Returns a dictionary with 'successes' and 'failures'.
    """
    if not LOG_FILE.exists():
        print(f"Log file not found: {LOG_FILE}")
        return {"successes": [], "failures": []}

    threshold = datetime.datetime.now() - datetime.timedelta(days=days)
    successes = []
    failures = []

    with LOG_FILE.open("r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            parts = line.split("|")
            if len(parts) < 8:
                continue

            # Format: TIMESTAMP|STRATEGY|STATUS|ROI_IMPROVEMENT|SHARPE_OLD|SHARPE_NEW|DD_OLD|DD_NEW
            timestamp_str = parts[0]
            strategy = parts[1]
            status = parts[2]
            roi_improvement = float(parts[3])

            try:
                timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

            if timestamp < threshold:
                continue

            entry = {
                "timestamp": timestamp,
                "strategy": strategy,
                "roi_improvement": roi_improvement,
                "sharpe_new": parts[5],
                "dd_new": parts[7]
            }

            if status == "SUCCESS":
                successes.append(entry)
            elif status == "FAILURE":
                failures.append(entry)

    return {"successes": successes, "failures": failures}


def generate_report_content(updates, log_data):
    """Generates the Markdown content for the report."""

    # Calculate total ROI improvement
    total_roi_improvement = sum(entry["roi_improvement"] for entry in log_data["successes"])

    # Identify stuck strategies: appeared in failures but not in successes
    successful_strategies = set(entry["strategy"] for entry in log_data["successes"])
    failed_strategies = set(entry["strategy"] for entry in log_data["failures"])
    stuck_strategies = failed_strategies - successful_strategies

    today = datetime.datetime.now().strftime("%Y-%m-%d")

    content = [
        f"# Weekly Strategy Report ({today})",
        "",
        "## 1. Updated Strategies",
        ""
    ]

    if updates:
        for strategy in updates:
            content.append(f"- {strategy}")
    else:
        content.append("No strategies updated this week.")

    content.append("")
    content.append("## 2. Portfolio ROI Improvement")
    content.append("")
    content.append(f"Total estimated improvement: **{total_roi_improvement:.2f}%**")

    if log_data["successes"]:
        content.append("")
        content.append("| Strategy | ROI Improvement | New Sharpe | New Drawdown |")
        content.append("|---|---|---|---|")
        for entry in log_data["successes"]:
            content.append(f"| {entry['strategy']} | {entry['roi_improvement']:.2f}% | {float(entry['sharpe_new']):.2f} | {float(entry['dd_new']):.2f} |")

    content.append("")
    content.append("## 3. Stuck Strategies")
    content.append("Strategies that failed optimization attempts this week and were not successfully updated:")
    content.append("")

    if stuck_strategies:
        for strategy in sorted(stuck_strategies):
            content.append(f"- {strategy}")
    else:
        content.append("No stuck strategies detected.")

    content.append("")
    return "\n".join(content)


def main():
    print("Generating Weekly Report...")

    updates = get_git_updates(DAYS)
    log_data = parse_optimization_log(DAYS)

    report_content = generate_report_content(updates, log_data)

    print(f"Writing report to {REPORT_FILE}...")
    with REPORT_FILE.open("w") as f:
        f.write(report_content)

    # Commit and Push
    print("Committing and pushing report...")

    # Configure git if needed (CI environment)
    # run_command(["git", "config", "user.name", "github-actions[bot]"], capture=False)
    # run_command(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], capture=False)
    # We assume git is configured or we use the existing config.

    run_command(["git", "add", str(REPORT_FILE)])

    # Check if there are changes to commit
    status = run_command(["git", "status", "--porcelain"])
    if status and str(REPORT_FILE) in status.stdout:
        run_command(["git", "commit", "-m", "chore: weekly report"])

        # Push to origin
        # Use HEAD to push to current branch (or main if detached but mapped)
        # In CI, we usually want to push to the branch we are on.
        # If run manually, same.
        result = run_command(["git", "push"])
        if result:
            print("Report pushed successfully.")
        else:
            print("Failed to push report.")
    else:
        print("No changes to report file (or already committed).")


if __name__ == "__main__":
    main()
