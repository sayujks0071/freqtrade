#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime

import requests


def scout_strategies(keywords, min_stars, limit, output_file):
    base_url = "https://api.github.com/search/repositories"
    query = f"{keywords} language:python"
    params = {"q": query, "sort": "updated", "order": "desc", "per_page": limit}

    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "Freqtrade-Scout"}

    try:
        response = requests.get(base_url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error searching GitHub: {e}")
        return

    items = data.get("items", [])
    results = []

    print(f"Found {len(items)} repositories. Filtering...")

    for item in items:
        if item["stargazers_count"] < min_stars:
            continue

        # Check license
        if not item.get("license"):
            print(f"Skipping {item['full_name']} (No license detected)")
            continue

        # Heuristics for quality
        score = 0
        score += item["stargazers_count"] * 0.1
        # Recency
        try:
            updated_at = datetime.strptime(item["updated_at"], "%Y-%m-%dT%H:%M:%SZ")
            days_since_update = (datetime.now() - updated_at).days
            if days_since_update < 30:
                score += 20
            elif days_since_update > 365:
                score -= 10
        except:
            updated_at = item["updated_at"]

        results.append(
            {
                "name": item["full_name"],
                "url": item["html_url"],
                "description": item["description"],
                "stars": item["stargazers_count"],
                "updated_at": item["updated_at"],
                "license": item["license"]["name"],
                "score": score,
            }
        )

    # Sort by score
    results.sort(key=lambda x: x["score"], reverse=True)

    # Output report
    lines = ["# Strategy Scout Report", ""]
    lines.append(f"Generated at: {datetime.now().isoformat()}")
    lines.append(f"Keywords: {keywords}")
    lines.append("")

    for r in results:
        lines.append(f"## [{r['name']}]({r['url']})")
        lines.append(f"- **Stars**: {r['stars']}")
        lines.append(f"- **Updated**: {r['updated_at']}")
        lines.append(f"- **License**: {r['license']}")
        lines.append(f"- **Score**: {r['score']:.1f}")
        lines.append(f"- Description: {r['description']}")
        lines.append("")

    with open(output_file, "w") as f:
        f.write("\n".join(lines))

    print(f"Report saved to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords", default="freqtrade strategy")
    parser.add_argument("--min-stars", type=int, default=5)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", default="user_data/reports/strategy_shortlist.md")

    args = parser.parse_args()

    scout_strategies(args.keywords, args.min_stars, args.limit, args.output)
