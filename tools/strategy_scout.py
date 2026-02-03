#!/usr/bin/env python3
import sys
import requests
import json
import time
from datetime import datetime, timezone

# Strategy Scout: Finds open-source Freqtrade strategies on GitHub
# Disclaimer: This is a discovery tool. All strategies must be audited.

GITHUB_API_URL = "https://api.github.com/search/repositories"
QUERY = "freqtrade strategy language:python created:>2023-01-01"

def search_strategies():
    print(f"Searching GitHub for: {QUERY}")

    # Check for rate limits or auth if provided (not implementing auth for simplicity unless needed)
    # Using public search, limited to 10 requests per minute usually.

    params = {
        "q": QUERY,
        "sort": "stars",
        "order": "desc",
        "per_page": 20
    }

    try:
        response = requests.get(GITHUB_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error searching GitHub: {e}")
        # Return mock data if API fails (e.g., rate limit) for demonstration
        return []

    results = []
    for item in data.get("items", []):
        repo = {
            "name": item["name"],
            "full_name": item["full_name"],
            "url": item["html_url"],
            "stars": item["stargazers_count"],
            "updated_at": item["updated_at"],
            "description": item["description"],
            "license": item["license"]["name"] if item["license"] else "None"
        }

        # Filter for license
        if repo["license"] == "None":
            continue

        results.append(repo)

    return results

def generate_report(strategies):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report = f"# Strategy Scout Report ({now})\n\n"
    report += "Top open-source Freqtrade strategies found on GitHub (with licenses).\n\n"

    report += "| Name | Stars | Updated | License | Description |\n"
    report += "|---|---|---|---|---|\n"

    for s in strategies:
        desc = (s['description'] or "").replace("|", "-")[:100]
        report += f"| [{s['full_name']}]({s['url']}) | {s['stars']} | {s['updated_at'][:10]} | {s['license']} | {desc} |\n"

    filename = f"user_data/reports/strategy_shortlist_{now}.md"
    try:
        with open(filename, "w") as f:
            f.write(report)
        print(f"Report saved to {filename}")
    except Exception as e:
        print(f"Error saving report: {e}")

if __name__ == "__main__":
    strategies = search_strategies()
    if strategies:
        generate_report(strategies)
    else:
        print("No strategies found.")
