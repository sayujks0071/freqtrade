#!/usr/bin/env python3
"""
Weekly Report Generator
Parses git log and optimization_log.txt to generate WEEKLY_REPORT.md
"""

import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


# Configuration
LOG_FILE = Path("optimization_log.txt")
REPORT_FILE = Path("WEEKLY_REPORT.md")

def run_command(cmd, capture=True):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"Error running command: {result.stderr}")
    return result

def get_git_commits(days=7):
    """
    Get git commit messages from the last `days` days.
    """
    # Use git log to get commits. --since accepts relative dates like "7 days ago"
    cmd = ["git", "log", f"--since={days} days ago", "--pretty=format:%s"]
    result = run_command(cmd, capture=True)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().split('\n')
    return []

def parse_commits(commits):
    """
    Parse commit messages to find strategy updates and ROI improvements.
    Format: "perf: optimized <StrategyName> (+<ROI>% ROI)"
    """
    updated_strategies = []
    total_roi_improvement = 0.0

    # Regex to extract strategy name and ROI improvement
    pattern = re.compile(r"perf: optimized ([\w\d]+) \(\+([\d.]+)% ROI\)")

    for message in commits:
        match = pattern.search(message)
        if match:
            strategy_name = match.group(1)
            roi = float(match.group(2))
            updated_strategies.append({"name": strategy_name, "roi": roi})
            total_roi_improvement += roi

    return updated_strategies, total_roi_improvement

def parse_optimization_log(days=7):
    """
    Parse optimization_log.txt to find stuck strategies.
    Format: YYYY-MM-DD HH:MM:SS - Strategy: <StrategyName> - Result: <SUCCESS|FAILURE>
    """
    stuck_strategies = []
    if not LOG_FILE.exists():
        return stuck_strategies

    cutoff_date = datetime.now() - timedelta(days=days)

    with LOG_FILE.open('r') as f:
        lines = f.readlines()

    # Regex to extract log entries
    pattern = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - Strategy: ([\w\d]+) - Result: (\w+)"
    )

    attempts = {} # Strategy -> list of results

    for line in lines:
        match = pattern.search(line)
        if match:
            timestamp_str = match.group(1)
            strategy_name = match.group(2)
            result = match.group(3)

            try:
                # Parse timestamp
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")

                # Check if within reporting period
                if timestamp >= cutoff_date:
                    if strategy_name not in attempts:
                        attempts[strategy_name] = []
                    attempts[strategy_name].append(result)
            except ValueError:
                continue

    # Identify stuck strategies: Attempted but never succeeded in the period
    for strategy, results in attempts.items():
        if "SUCCESS" not in results:
            stuck_strategies.append(strategy)

    return stuck_strategies

def generate_report(updated_strategies, total_roi, stuck_strategies):
    """
    Generate WEEKLY_REPORT.md content.
    """
    report = "# Weekly Optimization Report\n\n"
    report += f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n\n"

    report += "## Section 1: Updated Strategies\n"
    if updated_strategies:
        for s in updated_strategies:
            report += f"- **{s['name']}**: +{s['roi']:.2f}% ROI\n"
    else:
        report += "No strategies updated this week.\n"
    report += "\n"

    report += "## Section 2: Total Estimated Improvement\n"
    report += f"**Total ROI Improvement:** +{total_roi:.2f}%\n\n"

    report += "## Section 3: Stuck Strategies\n"
    report += (
        "The following strategies failed to improve despite optimization attempts "
        "(candidates for deletion):\n"
    )
    if stuck_strategies:
        for s in stuck_strategies:
            report += f"- {s}\n"
    else:
        report += "None.\n"

    return report

def main():
    print("Generating Weekly Report...")

    # 1. Parse Git Log
    commits = get_git_commits()
    updated_strategies, total_roi = parse_commits(commits)

    # 2. Parse Optimization Log
    stuck_strategies = parse_optimization_log()

    # 3. Generate Report
    report_content = generate_report(updated_strategies, total_roi, stuck_strategies)

    print("Writing report to WEEKLY_REPORT.md...")
    with REPORT_FILE.open('w') as f:
        f.write(report_content)

    # 4. Commit and Push
    # Check if there are changes to the report file
    status = run_command(["git", "status", "--porcelain"], capture=True)
    if str(REPORT_FILE) in status.stdout:
        run_command(["git", "add", str(REPORT_FILE)])
        run_command(["git", "commit", "-m", "docs: update weekly optimization report"])
        print("Report committed.")

        # Push
        # Use HEAD:main to handle detached HEAD state in CI
        run_command(["git", "push", "origin", "HEAD:main"])
        print("Report pushed.")
    else:
        print("No changes to report.")

if __name__ == "__main__":
    main()
