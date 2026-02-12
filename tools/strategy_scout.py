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
    "freqtrade hyperopt",
]
KNOWN_SOURCES = [
    "freqtrade/freqtrade-strategies",
    "iterativv/NostalgiaForInfinity",
]
REQUIRED_FILES = ["user_data/reports", "user_data/strategies_vendor"]
RATE_LIMIT_BUFFER = 5
TIMEOUT = 10
REQUEST_TIMEOUT = 10  # Seconds

# Licenses that are explicitly allowed
ALLOWED_LICENSES = [
    "mit",
    "apache-2.0",
    "bsd-3-clause",
    "bsd-2-clause",
    "gpl-3.0",
    "gpl-2.0",
    "lgpl-3.0",
    "lgpl-2.1",
    "agpl-3.0",
    "mpl-2.0",
    "unlicense",
]


class StrategyScout:
    def __init__(self, token: str | None = None, limit: int = 15):
        self.token = token
        self.limit = limit
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"token {self.token}"})
        self.session.headers.update({"Accept": "application/vnd.github.v3+json"})
        self.candidates: list[dict[str, Any]] = []

    def check_rate_limit(self):
        try:
            resp = self.session.get(f"{GITHUB_API_URL}/rate_limit", timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                core = data["resources"]["core"]
                remaining = core["remaining"]
                reset = core["reset"]
                print(f"DEBUG: Rate limit remaining: {remaining}")
                if remaining < RATE_LIMIT_BUFFER:
                    reset_time = datetime.datetime.fromtimestamp(reset)
                    wait_seconds = (reset_time - datetime.datetime.now()).total_seconds()
                    if wait_seconds > 0:
                        print(
                            f"WARNING: Rate limit low. Resets at {reset_time}. "
                            f"Waiting {wait_seconds:.0f} seconds..."
                        )
                        time.sleep(wait_seconds + 5)
            return True
        except Exception as e:
            print(f"Error checking rate limit: {e}")
            return True  # Assume ok if check fails, to avoid loop

    def search_github(self):
        print("Searching GitHub...")
        found_repos = {}  # Dedup by full_name

        self._search_queries(found_repos)
        self._add_known_sources(found_repos)

        # Convert to list
        self.candidates = list(found_repos.values())
        print(f"Total unique candidates found: {len(self.candidates)}")

    def _search_queries(self, found_repos):
        # 1. Search Queries
        for query in SEARCH_QUERIES:
            if not self.check_rate_limit():
                break

            print(f"Querying: {query}")
            # Sort by stars to get best quality first
            params = {"q": query, "sort": "stars", "order": "desc", "per_page": 30}
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

    def _add_known_sources(self, found_repos):
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

    def filter_and_score(self):  # noqa: C901
        print("Filtering and Scoring...")
        scored_candidates = []

        for repo in self.candidates:
            score = 0
            notes = []

            # Metadata filtering
            full_name = repo["full_name"]
            pushed_at = repo.get("pushed_at")
            license_data = repo.get("license")

            # 1. License Check (Strict)
            license_key = license_data.get("key") if license_data else None
            license_name = license_data.get("name", "Unknown") if license_data else "No License"

            if license_key in ALLOWED_LICENSES:
                score += 5  # Clear license
            elif license_key == "other":
                # Check if it's a known source, we trust them more
                if full_name in KNOWN_SOURCES:
                    score += 5
                else:
                    score += 1  # Weak positive, needs manual check
                    notes.append("License: Other (Manual check required)")
            elif license_key is None:
                # Reject no license, unless it's a known source
                if full_name in KNOWN_SOURCES:
                    score += 5
                    notes.append("License: Not detected by GitHub (Known Source)")
                else:
                    # Heuristic: Check if LICENSE file exists in root (later in deep inspect?)
                    # For now, drop unless known source.
                    score -= 10
                    notes.append("No License detected")
            else:
                # Unknown license key
                score += 1
                notes.append(f"License: {license_key}")

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
                score -= 5

            # 3. Description / Documentation
            description = repo.get("description", "") or ""
            if description and "freqtrade" in description.lower():
                score += 2

            # 4. Stars
            stars = repo.get("stargazers_count", 0)
            if stars > 100:
                score += 3
            elif stars > 10:
                score += 1

            repo["scout_score"] = score
            repo["scout_notes"] = notes
            repo["license_name"] = license_name
            repo["age_days"] = age_days

            # Strict filtering: Reject if no license detected (unless known source)
            if license_key is None and full_name not in KNOWN_SOURCES:
                continue

            # Filter out negative scores
            if score >= 0:
                scored_candidates.append(repo)

        # Sort by preliminary score to prioritize inspection
        self.candidates = sorted(scored_candidates, key=lambda x: x["scout_score"], reverse=True)
        print(f"Candidates after filtering: {len(self.candidates)}")

    def _find_strategy_files_tree(self, full_name, default_branch):
        """Helper to find strategy files in a repo using Git Tree API."""
        strategies = []
        found_path = None

        # Use Git Tree API (Recursive)
        try:
            url = f"{GITHUB_API_URL}/repos/{full_name}/git/trees/{default_branch}?recursive=1"
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 200:
                tree_data = resp.json()
                tree = tree_data.get("tree", [])

                # Filter for .py files in typical locations
                potential = []
                for item in tree:
                    path = item.get("path", "")
                    if path.endswith(".py") and not path.endswith("__init__.py"):
                        # Check location
                        if (
                            "user_data/strategies" in path
                            or "strategies/" in path
                            or "/" not in path
                        ):
                            potential.append(item)

                if potential:
                    # Construct download URLs
                    # Raw content URL:
                    # https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}
                    for p in potential:
                        p["download_url"] = (
                            f"https://raw.githubusercontent.com/{full_name}/"
                            f"{default_branch}/{p['path']}"
                        )

                    strategies = potential
                    # Use the directory of the first strategy as "found_path"
                    found_path = str(Path(strategies[0]["path"]).parent)
        except Exception as e:
            print(f"Error fetching tree for {full_name}: {e}")

        return strategies, found_path

    def _analyze_strategy_content(self, strat_file, repo):
        """Helper to download and analyze strategy content."""
        try:
            download_url = strat_file.get("download_url")
            if download_url:
                content_resp = requests.get(download_url, timeout=REQUEST_TIMEOUT)
                if content_resp.status_code == 200:
                    content = content_resp.text

                    # Check heuristics
                    if "IStrategy" in content:
                        repo["scout_score"] += 3
                        repo["scout_notes"].append("Is Freqtrade Strategy")
                    else:
                        # If it doesn't mention IStrategy, it might not be a freqtrade strategy
                        repo["scout_score"] -= 2
                        repo["scout_notes"].append("IStrategy not found")

                    if "stoploss" in content:
                        repo["scout_score"] += 2
                        repo["scout_notes"].append("Has stoploss")
                    if "minimal_roi" in content:
                        repo["scout_score"] += 2
                        repo["scout_notes"].append("Has ROI")
                    if "process_only_new_candles" in content:
                        repo["scout_score"] += 1
                        repo["scout_notes"].append("Explicit candle processing")
                    if "can_short" in content:
                        repo["scout_notes"].append("Futures/Shorts mentioned")

                    # Timeframe check
                    if "timeframe" in content:
                        repo["scout_notes"].append("Timeframe defined")

                    # Negative heuristics
                    if "martingale" in content.lower():
                        repo["scout_score"] -= 10
                        repo["scout_notes"].append("Martingale detected (Risk!)")
        except Exception as e:
            print(f"Failed to read file {strat_file.get('path')}: {e}")

    def deep_inspect(self, limit=None):
        limit = limit or self.limit
        print(f"Deep inspecting top {limit} candidates...")
        inspected_count = 0
        final_candidates = []

        # We might need to inspect more if some fail validation
        candidates_to_inspect = self.candidates[: limit * 2]

        for repo in candidates_to_inspect:
            if inspected_count >= limit and len(final_candidates) >= 15:
                break

            if not self.check_rate_limit():
                print("Rate limit exhausted, stopping inspection.")
                break

            full_name = repo["full_name"]
            default_branch = repo.get("default_branch", "master")
            print(f"Inspecting {full_name}...")

            strategies, found_path = self._find_strategy_files_tree(full_name, default_branch)

            repo["strategy_count"] = len(strategies)
            repo["strategy_path"] = found_path

            if len(strategies) > 0:
                repo["scout_score"] += min(len(strategies), 5) * 1  # +1 per strategy up to 5
                # Check the first strategy file for content
                self._analyze_strategy_content(strategies[0], repo)
                final_candidates.append(repo)
                inspected_count += 1
            else:
                repo["scout_score"] -= 5
                repo["scout_notes"].append("No strategies found")
                # Still add it? Maybe at the bottom.
                final_candidates.append(repo)

        # Append the rest of candidates that were not inspected
        inspected_ids = {c["full_name"] for c in final_candidates}
        for repo in self.candidates:
            if repo["full_name"] not in inspected_ids:
                final_candidates.append(repo)

        # Re-sort after inspection
        self.candidates = sorted(final_candidates, key=lambda x: x["scout_score"], reverse=True)

    def generate_report(self):
        print("Generating report...")
        report_dir = Path("user_data/reports")
        report_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        filename = report_dir / f"strategy_shortlist_{date_str}.md"

        # Ensure we have at least 15 candidates if possible
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
                    unique_notes = sorted(list(set(repo["scout_notes"])))
                    f.write(f"- **Notes:** {', '.join(unique_notes)}\n")

                f.write("- **Adoption Notes:** ")
                adoption = []
                if "Futures/Shorts mentioned" in repo.get("scout_notes", []):
                    adoption.append("Seems to support futures.")
                else:
                    adoption.append("Check for `can_short` if trading futures.")

                if "IStrategy not found" in repo.get("scout_notes", []):
                    adoption.append("WARNING: Might not be a standard Freqtrade strategy repo.")

                adoption.append("Verify `stoploss` and `leverage` settings for Delta futures.")
                f.write(" ".join(adoption) + "\n")
                f.write("\n")

            if rest_candidates:
                f.write("## Runners Up\n\n")
                f.write("| Rank | Repository | Score | Stars | License | Last Update |\n")
                f.write("|---|---|---|---|---|---|\n")
                for i, repo in enumerate(rest_candidates, 11):
                    # Limit runners up to 50
                    if i > 60:
                        break
                    url = repo["html_url"]
                    full = repo["full_name"]
                    score = repo.get("scout_score", 0)
                    stars = repo.get("stargazers_count", 0)
                    lic = repo.get("license_name", "Unknown")
                    last_update = repo.get("pushed_at", "").split("T")[0]
                    line = (
                        f"| {i} | [{full}]({url}) | {score} | {stars} | {lic} | {last_update} |\n"
                    )
                    f.write(line)
                f.write("\n")

        print(f"Report written to {filename}")
        return top_10

    def vendor_strategies(self, candidates, top_n=3):
        print(f"Vendoring top {top_n} strategies...")
        vendor_base_dir = Path("user_data/strategies_vendor")
        vendor_base_dir.mkdir(parents=True, exist_ok=True)

        count = 0
        for repo in candidates:
            if count >= top_n:
                break

            # Skip if score is too low or license is bad
            if repo.get("scout_score", 0) < 5:
                continue

            full_name = repo["full_name"]
            repo_name = repo["name"]
            safe_name = full_name.replace("/", "_")
            default_branch = repo.get("default_branch", "master")

            print(f"Vendoring from {full_name}...")
            strategies, _ = self._find_strategy_files_tree(full_name, default_branch)

            if not strategies:
                print(f"No strategies to vendor for {full_name}")
                continue

            vendor_dir = vendor_base_dir / safe_name
            vendor_dir.mkdir(parents=True, exist_ok=True)

            downloaded_files = 0
            try:
                for file_info in strategies:
                    if downloaded_files >= 3:
                        break

                    raw_url = file_info.get("download_url")
                    fname = Path(file_info.get("path")).name

                    if raw_url:
                        r = requests.get(raw_url, timeout=REQUEST_TIMEOUT)
                        if r.status_code == 200:
                            file_path = vendor_dir / fname
                            with file_path.open("w") as f:
                                f.write(r.text)
                            downloaded_files += 1

                if downloaded_files > 0:
                    license_file = vendor_dir / "LICENSE_NOTE.md"
                    with license_file.open("w") as f:
                        f.write(f"# License Note for {repo_name}\n\n")
                        f.write(f"Source: {repo['html_url']}\n")
                        f.write(f"License: {repo.get('license_name', 'Unknown')}\n")
                        f.write(f"Commit/Branch: {default_branch}\n")
                        f.write("Please check the original repository for full license details.\n")
                        f.write("Vendored by Freqtrade Strategy Scout.\n")

                    count += 1
            except Exception as e:
                print(f"Error vendoring {full_name}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Freqtrade Strategy Scout")
    parser.add_argument(
        "--token", help="GitHub API Token", default=os.environ.get("GITHUB_TOKEN")
    )
    parser.add_argument("--vendor", help="Vendor top strategies", action="store_true")
    parser.add_argument(
        "--limit", help="Number of candidates to deep inspect", type=int, default=20
    )
    args = parser.parse_args()

    scout = StrategyScout(token=args.token, limit=args.limit)
    scout.search_github()
    scout.filter_and_score()
    scout.deep_inspect()
    top_candidates = scout.generate_report()
    if args.vendor:
        scout.vendor_strategies(top_candidates)


if __name__ == "__main__":
    main()
