#!/usr/bin/env python3
"""
Strategy Scout for Freqtrade
Automatically discovers and shortlists the best open-source Python crypto trading strategies.
"""

import argparse
import datetime
import os
import sys
from pathlib import Path
from typing import Any, List, Dict

import requests

# Constants
GITHUB_API_URL = "https://api.github.com"
SEARCH_QUERIES = [
    "freqtrade strategy",
    "freqtrade-strategies",
    "FreqAI strategy",
    "crypto trading strategy python freqtrade",
]
KNOWN_SOURCES = ["freqtrade/freqtrade-strategies"]
RATE_LIMIT_BUFFER = 5
REQUEST_TIMEOUT = 10  # Seconds


class StrategyScout:
    def __init__(self, token: str | None = None):
        self.token = token
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"token {self.token}"})
        self.session.headers.update({"Accept": "application/vnd.github.v3+json"})
        self.candidates: List[Dict[str, Any]] = []

    def check_rate_limit(self):
        try:
            resp = self.session.get(f"{GITHUB_API_URL}/rate_limit", timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                core = data["resources"]["core"]
                remaining = core["remaining"]
                reset = core["reset"]
                if remaining < RATE_LIMIT_BUFFER:
                    reset_time = datetime.datetime.fromtimestamp(reset)
                    print(f"WARNING: Rate limit low ({remaining}). Resets at {reset_time}. Halting operations.")
                    return False
            return True
        except Exception as e:
            print(f"Error checking rate limit: {e}")
            return True  # Fail open if check fails

    def search_github(self):
        print("Searching GitHub...")
        found_repos = {}  # Dedup by full_name

        # 1. Search Queries
        for query in SEARCH_QUERIES:
            if not self.check_rate_limit():
                break

            print(f"Querying: {query}")
            params = {"q": query, "sort": "stars", "order": "desc", "per_page": 20}
            try:
                resp = self.session.get(
                    f"{GITHUB_API_URL}/search/repositories", params=params, timeout=REQUEST_TIMEOUT
                )
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    for item in items:
                        found_repos[item["full_name"]] = item
                else:
                    print(f"Search failed: {resp.status_code} {resp.text}")
            except Exception as e:
                print(f"Exception during search: {e}")

        # 2. Add Known Sources
        for source in KNOWN_SOURCES:
            if source not in found_repos:
                if not self.check_rate_limit():
                    break
                try:
                    resp = self.session.get(
                        f"{GITHUB_API_URL}/repos/{source}", timeout=REQUEST_TIMEOUT
                    )
                    if resp.status_code == 200:
                        found_repos[source] = resp.json()
                except Exception as e:
                    print(f"Error fetching source {source}: {e}")

        self.candidates = list(found_repos.values())
        print(f"Total unique candidates found: {len(self.candidates)}")

    def filter_and_score(self):
        print("Filtering and Scoring...")
        scored_candidates = []

        for repo in self.candidates:
            score = 0
            notes = []

            full_name = repo["full_name"]
            pushed_at = repo.get("pushed_at")
            license_data = repo.get("license")

            # 1. License Check
            license_name = "Unknown"
            if license_data:
                license_name = license_data.get("name", "Unknown")
                key = license_data.get("key", "")
                if key != "other" and key is not None:
                    score += 5  # Clear license
                elif key == "other":
                    license_name = "Other (Check manually)"
                    score += 1
            else:
                # Reject no license unless known source
                if full_name not in KNOWN_SOURCES:
                    continue

            # 2. Recency
            age_days = 9999
            if pushed_at:
                try:
                    pushed_dt = datetime.datetime.strptime(pushed_at, "%Y-%m-%dT%H:%M:%SZ")
                    age_days = (datetime.datetime.now() - pushed_dt).days
                    if age_days < 30:
                        score += 5
                    elif age_days < 90:
                        score += 3
                    elif age_days < 365:
                        score += 1
                    else:
                        score -= 2  # Stale
                except ValueError:
                    pass

            # 3. Description
            description = repo.get("description", "") or ""
            if "freqtrade" in description.lower():
                score += 2

            repo["scout_score"] = score
            repo["scout_notes"] = notes
            repo["license_name"] = license_name
            repo["age_days"] = age_days

            scored_candidates.append(repo)

        self.candidates = sorted(scored_candidates, key=lambda x: x["scout_score"], reverse=True)
        print(f"Candidates after filtering: {len(self.candidates)}")

    def _find_strategy_files(self, full_name):
        strategies = []
        found_path = None
        # Try common paths
        paths_to_check = ["user_data/strategies", "strategies", "."]

        for path in paths_to_check:
            try:
                url = f"{GITHUB_API_URL}/repos/{full_name}/contents/{path}"
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    contents = resp.json()
                    if isinstance(contents, list):
                        potential = [
                            f
                            for f in contents
                            if f["name"].endswith(".py") and f["name"] != "__init__.py"
                        ]
                        if potential:
                            strategies = potential
                            found_path = path
                            break
            except Exception:
                pass
        return strategies, found_path

    def _analyze_strategy_content(self, strat_file_info, repo):
        try:
            download_url = strat_file_info.get("download_url")
            if download_url:
                content_resp = requests.get(download_url, timeout=REQUEST_TIMEOUT)
                if content_resp.status_code == 200:
                    content = content_resp.text

                    if "stoploss" in content:
                        repo["scout_score"] += 2
                        repo["scout_notes"].append("Has stoploss")
                    if "minimal_roi" in content:
                        repo["scout_score"] += 2
                    if "populate_indicators" in content:
                        repo["scout_score"] += 2
                    if "can_short" in content:
                        repo["scout_notes"].append("Futures/Shorts mentioned")
                    if "martingale" in content.lower():
                        repo["scout_score"] -= 10
                        repo["scout_notes"].append("Martingale (Risk!)")
        except Exception as e:
            print(f"Failed to analyze content: {e}")

    def deep_inspect(self, limit=15):
        print(f"Deep inspecting top {limit} candidates...")
        count = 0
        for repo in self.candidates:
            if count >= limit:
                break

            if not self.check_rate_limit():
                break

            full_name = repo["full_name"]
            print(f"Inspecting {full_name}...")

            strategies, found_path = self._find_strategy_files(full_name)
            repo["strategy_count"] = len(strategies)
            repo["strategy_path"] = found_path

            if len(strategies) > 0:
                repo["scout_score"] += min(len(strategies), 5)
                # Inspect first strategy
                self._analyze_strategy_content(strategies[0], repo)
            else:
                repo["scout_score"] -= 5

            count += 1

        self.candidates = sorted(self.candidates, key=lambda x: x["scout_score"], reverse=True)

    def generate_report(self):
        print("Generating report...")
        report_dir = Path("user_data/reports")
        report_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        filename = report_dir / f"strategy_shortlist_{date_str}.md"

        top_10 = self.candidates[:10]

        with filename.open("w") as f:
            f.write(f"# Freqtrade Strategy Scout Report - {date_str}\n\n")
            f.write("## Top Candidates\n\n")
            for i, repo in enumerate(top_10, 1):
                f.write(f"### {i}. [{repo['full_name']}]({repo['html_url']})\n")
                f.write(f"- Score: {repo.get('scout_score', 0)}\n")
                f.write(f"- License: {repo.get('license_name', 'Unknown')}\n")
                f.write(f"- Notes: {', '.join(repo.get('scout_notes', []))}\n\n")

        print(f"Report written to {filename}")
        return top_10

    def vendor_strategies(self, candidates, top_n=5):
        print(f"Vendoring top {top_n} strategies...")
        vendor_base_dir = Path("user_data/strategies_vendor")
        vendor_base_dir.mkdir(parents=True, exist_ok=True)

        count = 0
        for repo in candidates:
            if count >= top_n:
                break

            path = repo.get("strategy_path")
            if not path:
                continue

            full_name = repo["full_name"]
            safe_name = full_name.replace("/", "_")
            vendor_dir = vendor_base_dir / safe_name
            vendor_dir.mkdir(parents=True, exist_ok=True)

            print(f"Vendoring {full_name} to {vendor_dir}...")

            # Re-fetch file list as we might need to iterate
            strategies, _ = self._find_strategy_files(full_name)

            for s in strategies[:3]: # Limit to 3 files
                durl = s.get("download_url")
                if durl:
                    try:
                        r = requests.get(durl, timeout=REQUEST_TIMEOUT)
                        if r.status_code == 200:
                            (vendor_dir / s["name"]).write_text(r.text)
                    except Exception as e:
                        print(f"Error downloading {s['name']}: {e}")

            # Add license note
            (vendor_dir / "LICENSE_NOTE.md").write_text(
                f"Source: {repo['html_url']}\nLicense: {repo.get('license_name')}\n"
            )
            count += 1

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", help="GitHub Token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--vendor", action="store_true", help="Vendor strategies")
    args = parser.parse_args()

    scout = StrategyScout(token=args.token)
    scout.search_github()
    scout.filter_and_score()
    scout.deep_inspect()
    candidates = scout.generate_report()

    if args.vendor:
        scout.vendor_strategies(candidates)

if __name__ == "__main__":
    main()
