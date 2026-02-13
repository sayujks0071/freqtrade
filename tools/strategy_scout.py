#!/usr/bin/env python3
"""
Strategy Scout for Freqtrade
Automatically discovers and shortlists the best open-source Python crypto trading strategies.
"""

import argparse
import ast
import contextlib
import datetime
import os
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
REQUEST_TIMEOUT = 10  # Seconds


class StrategyVisitor(ast.NodeVisitor):
    """
    AST Visitor to extract metadata from strategy files without executing them.
    """

    def __init__(self):
        self.metadata = {
            "stoploss": None,
            "minimal_roi": None,
            "timeframe": None,
            "can_short": False,
            "process_only_new_candles": None,
            "indicators": [],
        }

    def visit_ClassDef(self, node):
        # We only care about classes that look like strategies (inherit from IStrategy effectively)
        # But we can't easily check inheritance without resolving imports.
        # So we just look for specific fields in any class.
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        self._check_assignment(target.id, item.value)
        self.generic_visit(node)

    def _check_assignment(self, name, value):
        if name == "stoploss":
            self.metadata["stoploss"] = self._get_value(value)
        elif name == "minimal_roi":
            self.metadata["minimal_roi"] = "Dict"  # ROI is usually a dict, hard to parse fully
        elif name == "timeframe":
            self.metadata["timeframe"] = self._get_value(value)
        elif name == "can_short":
            self.metadata["can_short"] = self._get_value(value)
        elif name == "process_only_new_candles":
            self.metadata["process_only_new_candles"] = self._get_value(value)

    def _get_value(self, node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
                return -node.operand.value
        return None

    def visit_FunctionDef(self, node):
        if node.name == "populate_indicators":
            # heuristics to find indicators
            # We can check for 'qtpylib', 'ta.', 'talib.' calls
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Attribute):
                        if isinstance(child.func.value, ast.Name):
                            if child.func.value.id in ["ta", "talib", "qtpylib"]:
                                ind = f"{child.func.value.id}.{child.func.attr}"
                                if ind not in self.metadata["indicators"]:
                                    self.metadata["indicators"].append(ind)
        self.generic_visit(node)


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
                    print(f"WARNING: Rate limit low. Resets at {reset_time}. halting or degrading.")
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
            # Increased per_page to 100
            params = {"q": query, "sort": "stars", "order": "desc", "per_page": 100}
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
            score = 0
            notes = []

            # Metadata filtering
            full_name = repo["full_name"]
            pushed_at = repo.get("pushed_at")
            license_data = repo.get("license")

            # 1. License Check
            license_name = "Unknown"
            is_known_source = full_name in KNOWN_SOURCES

            if license_data and license_data.get("key") != "other":
                license_name = license_data.get("name", "Unknown")
                score += 5  # Clear license
            elif license_data and license_data.get("key") == "other":
                license_name = "Other (Check manually)"
                # Strictly penalize "Other" unless known source, or at least don't give points
                if is_known_source:
                    score += 5
                else:
                    score += 1
            else:
                # No license
                if is_known_source:
                    score += 5
                    license_name = "Implicit (Known Source)"
                else:
                    # Reject "no license"
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

    def _fetch_repo_tree(self, repo):
        """Fetch recursive tree to find strategy files."""
        full_name = repo["full_name"]
        default_branch = repo.get("default_branch", "master")
        strategies = []

        url = f"{GITHUB_API_URL}/repos/{full_name}/git/trees/{default_branch}?recursive=1"
        try:
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                tree = resp.json().get("tree", [])
                for item in tree:
                    path = item.get("path", "")
                    # Heuristic: .py file, contains 'strategy' in path or name, not __init__
                    if path.endswith(".py") and not path.endswith("__init__.py"):
                        # Check if it looks like a strategy file location
                        if (
                            "strategies" in path
                            or "Strategy" in path
                            or "freqtrade" in path.lower()
                        ):
                            # We need the raw download url
                            base = "https://raw.githubusercontent.com"
                            item["download_url"] = f"{base}/{full_name}/{default_branch}/{path}"
                            strategies.append(item)
        except Exception as e:
            print(f"Error fetching tree for {full_name}: {e}")

        return strategies

    def _analyze_strategy_content(self, content):
        """Analyze strategy content using AST."""
        visitor = StrategyVisitor()
        with contextlib.suppress(Exception):
            tree = ast.parse(content)
            visitor.visit(tree)
        return visitor.metadata

    def deep_inspect(self, limit=15):
        print(f"Deep inspecting top {limit} candidates...")
        inspected_count = 0

        for repo in self.candidates:
            if inspected_count >= limit:
                break

            if not self.check_rate_limit():
                print("Rate limit exhausted, stopping inspection.")
                break

            self._inspect_single_repo(repo)
            inspected_count += 1

        # Re-sort after inspection
        self.candidates = sorted(self.candidates, key=lambda x: x["scout_score"], reverse=True)

    def _inspect_single_repo(self, repo):
        full_name = repo["full_name"]
        print(f"Inspecting {full_name}...")

        strategies = self._fetch_repo_tree(repo)
        repo["strategy_count"] = len(strategies)
        repo["strategies"] = strategies

        if strategies:
            repo["scout_score"] += min(len(strategies), 5) * 1
            self._analyze_first_strategy(repo, strategies[0])
        else:
            repo["scout_score"] -= 5

    def _analyze_first_strategy(self, repo, strategy_file):
        try:
            # Fetch content
            content_resp = requests.get(
                strategy_file["download_url"], timeout=REQUEST_TIMEOUT
            )
            if content_resp.status_code == 200:
                content = content_resp.text
                metadata = self._analyze_strategy_content(content)
                self._apply_metadata_score(repo, metadata, content)
        except Exception as e:
            print(f"Failed to analyze content for {repo['full_name']}: {e}")

    def _apply_metadata_score(self, repo, metadata, content):
        if metadata["stoploss"] is not None:
            repo["scout_score"] += 2
            repo["scout_notes"].append("Has stoploss")
        if metadata["minimal_roi"] is not None:
            repo["scout_score"] += 2
            repo["scout_notes"].append("Has ROI")
        if metadata["can_short"] is True:
            repo["scout_notes"].append("Futures/Shorts mentioned")
            repo["can_short"] = True
        if metadata["indicators"]:
            repo["scout_score"] += 2
            repo["indicators_sample"] = metadata["indicators"][:5]

        if metadata["timeframe"]:
            repo["timeframe"] = metadata["timeframe"]

        if "martingale" in content.lower():
            repo["scout_score"] -= 10
            repo["scout_notes"].append("Martingale detected (Risk!)")

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

                if repo.get("timeframe"):
                    f.write(f"- **Timeframe:** {repo['timeframe']}\n")

                if repo.get("indicators_sample"):
                    f.write(f"- **Indicators (Sample):** {', '.join(repo['indicators_sample'])}\n")

                if repo.get("scout_notes"):
                    f.write(f"- **Notes:** {', '.join(repo['scout_notes'])}\n")

                f.write("- **Adoption Notes:** ")
                adoption = []
                if repo.get("can_short"):
                    adoption.append("**Futures Support:** detected `can_short=True`.")
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
                    url = repo["html_url"]
                    full = repo["full_name"]
                    score = repo.get("scout_score", 0)
                    stars = repo.get("stargazers_count", 0)
                    lic = repo.get("license_name", "Unknown")
                    line = f"| {i} | [{full}]({url}) | {score} | {stars} | {lic} |\n"
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
            strategies = repo.get("strategies", [])

            if not strategies:
                continue

            print(f"Vendoring from {full_name}...")

            vendor_dir = vendor_base_dir / safe_name
            vendor_dir.mkdir(parents=True, exist_ok=True)

            try:
                downloaded = 0
                for file_info in strategies:
                    if downloaded >= 3:
                        break

                    fname = Path(file_info.get("path", "")).name
                    raw_url = file_info.get("download_url")

                    if raw_url:
                        r = requests.get(raw_url, timeout=REQUEST_TIMEOUT)
                        if r.status_code == 200:
                            file_path = vendor_dir / fname
                            with file_path.open("w") as f:
                                f.write(r.text)
                            downloaded += 1

                if downloaded > 0:
                    license_file = vendor_dir / "LICENSE_NOTE.md"
                    with license_file.open("w") as f:
                        f.write(f"# License Note for {repo_name}\n\n")
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
