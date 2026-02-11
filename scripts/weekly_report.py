#!/usr/bin/env python3
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


OPTIMIZATION_LOG_FILE = Path("optimization_log.txt")
REPORT_FILE = Path("WEEKLY_REPORT.md")


def get_git_logs(days=7):
    """Get git logs for the last N days."""
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    cmd = ["git", "log", f"--since={since_date}", "--pretty=format:%s"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error getting git logs: {result.stderr}")
        return []
    return result.stdout.splitlines()


def parse_optimization_log(days=7):
    """Parse optimization log for the last N days."""
    if not OPTIMIZATION_LOG_FILE.exists():
        return []

    entries = []
    cutoff_date = datetime.now() - timedelta(days=days)

    with OPTIMIZATION_LOG_FILE.open("r") as f:
        # Skip header
        next(f, None)
        for line in f:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue

            date_str = parts[0]
            try:
                entry_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

            if entry_date >= cutoff_date:
                # robust extraction
                strategy = parts[1]
                if "Strategy:" in strategy:
                    strategy = strategy.split("Strategy:", 1)[1].strip()

                outcome = parts[2]
                if "Outcome:" in outcome:
                    outcome = outcome.split("Outcome:", 1)[1].strip()

                entries.append(
                    {
                        "date": entry_date,
                        "strategy": strategy,
                        "outcome": outcome,
                        "details": parts[3] if len(parts) > 3 else "",
                    }
                )
    return entries


def generate_report_content(updated_strategies, total_roi_improvement, stuck_strategies):
    report_content = "# Weekly Strategy Report\n\n"
    report_content += f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n\n"

    report_content += "## 1. Updated Strategies\n"
    if updated_strategies:
        for strat in sorted(updated_strategies):
            report_content += f"- {strat}\n"
    else:
        report_content += "No strategies updated this week.\n"
    report_content += "\n"

    report_content += "## 2. Total ROI Improvement\n"
    report_content += f"Total estimated improvement: {total_roi_improvement:+.2f}%\n\n"

    report_content += "## 3. Stuck Strategies (Candidates for Deletion)\n"
    if stuck_strategies:
        for strat in sorted(stuck_strategies):
            report_content += f"- {strat}\n"
    else:
        report_content += "No stuck strategies detected.\n"
    return report_content


def main():
    print("Generating weekly report...")

    # 1. Parse Git Logs for ROI and Updates
    logs = get_git_logs()
    updated_strategies = set()
    total_roi_improvement = 0.0

    # Regex to match "perf: optimized {strategy} ({roi_diff:+.2f}% ROI improvement)"
    roi_pattern = re.compile(r"perf: optimized\s+(\w+)\s+\(([+\-]?\d+\.\d+)%\s+ROI improvement\)")

    for log in logs:
        match = roi_pattern.search(log)
        if match:
            strategy = match.group(1)
            roi = float(match.group(2))
            updated_strategies.add(strategy)
            total_roi_improvement += roi

    # 2. Parse Optimization Log for Stuck Strategies
    opt_entries = parse_optimization_log()
    strategy_outcomes = {}

    for entry in opt_entries:
        strat = entry["strategy"]
        outcome = entry["outcome"]
        if strat not in strategy_outcomes:
            strategy_outcomes[strat] = {"success": 0, "failure": 0}

        if outcome == "SUCCESS":
            strategy_outcomes[strat]["success"] += 1
        elif outcome == "FAILURE":
            strategy_outcomes[strat]["failure"] += 1

    stuck_strategies = []
    for strat, counts in strategy_outcomes.items():
        # A strategy is stuck if it has failures but NO successes in the period
        if counts["failure"] > 0 and counts["success"] == 0:
            stuck_strategies.append(f"{strat} (Failed {counts['failure']} times)")

    # 3. Generate Report
    report_content = generate_report_content(
        updated_strategies, total_roi_improvement, stuck_strategies
    )

    with REPORT_FILE.open("w") as f:
        f.write(report_content)

    print(f"Report generated: {REPORT_FILE}")


if __name__ == "__main__":
    main()
