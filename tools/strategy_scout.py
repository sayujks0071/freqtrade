#!/usr/bin/env python3
"""
Strategy Scout for Freqtrade
Automatically discovers and shortlists the best open-source
Python crypto trading strategies.
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
REQUIRED_FILES = ["user_data/reports", "user_data/strategies_vendor"]
RATE_LIMIT_BUFFER = 5
TIMEOUT = 10


class StrategyScout:
    def __init__(self, token: str | None = None):
        self.token = token
        self.session = requests.Session()
        if self.token:
            auth_header = {"Authorization": f"token {self.token}"}
            self.session.headers.update(auth_header)
        accept_header = {"Accept": "application/vnd.github.v3+json"}
        self.session.headers.update(accept_header)
        self.candidates: list[dict[str, Any]] = []

    def check_rate_limit(self) -> bool:
        try:
            url = f"{GITHUB_API_URL}/rate_limit"
            resp = self.session.get(url, timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                core = data["resources"]["core"]
                remaining = core["remaining"]
                reset = core["reset"]
                if remaining < RATE_LIMIT_BUFFER:
                    reset_time = datetime.datetime.fromtimestamp(reset)
                    print(
                        f"WARNING: Rate limit low. Resets at {reset_time}. "
                        "Halting or degrading."
                    )
                    return False
            return True
        except Exception as e:
            print(f"Error checking rate limit: {e}")
            return True

    def _search_query(self, query: str, found_repos: dict[str, Any]):
        if not self.check_rate_limit():
            return

        print(f"Querying: {query}")
        # Sort by stars to get best quality first
        params: dict[str, str | int] = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": 20,
        }
        try:
            resp = self.session.get(
                f"{GITHUB_API_URL}/search/repositories",
                params=params,
                timeout=TIMEOUT,
            )
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    found_repos[item["full_name"]] = item
            else:
                print(f"Search failed: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"Exception during search: {e}")

    def _add_known_source(self, source: str, found_repos: dict[str, Any]):
        if source in found_repos:
            return
        if not self.check_rate_limit():
            return
        try:
            url = f"{GITHUB_API_URL}/repos/{source}"
            resp = self.session.get(url, timeout=TIMEOUT)
            if resp.status_code == 200:
                found_repos[source] = resp.json()
        except Exception as e:
            print(f"Error fetching source {source}: {e}")

    def search_github(self):
        print("Searching GitHub...")
        found_repos: dict[str, Any] = {}

        for query in SEARCH_QUERIES:
            self._search_query(query, found_repos)
            time.sleep(1)

        for source in KNOWN_SOURCES:
            self._add_known_source(source, found_repos)

        self.candidates = list(found_repos.values())
        print(f"Total unique candidates found: {len(self.candidates)}")

    def _calculate_score(
        self, repo: dict[str, Any]
    ) -> tuple[int, list[str], str, int]:
        score = 0
        notes: list[str] = []
        full_name = repo["full_name"]
        pushed_at = repo.get("pushed_at")
        license_data = repo.get("license")

        # 1. License Check
        license_name = "Unknown"
        if license_data and license_data.get("key") != "other":
            license_name = license_data.get("name", "Unknown")
            score += 5
        elif license_data and license_data.get("key") == "other":
            license_name = "Other (Check manually)"
            score += 1
        else:
            if full_name not in KNOWN_SOURCES:
                pass

        # 2. Recency
        age_days = 9999
        if pushed_at:
            try:
                dt = datetime.datetime.strptime(
                    pushed_at, "%Y-%m-%dT%H:%M:%SZ"
                )
                age_days = (datetime.datetime.now() - dt).days
                if age_days < 30:
                    score += 5
                elif age_days < 90:
                    score += 3
                elif age_days < 365:
                    score += 1
                else:
                    score -= 2
            except ValueError:
                pass

        # 3. Description / Documentation
        description = repo.get("description", "") or ""
        if "freqtrade" in description.lower():
            score += 2

        return score, notes, license_name, age_days

    def filter_and_score(self):
        print("Filtering and Scoring...")
        scored_candidates = []

        for repo in self.candidates:
            full_name = repo["full_name"]
            if (
                repo.get("license") is None
                and full_name not in KNOWN_SOURCES
                and repo.get("stargazers_count", 0) < 5
            ):
                continue

            score, notes, license_name, age_days = self._calculate_score(repo)

            repo["scout_score"] = score
            repo["scout_notes"] = notes
            repo["license_name"] = license_name
            repo["age_days"] = age_days

            scored_candidates.append(repo)

        self.candidates = sorted(
            scored_candidates, key=lambda x: x["scout_score"], reverse=True
        )
        print(f"Candidates after filtering: {len(self.candidates)}")

    def _find_strategy_files(
        self, full_name: str
    ) -> tuple[list[dict[str, Any]], str | None]:
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
                            if f["name"].endswith(".py")
                            and f["name"] != "__init__.py"
                        ]
                        if potential:
                            strategies = potential
                            found_path = path
                            break
            except Exception:  # noqa: S110
                # S110: Intentionally suppressing exception during search
                # to continue with other paths
                pass
        return strategies, found_path

    def _analyze_strategy_content(
        self, strat_file: dict[str, Any], repo: dict[str, Any]
    ):
        try:
            download_url = strat_file.get("download_url")
            if download_url:
                content_resp = requests.get(download_url, timeout=TIMEOUT)
                if content_resp.status_code == 200:
                    content = content_resp.text

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

                    if "martingale" in content.lower():
                        repo["scout_score"] -= 10
                        repo["scout_notes"].append("Martingale (Risk!)")
        except Exception as e:
            print(f"Failed to read file {strat_file['name']}: {e}")

    def deep_inspect(self, limit: int = 15):
        print(f"Deep inspecting top {limit} candidates...")
        inspected_count = 0

        for repo in self.candidates:
            if inspected_count >= limit:
                break

            if not self.check_rate_limit():
                print("Rate limit exhausted, stopping inspection.")
                break

            full_name = repo["full_name"]
            print(f"Inspecting {full_name}...")

            strategies, found_path = self._find_strategy_files(full_name)

            repo["strategy_count"] = len(strategies)
            repo["strategy_path"] = found_path

            if len(strategies) > 0:
                repo["scout_score"] += min(len(strategies), 5) * 1
                self._analyze_strategy_content(strategies[0], repo)
            else:
                repo["scout_score"] -= 5

            inspected_count += 1
            time.sleep(0.5)

        self.candidates = sorted(
            self.candidates, key=lambda x: x["scout_score"], reverse=True
        )

    def generate_report(self) -> list[dict[str, Any]]:
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
                f.write(
                    f"### {i}. [{repo['full_name']}]({repo['html_url']})\n"
                )
                f.write(f"- **Score:** {repo.get('scout_score', 0)}\n")
                f.write(f"- **Stars:** {repo.get('stargazers_count', 0)}\n")
                f.write(
                    f"- **License:** {repo.get('license_name', 'Unknown')}\n"
                )
                strategy_count = repo.get("strategy_count", "N/A")
                f.write(f"- **Strategies Found:** {strategy_count}\n")
                if repo.get("pushed_at"):
                    last_update = repo.get("pushed_at", "").split("T")[0]
                    f.write(f"- **Last Update:** {last_update}\n")

                desc = repo.get("description")
                if desc:
                    f.write(f"- **Description:** {desc}\n")

                if repo.get("scout_notes"):
                    notes = ", ".join(repo["scout_notes"])
                    f.write(f"- **Notes:** {notes}\n")

                f.write("- **Adoption Notes:** ")
                adoption = []
                if "Futures/Shorts mentioned" in repo.get("scout_notes", []):
                    adoption.append("Seems to support futures.")
                else:
                    adoption.append(
                        "Check for `can_short` if trading futures."
                    )
                adoption.append(
                    "Verify `stoploss` and `leverage` settings for Delta."
                )
                f.write(" ".join(adoption) + "\n")
                f.write("\n")

            if rest_candidates:
                f.write("## Other Candidates\n\n")
                f.write("| Rank | Repository | Score | Stars | License |\n")
                f.write("|---|---|---|---|---|\n")
                for i, repo in enumerate(rest_candidates, 11):
                    repo_score = repo.get("scout_score", 0)
                    repo_stars = repo.get("stargazers_count", 0)
                    repo_license = repo.get("license_name", "Unknown")
                    line = (
                        f"| {i} | [{repo['full_name']}]({repo['html_url']}) | "
                        f"{repo_score} | {repo_stars} | {repo_license} |\n"
                    )
                    f.write(line)
                f.write("\n")

        print(f"Report written to {filename}")
        return top_10

    def vendor_strategies(
        self, candidates: list[dict[str, Any]], top_n: int = 5
    ):
        print(f"Vendoring top {top_n} strategies...")
        vendor_base_dir = Path("user_data/strategies_vendor")
        vendor_base_dir.mkdir(parents=True, exist_ok=True)

        count = 0
        for repo in candidates:
            if count >= top_n:
                break

            full_name = repo["full_name"]
            safe_name = full_name.replace("/", "_")
            path = repo.get("strategy_path")

            if not path:
                continue

            print(f"Vendoring from {full_name}...")

            vendor_dir = vendor_base_dir / safe_name
            vendor_dir.mkdir(parents=True, exist_ok=True)

            try:
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
                                    file_path = vendor_dir / file_info["name"]
                                    with file_path.open("w") as f:
                                        f.write(r.text)
                                    downloaded += 1

                    license_file = vendor_dir / "LICENSE_NOTE.md"
                    with license_file.open("w") as f:
                        f.write(f"# License Note for {repo['name']}\n\n")
                        f.write(f"Source: {repo['html_url']}\n")
                        f.write(
                            f"License: {repo.get('license_name', 'Unknown')}\n"
                        )
                        f.write(
                            "Please check the original repository for "
                            "full license details.\n"
                        )

                    count += 1
            except Exception as e:
                print(f"Error vendoring {full_name}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Freqtrade Strategy Scout")
    parser.add_argument(
        "--token",
        help="GitHub API Token",
        default=os.environ.get("GITHUB_TOKEN")
    )
    parser.add_argument(
        "--vendor", help="Vendor top strategies", action="store_true"
    )
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
