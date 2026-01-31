#!/usr/bin/env python3
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}


def search_github(query):
    url = "https://api.github.com/search/repositories"
    params = {"q": query, "sort": "updated", "order": "desc", "per_page": 20}
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
    except requests.RequestException as e:
        print(f"Error searching GitHub: {e}")
        return []

    if resp.status_code != 200:
        print(f"Error searching GitHub: {resp.status_code} {resp.text}")
        return []
    return resp.json().get("items", [])


def score_repo(repo):
    score = 0
    # Recency
    updated_at = datetime.strptime(repo["updated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    days_since_update = (datetime.now(timezone.utc) - updated_at).days
    if days_since_update < 30:
        score += 3
    elif days_since_update < 90:
        score += 1

    # Stars
    stars = repo["stargazers_count"]
    if stars > 50:
        score += 2
    if stars > 100:
        score += 1

    # License
    if repo.get("license"):
        score += 2  # Has license
        if repo["license"]["key"] in ["mit", "apache-2.0", "gpl-3.0"]:
            score += 1  # Standard license
    else:
        score -= 5  # No license -> reject/penalty

    return score


def main():
    query = "freqtrade strategy language:python"
    print(f"Searching GitHub for: {query}...")

    repos = search_github(query)

    scored_repos = []
    for repo in repos:
        s = score_repo(repo)
        if s > 0:  # minimal quality
            scored_repos.append((s, repo))

    scored_repos.sort(key=lambda x: x[0], reverse=True)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_file = f"user_data/reports/strategy_shortlist_{date_str}.md"

    with Path(report_file).open("w") as f:
        f.write(f"# Strategy Shortlist ({date_str})\n\n")
        f.write("| Score | Name | Stars | Updated | License | URL |\n")
        f.write("|---|---|---|---|---|---|\n")

        for score, repo in scored_repos:
            license_name = (
                repo["license"]["name"] if repo.get("license") else "None"
            )
            f.write(
                f"| {score} | {repo['name']} | {repo['stargazers_count']} | "
                f"{repo['updated_at'][:10]} | {license_name} | {repo['html_url']} |\n"
            )

    print(f"Found {len(scored_repos)} strategies. Report written to {report_file}")


if __name__ == "__main__":
    main()
