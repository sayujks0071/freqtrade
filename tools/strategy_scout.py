#!/usr/bin/env python3
"""
Strategy Scout for Freqtrade
Automatically discovers and shortlists the best open-source Python crypto trading strategies.
"""

import argparse
import datetime
import os
import re
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
KNOWN_SOURCES = [
    "freqtrade/freqtrade-strategies",
    "paulcpk/freqtrade-strategies-that-work",
]
REQUIRED_FILES = ["user_data/reports", "user_data/strategies_vendor"]
RATE_LIMIT_BUFFER = 5
TIMEOUT = 10
REQUEST_TIMEOUT = 10  # Seconds


class StrategyScout:
    def __init__(self, token: str | None = None):
        self.token = token
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
                    print(
                        f"WARNING: Rate limit low. Resets at {reset_time}. "
                        "Halting or degrading inspection."
                    )
                    return False
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

    def filter_and_score(self):
        print("Filtering and Scoring...")
        scored_candidates = []

        for repo in self.candidates:
            score = self._calculate_initial_score(repo)
            if score is None:
                continue

            repo["scout_score"] = score
            if "scout_notes" not in repo:
                repo["scout_notes"] = []
            repo["license_name"] = self._get_license_name(repo)
            repo["age_days"] = self._calculate_age_days(repo)

            scored_candidates.append(repo)

        # Sort by preliminary score to prioritize inspection
        self.candidates = sorted(scored_candidates, key=lambda x: x["scout_score"], reverse=True)
        print(f"Candidates after filtering: {len(self.candidates)}")

    def _get_license_name(self, repo):
        license_data = repo.get("license")
        if license_data:
            if license_data.get("key") != "other":
                return license_data.get("name", "Unknown")
            elif license_data.get("key") == "other":
                return "Other (Check manually)"
        return "Unknown"

    def _calculate_age_days(self, repo):
        pushed_at = repo.get("pushed_at")
        if pushed_at:
            pushed_dt = datetime.datetime.strptime(pushed_at, "%Y-%m-%dT%H:%M:%SZ")
            return (datetime.datetime.now() - pushed_dt).days
        return 9999

    def _calculate_initial_score(self, repo):
        score = 0
        full_name = repo["full_name"]
        license_data = repo.get("license")

        # 1. License Check
        has_license = False
        if license_data:
            if license_data.get("key") != "other":
                score += 5  # Clear license
                has_license = True
            elif license_data.get("key") == "other":
                score += 1
                has_license = True

        # Reject "no license" unless it's a known source
        if not has_license and full_name not in KNOWN_SOURCES:
            return None

        # Bonus for known sources
        if full_name in KNOWN_SOURCES:
            score += 5

        # 2. Recency
        age_days = self._calculate_age_days(repo)
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

        return score

    def _find_strategy_files(self, full_name):
        """Helper to find strategy files in a repo."""
        strategies = []
        found_path = None
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
            except Exception:  # noqa: S110
                pass
        return strategies, found_path

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
            print(f"Inspecting {full_name}...")

            strategies, found_path = self._find_strategy_files(full_name)

            repo["strategy_count"] = len(strategies)
            repo["strategy_path"] = found_path

            if len(strategies) > 0:
                repo["scout_score"] += min(len(strategies), 5) * 1  # +1 per strategy up to 5
                # Inspect up to 3 strategies to get better heuristics
                files_to_inspect = strategies[:3]
                self._analyze_strategies(files_to_inspect, repo)
            else:
                repo["scout_score"] -= 5

            inspected_count += 1

        # Re-sort after inspection
        self.candidates = sorted(self.candidates, key=lambda x: x["scout_score"], reverse=True)

    def _analyze_strategies(self, files, repo):
        """Analyze multiple strategy files for heuristics, avoiding duplicate scores."""
        unique_notes = set(repo.get("scout_notes", []))
        score_bonus = 0
        max_bonus = 10  # Cap heuristic bonus

        # Flags to prevent double counting per repo
        flags = {
            "stoploss": False,
            "roi": False,
            "indicators": False,
            "shorts": False,
            "martingale": False,
        }

        for strat_file in files:
            content = self._download_content(strat_file)
            if not content:
                continue

            # Check heuristics
            if "stoploss" in content and not flags["stoploss"]:
                score_bonus += 2
                unique_notes.add("Has stoploss")
                flags["stoploss"] = True
            if "minimal_roi" in content and not flags["roi"]:
                score_bonus += 2
                unique_notes.add("Has ROI")
                flags["roi"] = True
            if "populate_indicators" in content and not flags["indicators"]:
                score_bonus += 2
                flags["indicators"] = True  # Note added by _detect_indicators

            if "can_short" in content and not flags["shorts"]:
                unique_notes.add("Futures/Shorts mentioned")
                flags["shorts"] = True

            # Timeframe (can be multiple)
            tf_match = re.search(r"timeframe\s*=\s*['\"]([^'\"]+)['\"]", content)
            if tf_match:
                unique_notes.add(f"Timeframe: {tf_match.group(1)}")

            # Indicators detection
            self._detect_indicators(content, unique_notes)

            # Negative heuristics (apply once)
            if "martingale" in content.lower() and not flags["martingale"]:
                score_bonus -= 10
                unique_notes.add("Martingale detected (Risk!)")
                flags["martingale"] = True

        repo["scout_score"] += min(score_bonus, max_bonus)
        repo["scout_notes"] = list(unique_notes)

    def _download_content(self, strat_file):
        try:
            download_url = strat_file.get("download_url")
            if not download_url:
                return None

            content_resp = requests.get(download_url, timeout=REQUEST_TIMEOUT)
            if content_resp.status_code == 200:
                return content_resp.text
        except Exception as e:
            print(f"Failed to read file {strat_file['name']}: {e}")
        return None

    def _detect_indicators(self, content, unique_notes):
        indicators = []
        if "talib." in content:
            indicators.append("talib")
        if "qtpylib." in content:
            indicators.append("qtpylib")
        if "technical." in content:
            indicators.append("technical")
        if "pandas_ta" in content:
            indicators.append("pandas_ta")
        if indicators:
            unique_notes.add(f"Indicators: {', '.join(indicators)}")

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
                self._write_candidate_details(f, i, repo)

            if rest_candidates:
                self._write_other_candidates(f, rest_candidates)

        print(f"Report written to {filename}")
        return top_10

    def _write_candidate_details(self, f, i, repo):
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
            # Sort notes for consistent output
            sorted_notes = sorted(repo.get("scout_notes", []))
            f.write(f"- **Notes:** {', '.join(sorted_notes)}\n")

        f.write("- **Adoption Notes:** ")
        adoption = []
        if "Futures/Shorts mentioned" in repo.get("scout_notes", []):
            adoption.append("Seems to support futures.")
        else:
            adoption.append("Check for `can_short` if trading futures.")
        adoption.append("Verify `stoploss` and `leverage` settings for Delta futures.")
        f.write(" ".join(adoption) + "\n")
        f.write("\n")

    def _write_other_candidates(self, f, candidates):
        f.write("## Other Candidates\n\n")
        f.write("| Rank | Repository | Score | Stars | License |\n")
        f.write("|---|---|---|---|---|\n")
        for i, repo in enumerate(candidates, 11):
            url = repo["html_url"]
            full = repo["full_name"]
            score = repo.get("scout_score", 0)
            stars = repo.get("stargazers_count", 0)
            lic = repo.get("license_name", "Unknown")
            line = f"| {i} | [{full}]({url}) | {score} | {stars} | {lic} |\n"
            f.write(line)
        f.write("\n")

    def vendor_strategies(self, candidates, top_n=5):
        print(f"Vendoring top {top_n} strategies...")
        vendor_base_dir = Path("user_data/strategies_vendor")
        vendor_base_dir.mkdir(parents=True, exist_ok=True)

        count = 0
        for repo in candidates:
            if count >= top_n:
                break

            if self._vendor_repo(repo, vendor_base_dir):
                count += 1

    def _vendor_repo(self, repo, base_dir):
        full_name = repo["full_name"]
        repo_name = repo["name"]
        safe_name = full_name.replace("/", "_")
        path = repo.get("strategy_path")

        if not path:
            return False

        print(f"Vendoring from {full_name}...")
        vendor_dir = base_dir / safe_name
        vendor_dir.mkdir(parents=True, exist_ok=True)

        try:
            url = f"{GITHUB_API_URL}/repos/{full_name}/contents/{path}"
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                contents = resp.json()
                self._download_files(contents, vendor_dir)
                self._write_license_note(vendor_dir, repo, repo_name)
                return True
            else:
                print(f"Error fetching {full_name}: {resp.status_code}")
                self._cleanup_dir(vendor_dir)
                return False
        except Exception as e:
            print(f"Error vendoring {full_name}: {e}")
            self._cleanup_dir(vendor_dir)
            return False

    def _download_files(self, contents, vendor_dir):
        downloaded = 0
        for file_info in contents:
            fname = file_info.get("name", "")
            if not fname.endswith(".py") or fname == "__init__.py":
                continue

            if downloaded >= 3:
                # Limit to 3 files per repo to save bandwidth/noise
                break

            raw_url = file_info.get("download_url")
            if raw_url:
                r = requests.get(raw_url, timeout=REQUEST_TIMEOUT)
                if r.status_code == 200:
                    file_path = vendor_dir / file_info["name"]
                    with file_path.open("w") as f:
                        f.write(r.text)
                    downloaded += 1

    def _write_license_note(self, vendor_dir, repo, repo_name):
        license_file = vendor_dir / "LICENSE_NOTE.md"
        with license_file.open("w") as f:
            f.write(f"# License Note for {repo_name}\n\n")
            f.write(f"Source: {repo['html_url']}\n")
            f.write(f"License: {repo.get('license_name', 'Unknown')}\n")
            f.write("Please check the original repository for full license details.\n")

    def _cleanup_dir(self, directory):
        if directory.exists() and not any(directory.iterdir()):
            directory.rmdir()


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
