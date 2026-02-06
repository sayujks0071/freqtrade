#!/usr/bin/env python3
"""
Strategy Scout for Freqtrade
Automatically discovers and shortlists the best open-source Python crypto trading strategies.
"""

import argparse
import datetime
import os
import time
from pathlib import Path
from typing import Any

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
REQUEST_TIMEOUT = 10  # Seconds
MAX_DEEP_INSPECT = 20  # Limit deep inspection to top N to save API calls


class StrategyScout:
    def __init__(self, token: str | None = None):
        self.token = token
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"token {self.token}"})
        self.session.headers.update(
            {"Accept": "application/vnd.github.v3+json", "User-Agent": "Freqtrade-Strategy-Scout"}
        )
        self.candidates: list[dict[str, Any]] = []

    def check_rate_limit(self) -> bool:
        """
        Check GitHub API rate limit.
        Returns False if limit is exhausted and we should stop/pause.
        """
        try:
            resp = self.session.get(f"{GITHUB_API_URL}/rate_limit", timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                core = data["resources"]["core"]
                remaining = core["remaining"]
                reset = core["reset"]

                if remaining < RATE_LIMIT_BUFFER:
                    reset_time = datetime.datetime.fromtimestamp(reset, datetime.UTC)
                    print(
                        f"WARNING: Rate limit low ({remaining}). "
                        f"Resets at {reset_time}. Halting requests."
                    )
                    return False
            return True
        except Exception as e:
            print(f"Error checking rate limit: {e}")
            return True  # Assume ok if check fails, to avoid premature exit

    def search_github(self):  # noqa: C901
        print("Searching GitHub...")
        found_repos = {}  # Dedup by full_name

        # 1. Search Queries
        for query in SEARCH_QUERIES:
            if not self.check_rate_limit():
                break

            print(f"Querying: {query}")
            # Sort by stars to get best quality first
            params = {"q": query, "sort": "stars", "order": "desc", "per_page": 30}
            try:
                resp = self.session.get(
                    f"{GITHUB_API_URL}/search/repositories", params=params, timeout=TIMEOUT
                )
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    for item in items:
                        found_repos[item["full_name"]] = item
                    time.sleep(1)  # Be nice
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
                    resp = self.session.get(f"{GITHUB_API_URL}/repos/{source}", timeout=TIMEOUT)
                    if resp.status_code == 200:
                        found_repos[source] = resp.json()
                except Exception as e:
                    print(f"Error fetching source {source}: {e}")

        # Convert to list
        self.candidates = list(found_repos.values())
        print(f"Total unique candidates found: {len(self.candidates)}")

    def filter_and_score(self):
        print("Filtering and Scoring...")
        scored_candidates = []

        for repo in self.candidates:
            score = 0
            notes = []

            # Metadata filtering
            full_name = repo["full_name"]
            # stars = repo.get("stargazers_count", 0)  # Used for reporting but not primary score
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
                # Penalize no license, but keep if known source
                if full_name not in KNOWN_SOURCES:
                    # Reject no license unless it is a known source
                    continue

            # 2. Recency
            if pushed_at:
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
            else:
                age_days = 9999

            # 3. Description / Documentation
            description = repo.get("description", "") or ""
            if description and "freqtrade" in description.lower():
                score += 2

            repo["scout_score"] = score
            repo["scout_notes"] = notes
            repo["license_name"] = license_name
            repo["age_days"] = age_days

            scored_candidates.append(repo)

        # Sort by preliminary score to prioritize inspection
        self.candidates = sorted(scored_candidates, key=lambda x: x["scout_score"], reverse=True)
        print(f"Candidates after filtering: {len(self.candidates)}")

    def _find_strategy_files(self, full_name):
        """Helper to find strategy files in a repo."""
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
                            break  # Found strategies
                elif resp.status_code == 403:
                    # Rate limit hit during loop
                    break
            except Exception:  # noqa: S110
                # Ignore path errors
                pass

        return strategies, found_path

    def deep_inspect(self, limit=MAX_DEEP_INSPECT):  # noqa: C901
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

            strategies, found_path = self._find_strategy_files(full_name)

            repo["strategy_count"] = len(strategies)
            repo["strategy_path"] = found_path

            if len(strategies) > 0:
                repo["scout_score"] += min(len(strategies), 5) * 1  # +1 per strategy up to 5

                # Check the first strategy file for content
                strat_file = strategies[0]
                download_url = strat_file.get("download_url")

                if download_url:
                    try:
                        # Use download_url (raw) to avoid API quota if possible?
                        # Note: raw.githubusercontent.com might not need token
                        # but if it's a private repo (not here) it would.
                        # We use session just in case, but standard requests is fine for public.
                        content_resp = requests.get(download_url, timeout=TIMEOUT)
                        if content_resp.status_code == 200:
                            content = content_resp.text

                            # Check heuristics
                            if "stoploss" in content:
                                repo["scout_score"] += 2
                                repo["scout_notes"].append("Has stoploss")
                            if "minimal_roi" in content:
                                repo["scout_score"] += 2
                                repo["scout_notes"].append("Has ROI")
                            if "populate_indicators" in content:
                                repo["scout_score"] += 2
                            if "can_short" in content:
                                repo["scout_notes"].append("Futures/Shorts mentioned")

                            # Indicators check (naive)
                            indicators = set()
                            if "qtpylib." in content:
                                indicators.add("qtpylib")
                            if "ta." in content:
                                indicators.add("ta-lib")
                            repo["indicators"] = list(indicators)

                            # Negative heuristics
                            if "martingale" in content.lower():
                                repo["scout_score"] -= 10
                                repo["scout_notes"].append("Martingale detected (Risk!)")
                    except Exception as e:
                        print(f"Failed to read file {strat_file['name']}: {e}")
            else:
                # No strategies found in typical folders
                repo["scout_score"] -= 5
                repo["strategy_count"] = 0

            inspected_count += 1
            time.sleep(0.5)  # Be nice

        # Re-sort after inspection
        self.candidates = sorted(self.candidates, key=lambda x: x["scout_score"], reverse=True)

    def generate_report(self):
        print("Generating report...")
        report_dir = Path("user_data/reports")
        report_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        filename = report_dir / f"strategy_shortlist_{date_str}.md"

        top_10 = self.candidates[:10]
        rest_candidates = self.candidates[10:]

        with filename.open("w") as f:
            f.write(f"# Freqtrade Strategy Scout Report - {date_str}\n\n")
            f.write("## Top 10 Candidates\n\n")

            for i, repo in enumerate(top_10, 1):
                f.write(f"### {i}. [{repo['full_name']}]({repo['html_url']})\n")
                f.write(f"- **Score:** {repo.get('scout_score', 0)}\n")
                f.write(f"- **Stars:** {repo.get('stargazers_count', 0)}\n")
                f.write(f"- **License:** {repo.get('license_name', 'Unknown')}\n")
                f.write(f"- **Strategies Found:** {repo.get('strategy_count', 'N/A')}\n")

                pushed = repo.get("pushed_at")
                if pushed:
                    last_update = pushed.split("T")[0]
                    f.write(f"- **Last Update:** {last_update}\n")

                desc = repo.get("description")
                if desc:
                    f.write(f"- **Description:** {desc.strip()}\n")

                if repo.get("scout_notes"):
                    f.write(f"- **Notes:** {', '.join(repo['scout_notes'])}\n")

                if repo.get("indicators"):
                    f.write(f"- **Indicators:** {', '.join(repo['indicators'])}\n")

                f.write("- **Adoption Notes:** ")
                adoption = []
                if "Futures/Shorts mentioned" in repo.get("scout_notes", []):
                    adoption.append("Seems to support futures.")
                else:
                    adoption.append("Check for `can_short` if trading futures.")
                adoption.append(
                    "Verify `stoploss` and `leverage` settings for Delta futures."
                )
                f.write(" ".join(adoption) + "\n")
                f.write("\n")

            if rest_candidates:
                f.write("## Other Candidates\n\n")
                f.write("| Rank | Repository | Score | Stars | License |\n")
                f.write("|---|---|---|---|---|\n")
                for i, repo in enumerate(rest_candidates, 11):
                    score = repo.get("scout_score", 0)
                    stars = repo.get("stargazers_count", 0)
                    lic = repo.get("license_name", "Unknown")
                    line = (
                        f"| {i} | [{repo['full_name']}]({repo['html_url']}) | "
                        f"{score} | {stars} | {lic} |\n"
                    )
                    f.write(line)
                f.write("\n")

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
            repo_name = repo["name"]
            safe_name = full_name.replace("/", "_")
            path = repo.get("strategy_path")

            if not path:
                continue  # Can't vendor if we didn't find the path

            print(f"Vendoring from {full_name}...")

            vendor_dir = vendor_base_dir / safe_name
            vendor_dir.mkdir(parents=True, exist_ok=True)

            try:
                # Re-fetch file list for that path
                url = f"{GITHUB_API_URL}/repos/{full_name}/contents/{path}"
                resp = self.session.get(url, timeout=TIMEOUT)

                if resp.status_code == 200:
                    contents = resp.json()
                    downloaded = 0
                    for file_info in contents:
                        is_py = file_info["name"].endswith(".py")
                        is_init = file_info["name"] == "__init__.py"

                        if is_py and not is_init:
                            if downloaded >= 3:
                                break

                            raw_url = file_info.get("download_url")
                            if raw_url:
                                r = requests.get(raw_url, timeout=TIMEOUT)
                                if r.status_code == 200:
                                    # Save file
                                    file_path = vendor_dir / file_info["name"]
                                    with file_path.open("w") as f:
                                        f.write(r.text)
                                    downloaded += 1
                                    print(f"  Downloaded {file_info['name']}")

                    # Create LICENSE_NOTE.md
                    license_file = vendor_dir / "LICENSE_NOTE.md"
                    with license_file.open("w") as f:
                        f.write(f"# License Note for {repo_name}\n\n")
                        f.write(f"Source: {repo['html_url']}\n")
                        f.write(f"License: {repo.get('license_name', 'Unknown')}\n")
                        f.write(
                            "Please check the original repository for full license details.\n"
                        )

                    count += 1
                else:
                    print(f"Failed to list files for vendoring {full_name}: {resp.status_code}")
            except Exception as e:
                print(f"Error vendoring {full_name}: {e}")

            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="Freqtrade Strategy Scout")
    parser.add_argument(
        "--token", help="GitHub API Token", default=os.environ.get("GITHUB_TOKEN")
    )
    parser.add_argument("--vendor", help="Vendor top strategies", action="store_true")
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
