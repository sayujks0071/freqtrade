#!/usr/bin/env python3
# ruff: noqa: I001
"""
Strategy Scout for Freqtrade.

Automatically discovers and shortlists the best open-source Python crypto trading strategies
that are compatible with Freqtrade.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
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


class StrategyScout:
    def __init__(self, token: str | None = None) -> None:
        self.token = token
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"token {self.token}"})
        self.session.headers.update({"Accept": "application/vnd.github.v3+json"})
        self.candidates: list[dict[str, Any]] = []

    def check_rate_limit(self) -> bool:
        """Check if we have enough API quota left."""
        try:
            resp = self.session.get(f"{GITHUB_API_URL}/rate_limit", timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                core = data["resources"]["core"]
                remaining = core["remaining"]
                reset = core["reset"]

                # print(f"DEBUG: Rate limit remaining: {remaining}")
                if remaining < RATE_LIMIT_BUFFER:
                    reset_time = datetime.datetime.fromtimestamp(
                        reset, tz=datetime.timezone.utc  # noqa: UP017
                    )
                    print(
                        f"WARNING: Rate limit low. Resets at {reset_time}. Halting or degrading."
                    )
                    return False
            return True
        except Exception as e:
            print(f"Error checking rate limit: {e}")
            # If we get an error checking rate limit, assume it's bad or we are blocked
            return False

    def _scrape_search(self, query: str) -> list[dict[str, Any]]:
        """Fallback to scraping GitHub search results."""
        print(f"Scraping search for: {query}")
        results = []
        try:
            # Add type=Repositories to ensure we look for repos
            url = f"https://github.com/search?q={query}&type=Repositories"
            # Use a standard user agent to avoid immediate blocking
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/91.0.4472.124 Safari/537.36"
                )
            }
            resp = requests.get(url, headers=headers, timeout=TIMEOUT)
            if resp.status_code == 200:
                # Naive regex to find repo links
                # Look for href="/user/repo"
                matches = re.findall(r'href="(/[\w.-]+/[\w.-]+)"', resp.text)

                for m in matches:
                    full_name = m.lstrip("/")
                    # Filter out common non-repo paths
                    if full_name.lower() in [
                        "login",
                        "join",
                        "pricing",
                        "features",
                        "explore",
                        "topics",
                        "marketplace",
                        "site/terms",
                        "site/privacy",
                        "search",
                    ]:
                        continue
                    if "github.com" in full_name:
                        continue
                    if full_name.count("/") != 1:
                        continue

                    # Deduplicate in the calling function, but create a basic object here
                    results.append(
                        {
                            "full_name": full_name,
                            "name": full_name.split("/")[-1],
                            "html_url": f"https://github.com/{full_name}",
                            "description": "Scraped from search results",
                            "stargazers_count": 0,  # Cannot easily scrape without parsing
                            "pushed_at": None,  # Cannot easily scrape
                            "license": {"key": "other", "name": "Unknown (Scraped)"},
                            "scraped": True,
                        }
                    )
            else:
                print(f"Scraping failed with status {resp.status_code}")
        except Exception as e:
            print(f"Error scraping search: {e}")

        return results

    def _search_api_query(
        self, query: str, found_repos: dict[str, Any]
    ) -> bool:  # Returns True if API is still usable
        print(f"Querying API: {query}")
        params = {"q": query, "sort": "stars", "order": "desc", "per_page": 20}
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
                return True
            elif resp.status_code in [403, 429]:
                print("Rate limit hit (403/429). Switching to scraping.")
                return False
            else:
                print(f"Search failed: {resp.status_code} {resp.text}")
                return True  # Error but not rate limit, try next query?
        except Exception as e:
            print(f"Exception during API search: {e}")
            return False

    def search_github(self) -> None:
        """Search GitHub for strategies."""
        print("Searching GitHub...")
        found_repos: dict[str, dict[str, Any]] = {}  # Dedup by full_name
        use_api = True

        # Check rate limit once at the start
        if not self.check_rate_limit():
            use_api = False
            print("Switching to scraping mode due to rate limit.")

        # 1. Search Queries
        for query in SEARCH_QUERIES:
            if use_api:
                if not self.check_rate_limit():
                    use_api = False
                    print("Rate limit hit during search. Switching to scraping.")
                else:
                    use_api = self._search_api_query(query, found_repos)

            if not use_api:
                items = self._scrape_search(query)
                for item in items:
                    if item["full_name"] not in found_repos:
                        found_repos[item["full_name"]] = item

            # Sleep briefly
            time.sleep(2)

        print("DEBUG: Starting known sources check")
        # 2. Add Known Sources
        for source in KNOWN_SOURCES:
            if source not in found_repos:
                self._add_known_source(source, found_repos, use_api)

        # Convert to list
        self.candidates = list(found_repos.values())
        print(f"Total unique candidates found: {len(self.candidates)}")

    def _add_known_source(self, source: str, found_repos: dict[str, Any], use_api: bool) -> None:
        if use_api:
            try:
                resp = self.session.get(f"{GITHUB_API_URL}/repos/{source}", timeout=TIMEOUT)
                if resp.status_code == 200:
                    found_repos[source] = resp.json()
                    return
            except Exception as e:
                print(f"Error fetching source {source}: {e}")

        # Fallback
        found_repos[source] = {
            "full_name": source,
            "name": source.split("/")[-1],
            "html_url": f"https://github.com/{source}",
            "description": "Known Source",
            "license": {"key": "other", "name": "Known Source"},
            "scraped": True,
        }

    def _score_candidate(self, repo: dict[str, Any]) -> dict[str, Any] | None:
        score = 0
        notes = []
        full_name = repo["full_name"]
        pushed_at = repo.get("pushed_at")
        license_data = repo.get("license")
        is_scraped = repo.get("scraped", False)

        if is_scraped:
            score += 1
            notes.append("Scraped (details missing)")

        # 1. License Check
        license_name = "Unknown"
        if license_data and license_data.get("key") != "other":
            license_name = license_data.get("name", "Unknown")
            score += 5
        elif license_data and license_data.get("key") == "other":
            license_name = "Other (Check manually)"
            score += 1
        else:
            if full_name not in KNOWN_SOURCES and not is_scraped:
                return None  # Reject
            if is_scraped:
                pass  # Benefit of doubt

        # 2. Recency
        age_days = 9999
        if pushed_at:
            pushed_dt = datetime.datetime.strptime(
                pushed_at, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(
                tzinfo=datetime.timezone.utc  # noqa: UP017
            )
            age_days = (
                datetime.datetime.now(datetime.timezone.utc) - pushed_dt  # noqa: UP017
            ).days
            if age_days < 30:
                score += 5
            elif age_days < 90:
                score += 3
            elif age_days < 365:
                score += 1
            else:
                score -= 2
        elif is_scraped:
            pass

        # 3. Description
        description = repo.get("description") or ""
        if "freqtrade" in description.lower():
            score += 2

        repo["scout_score"] = score
        repo["scout_notes"] = notes
        repo["license_name"] = license_name
        repo["age_days"] = age_days
        return repo

    def filter_and_score(self) -> None:
        """Filter candidates and assign a preliminary score."""
        print("Filtering and Scoring...")
        scored_candidates = []

        for repo in self.candidates:
            scored = self._score_candidate(repo)
            if scored:
                scored_candidates.append(scored)

        # Sort by preliminary score to prioritize inspection
        self.candidates = sorted(scored_candidates, key=lambda x: x["scout_score"], reverse=True)
        print(f"Candidates after filtering: {len(self.candidates)}")

    def _find_strategy_files(self, full_name: str) -> tuple[list[dict[str, Any]], str | None]:
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
                            break
                elif resp.status_code == 403:
                    # Rate limit hit inside deep inspect
                    raise Exception("Rate limit hit")
            except Exception:  # noqa: S110
                pass
        return strategies, found_path

    def _analyze_strategy_content(self, strat_file: dict[str, Any], repo: dict[str, Any]) -> None:
        """Helper to download and analyze strategy content."""
        try:
            download_url = strat_file.get("download_url")
            if download_url:
                content_resp = requests.get(download_url, timeout=TIMEOUT)
                if content_resp.status_code == 200:
                    content = content_resp.text

                    # Check heuristics
                    if "stoploss" in content:
                        repo["scout_score"] += 2
                        repo.setdefault("scout_notes", []).append("Has stoploss")
                    if "minimal_roi" in content:
                        repo["scout_score"] += 2
                        repo.setdefault("scout_notes", []).append("Has ROI")
                    if "populate_indicators" in content:
                        repo["scout_score"] += 2
                    if "can_short" in content:
                        repo.setdefault("scout_notes", []).append("Futures/Shorts mentioned")

                    # Negative heuristics
                    if "martingale" in content.lower():
                        repo["scout_score"] -= 10
                        repo.setdefault("scout_notes", []).append("Martingale detected (Risk!)")
        except Exception as e:
            print(f"Failed to read file {strat_file['name']}: {e}")

    def deep_inspect(self, limit: int = 15) -> None:
        """Deep inspect top candidates to refine score."""
        print(f"Deep inspecting top {limit} candidates...")

        # Take a snapshot of candidates to iterate over safely, though we modify objects in place
        candidates_to_inspect = self.candidates[:limit]

        for repo in candidates_to_inspect:
            # Check rate limit before each repo inspection if possible
            # But if we are in scraped mode, we might want to skip deep inspection completely
            # or try to use raw.githubusercontent if we knew paths.
            # For now, just try to check rate limit.
            if not self.check_rate_limit():
                print("Rate limit exhausted, skipping deep inspection for remaining.")
                repo.setdefault("scout_notes", []).append("Deep inspection skipped (Rate Limit)")
                continue

            full_name = repo["full_name"]
            print(f"Inspecting {full_name}...")

            strategies, found_path = self._find_strategy_files(full_name)

            repo["strategy_count"] = len(strategies)
            repo["strategy_path"] = found_path

            if len(strategies) > 0:
                repo["scout_score"] += min(len(strategies), 5) * 1  # +1 per strategy up to 5

                # Analyze the first strategy found
                self._analyze_strategy_content(strategies[0], repo)
            else:
                # Penalize if no strategies found
                if not repo.get("scraped"):
                     repo["scout_score"] -= 5

            # Sleep to be nice to API
            time.sleep(0.5)

        # Re-sort after inspection
        self.candidates = sorted(self.candidates, key=lambda x: x["scout_score"], reverse=True)

    def generate_report(self) -> list[dict[str, Any]]:
        """Generate markdown report."""
        print("Generating report...")
        report_dir = Path("user_data/reports")
        report_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.datetime.now(datetime.timezone.utc).strftime(  # noqa: UP017
            "%Y-%m-%d"
        )
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

                notes = repo.get("scout_notes", [])
                if notes:
                    f.write(f"- **Notes:** {', '.join(set(notes))}\n")

                f.write("- **Adoption Notes:** ")
                adoption = []
                if "Futures/Shorts mentioned" in notes:
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
        """Vendor top strategies."""
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
                print(f"Skipping vendoring for {full_name} (path not found).")
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
                                    # Save file
                                    with (vendor_dir / file_info["name"]).open("w") as f:
                                        f.write(r.text)
                                    downloaded += 1
                                time.sleep(0.5)

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
