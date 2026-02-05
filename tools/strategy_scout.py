#!/usr/bin/env python3
"""
Strategy Scout for Freqtrade
Automatically discovers and shortlists the best open-source Python crypto trading strategies.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


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
    def __init__(self, token: str | None = None) -> None:
        self.token = token
        self.headers = {
            "User-Agent": "Freqtrade-Scout",
            "Accept": "application/vnd.github.v3+json",
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"
        self.candidates: list[dict[str, Any]] = []

    def _request(self, url: str) -> dict[str, Any] | None:
        """Helper for urllib requests with error handling."""
        req = Request(url, headers=self.headers)  # noqa: S310
        try:
            with urlopen(req, timeout=TIMEOUT) as response:  # noqa: S310
                # Check rate limits
                remaining = response.getheader("X-RateLimit-Remaining")
                if remaining and int(remaining) < RATE_LIMIT_BUFFER:
                    reset = response.getheader("X-RateLimit-Reset")
                    # Use intermediate variable to keep line length down and satisfy ruff/flake8
                    utc = datetime.timezone.utc
                    reset_time = datetime.datetime.fromtimestamp(int(reset), utc)  # noqa: UP017
                    print(f"WARNING: Rate limit low ({remaining}). Resets at {reset_time}.")
                    # Simple backoff - just sleep if it's critical, but here just warn
                    # Ideally we would wait, but for now we proceed with caution

                data = response.read()
                return json.loads(data)
        except HTTPError as e:
            print(f"HTTP Error {e.code} for {url}: {e.reason}")
            if e.code == 403:
                print("Rate limit likely exceeded.")
        except URLError as e:
            print(f"URL Error for {url}: {e.reason}")
        except Exception as e:
            print(f"Error fetching {url}: {e}")
        return None

    def search_github(self) -> None:
        print("Searching GitHub...")
        found_repos: dict[str, dict[str, Any]] = {}  # Dedup by full_name

        # 1. Search Queries
        for query in SEARCH_QUERIES:
            print(f"Querying: {query}")
            # Sort by stars to get best quality first
            safe_query = quote(query)
            url = (
                f"{GITHUB_API_URL}/search/repositories"
                f"?q={safe_query}&sort=stars&order=desc&per_page=20"
            )
            data = self._request(url)
            if data and "items" in data:
                for item in data["items"]:
                    found_repos[item["full_name"]] = item
            time.sleep(1)  # Be nice to API

        # 2. Add Known Sources
        for source in KNOWN_SOURCES:
            if source not in found_repos:
                url = f"{GITHUB_API_URL}/repos/{source}"
                data = self._request(url)
                if data:
                    found_repos[source] = data

        # Convert to list
        self.candidates = list(found_repos.values())
        print(f"Total unique candidates found: {len(self.candidates)}")

    def filter_and_score(self) -> None:
        print("Filtering and Scoring...")
        scored_candidates = []

        for repo in self.candidates:
            score = 0
            notes: list[str] = []

            # Metadata filtering
            full_name = repo["full_name"]
            pushed_at = repo.get("pushed_at")
            license_data = repo.get("license")

            # 1. License Check
            license_name = "Unknown"
            has_valid_license = False

            if license_data and license_data.get("key") != "other":
                license_name = license_data.get("name", "Unknown")
                has_valid_license = True
                score += 5  # Clear license
            elif license_data and license_data.get("key") == "other":
                license_name = "Other (Check manually)"
                # "Other" might be a custom license or unrecognized, strict rules say clear license
                # We give it a small score but strict filtering might exclude it below
                score += 1

            # Strict license check: Reject "no license" (None) or "other" if not known source
            # The prompt says: "Only use public repos with clear licenses... Reject 'no license'"
            # We allow KNOWN_SOURCES to bypass this as they are manually vetted.
            if not has_valid_license and full_name not in KNOWN_SOURCES:
                continue

            # 2. Recency
            age_days = 9999
            if pushed_at:
                try:
                    # Python 3.9+ supports fromisoformat for some formats, but GitHub uses Z
                    pushed_dt = datetime.datetime.strptime(pushed_at, "%Y-%m-%dT%H:%M:%SZ")
                    # Make it UTC aware to match datetime.now(timezone.utc)
                    pushed_dt = pushed_dt.replace(tzinfo=datetime.timezone.utc)
                    now_utc = datetime.datetime.now(datetime.timezone.utc)  # noqa: UP017
                    age_days = (now_utc - pushed_dt).days

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

            # 3. Description / Documentation
            description = repo.get("description", "") or ""
            if description and "freqtrade" in description.lower():
                score += 2

            repo["scout_score"] = score
            repo["scout_notes"] = notes
            repo["license_name"] = license_name
            repo["age_days"] = age_days

            scored_candidates.append(repo)

        # Sort by preliminary score
        self.candidates = sorted(scored_candidates, key=lambda x: x["scout_score"], reverse=True)
        print(f"Candidates after filtering: {len(self.candidates)}")

    def _find_strategy_files(self, full_name: str) -> tuple[list[dict[str, Any]], str | None]:
        """Helper to find strategy files in a repo."""
        strategies: list[dict[str, Any]] = []
        found_path = None
        paths_to_check = ["user_data/strategies", "strategies", "."]

        for path in paths_to_check:
            url = f"{GITHUB_API_URL}/repos/{full_name}/contents/{path}"
            data = self._request(url)
            if isinstance(data, list):
                potential = [
                    f
                    for f in data
                    if f["name"].endswith(".py") and f["name"] != "__init__.py"
                ]
                if potential:
                    strategies = potential
                    found_path = path
                    break
        return strategies, found_path

    def deep_inspect(self, limit: int = 15) -> None:
        print(f"Deep inspecting top {limit} candidates...")
        inspected_count = 0

        for repo in self.candidates:
            if inspected_count >= limit:
                break

            full_name = repo["full_name"]
            print(f"Inspecting {full_name}...")

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
                        # Use generic urllib request for raw content
                        # Since it's raw content, we don't parse JSON
                        req = Request(download_url)  # noqa: S310
                        with urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310
                            content = r.read().decode("utf-8")

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

                            # Negative heuristics
                            if "martingale" in content.lower():
                                repo["scout_score"] -= 10
                                repo["scout_notes"].append("Martingale detected (Risk!)")
                    except Exception as e:
                        print(f"Failed to analyze content for {full_name}: {e}")
            else:
                repo["scout_score"] -= 5

            inspected_count += 1
            time.sleep(0.5)

        # Re-sort after inspection
        self.candidates = sorted(self.candidates, key=lambda x: x["scout_score"], reverse=True)

    def generate_report(self) -> list[dict[str, Any]]:
        print("Generating report...")
        report_dir = Path("user_data/reports")
        report_dir.mkdir(parents=True, exist_ok=True)

        # Use timezone-aware datetime for the filename to be safe, but local/utc date is fine
        now_utc = datetime.datetime.now(datetime.timezone.utc)  # noqa: UP017
        date_str = now_utc.strftime("%Y-%m-%d")
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

                last_update = repo.get("pushed_at", "").split("T")[0]
                f.write(f"- **Last Update:** {last_update}\n")

                desc = repo.get("description")
                if desc:
                    f.write(f"- **Description:** {desc}\n")

                if repo.get("scout_notes"):
                    f.write(f"- **Notes:** {', '.join(repo['scout_notes'])}\n")

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

    def vendor_strategies(self, candidates: list[dict[str, Any]], top_n: int = 5) -> None:
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
                continue

            print(f"Vendoring from {full_name}...")

            vendor_dir = vendor_base_dir / safe_name
            vendor_dir.mkdir(parents=True, exist_ok=True)

            try:
                # Re-fetch file list for that path
                url = f"{GITHUB_API_URL}/repos/{full_name}/contents/{path}"
                data = self._request(url)
                if isinstance(data, list):
                    downloaded = 0
                    for file_info in data:
                        is_py = file_info["name"].endswith(".py")
                        is_init = file_info["name"] == "__init__.py"

                        if is_py and not is_init:
                            if downloaded >= 3:
                                break

                            raw_url = file_info.get("download_url")
                            if raw_url:
                                req = Request(raw_url)  # noqa: S310
                                with urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310
                                    content = r.read().decode("utf-8")
                                    with (vendor_dir / file_info["name"]).open("w") as f:
                                        f.write(content)
                                    downloaded += 1
                                time.sleep(0.5)

                    # Create LICENSE_NOTE.md
                    license_file = vendor_dir / "LICENSE_NOTE.md"
                    with license_file.open("w") as f:
                        f.write(f"# License Note for {repo_name}\n\n")
                        f.write(f"Source: {repo['html_url']}\n")
                        f.write(f"License: {repo.get('license_name', 'Unknown')}\n")
                        f.write(
                            "Please check the original repository for full "
                            "license details.\n"
                        )

                    count += 1
            except Exception as e:
                print(f"Error vendoring {full_name}: {e}")


def main() -> None:
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
