#!/usr/bin/env python3
"""
Strategy Scout for Freqtrade
Automatically discovers and shortlists the best open-source Python crypto trading strategies.
"""

import argparse
import datetime
import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


# Constants
GITHUB_API_URL = "https://api.github.com"
SEARCH_QUERIES = [
    "freqtrade strategy",
    "freqtrade-strategies",
    "FreqAI strategy",
    "crypto trading strategy python freqtrade",
]
KNOWN_SOURCES = ["freqtrade/freqtrade-strategies"]
USER_AGENT = "Freqtrade-Scout"
RATE_LIMIT_BUFFER = 5
TIMEOUT = 10


class StrategyScout:
    def __init__(self, token: str | None = None):
        self.token = token
        self.candidates: list[dict[str, Any]] = []
        self.context = ssl.create_default_context()

    def _make_request(self, url: str, params: dict | None = None) -> dict | None:
        """
        Helper to make HTTP requests using urllib.
        """
        if params:
            query_string = urllib.parse.urlencode(params)
            url = f"{url}?{query_string}"

        req = urllib.request.Request(url)  # noqa: S310
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/vnd.github.v3+json")
        if self.token:
            req.add_header("Authorization", f"token {self.token}")

        try:
            with urllib.request.urlopen(  # noqa: S310
                req, context=self.context, timeout=TIMEOUT
            ) as response:
                if response.status == 200:
                    return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 403:
                print(f"Rate limit hit or access denied for {url}: {e}")
                # Check headers for rate limit reset
                reset = e.headers.get("X-RateLimit-Reset")
                if reset:
                    reset_time = datetime.datetime.fromtimestamp(
                        int(reset),
                        datetime.timezone.utc,  # noqa: UP017
                    )
                    print(f"Rate limit resets at {reset_time}")
            else:
                print(f"HTTP Error {e.code} for {url}: {e}")
        except Exception as e:
            print(f"Error fetching {url}: {e}")
        return None

    def check_rate_limit(self) -> bool:
        """
        Check if we have enough API calls remaining.
        """
        data = self._make_request(f"{GITHUB_API_URL}/rate_limit")
        if data:
            core = data.get("resources", {}).get("core", {})
            remaining = core.get("remaining", 0)
            print(f"DEBUG: Rate limit remaining: {remaining}")
            if remaining < RATE_LIMIT_BUFFER:
                print("WARNING: Rate limit low. Halting operations.")
                return False
            return True
        return True  # Assume ok if check fails to avoid blocking, relying on 403 handling

    def search_github(self):
        print("Searching GitHub...")
        found_repos = {}  # Dedup by full_name

        # 1. Search Queries
        for query in SEARCH_QUERIES:
            if not self.check_rate_limit():
                break

            print(f"Querying: {query}")
            # Sort by stars to get best quality first
            params = {"q": query, "sort": "stars", "order": "desc", "per_page": 20}
            data = self._make_request(f"{GITHUB_API_URL}/search/repositories", params=params)
            if data:
                items = data.get("items", [])
                for item in items:
                    found_repos[item["full_name"]] = item

        # 2. Add Known Sources
        for source in KNOWN_SOURCES:
            if source not in found_repos:
                if not self.check_rate_limit():
                    break
                data = self._make_request(f"{GITHUB_API_URL}/repos/{source}")
                if data:
                    found_repos[source] = data

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
                # Reject no license unless it's a known source (which we know is compatible)
                if full_name not in KNOWN_SOURCES:
                    continue

            # 2. Recency
            age_days = 9999
            if pushed_at:
                try:
                    pushed_dt = datetime.datetime.strptime(pushed_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                        tzinfo=datetime.timezone.utc  # noqa: UP017
                    )
                    age_days = (
                        datetime.datetime.now(datetime.timezone.utc) - pushed_dt  # noqa: UP017
                    ).days
                except ValueError:
                    pass

                if age_days < 30:
                    score += 5
                elif age_days < 90:
                    score += 3
                elif age_days < 365:
                    score += 1
                else:
                    score -= 2  # Stale

            # 3. Description / Documentation
            description = repo.get("description", "") or ""
            if "freqtrade" in description.lower():
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
            url = f"{GITHUB_API_URL}/repos/{full_name}/contents/{path}"
            data = self._make_request(url)
            if isinstance(data, list):
                potential = [
                    f for f in data if f["name"].endswith(".py") and f["name"] != "__init__.py"
                ]
                if potential:
                    strategies = potential
                    found_path = path
                    break
        return strategies, found_path

    def deep_inspect(self, limit=15):  # noqa: C901
        print(f"Deep inspecting top {limit} candidates...")
        inspected_count = 0
        final_candidates = []

        for repo in self.candidates:
            if inspected_count >= limit:
                # Keep the rest without inspection if we hit limit?
                # Or just drop them? For report, we probably want to keep them but listed lower.
                final_candidates.append(repo)
                continue

            if not self.check_rate_limit():
                print("Rate limit exhausted, stopping inspection.")
                final_candidates.append(repo)
                continue

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
                        req = urllib.request.Request(download_url)  # noqa: S310
                        req.add_header("User-Agent", USER_AGENT)
                        with urllib.request.urlopen(  # noqa: S310
                            req, context=self.context, timeout=TIMEOUT
                        ) as response:
                            if response.status == 200:
                                content = response.read().decode("utf-8")

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
                        print(f"Failed to read content for {strat_file['name']}: {e}")
            else:
                repo["scout_score"] -= 5  # No strategies found, probably false positive

            final_candidates.append(repo)
            inspected_count += 1

        self.candidates = sorted(final_candidates, key=lambda x: x["scout_score"], reverse=True)

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
                if repo.get("pushed_at"):
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
                adoption.append("Verify `stoploss` and `leverage` settings for Delta futures.")
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
            path = repo.get("strategy_path")

            if not path:
                continue

            print(f"Vendoring from {full_name}...")
            vendor_dir = vendor_base_dir / safe_name
            vendor_dir.mkdir(parents=True, exist_ok=True)

            try:
                url = f"{GITHUB_API_URL}/repos/{full_name}/contents/{path}"
                data = self._make_request(url)
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
                                req = urllib.request.Request(raw_url)  # noqa: S310
                                req.add_header("User-Agent", USER_AGENT)
                                with urllib.request.urlopen(  # noqa: S310
                                    req, context=self.context, timeout=TIMEOUT
                                ) as r:
                                    if r.status == 200:
                                        content = r.read().decode("utf-8")
                                        with (vendor_dir / file_info["name"]).open("w") as f:
                                            f.write(content)
                                        downloaded += 1

                    # Create LICENSE_NOTE.md
                    license_file = vendor_dir / "LICENSE_NOTE.md"
                    with license_file.open("w") as f:
                        f.write(f"# License Note for {repo['name']}\n\n")
                        f.write(f"Source: {repo['html_url']}\n")
                        f.write(f"License: {repo.get('license_name', 'Unknown')}\n")
                        f.write("Please check the original repository for full license details.\n")

                    count += 1

            except Exception as e:
                print(f"Error vendoring {full_name}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Freqtrade Strategy Scout")
    parser.add_argument("--token", help="GitHub API Token", default=os.environ.get("GITHUB_TOKEN"))
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
