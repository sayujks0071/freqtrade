#!/usr/bin/env python3
import datetime
import re
import subprocess
from pathlib import Path


# Configuration
REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = REPO_ROOT / "optimization_log.txt"
REPORT_FILE = REPO_ROOT / "WEEKLY_REPORT.md"


def run_command(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error running command {' '.join(cmd)}: {result.stderr}")
        return result.stdout.strip()
    except Exception as e:
        print(f"Exception running command {' '.join(cmd)}: {e}")
        return ""


def get_git_commits(days=7):
    # Format: Hash|Subject|Date
    cmd = ["git", "log", f"--since={days} days ago", "--pretty=format:%H|%s|%ad", "--date=iso"]
    output = run_command(cmd)
    commits = []
    if output:
        for line in output.split("\n"):
            parts = line.split("|")
            if len(parts) >= 3:
                commits.append({"hash": parts[0], "subject": parts[1], "date": parts[2]})
    return commits


def parse_optimization_logs(days=7):
    if not LOG_FILE.exists():
        print(f"Warning: {LOG_FILE} not found.")
        return []

    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
    attempts = []

    try:
        with LOG_FILE.open('r') as f:
            for line in f:
                # Parse timestamp: 2026-02-07 16:39:45,513
                # We can just take the first 19 chars
                if len(line) < 19:
                    continue
                try:
                    ts_str = line[:19]
                    dt = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                    if dt > cutoff_date:
                        if "Selected Strategy:" in line:
                            parts = line.split("Selected Strategy:")
                            if len(parts) > 1:
                                strategy = parts[1].strip()
                                attempts.append(strategy)
                except ValueError:
                    continue
    except Exception as e:
        print(f"Error reading log file: {e}")
        return []

    return attempts


def generate_report():
    commits = get_git_commits()
    attempts = parse_optimization_logs()

    updated_strategies = []
    total_roi_improvement = 0.0

    # Regex for commit message: perf: optimized {strategy} (+{roi}% ROI)
    # Example: perf: optimized DeltaSafeStrategy (+2.57% ROI)
    regex = re.compile(r"perf: optimized\s+(\w+)\s+\(\+([\d\.]+)\%\s+ROI\)")

    for commit in commits:
        match = regex.search(commit["subject"])
        if match:
            strategy = match.group(1)
            roi = float(match.group(2))
            updated_strategies.append(
                {"strategy": strategy, "roi": roi, "hash": commit["hash"], "date": commit["date"]}
            )
            total_roi_improvement += roi

    # Stuck strategies
    # Strategies attempted but not in updated_strategies (successful commits)
    successful_strategy_names = {s["strategy"] for s in updated_strategies}
    stuck_strategies = set([s for s in attempts if s not in successful_strategy_names])

    # Generate Markdown
    report = "# Weekly Optimization Report\n\n"
    report += f"**Date:** {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"

    report += "## 1. Updated Strategies\n"
    if updated_strategies:
        report += "| Strategy | ROI Improvement | Commit | Date |\n"
        report += "|---|---|---|---|\n"
        for s in updated_strategies:
            report += (
                f"| {s['strategy']} | +{s['roi']:.2f}% | {s['hash'][:7]} | {s['date'][:10]} |\n"
            )
    else:
        report += "No strategies were updated this week.\n"

    report += "\n## 2. Total Estimated Improvement in Portfolio ROI\n"
    report += f"**+{total_roi_improvement:.2f}%**\n"

    report += "\n## 3. Stuck Strategies (Candidates for Deletion)\n"
    if stuck_strategies:
        report += (
            "The following strategies were selected for optimization but failed to improve:\n\n"
        )
        for s in stuck_strategies:
            report += f"- {s}\n"
    else:
        report += "No stuck strategies found.\n"

    return report


def main():
    print("Generating weekly report...")
    report_content = generate_report()

    with REPORT_FILE.open("w") as f:
        f.write(report_content)

    print(f"Report generated at {REPORT_FILE}")

    # Git operations
    # Check if report changed
    run_command(["git", "add", str(REPORT_FILE)])

    # Only commit if there are changes
    status = run_command(["git", "status", "--porcelain"])
    if str(REPORT_FILE.name) in status:
        msg = f"docs: update weekly report ({datetime.datetime.now().strftime('%Y-%m-%d')})"
        run_command(["git", "commit", "-m", msg])
        print("Report committed.")

        # Push
        branch = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if branch:
            print(f"Pushing to {branch}...")
            # We use subprocess.run directly here to capture exit code properly in main
            res = subprocess.run(["git", "push", "origin", branch], capture_output=True, text=True)
            if res.returncode == 0:
                print("Report pushed successfully.")
            else:
                print(f"Failed to push report: {res.stderr}")
        else:
            print("Could not determine current branch. Skipping push.")
    else:
        print("No changes to report.")


if __name__ == "__main__":
    main()
