#!/usr/bin/env python3
import argparse
import datetime
import os
import time
from pathlib import Path
from typing import Any, Dict, List

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
TIMEOUT = 10


class StrategyScout:
    def __init__(self, token: str = None):
        self.token = token
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"token {self.token}"})
        self.session.headers.update({"Accept": "application/vnd.github.v3+json"})
        self.candidates: List[Dict[str, Any]] = []

    def check_rate_limit(self) -> bool:
        try:
            resp = self.session.get(f"{GITHUB_API_URL}/rate_limit", timeout=TIMEOUT)
            if resp.status_code == 200:
                core = resp.json()["resources"]["core"]
                remaining = core["remaining"]
                reset = core["reset"]
                # print(f"DEBUG: Rate limit remaining: {remaining}")
                if remaining < RATE_LIMIT_BUFFER:
                    reset_time = datetime.datetime.fromtimestamp(reset)
                    print(f"WARNING: Rate limit low. Resets at {reset_time}. Halting.")
                    return False
            return True
        except Exception as e:
            print(f"Error checking rate limit: {e}")
            return True  # Assume ok

    def search_github(self):
        print("Searching GitHub...")
        found_repos = {}  # Dedup by full_name

        for query in SEARCH_QUERIES:
            if not self.check_rate_limit():
                break

            print(f"Querying: {query}")
            # Sort by stars to get best quality first
            params = {"q": query, "sort": "stars", "order": "desc", "per_page": 20}
            try:
                resp = self.session.get(
                    f"{GITHUB_API_URL}/search/repositories", params=params, timeout=TIMEOUT
                )
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    for item in items:
                        found_repos[item["full_name"]] = item
                else:
                    print(f"Search failed: {resp.status_code} {resp.text}")
            except Exception as e:
                print(f"Exception during search: {e}")

        # Add Known Sources
        for source in KNOWN_SOURCES:
            if source not in found_repos:
                if not self.check_rate_limit():
                    break
                try:
                    resp = self.session.get(f"{GITHUB_API_URL}/repos/{source}", timeout=TIMEOUT)
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
            if license_data and license_data.get("key") != "other":
                license_name = license_data.get("name", "Unknown")
                score += 5  # Clear license
            elif license_data and license_data.get("key") == "other":
                license_name = "Other (Check manually)"
                score += 1
            else:
                # No license usually means unsafe to use legally
                if full_name not in KNOWN_SOURCES:
                    # Penalize heavily unless known source
                    score -= 5
                    notes.append("No License")

            # 2. Recency
            if pushed_at:
                dt = datetime.datetime.strptime(pushed_at, "%Y-%m-%dT%H:%M:%SZ")
                age_days = (datetime.datetime.now() - dt).days
                if age_days < 30:
                    score += 5
                elif age_days < 90:
                    score += 3
                elif age_days < 365:
                    score += 1
                else:
                    score -= 2  # Stale
            else:
                age_days = 9999

            # 3. Description
            description = repo.get("description", "") or ""
            if "freqtrade" in description.lower():
                score += 2

            repo["scout_score"] = score
            repo["scout_notes"] = notes
            repo["license_name"] = license_name
            repo["age_days"] = age_days

            scored_candidates.append(repo)

        # Sort by preliminary score
        self.candidates = sorted(scored_candidates, key=lambda x: x["scout_score"], reverse=True)

    def deep_inspect(self, limit=15):
        print(f"Deep inspecting top {limit} candidates...")
        inspected_count = 0

        for repo in self.candidates:
            if inspected_count >= limit:
                break

            if not self.check_rate_limit():
                print("Rate limit exhausted, stopping inspection.")
                break

            full_name = repo["full_name"]
            # print(f"Inspecting {full_name}...")

            # Find strategy files
            strategies = []
            found_path = None
            paths_to_check = ["user_data/strategies", "strategies", "."]

            for path in paths_to_check:
                try:
                    url = f"{GITHUB_API_URL}/repos/{full_name}/contents/{path}"
                    resp = self.session.get(url, timeout=TIMEOUT)
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

            repo["strategy_count"] = len(strategies)
            repo["strategy_path"] = found_path
            repo["strategies"] = strategies  # Store for vendoring

            if len(strategies) > 0:
                repo["scout_score"] += min(len(strategies), 5) * 1

                # Check content of first strategy
                strat_file = strategies[0]
                download_url = strat_file.get("download_url")
                if download_url:
                    try:
                        r = requests.get(download_url, timeout=TIMEOUT)
                        if r.status_code == 200:
                            content = r.text
                            if "stoploss" in content:
                                repo["scout_score"] += 2
                                repo["scout_notes"].append("Has stoploss")
                            if "minimal_roi" in content:
                                repo["scout_score"] += 2
                                repo["scout_notes"].append("Has ROI")
                            if "can_short" in content:
                                repo["scout_notes"].append("Futures/Shorts mentioned")
                            if "martingale" in content.lower():
                                repo["scout_score"] -= 10
                                repo["scout_notes"].append("Martingale detected (Risk!)")
                    except Exception:
                        pass
            else:
                # No strategies found
                repo["scout_score"] -= 5

            inspected_count += 1
            # Sleep slightly to be nice
            time.sleep(0.5)

        # Re-sort
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
            f.write("## Top 10 Candidates\n\n")

            for i, repo in enumerate(top_10, 1):
                f.write(f"### {i}. [{repo['full_name']}]({repo['html_url']})\n")
                f.write(f"- **Score:** {repo.get('scout_score', 0)}\n")
                f.write(f"- **Stars:** {repo.get('stargazers_count', 0)}\n")
                f.write(f"- **License:** {repo.get('license_name', 'Unknown')}\n")
                f.write(f"- **Strategies:** {repo.get('strategy_count', 0)}\n")
                f.write(f"- **Last Update:** {repo.get('pushed_at', '').split('T')[0]}\n")
                if repo.get("scout_notes"):
                    f.write(f"- **Notes:** {', '.join(repo['scout_notes'])}\n")
                f.write("\n")

            f.write("## Other Candidates\n\n")
            f.write("| Rank | Repository | Score | License |\n")
            f.write("|---|---|---|---|\n")
            for i, repo in enumerate(self.candidates[10:], 11):
                f.write(
                    f"| {i} | [{repo['full_name']}]({repo['html_url']}) | {repo.get('scout_score', 0)} | {repo.get('license_name', 'Unknown')} |\n"
                )

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

            full_name = repo["full_name"]
            safe_name = full_name.replace("/", "_")
            strategies = repo.get("strategies", [])

            if not strategies:
                continue

            print(f"Vendoring from {full_name}...")
            target_dir = vendor_base_dir / safe_name
            target_dir.mkdir(parents=True, exist_ok=True)

            # Download up to 3 strategies
            dl_count = 0
            for strat in strategies:
                if dl_count >= 3:
                    break

                raw_url = strat.get("download_url")
                if raw_url:
                    try:
                        r = requests.get(raw_url, timeout=TIMEOUT)
                        if r.status_code == 200:
                            with (target_dir / strat["name"]).open("w") as f:
                                f.write(r.text)
                            dl_count += 1
                    except Exception as e:
                        print(f"Error downloading {strat['name']}: {e}")

            # Create LICENSE_NOTE.md
            with (target_dir / "LICENSE_NOTE.md").open("w") as f:
                f.write(f"# License Note for {repo['name']}\n\n")
                f.write(f"Source: {repo['html_url']}\n")
                f.write(f"License: {repo.get('license_name', 'Unknown')}\n")
                f.write("Check original repository for full license details.\n")

            count += 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--token", help="GitHub API Token", default=os.environ.get("GITHUB_TOKEN")
    )
    parser.add_argument("--vendor", action="store_true", help="Vendor top strategies")
    args = parser.parse_args()

    scout = StrategyScout(token=args.token)
    scout.search_github()
    scout.filter_and_score()
    scout.deep_inspect()
    top_candidates = scout.generate_report()

    if args.vendor:
        scout.vendor_strategies(top_candidates)


if __name__ == "__main__":
    main()
