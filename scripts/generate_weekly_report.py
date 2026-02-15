import argparse
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


def get_git_log(days=7):
    """
    Get git log for the last N days.
    Returns a list of commit messages.
    """
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    cmd = ["git", "log", f"--since={since_date}", "--pretty=format:%s"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.splitlines()
    except subprocess.CalledProcessError as e:
        print(f"Error running git log: {e}")
        return []


def parse_git_log(log_lines):
    """
    Parse git log to find updated strategies and ROI improvement.
    Looking for messages like: perf: optimized {strategy} (+{roi}% ROI)
    Returns:
        updated_strategies (list of dicts): [{"strategy": name, "roi": float}]
        total_roi (float): Sum of ROI improvements
    """
    updated_strategies = []
    total_roi = 0.0

    # regex for: perf: optimized {strategy} (+{roi}% ROI)
    pattern = re.compile(r"perf: optimized\s+([\w\s-]+)\s+\(\+([\d\.]+)\%\s+ROI\)")

    for line in log_lines:
        match = pattern.search(line)
        if match:
            strategy = match.group(1)
            try:
                roi = float(match.group(2))
            except ValueError:
                continue

            updated_strategies.append({"strategy": strategy, "roi": roi})
            total_roi += roi

    return updated_strategies, total_roi


def parse_optimization_log(filepath="optimization_log.txt"):
    """
    Parse optimization log to find stuck strategies.
    A strategy is considered stuck if it has failed evaluations and no subsequent success.
    Returns:
        stuck_strategies (dict): {strategy_name: failure_count}
    """
    stuck_candidates = {}

    path = Path(filepath)
    if not path.exists():
        print(f"Warning: {filepath} not found. Skipping optimization log parsing.")
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return {}

    lines = content.splitlines()
    current_strategy = None

    for line in lines:
        if "Selected Strategy:" in line:
            parts = line.split("Selected Strategy:")
            if len(parts) > 1:
                current_strategy = parts[1].strip()

        if current_strategy:
            if "Evaluation FAILED" in line:
                stuck_candidates[current_strategy] = stuck_candidates.get(current_strategy, 0) + 1
            elif "Evaluation PASSED" in line:
                # If it passed, it's not stuck anymore. Remove from candidates.
                stuck_candidates.pop(current_strategy, None)

    return stuck_candidates


def generate_markdown(updated_strategies, total_roi, stuck_strategies):
    """
    Generate the markdown report content.
    """
    md = "# Weekly Strategy Optimization Report\n\n"
    md += f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n\n"

    md += "## 1. Updated Strategies\n"
    if updated_strategies:
        for item in updated_strategies:
            md += f"- **{item['strategy']}**: +{item['roi']:.2f}% ROI\n"
    else:
        md += "No strategies were updated this week.\n"

    md += "\n## 2. Total Estimated Improvement\n"
    md += f"**Total Portfolio ROI Improvement:** +{total_roi:.2f}%\n"

    md += "\n## 3. Stuck Strategies (Candidates for Deletion)\n"
    if stuck_strategies:
        md += "The following strategies failed to improve despite optimization attempts:\n"
        for strategy, count in stuck_strategies.items():
            md += f"- **{strategy}**: Failed {count} times\n"
    else:
        md += "No stuck strategies detected.\n"

    return md


def main():
    parser = argparse.ArgumentParser(description="Generate Weekly Strategy Report")
    parser.add_argument(
        "--days", type=int, default=7, help="Number of days to look back in git log"
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default="optimization_log.txt",
        help="Path to optimization log file",
    )
    parser.add_argument(
        "--output", type=str, default="WEEKLY_REPORT.md", help="Output markdown file"
    )
    parser.add_argument("--push", action="store_true", help="Commit and push the report to remote")
    args = parser.parse_args()

    # 1. Parse git log
    print(f"Fetching git log for last {args.days} days...")
    log_lines = get_git_log(days=args.days)
    updated_strategies, total_roi = parse_git_log(log_lines)
    print(f"Found {len(updated_strategies)} updated strategies.")

    # 2. Parse optimization log
    print(f"Parsing optimization log: {args.log_file}...")
    stuck_strategies = parse_optimization_log(args.log_file)
    print(f"Found {len(stuck_strategies)} stuck strategies.")

    # 3. Generate report
    report_content = generate_markdown(updated_strategies, total_roi, stuck_strategies)

    # 4. Write to file
    output_path = Path(args.output)
    try:
        with output_path.open("w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"Report generated: {output_path}")
    except Exception as e:
        print(f"Error writing report to {output_path}: {e}")
        sys.exit(1)

    # 5. Commit and Push if requested
    if args.push:
        try:
            subprocess.run(["git", "add", str(output_path)], check=True)
            subprocess.run(
                ["git", "commit", "-m", "docs: update weekly strategy report"], check=False
            )
            subprocess.run(["git", "push", "origin", "HEAD:develop"], check=True)
            print("Report pushed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Error during git operations: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
