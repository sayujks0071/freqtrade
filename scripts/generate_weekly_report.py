#!/usr/bin/env python3
"""
Weekly Reporting Script
Aggregates optimization logs and git commits to generate a weekly report.
"""
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


# Configuration
REPO_ROOT = Path(__file__).resolve().parent.parent
OPTIMIZATION_LOG = REPO_ROOT / "optimization_log.txt"
REPORT_FILE = REPO_ROOT / "WEEKLY_REPORT.md"


def run_command(cmd, capture=True):
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"Error running command: {' '.join(cmd)}")
        print(result.stderr)
    return result


def get_git_commits(days=7):
    """Get git commits from the last N days."""
    # Ensure we use UTC for consistency
    since_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cmd = [
        "git",
        "log",
        f"--since={since_date}",
        "--pretty=format:%h - %s (%an) [%cd]",
        "--date=short",
    ]
    result = run_command(cmd)
    if result.returncode == 0:
        return result.stdout.strip().splitlines()
    return []


def parse_optimization_log(days=7):
    """Parse optimization logs from the last N days."""
    if not OPTIMIZATION_LOG.exists():
        return []

    logs = []
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    with OPTIMIZATION_LOG.open("r") as f:
        for line in f:
            try:
                entry = json.loads(line)
                ts_str = entry.get("timestamp")
                if not ts_str:
                    continue

                try:
                    ts = datetime.fromisoformat(ts_str)
                except ValueError:
                    continue

                # Handle timezone naive timestamps from daily_optimize.py
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)

                if ts >= cutoff_date:
                    logs.append(entry)
            except json.JSONDecodeError:
                continue
    return logs


def generate_report(commits, logs):
    """Synthesize the report content."""

    # Section 1: Updated Strategies (Successes)
    successful_updates = [log for log in logs if log.get("status") == "success"]

    # Section 2: Total Estimated Improvement
    total_roi_improvement = sum(log.get("roi_change", 0.0) for log in successful_updates)

    # Section 3: Stuck Strategies (Failures)
    failed_attempts = [log for log in logs if log.get("status") == "failed"]

    report_lines = []
    report_lines.append(f"# Weekly Report - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    report_lines.append("")

    report_lines.append("## 1. Updated Strategies")
    if successful_updates:
        for update in successful_updates:
            strategy = update.get("strategy", "Unknown")
            roi = update.get("roi_change", 0.0)
            sharpe = update.get("sharpe_change", 0.0)
            report_lines.append(f"- **{strategy}**: ROI {roi:+.2f}%, Sharpe {sharpe:+.4f}")
    else:
        report_lines.append("No strategies were successfully updated this week.")
    report_lines.append("")

    report_lines.append("## 2. Total Estimated Improvement")
    report_lines.append(f"**Total Portfolio ROI Improvement:** {total_roi_improvement:+.2f}%")
    report_lines.append("")

    report_lines.append("## 3. Stuck Strategies (Candidates for Deletion)")
    if failed_attempts:
        # Deduplicate by strategy
        stuck_strategies = set(log.get("strategy") for log in failed_attempts)
        for strategy in stuck_strategies:
            count = sum(1 for log in failed_attempts if log.get("strategy") == strategy)
            report_lines.append(f"- **{strategy}**: Failed optimization {count} times.")
    else:
        report_lines.append("No failed optimization attempts recorded.")
    report_lines.append("")

    report_lines.append("## Recent Commits")
    if commits:
        for commit in commits:
            report_lines.append(f"- {commit}")
    else:
        report_lines.append("No commits in the last 7 days.")

    return "\n".join(report_lines)


def main():
    print("Generating weekly report...")

    commits = get_git_commits()
    logs = parse_optimization_log()

    report_content = generate_report(commits, logs)

    with REPORT_FILE.open("w") as f:
        f.write(report_content)

    print(f"Report generated at {REPORT_FILE}")

    # Commit and push
    # Check if there are changes
    status = run_command(["git", "status", "--porcelain"])
    if REPORT_FILE.name in status.stdout:
        print("Committing and pushing report...")
        run_command(["git", "add", str(REPORT_FILE)])
        run_command(["git", "commit", "-m", "docs: update weekly report"])

        # Determine current branch
        branch_res = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        current_branch = branch_res.stdout.strip()

        # If detached HEAD, assume main for pull target
        target_branch = "main" if current_branch == "HEAD" else current_branch

        print(f"Pulling rebase from origin/{target_branch}...")
        run_command(["git", "pull", "--rebase", "origin", target_branch], capture=False)

        push_cmd = ["git", "push", "origin"]
        if current_branch == "HEAD":
             push_cmd.append("HEAD:main")
        else:
             push_cmd.append(current_branch)

        print(f"Pushing to {push_cmd[-1]}...")
        run_command(push_cmd, capture=False)
    else:
        print("No changes to report.")

if __name__ == "__main__":
    main()
