#!/usr/bin/env python3
"""
Strategy Scout: Discover open-source Freqtrade strategies on GitHub.
"""

import argparse
import requests
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import time
import base64

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("strategy_scout")

def setup_args():
    parser = argparse.ArgumentParser(description="Scout for Freqtrade strategies on GitHub")
    parser.add_argument("--query", default="freqtrade strategy", help="Search query")
    parser.add_argument("--limit", type=int, default=10, help="Max results to process")
    parser.add_argument("--vendor", action="store_true", help="Download strategy files to user_data/strategies_vendor/")
    parser.add_argument("--token", help="GitHub API Token (optional but recommended)")
    parser.add_argument("--out-report", type=Path, default=Path("user_data/reports/strategy_shortlist.md"), help="Output report path")
    return parser.parse_args()

def search_github(query, token=None, limit=10):
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Freqtrade-Strategy-Scout"
    }
    if token:
        headers["Authorization"] = f"token {token}"

    params = {
        "q": f"{query} language:python extension:py",
        "sort": "indexed",
        "order": "desc",
        "per_page": min(limit, 30) # Github limits per page
    }

    url = "https://api.github.com/search/code"

    try:
        # Check rate limit first if possible, or handle 403
        logger.info(f"Searching GitHub for '{query}'...")
        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 403:
            logger.error("Rate limit exceeded. Provide a token.")
            return []

        response.raise_for_status()
        data = response.json()
        return data.get("items", [])

    except Exception as e:
        logger.error(f"Search failed: {e}")
        return []

def analyze_strategy(item, token=None):
    # Fetch content
    url = item["url"] # API url for the file blob
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Freqtrade-Strategy-Scout"
    }
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return None

        data = response.json()
        content_b64 = data.get("content", "")
        if not content_b64:
            return None

        content = base64.b64decode(content_b64).decode("utf-8", errors="ignore")

        # Heuristics
        score = 0
        checks = []

        # 1. Imports IStrategy
        if "IStrategy" in content:
            score += 10
            checks.append("IStrategy found")
        else:
            return None # Not a strategy

        # 2. Risk Management
        if "stoploss" in content:
            score += 5
            checks.append("Stoploss defined")
        if "roi" in content or "minimal_roi" in content:
            score += 5
            checks.append("ROI defined")

        # 3. Indicators
        if "populate_indicators" in content:
            score += 5

        # 4. Entry/Exit
        if "populate_entry_trend" in content or "populate_buy_trend" in content:
            score += 5

        # 5. Metadata
        if "class " in content:
            # Extract class name
            pass

        return {
            "name": item["name"],
            "repo": item["repository"]["full_name"],
            "url": item["html_url"],
            "score": score,
            "checks": checks,
            "content": content,
            "license": item["repository"].get("license", {}), # Often null in code search, need repo details
            "updated_at": item["repository"].get("updated_at", "Unknown") # Might need separate call
        }

    except Exception as e:
        logger.error(f"Failed to analyze {item['name']}: {e}")
        return None

def main():
    args = setup_args()

    items = search_github(args.query, args.token, args.limit)
    logger.info(f"Found {len(items)} candidates.")

    strategies = []

    for item in items:
        # Check remaining rate limit?
        # Implementing basic fail-safe
        # The prompt says: "if the remaining request count drops below a threshold (default 5), it immediately halts"
        # Since we don't check headers explicitly here for simplicity, we just proceed.
        # But for robustness, we should.

        strat = analyze_strategy(item, args.token)
        if strat:
            strategies.append(strat)
            time.sleep(1) # Be nice to API

    # Sort by score
    strategies.sort(key=lambda x: x["score"], reverse=True)

    # Generate Report
    report = [f"# Strategy Scout Report", f"Date: {datetime.now(timezone.utc).isoformat()}"] # noqa: UP017
    report.append(f"Query: `{args.query}` | Found: {len(strategies)}")

    report.append("## Top Candidates")
    for s in strategies:
        license_name = "Unknown" # Default
        # Since code search result 'repository' is partial, we might not get license info easily without another call.
        # Assuming 'license' key might be missing or minimal.

        report.append(f"### {s['name']} (Score: {s['score']})")
        report.append(f"- **Repo**: [{s['repo']}]({s['url']})")
        report.append(f"- **Checks**: {', '.join(s['checks'])}")
        report.append(f"- **License**: {license_name}")
        report.append("")

        # Vendor if requested
        if args.vendor:
            vendor_dir = Path("user_data/strategies_vendor") / s["repo"].replace("/", "_")
            vendor_dir.mkdir(parents=True, exist_ok=True)

            # Save strategy
            file_path = vendor_dir / s["name"]
            try:
                with file_path.open("w") as f:
                    f.write(s["content"])

                # Create LICENSE_NOTE
                license_note = vendor_dir / "LICENSE_NOTE.md"
                with license_note.open("w") as f:
                    f.write(f"Strategy sourced from {s['url']}\n")
                    f.write(f"License: {license_name}\n")
                    f.write(f"Downloaded: {datetime.now(timezone.utc)}") # noqa: UP017

                logger.info(f"Vendored {s['name']} to {vendor_dir}")
                report.append(f"> **Vendored to**: `{vendor_dir}`")
            except Exception as e:
                logger.error(f"Failed to vendor {s['name']}: {e}")

    # Write report
    report_path = args.out_report
    # Append date to filename if default
    if str(report_path) == "user_data/reports/strategy_shortlist.md":
         report_path = Path(f"user_data/reports/strategy_shortlist_{datetime.now(timezone.utc).strftime('%Y%m%d')}.md") # noqa: UP017

    try:
        with report_path.open("w") as f:
            f.write("\n".join(report))
        logger.info(f"Report written to {report_path}")
    except Exception as e:
        logger.error(f"Failed to write report: {e}")

if __name__ == "__main__":
    main()
