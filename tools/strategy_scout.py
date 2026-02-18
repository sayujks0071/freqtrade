#!/usr/bin/env python3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests


# Known sources to fallback or prioritize
KNOWN_SOURCES = [
    "freqtrade/freqtrade-strategies",
    "iterativ/freqtrade-strategies",
    "paulcpk/freqtrade-strategies-that-work",
]


def search_github(query="freqtrade strategy"):
    # Basic search, rate limited without token
    url = "https://api.github.com/search/repositories"
    params = {
        "q": query,
        "sort": "updated",
        "order": "desc",
    }
    headers = {
        "User-Agent": "Freqtrade-Strategy-Scout",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get("items", [])
        else:
            print(f"GitHub Search API returned {response.status_code}")
            return []
    except requests.RequestException as e:
        print(f"GitHub Search failed: {e}")
        return []
    except Exception as e:
        print(f"Error: {e}")
        return []


def main():
    if "--help" in sys.argv:
        print("Usage: strategy_scout.py")
        sys.exit(0)

    print("Scouting for strategies...")
    strategies = []

    # Add known sources
    for repo in KNOWN_SOURCES:
        strategies.append(
            {
                "full_name": repo,
                "html_url": f"https://github.com/{repo}",
                "description": "Known Source",
                "stargazers_count": "N/A",
            }
        )

    # Try search
    found = search_github("freqtrade strategy python")
    if found:
        strategies.extend(found)

    # Deduplicate
    unique = {}
    for s in strategies:
        if s["html_url"] not in unique:
            unique[s["html_url"]] = s

    # Generate Report
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")  # noqa: UP017
    report_file = Path(f"user_data/reports/strategy_shortlist_{timestamp}.md")

    report_file.parent.mkdir(parents=True, exist_ok=True)

    with report_file.open("w") as f:
        f.write(f"# Strategy Shortlist {timestamp}\n\n")
        f.write("| Repo | Stars | Description |\n")
        f.write("| --- | --- | --- |\n")
        for s in unique.values():
            desc = s.get("description", "") or ""
            desc = desc.replace("\n", " ")
            repo_link = f"[{s['full_name']}]({s['html_url']})"
            stars = s.get("stargazers_count", 0)
            f.write(f"| {repo_link} | {stars} | {desc} |\n")

    print(f"Report generated: {report_file}")


if __name__ == "__main__":
    main()
