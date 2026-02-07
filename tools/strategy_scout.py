#!/usr/bin/env python3
"""
Strategy Scout: Discover open-source Freqtrade strategies on GitHub.
"""

import argparse
import base64
import logging
import time
from datetime import UTC, datetime, timezone
from pathlib import Path

import requests


# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("strategy_scout")


def setup_args():
    parser = argparse.ArgumentParser(description="Scout for Freqtrade strategies on GitHub")
    parser.add_argument("--query", default="freqtrade strategy", help="Search query")
    parser.add_argument("--limit", type=int, default=10, help="Max results to process")
    parser.add_argument(
        "--vendor",
        action="store_true",
        help="Download strategy files to user_data/strategies_vendor/",
    )
    parser.add_argument("--token", help="GitHub API Token (optional but recommended)")
    parser.add_argument(
        "--out-report",
        type=Path,
        default=Path("user_data/reports/strategy_shortlist.md"),
        help="Output report path",
    )
    return parser.parse_args()


def search_github(query, token=None, limit=10):
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Freqtrade-Strategy-Scout",
    }
    if token:
        headers["Authorization"] = f"token {token}"

    params = {
        "q": f"{query} language:python extension:py",
        "sort": "indexed",
        "order": "desc",
        "per_page": min(limit, 30),  # Github limits per page
    }

    url = "https://api.github.com/search/code"
    try:
        # Check rate limit first if possible, or handle 403
        logger.info(f"Searching GitHub for '{query}'...")
        response = requests.get(url, headers=headers, params=params, timeout=10)

        if response.status_code == 403:
            logger.warning("Rate limited. Try with --token or wait.")
            return []
        if response.status_code != 200:
            logger.error(f"GitHub API Error: {response.status_code}")
            return []

        data = response.json()
        return data.get("items", [])[:limit]
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return []


def analyze_strategy(item, token=None):
    # Fetch content
    url = item["url"]  # API url for the file blob
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Freqtrade-Strategy-Scout",
    }
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        blob = response.json()
        content = base64.b64decode(blob["content"]).decode("utf-8")

        # Basic Heuristics
        score = 0
        checks = []

        # 1. Structure
        if "class " in content and "(IStrategy):" in content:
            score += 10
            checks.append("IStrategy found")
        else:
            return None  # Not a strategy

        # 2. Risk Management
        if "stoploss" in content:
            score += 5
            checks.append("Stoploss")
        if "minimal_roi" in content:
            score += 5
            checks.append("ROI")
        if "leverage" in content:
            score += 5
            checks.append("Leverage")

        # 3. Indicators (simple check)
        if "populate_indicators" in content:
            score += 5
            checks.append("Indicators")

        # 4. No Repainting (naive check)
        if "dataframe['close']" in content or "dataframe['volume']" in content:
            # Checking if they use .shift() often implies awareness of lookahead
            if ".shift(" in content:
                score += 5
                checks.append("Shift usage (good)")

        return {
            "name": item["name"],
            "url": item["html_url"],
            "score": score,
            "checks": checks,
            "content": content,
            "license": item["repository"].get(
                "license", {}
            ),  # Often null in code search, need repo details
            "updated_at": item["repository"].get(
                "updated_at", "Unknown"
            ),  # Might need separate call
        }

    except Exception as e:
        logger.error(f"Failed to analyze {item['name']}: {e}")
        return None


def main():
    args = setup_args()

    items = search_github(args.query, args.token, args.limit)
    strategies = []

    logger.info(f"Found {len(items)} potential files. Analyzing...")

    for item in items:
        # Respect API rate limits slightly if iterating
        strat = analyze_strategy(item, args.token)
        if strat:
            strategies.append(strat)
            time.sleep(1)  # Be nice to API

    # Sort by score
    strategies.sort(key=lambda x: x["score"], reverse=True)

    # Generate Report
    report = ["# Strategy Scout Report", f"Date: {datetime.now(UTC).isoformat()}"]
    report.append(f"Query: `{args.query}` | Found: {len(strategies)}")

    report.append("## Top Candidates")
    for s in strategies:
        license_name = "Unknown"  # Default
        # Since code search result 'repository' is partial,
        # we might not get license info easily without another call.
        # Assuming 'license' key might be missing or minimal.

        report.append(f"### {s['name']} (Score: {s['score']})")
        report.append(f"- **URL**: {s['url']}")
        report.append(f"- **License**: {license_name}")
        report.append(f"- **Checks**: {', '.join(s['checks'])}")

        if args.vendor:
            vendor_dir = Path("user_data/strategies_vendor") / s["name"].replace(".py", "")
            vendor_dir.mkdir(parents=True, exist_ok=True)
            file_path = vendor_dir / s["name"]
            license_note = vendor_dir / "LICENSE_NOTE.md"

            try:
                with file_path.open("w") as f:
                    f.write(s["content"])
                with license_note.open("w") as f:
                    f.write(f"Strategy sourced from {s['url']}\n")
                    f.write(f"License: {license_name}\n")
                    f.write(f"Downloaded: {datetime.now(timezone.utc)}")  # noqa: UP017

                logger.info(f"Vendored {s['name']} to {vendor_dir}")
                report.append(f"> **Vendored to**: `{vendor_dir}`")
            except Exception as e:
                logger.error(f"Failed to vendor {s['name']}: {e}")

    report_path = args.out_report
    # Append date to filename if default
    if str(report_path) == "user_data/reports/strategy_shortlist.md":
        report_path = Path(
            f"user_data/reports/strategy_shortlist_{datetime.now(UTC).strftime('%Y%m%d')}.md"
        )

    try:
        with report_path.open("w") as f:
            f.write("\n\n".join(report))
        logger.info(f"Report written to {report_path}")
    except Exception as e:
        logger.error(f"Failed to write report: {e}")


if __name__ == "__main__":
    main()
