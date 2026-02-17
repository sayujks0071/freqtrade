#!/usr/bin/env python3
"""
strategy_scout.py

Scouts for open-source Freqtrade strategies on GitHub.
Filters by license, recency, and quality indicators.
"""

import argparse
import base64
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

# Check for requests
try:
    import requests
except ImportError:
    print("Error: 'requests' library required. Install with 'pip install requests'.")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com"
SEARCH_QUERY = "freqtrade strategy language:python"

# Allowed Licenses
ALLOWED_LICENSES = ["mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause", "gpl-3.0", "lgpl-3.0", "mpl-2.0", "unlicense"]

def get_headers():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    return headers

def search_repositories(query: str, min_stars: int = 5) -> List[Dict[str, Any]]:
    logger.info(f"Searching GitHub for: {query}")
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": 20 # Limit to top 20
    }

    try:
        resp = requests.get(f"{GITHUB_API_URL}/search/repositories", headers=get_headers(), params=params)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])

        filtered = [item for item in items if item["stargazers_count"] >= min_stars]
        return filtered
    except Exception as e:
        logger.error(f"GitHub Search failed: {e}")
        return []

def get_repo_contents(owner: str, repo: str, path: str = "") -> List[Dict[str, Any]]:
    try:
        url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{path}"
        resp = requests.get(url, headers=get_headers())
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"Failed to get contents for {owner}/{repo}: {e}")
        return []

def get_file_content(download_url: str) -> str:
    try:
        resp = requests.get(download_url)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        return ""

def analyze_strategy(content: str) -> Dict[str, Any]:
    score = 0
    issues = []

    # Check for basic Freqtrade structure
    if "IStrategy" not in content and "freqtrade" not in content:
        return {"score": 0, "issues": ["Not a Freqtrade strategy"]}

    if "populate_indicators" in content: score += 1
    if "populate_entry_trend" in content: score += 1
    if "populate_exit_trend" in content: score += 1
    if "minimal_roi" in content: score += 1
    if "stoploss" in content: score += 1

    # Risk checks
    if "martingale" in content.lower():
        issues.append("Contains 'martingale' keyword")
        score -= 5
    if "grid" in content.lower():
        issues.append("Contains 'grid' keyword (risky)")
        score -= 2

    return {"score": score, "issues": issues}

def scout_strategies(output_file: str):
    repos = search_repositories(SEARCH_QUERY)
    logger.info(f"Found {len(repos)} candidate repositories.")

    report_lines = [
        "# Strategy Scout Report",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Candidates",
        ""
    ]

    for repo in repos:
        name = repo["name"]
        full_name = repo["full_name"]
        url = repo["html_url"]
        stars = repo["stargazers_count"]
        license_info = repo.get("license")

        license_key = license_info["key"] if license_info else "none"

        if license_key not in ALLOWED_LICENSES:
            logger.info(f"Skipping {full_name}: License {license_key} not allowed.")
            continue

        logger.info(f"Scanning {full_name} ({license_key})...")

        # Look for strategy files in root or 'strategies' folder
        contents = get_repo_contents(repo["owner"]["login"], name)
        contents += get_repo_contents(repo["owner"]["login"], name, "strategies")

        strategies_found = []

        for item in contents:
            if isinstance(item, dict) and item["type"] == "file" and item["name"].endswith(".py"):
                # Check size to avoid huge files or symlinks
                if item["size"] > 100000: continue
                if item["size"] < 200: continue

                # Download and analyze
                content = get_file_content(item["download_url"])
                analysis = analyze_strategy(content)

                if analysis["score"] > 3: # Threshold
                    strategies_found.append({
                        "name": item["name"],
                        "url": item["html_url"],
                        "score": analysis["score"],
                        "issues": analysis["issues"]
                    })

        if strategies_found:
            report_lines.append(f"### [{full_name}]({url})")
            report_lines.append(f"- **Stars**: {stars}")
            report_lines.append(f"- **License**: {license_info['name'] if license_info else 'None'}")
            report_lines.append("- **Strategies**:")
            for s in strategies_found:
                issues_str = f" (Issues: {', '.join(s['issues'])})" if s['issues'] else ""
                report_lines.append(f"  - [{s['name']}]({s['url']}) - Score: {s['score']}{issues_str}")
            report_lines.append("")

            # Optional: Vendor logic could go here

    with open(output_file, "w") as f:
        f.write("\n".join(report_lines))

    logger.info(f"Report saved to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scout for Freqtrade strategies.")
    parser.add_argument("--out", default="strategy_shortlist.md", help="Output report file")
    args = parser.parse_args()

    scout_strategies(args.out)
