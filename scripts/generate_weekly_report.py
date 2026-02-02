#!/usr/bin/env python3
"""
Weekly Report Generator
"""

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


def run_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return result


def get_git_log_data(days=7):
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    cmd = [
        "git",
        "log",
        f"--since={since_date}",
        "--pretty=format:%s",
    ]
    result = run_command(cmd)

    strategies_updated = set()
    total_roi_improvement = 0.0

    # Regex to match: perf: optimized StrategyName (+X.XX% ROI)
    pattern = re.compile(r"perf: optimized\s+(.+?)\s+\(\+([\d\.]+)\%\s+ROI\)")

    if result.returncode == 0:
        for line in result.stdout.splitlines():
            match = pattern.search(line)
            if match:
                strategy = match.group(1)
                roi = float(match.group(2))
                strategies_updated.add(strategy)
                total_roi_improvement += roi

    return strategies_updated, total_roi_improvement


def get_optimization_log_data(days=7):
    if not OPTIMIZATION_LOG.exists():
        return {}

    cutoff_date = datetime.now() - timedelta(days=days)
    data = {}  # strategy -> list of attempts

    try:
        with OPTIMIZATION_LOG.open("r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # Handle potentially missing keys
                    timestamp_str = entry.get("timestamp")
                    if not timestamp_str:
                        continue

                    timestamp = datetime.fromisoformat(timestamp_str)
                    if timestamp > cutoff_date:
                        strategy = entry.get("strategy")
                        if strategy:
                            if strategy not in data:
                                data[strategy] = []
                            data[strategy].append(entry)
                except (json.JSONDecodeError, ValueError):
                    continue
    except Exception as e:
        print(f"Error reading optimization log: {e}")

    return data


def identify_stuck_strategies(opt_data, updated_strategies):
    stuck_strategies = set()

    for strategy, attempts in opt_data.items():
        # If strategy was successfully updated (in git log), it's not stuck
        if strategy in updated_strategies:
            continue

        # Check if it has failures
        has_failure = any(a.get("status") == "failed" for a in attempts)

        if has_failure:
            stuck_strategies.add(strategy)

    return stuck_strategies


def generate_markdown(updated_strategies, total_roi, stuck_strategies):
    lines = []
    lines.append("# Weekly Strategy Optimization Report")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")

    lines.append("## Section 1: Strategies Updated")
    if updated_strategies:
        for strategy in sorted(updated_strategies):
            lines.append(f"- {strategy}")
    else:
        lines.append("No strategies updated this week.")
    lines.append("")

    lines.append("## Section 2: Total Estimated Improvement in Portfolio ROI")
    lines.append(f"**+{total_roi:.2f}%**")
    lines.append("")

    lines.append("## Section 3: Stuck Strategies")
    lines.append(
        "Strategies that failed to improve despite optimization attempts (candidates for deletion):"
    )
    if stuck_strategies:
        for strategy in sorted(stuck_strategies):
            lines.append(f"- {strategy}")
    else:
        lines.append("No stuck strategies detected.")
    lines.append("")

    return "\n".join(lines)


def get_current_branch():
    """Get the current git branch name."""
    result = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def commit_and_push_report():
    print("Committing and pushing report...")

    # Add file
    run_command(["git", "add", str(REPORT_FILE)])

    # Commit
    msg = "docs: update weekly report"
    result = run_command(["git", "commit", "-m", msg])

    if result.returncode != 0:
        if "nothing to commit" in result.stdout:
            print("No changes to report.")
            return
        print(f"Error committing report: {result.stderr}")
        return

    # Push
    branch = get_current_branch()
    if branch:
        print(f"Pushing to {branch}...")
        result = run_command(["git", "push", "origin", branch])
        if result.returncode == 0:
            print("Report pushed successfully.")
        else:
            print(f"Error pushing report: {result.stderr}")
    else:
        print("Could not determine current branch. Push skipped.")


def main():
    # 1. Parse Data
    updated_strategies, total_roi = get_git_log_data()
    opt_data = get_optimization_log_data()

    # 2. Analyze
    stuck_strategies = identify_stuck_strategies(opt_data, updated_strategies)

    # 3. Generate Report
    report_content = generate_markdown(updated_strategies, total_roi, stuck_strategies)

    # 4. Write File
    try:
        with REPORT_FILE.open("w") as f:
            f.write(report_content)
        print(f"Report generated at {REPORT_FILE}")
    except Exception as e:
        print(f"Error writing report: {e}")
        sys.exit(1)

    # 5. Commit and Push
    commit_and_push_report()


if __name__ == "__main__":
    main()
