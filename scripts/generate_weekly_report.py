#!/usr/bin/env python3
"""
Generates a weekly report of strategy optimizations.
"""

import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


USER_DATA_DIR = Path("user_data")
LOG_FILE = USER_DATA_DIR / "optimization_log.txt"
REPORT_FILE = Path("WEEKLY_REPORT.md")


def run_command(cmd, capture=True):
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"Error running command: {result.stderr}")
    return result


def get_last_sunday():
    today = datetime.now()
    # Calculate date of 7 days ago
    start_date = today - timedelta(days=7)
    return start_date


def parse_git_log(since_date):
    cmd = [
        "git",
        "log",
        f"--since={since_date.isoformat()}",
        "--pretty=format:%h|%s|%ad",
        "--date=iso",
    ]
    result = run_command(cmd)
    commits = []
    if result.returncode == 0 and result.stdout:
        for line in result.stdout.splitlines():
            parts = line.split("|")
            if len(parts) >= 3:
                commits.append({"hash": parts[0], "subject": parts[1], "date": parts[2]})
    return commits


def parse_optimization_log(since_date):
    if not LOG_FILE.exists():
        return []

    failed_strategies = []
    current_strategy = None
    current_run_start = None

    with LOG_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            match_start = re.search(r"--- Optimization Run Started: (.+) ---", line)
            if match_start:
                try:
                    current_run_start = datetime.fromisoformat(match_start.group(1))
                except ValueError:
                    current_run_start = None
                current_strategy = None  # Reset strategy for new run
                continue

            if current_run_start and current_run_start >= since_date:
                match_strat = re.search(r"Selected Strategy: (.+)", line)
                if match_strat:
                    current_strategy = match_strat.group(1).strip()

                if "Evaluation FAILED" in line and current_strategy:
                    failed_strategies.append(
                        {"strategy": current_strategy, "date": current_run_start}
                    )
                    current_strategy = None

    return failed_strategies


def generate_report():
    since_date = get_last_sunday()
    commits = parse_git_log(since_date)
    failures = parse_optimization_log(since_date)

    updated_strategies = []
    total_roi_improvement = 0.0

    # Parse commits for "perf: optimized {strategy} (+{roi}% ROI)"
    # Regex: perf: optimized (.+) \(\+(.+)% ROI\)
    roi_pattern = re.compile(r"perf: optimized (.+) \(\+(.+)% ROI\)")

    for commit in commits:
        match = roi_pattern.search(commit["subject"])
        if match:
            strategy = match.group(1)
            roi = float(match.group(2))
            updated_strategies.append(
                {"strategy": strategy, "roi": roi, "hash": commit["hash"], "date": commit["date"]}
            )
            total_roi_improvement += roi

    # Filter stuck strategies
    stuck_counts = {}
    for fail in failures:
        strat = fail["strategy"]
        stuck_counts[strat] = stuck_counts.get(strat, 0) + 1

    # Generate Markdown
    report = "# Weekly Optimization Report\n\n"
    report += (
        f"**Period:** {since_date.strftime('%Y-%m-%d')} to "
        f"{datetime.now().strftime('%Y-%m-%d')}\n\n"
    )

    report += "## 1. Updated Strategies\n"
    if updated_strategies:
        report += "| Strategy | ROI Improvement | Date | Commit |\n"
        report += "|---|---|---|---|\n"
        for item in updated_strategies:
            report += (
                f"| {item['strategy']} | +{item['roi']:.2f}% | "
                f"{item['date'][:10]} | {item['hash']} |\n"
            )
    else:
        report += "No strategies updated this week.\n"

    report += "\n## 2. Total Estimated Improvement\n"
    report += f"**Total Portfolio ROI Improvement:** +{total_roi_improvement:.2f}%\n"

    report += "\n## 3. Stuck Strategies (Failed Optimization)\n"
    if stuck_counts:
        report += "Strategies that failed to improve during optimization attempts:\n\n"
        report += "| Strategy | Failures |\n"
        report += "|---|---|\n"
        for strat, count in stuck_counts.items():
            report += f"| {strat} | {count} |\n"
    else:
        report += "No stuck strategies detected.\n"

    return report


def main():
    report_content = generate_report()

    with REPORT_FILE.open("w") as f:
        f.write(report_content)

    print(f"Generated {REPORT_FILE}")

    # Commit and push
    # Check if there are changes
    run_command(["git", "add", str(REPORT_FILE)])
    diff_res = subprocess.run(["git", "diff-index", "--quiet", "HEAD", "--", str(REPORT_FILE)])

    if diff_res.returncode != 0:
        print("Committing report...")
        run_command(["git", "commit", "-m", "docs: update weekly report"])

        # Determine current branch
        res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True
        )
        current_branch = res.stdout.strip()

        print(f"Pushing to {current_branch}...")
        push_cmd = ["git", "push", "origin"]
        if current_branch == "main":
            push_cmd.append("HEAD:main")
        else:
            push_cmd.append(current_branch)

        run_command(push_cmd)
    else:
        print("No changes in report.")


if __name__ == "__main__":
    main()
