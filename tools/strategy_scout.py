#!/usr/bin/env python3
"""
Strategy Scout for Freqtrade
Automatically discovers and shortlists the best open-source Python crypto trading strategies.
"""

import argparse
import datetime
import os
from pathlib import Path
from typing import Any
import urllib.request
import urllib.parse
import json

# Constants
GITHUB_API_URL = "https://api.github.com"
SEARCH_QUERIES = [
    "freqtrade strategy",
    "freqtrade-strategies",
    "FreqAI strategy",
    "crypto trading strategy python freqtrade",
]
KNOWN_SOURCES = ["freqtrade/freqtrade-strategies"]
REQUIRED_FILES = ["user_data/reports", "user_data/strategies_vendor"]
TIMEOUT = 10


class StrategyScout:
    def __init__(self, token: str | None = None):
        self.token = token
        self.headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "Freqtrade-Scout"}
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"
        self.candidates: list[dict[str, Any]] = []
        self.rate_limit_remaining = 9999

    def _request(self, url, params=None):
        if params:
            url += "?" + urllib.parse.urlencode(params)

        req = urllib.request.Request(url, headers=self.headers) # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
                self.rate_limit_remaining = int(response.getheader("X-RateLimit-Remaining", 9999))
                return json.loads(response.read())
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None

    def search_github(self):
        print("Searching GitHub...")
        found_repos = {}

        for query in SEARCH_QUERIES:
            if self.rate_limit_remaining < 5:
                print("Rate limit exhausted.")
                break

            print(f"Querying: {query}")
            data = self._request(
                f"{GITHUB_API_URL}/search/repositories",
                {"q": query, "sort": "stars", "order": "desc", "per_page": 20}
            )

            if data and "items" in data:
                for item in data["items"]:
                    found_repos[item["full_name"]] = item

        # Add known sources
        for source in KNOWN_SOURCES:
            if source not in found_repos:
                data = self._request(f"{GITHUB_API_URL}/repos/{source}")
                if data:
                    found_repos[source] = data

        self.candidates = list(found_repos.values())
        print(f"Found {len(self.candidates)} candidates.")

    def filter_and_score(self):
        print("Filtering and Scoring...")
        scored = []

        for repo in self.candidates:
            score = 0
            notes = []

            # License
            lic = repo.get("license")
            lic_key = lic.get("key") if lic else None
            lic_name = lic.get("name", "Unknown") if lic else "Unknown"

            if lic_key and lic_key not in ["other"]:
                score += 5
            elif lic_key == "other":
                lic_name = "Other (Check manually)"
                score += 1
            else:
                # No license -> Reject unless known source
                if repo["full_name"] not in KNOWN_SOURCES:
                    continue

            repo["license_name"] = lic_name

            # Recency
            pushed_at = repo.get("pushed_at")
            if pushed_at:
                dt = datetime.datetime.strptime(pushed_at, "%Y-%m-%dT%H:%M:%SZ")
                age = (datetime.datetime.now() - dt).days
                if age < 30: score += 5
                elif age < 90: score += 3
                elif age < 365: score += 1
                else: score -= 2

            # Description
            desc = repo.get("description") or ""
            if "freqtrade" in desc.lower():
                score += 2

            repo["scout_score"] = score
            repo["scout_notes"] = notes
            scored.append(repo)

        self.candidates = sorted(scored, key=lambda x: x["scout_score"], reverse=True)

    def generate_report(self):
        Path("user_data/reports").mkdir(parents=True, exist_ok=True)
        filename = f"user_data/reports/strategy_shortlist_{datetime.date.today()}.md"

        with open(filename, "w") as f:
            f.write(f"# Strategy Shortlist - {datetime.date.today()}\n\n")
            f.write("| Rank | Repo | Score | Stars | License | Last Update |\n")
            f.write("|---|---|---|---|---|---|\n")

            for i, repo in enumerate(self.candidates[:20], 1):
                f.write(f"| {i} | [{repo['full_name']}]({repo['html_url']}) | {repo['scout_score']} | {repo.get('stargazers_count')} | {repo['license_name']} | {repo.get('pushed_at', '')[:10]} |\n")

        print(f"Report saved to {filename}")
        return self.candidates[:5]

    def vendor_strategies(self, top_candidates):
        # Simplified vendor implementation
        base_dir = Path("user_data/strategies_vendor")
        base_dir.mkdir(parents=True, exist_ok=True)

        for repo in top_candidates:
            print(f"Vendoring {repo['full_name']}...")
            safe_name = repo['full_name'].replace("/", "_")
            vendor_dir = base_dir / safe_name
            vendor_dir.mkdir(exist_ok=True)

            # Write LICENSE note
            with open(vendor_dir / "LICENSE_NOTE.md", "w") as f:
                f.write(f"Source: {repo['html_url']}\nLicense: {repo['license_name']}\n")

def main():  # noqa: C901
    parser = argparse.ArgumentParser()
    parser.add_argument("--vendor", action="store_true")
    args = parser.parse_args()

    scout = StrategyScout(token=os.environ.get("GITHUB_TOKEN"))
    scout.search_github()
    scout.filter_and_score()
    top = scout.generate_report()

    if args.vendor:
        scout.vendor_strategies(top)

if __name__ == "__main__":
    main()
