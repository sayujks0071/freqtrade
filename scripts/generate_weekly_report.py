#!/usr/bin/env python3
"""
Weekly Reporting Script
Aggregates optimization logs and git commit history to generate a weekly report.
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
REPO_ROOT = Path(__file__).resolve().parent.parent
OPTIMIZATION_LOG = REPO_ROOT / "optimization_log.txt"
REPORT_FILE = REPO_ROOT / "WEEKLY_REPORT.md"


def run_command(cmd, capture=True, check=False):
    """Runs a shell command."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            check=check,
            cwd=REPO_ROOT
        )
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {' '.join(cmd)}")
        if e.stderr:
            print(e.stderr)
        return None


def get_weekly_updates(days=7):
    """
    Parses git log for commit messages matching 'perf: optimized <Strategy> (+<ROI>% ROI)'.
    Returns a list of dicts: {'strategy': str, 'roi': float, 'date': str}
    """
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    cmd = [
        "git", "log",
        f"--since={since_date}",
        "--pretty=format:%ad|%s",
        "--date=short"
    ]

    result = run_command(cmd)
    if not result or result.returncode != 0:
        return []

    updates = []
    # Regex to match: perf: optimized StrategyName (+1.23% ROI)
    pattern = re.compile(r"perf: optimized (\w+) \(\+([\d.]+)% ROI\)")

    for line in result.stdout.splitlines():
        if not line:
            continue
        try:
            date_str, message = line.split("|", 1)
            match = pattern.search(message)
            if match:
                updates.append({
                    "strategy": match.group(1),
                    "roi": float(match.group(2)),
                    "date": date_str
                })
        except ValueError:
            continue

    return updates


def get_optimization_attempts(days=7):
    """
    Reads optimization_log.txt and filters for entries in the last 'days'.
    Returns a list of dicts: {'timestamp': datetime, 'strategy': str, 'status': str, 'details': str}
    """
    if not OPTIMIZATION_LOG.exists():
        return []

    attempts = []
    cutoff = datetime.now() - timedelta(days=days)

    with OPTIMIZATION_LOG.open("r") as f:
        for line in f:
            parts = line.strip().split(" | ")
            if len(parts) < 3:
                continue

            try:
                # Assuming format: YYYY-MM-DD HH:MM:SS | Strategy | Status | Details
                ts_str = parts[0]
                strategy = parts[1]
                status = parts[2]
                details = parts[3] if len(parts) > 3 else ""

                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")

                if ts > cutoff:
                    attempts.append({
                        "timestamp": ts,
                        "strategy": strategy,
                        "status": status,
                        "details": details
                    })
            except ValueError:
                continue

    return attempts


def identify_stuck_strategies(attempts, updates):
    """
    Identifies strategies that have failed attempts and no successful updates/optimizations.
    """
    # Strategies that were successfully updated (committed)
    updated_strategies = {u["strategy"] for u in updates}

    # Strategies that had "SUCCESS" in logs (might be same as updated, but just in case)
    success_strategies = {a["strategy"] for a in attempts if a["status"] == "SUCCESS"}

    # Strategies that failed
    failed_counts = {}
    for a in attempts:
        if a["status"] == "FAILED":
            failed_counts[a["strategy"]] = failed_counts.get(a["strategy"], 0) + 1

    stuck = []
    for strategy, count in failed_counts.items():
        if strategy not in updated_strategies and strategy not in success_strategies:
            stuck.append({
                "strategy": strategy,
                "failures": count
            })

    return stuck


def generate_report(updates, stuck_strategies):
    """Generates the Markdown report content."""

    total_roi = sum(u["roi"] for u in updates)
    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    lines = [
        f"# Weekly Strategy Optimization Report",
        f"**Period:** {start_date} to {end_date}",
        "",
        "## 1. Updated Strategies",
        "The following strategies were successfully optimized and updated:",
        ""
    ]

    if updates:
        lines.append("| Date | Strategy | ROI Improvement |")
        lines.append("|---|---|---|")
        for u in updates:
            lines.append(f"| {u['date']} | {u['strategy']} | +{u['roi']:.2f}% |")
    else:
        lines.append("*No strategies were updated this week.*")

    lines.append("")
    lines.append("## 2. Total Estimated Improvement")
    lines.append(f"**Total Portfolio ROI Improvement:** +{total_roi:.2f}%")
    lines.append("")

    lines.append("## 3. Stuck Strategies")
    lines.append("Strategies that failed optimization attempts multiple times without success (candidates for deletion or review):")
    lines.append("")

    if stuck_strategies:
        lines.append("| Strategy | Failed Attempts |")
        lines.append("|---|---|")
        for s in stuck_strategies:
            lines.append(f"| {s['strategy']} | {s['failures']} |")
    else:
        lines.append("*No stuck strategies identified.*")

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate Weekly Optimization Report")
    parser.add_argument("--dry-run", action="store_true", help="Generate report but do not commit/push")
    parser.add_argument("--days", type=int, default=7, help="Number of days to look back")
    args = parser.parse_args()

    print(f"Generating report for the last {args.days} days...")

    updates = get_weekly_updates(args.days)
    attempts = get_optimization_attempts(args.days)
    stuck = identify_stuck_strategies(attempts, updates)

    report_content = generate_report(updates, stuck)

    print("Writing report to WEEKLY_REPORT.md...")
    with REPORT_FILE.open("w") as f:
        f.write(report_content)

    if args.dry_run:
        print("\n[DRY-RUN] Report content preview:")
        print("-" * 40)
        print(report_content)
        print("-" * 40)
        print("Skipping git operations.")
        return

    # Git operations
    print("Committing and pushing report...")

    # Check if there are changes
    status = run_command(["git", "status", "--porcelain", str(REPORT_FILE)])
    if not status or not status.stdout.strip():
        print("No changes to report.")
        return

    # Add, Commit, Push
    run_command(["git", "add", str(REPORT_FILE)], check=True)

    commit_msg = f"docs: update weekly report ({datetime.now().strftime('%Y-%m-%d')})"
    run_command(["git", "commit", "-m", commit_msg], check=True)

    # Push to main branch (safe for detached HEAD)
    res = run_command(["git", "push", "origin", "HEAD:main"], check=False)
    if res and res.returncode == 0:
        print("Report pushed successfully.")
    else:
        print("Failed to push report. It is committed locally.")


if __name__ == "__main__":
    main()
