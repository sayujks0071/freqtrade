"""
Strategy Scout
Searches GitHub for Freqtrade strategies, audits them for safety, and generates a shortlist.
"""

import argparse
import base64
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
KNOWN_SOURCES = [
    "paulcpk/freqtrade-strategies-that-work",
    "freqtrade/freqtrade-strategies",
    "iterativv/NostalgiaForInfinity",
]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", help="GitHub API Token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--limit", type=int, default=10, help="Max repos to scan")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("user_data/reports"), help="Output directory"
    )
    parser.add_argument(
        "--vendor",
        action="store_true",
        help="Vendor strategies to user_data/strategies_vendor",
    )
    return parser.parse_args()


def github_request(url, token=None):
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code == 200:
        return response.json()
    if response.status_code == 403:
        logger.warning("GitHub API Rate Limit Exceeded")
    return None


def search_repositories(token, limit):
    query = "topic:freqtrade-strategy language:python sort:updated"
    url = f"{GITHUB_API}/search/repositories?q={query}&per_page={limit}"
    data = github_request(url, token)
    if data:
        return data.get("items", [])
    return []


def get_repo_content(repo_full_name, path="", token=None):
    url = f"{GITHUB_API}/repos/{repo_full_name}/contents/{path}"
    return github_request(url, token)


def decode_content(content_data):
    if content_data.get("encoding") == "base64":
        return base64.b64decode(content_data["content"]).decode("utf-8", errors="ignore")
    return ""


def check_indicators(content, notes):
    indicators = []
    if "talib" in content:
        indicators.append("talib")
    if "qtpylib" in content:
        indicators.append("qtpylib")
    if "pandas_ta" in content:
        indicators.append("pandas_ta")
    if "technical" in content:
        indicators.append("technical")
    if indicators:
        notes.append(f"Indicators: {', '.join(indicators)}")


def analyze_strategy(content):
    score = 0
    notes = []

    # Check for Strategy Class
    if "class " in content and "(IStrategy)" in content:
        score += 10
        notes.append("Implements IStrategy")
    else:
        return 0, ["Not a strategy file"]

    # Check for Repainting Prevention
    if "process_only_new_candles = True" in content:
        score += 20
        notes.append("Prevents repainting (process_only_new_candles=True)")
    else:
        score -= 50
        notes.append("Risk: process_only_new_candles missing or False")

    # Check for Risk Controls
    if "stoploss =" in content:
        score += 10
        notes.append("Has stoploss")
    if "minimal_roi =" in content:
        score += 10
        notes.append("Has ROI")

    # Check for Docstrings
    if '"""' in content or "'''" in content:
        score += 5
        notes.append("Has documentation")

    check_indicators(content, notes)

    # Check for Futures Compatibility (Timeframes, etc)
    # Regex for timeframe
    tf_match = re.search(r"timeframe\s*=\s*['\"]([^'\"]+)['\"]", content)
    if tf_match:
        notes.append(f"Timeframe: {tf_match.group(1)}")

    # Check for dangerous patterns
    if "Martingale" in content:
        score -= 100
        notes.append("Risk: Martingale detected")

    return score, notes


def process_repo(repo, token, vendor=False):
    name = repo["full_name"]
    logger.info(f"Scanning {name}...")

    license_info = repo.get("license")
    license_name = license_info["name"] if license_info else "None"

    if not license_info and name not in KNOWN_SOURCES:
        logger.warning(f"Skipping {name}: No license")
        return None

    updated_at = datetime.fromisoformat(repo["updated_at"].replace("Z", "+00:00"))
    if datetime.now(UTC) - updated_at > timedelta(days=365):
        logger.warning(f"Skipping {name}: Stale (>1 year)")
        return None

    path = "user_data/strategies" if "freqtrade" in name else ""
    contents = get_repo_content(name, path, token)
    if not contents:
        contents = get_repo_content(name, "", token)

    if not isinstance(contents, list):
        return None

    strategy_files = [f for f in contents if f["name"].endswith(".py") and f["type"] == "file"]
    results = []

    for f in strategy_files[:3]:
        file_data = get_repo_content(name, f["path"], token)
        if not file_data:
            continue

        content = decode_content(file_data)
        score, notes = analyze_strategy(content)

        if score > 0:
            results.append(
                {
                    "repo": name,
                    "file": f["name"],
                    "url": f["html_url"],
                    "score": score,
                    "license": license_name,
                    "updated": repo["updated_at"],
                    "notes": notes,
                    "raw_content": content if vendor else None,
                }
            )
    return results


def main():
    args = parse_args()

    logger.info("Scouting for strategies...")
    repos = search_repositories(args.token, args.limit)

    all_results = []
    for repo in repos:
        results = process_repo(repo, args.token, args.vendor)
        if results:
            all_results.extend(results)

    # Generate Report
    all_results.sort(key=lambda x: x["score"], reverse=True)

    report_name = f"strategy_shortlist_{datetime.now(UTC).strftime('%Y%m%d')}.md"
    report_file = args.output_dir / report_name

    with report_file.open("w") as f:
        f.write("# Strategy Scout Shortlist\n\n")
        f.write(f"Date: {datetime.now(UTC).isoformat()}\n\n")

        for res in all_results:
            f.write(f"## {res['file']} (Score: {res['score']})\n")
            f.write(f"- **Repo**: [{res['repo']}]({res['url']})\n")
            f.write(f"- **License**: {res['license']}\n")
            f.write(f"- **Updated**: {res['updated']}\n")
            f.write("- **Notes**:\n")
            for n in res["notes"]:
                f.write(f"  - {n}\n")
            f.write("\n")

            # Vendor Logic
            if args.vendor and res["raw_content"]:
                vendor_dir = Path(f"user_data/strategies_vendor/{res['repo'].replace('/', '_')}")
                vendor_dir.mkdir(parents=True, exist_ok=True)

                (vendor_dir / res["file"]).write_text(res["raw_content"])

                # License Note
                (vendor_dir / "LICENSE_NOTE.md").write_text(
                    f"Strategy sourced from {res['repo']}\nLicense: {res['license']}\n"
                )

    logger.info(f"Report written to {report_file}")
    if args.vendor:
        logger.info("Strategies vendored to user_data/strategies_vendor/")


if __name__ == "__main__":
    main()
