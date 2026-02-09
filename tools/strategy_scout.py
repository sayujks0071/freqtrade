#!/usr/bin/env python3
"""
Strategy Scout for Freqtrade
Automatically discovers and shortlists the best open-source Python crypto trading strategies.
"""

import argparse
import ast
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
    def __init__(self):
        self.metadata = {
            "timeframe": None,
            "stoploss": None,
            "can_short": False,
            "process_only_new_candles": False,
            "minimal_roi": False,
            "populate_indicators": False,
            "populate_entry_trend": False,
            "populate_exit_trend": False,
            "martingale": False,
        }

    def visit_Assign(self, node):
        # Check for global variables or class attributes
        for target in node.targets:
            if isinstance(target, ast.Name):
                self._check_assignment(target.id, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if isinstance(node.target, ast.Name):
            self._check_assignment(node.target.id, node.value)
        self.generic_visit(node)

    def _check_assignment(self, name, value):
        if name == "timeframe":
            if isinstance(value, ast.Constant):
                self.metadata["timeframe"] = value.value
        elif name == "stoploss":
            if isinstance(value, ast.Constant):
                self.metadata["stoploss"] = value.value
            elif isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.USub):
                if isinstance(value.operand, ast.Constant):  # Handle -0.1
                    self.metadata["stoploss"] = -value.operand.value
        elif name == "can_short":
            if isinstance(value, ast.Constant):
                self.metadata["can_short"] = value.value
        elif name == "process_only_new_candles":
            if isinstance(value, ast.Constant):
                self.metadata["process_only_new_candles"] = value.value
        elif name == "minimal_roi":
             self.metadata["minimal_roi"] = True

    def visit_FunctionDef(self, node):
        if node.name == "populate_indicators":
            self.metadata["populate_indicators"] = True
        elif node.name == "populate_entry_trend":
            self.metadata["populate_entry_trend"] = True
        elif node.name == "populate_exit_trend":
            self.metadata["populate_exit_trend"] = True
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        # We also need to check class attributes
        for item in node.body:
             if isinstance(item, ast.Assign):
                 for target in item.targets:
                     if isinstance(target, ast.Name):
                         self._check_assignment(target.id, item.value)
             elif isinstance(item, ast.AnnAssign):
                 if isinstance(item.target, ast.Name):
                     self._check_assignment(item.target.id, item.value)
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
            # Check headers from last response if available, or just proceed cautiously
            # But here we explicitly check /rate_limit endpoint occasionally or on error
            resp = self.session.get(f"{GITHUB_API_URL}/rate_limit", timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                core = data["resources"]["core"]
                remaining = core["remaining"]
                reset = core["reset"]
                # print(f"DEBUG: Rate limit remaining: {remaining}")
                if remaining < RATE_LIMIT_BUFFER:
                    reset_time = datetime.datetime.fromtimestamp(reset)
                    print(f"WARNING: Rate limit low. Resets at {reset_time}. halting or degrading.")
                    return False
            elif resp.status_code == 403:
                 print("WARNING: Rate limit exceeded (403).")
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
            if license_data and license_data.get("key") != "other":
                license_name = license_data.get("name", "Unknown")
                score += 5  # Clear license
            elif license_data and license_data.get("key") == "other":
                license_name = "Other (Check manually)"
                score += 1
            else:
                # If no license and not a known source, skip
                if full_name not in KNOWN_SOURCES:
                    # print(f"Skipping {full_name} due to missing license.")
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

            # Initialize default metadata in repo dict
            repo["extracted_metadata"] = {
                "timeframe": "N/A",
                "stoploss": "N/A",
                "can_short": False,
                "process_only_new_candles": False
            }

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

    def _analyze_strategy_content(self, strat_file, repo):
        """Helper to download and analyze strategy content using AST."""
        try:
            download_url = strat_file.get("download_url")
            if download_url:
                content_resp = requests.get(download_url, timeout=REQUEST_TIMEOUT)
                if content_resp.status_code == 200:
                    content = content_resp.text

                    # Text-based checks (fallback/supplement)
                    if "martingale" in content.lower():
                        repo["scout_score"] -= 10
                        repo["scout_notes"].append("Martingale detected (Risk!)")

                    # AST Parsing
                    try:
                        tree = ast.parse(content)
                        visitor = StrategyVisitor()
                        visitor.visit(tree)
                        metadata = visitor.metadata

                        # Store metadata
                        repo["extracted_metadata"] = metadata

                        # Scoring based on AST
                        if metadata["stoploss"] is not None:
                            repo["scout_score"] += 2
                            repo["scout_notes"].append(f"Stoploss: {metadata['stoploss']}")

                        if metadata["minimal_roi"]:
                            repo["scout_score"] += 2

                        if metadata["process_only_new_candles"]:
                            repo["scout_score"] += 5
                            repo["scout_notes"].append("Non-repainting (process_only_new_candles)")

                        if metadata["can_short"]:
                            repo["scout_score"] += 3
                            repo["scout_notes"].append("Futures/Shorts ready")

                        if metadata["populate_indicators"]:
                            repo["scout_score"] += 2

                        if metadata["populate_entry_trend"] and metadata["populate_exit_trend"]:
                            repo["scout_score"] += 2

                    except SyntaxError:
                        repo["scout_notes"].append("Syntax Error in parsing")
                    except Exception as e:
                        repo["scout_notes"].append(f"AST Error: {e}")

        except Exception as e:
            print(f"Failed to read file {strat_file['name']}: {e}")

    def deep_inspect(self, limit=15):
        print(f"Deep inspecting top {limit} candidates...")
        inspected_count = 0
        final_candidates = []

        for i, repo in enumerate(self.candidates):
            if inspected_count >= limit:
                # Add the rest without inspection if needed, or just break
                # But we want to keep the list populated for "Other Candidates"
                final_candidates.append(repo)
                continue

            if not self.check_rate_limit():
                print("Rate limit exhausted, stopping inspection.")
                final_candidates.extend(self.candidates[i:])
                break

            full_name = repo["full_name"]
            print(f"Inspecting {full_name}...")

            strategies, found_path = self._find_strategy_files(full_name)

            repo["strategy_count"] = len(strategies)
            repo["strategy_path"] = found_path

            if len(strategies) > 0:
                repo["scout_score"] += min(len(strategies), 5) * 1  # +1 per strategy up to 5
                # Check the first strategy file for content
                self._analyze_strategy_content(strategies[0], repo)
            else:
                repo["scout_score"] -= 5

            final_candidates.append(repo)
            inspected_count += 1

        self.candidates = final_candidates
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
                if repo.get("pushed_at"):
                    last_update = repo.get("pushed_at", "").split("T")[0]
                    f.write(f"- **Last Update:** {last_update}\n")

                desc = repo.get("description")
                if desc:
                    f.write(f"- **Description:** {desc}\n")

                meta = repo.get("extracted_metadata", {})
                if meta:
                     f.write(f"- **Timeframe:** {meta.get('timeframe', 'N/A')}\n")
                     f.write(f"- **Stoploss:** {meta.get('stoploss', 'N/A')}\n")
                     f.write(f"- **Can Short:** {meta.get('can_short', False)}\n")
                     f.write(f"- **Process Only New Candles:** {meta.get('process_only_new_candles', False)}\n")

                if repo.get("scout_notes"):
                    f.write(f"- **Notes:** {', '.join(repo['scout_notes'])}\n")

                f.write("- **Adoption Notes:** ")
                adoption = []
                if meta.get("can_short"):
                    adoption.append("Futures ready (can_short=True).")
                else:
                    adoption.append("Check for `can_short` if trading futures.")

                stoploss = meta.get("stoploss")
                if stoploss and isinstance(stoploss, (int, float)) and stoploss > -0.05: # e.g. -0.01 (1%)
                     adoption.append("Tight stoploss detected.")

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
            path = repo.get("strategy_path")

            if not path:
                continue  # Can't vendor if we didn't find the path

            print(f"Vendoring from {full_name}...")

            vendor_dir = vendor_base_dir / safe_name
            vendor_dir.mkdir(parents=True, exist_ok=True)

            try:
                url = f"{GITHUB_API_URL}/repos/{full_name}/contents/{path}"
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    contents = resp.json()
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
