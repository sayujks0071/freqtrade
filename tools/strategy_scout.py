#!/usr/bin/env python3
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# Known sources to fallback or prioritize
KNOWN_SOURCES = [
    "freqtrade/freqtrade-strategies",
    "iterativ/freqtrade-strategies",
    "paulcpk/freqtrade-strategies-that-work",
]


def search_github(query="freqtrade strategy"):
    # Basic search, rate limited without token
    url = f"https://api.github.com/search/repositories?q={query}&sort=updated&order=desc"
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Freqtrade-Strategy-Scout")
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                return data.get("items", [])
            else:
                print(f"GitHub Search API returned {response.status}")
                return []
    except urllib.error.URLError as e:
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
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    report_file = f"user_data/reports/strategy_shortlist_{timestamp}.md"

    os.makedirs(os.path.dirname(report_file), exist_ok=True)

    with open(report_file, "w") as f:
        f.write(f"# Strategy Shortlist {timestamp}\n\n")
        f.write("| Repo | Stars | Description |\n")
        f.write("| --- | --- | --- |\n")
        for s in unique.values():
            desc = s.get("description", "") or ""
            desc = desc.replace("\n", " ")
            f.write(
                f"| [{s['full_name']}]({s['html_url']}) | {s.get('stargazers_count', 0)} | {desc} |\n"
            )

    print(f"Report generated: {report_file}")


if __name__ == "__main__":
    main()
