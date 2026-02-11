#!/usr/bin/env python3
"""
Strategy Scout: Discover and shortlist Freqtrade strategies from GitHub.
"""

import argparse
import ast
import base64
import datetime
import logging
import time
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)


class StrategyVisitor(ast.NodeVisitor):
    def __init__(self):
        self.is_strategy = False
        self.metadata = {
            "stoploss": None,
            "minimal_roi": None,
            "timeframe": None,
            "can_short": None,
            "process_only_new_candles": None,
            "indicators": [],
            "risk_controls": False,
        }
        self.has_indicators = False
        self.has_entry = False
        self.has_exit = False
        self.docstring = None

    def visit_ClassDef(self, node: ast.ClassDef):
        # Check inheritance
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "IStrategy":
                self.is_strategy = True
            elif isinstance(base, ast.Attribute) and base.attr == "IStrategy":
                self.is_strategy = True

        if self.is_strategy:
            self.docstring = ast.get_docstring(node)
            self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        if not self.is_strategy:
            return

        for target in node.targets:
            if isinstance(target, ast.Name):
                key = target.id
                if key in self.metadata:
                    try:
                        # Extract value if it's a simple literal
                        if isinstance(node.value, ast.Constant):
                            self.metadata[key] = node.value.value
                        elif isinstance(node.value, ast.Dict):
                            self.metadata[key] = "Dict" # Placeholder
                            if key == "minimal_roi":
                                self.metadata["risk_controls"] = True
                        elif isinstance(node.value, ast.UnaryOp) and isinstance(node.value.op, ast.USub):
                            if isinstance(node.value.operand, ast.Constant): # Handle negative numbers
                                val = node.value.operand.value
                                self.metadata[key] = -val
                    except Exception:
                        pass

                if key == "stoploss":
                    self.metadata["risk_controls"] = True

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if not self.is_strategy:
            return

        if node.name == "populate_indicators":
            self.has_indicators = True
            # Could analyze body for talib calls
        elif node.name == "populate_entry_trend":
            self.has_entry = True
        elif node.name == "populate_exit_trend":
            self.has_exit = True


class StrategyScout:
    def __init__(self, token: str | None = None, limit: int = 50):
        self.base_url = "https://api.github.com"
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            self.headers["Authorization"] = f"token {token}"
        self.limit = limit
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.remaining_rate_limit = 10  # Assume low until checked
        self.rate_limit_reset = 0

    def _check_rate_limit(self, response: requests.Response) -> None:
        self.remaining_rate_limit = int(response.headers.get("x-ratelimit-remaining", 10))
        self.rate_limit_reset = int(response.headers.get("x-ratelimit-reset", 0))

        if self.remaining_rate_limit < 2:
            wait_time = max(0, self.rate_limit_reset - int(time.time())) + 1
            logger.warning(f"Rate limit approaching. Sleeping for {wait_time} seconds.")
            time.sleep(wait_time)

    def search_repos(self, queries: list[str]) -> list[dict[str, Any]]:
        """
        Search GitHub for repositories matching the queries.
        """
        unique_repos = {}

        for query in queries:
            page = 1
            while len(unique_repos) < self.limit:
                logger.info(f"Searching for '{query}' (page {page})...")
                url = f"{self.base_url}/search/repositories"
                params = {
                    "q": query,
                    "sort": "updated",
                    "order": "desc",
                    "per_page": 30,
                    "page": page,
                }

                try:
                    resp = self.session.get(url, params=params)
                    self._check_rate_limit(resp)
                    resp.raise_for_status()
                    data = resp.json()

                    items = data.get("items", [])
                    if not items:
                        break

                    for item in items:
                        repo_id = item["id"]
                        if repo_id not in unique_repos:
                            unique_repos[repo_id] = item

                    if len(items) < 30:
                        break # End of results

                    page += 1
                    # Simple safety sleep
                    time.sleep(1)

                except requests.exceptions.RequestException as e:
                    logger.error(f"Error searching GitHub: {e}")
                    break

        # Sort by updated_at desc
        sorted_repos = sorted(
            unique_repos.values(),
            key=lambda x: x.get("updated_at", ""),
            reverse=True
        )
        return sorted_repos[:self.limit]

    def get_repo_contents(self, owner: str, repo: str, path: str = "") -> list[dict]:
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"
        try:
            resp = self.session.get(url)
            self._check_rate_limit(resp)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return [data]
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching contents for {owner}/{repo}/{path}: {e}")
            return []

    def get_file_content(self, url: str) -> str | None:
        try:
            resp = self.session.get(url)
            self._check_rate_limit(resp)
            resp.raise_for_status()
            data = resp.json()
            if "content" in data and "encoding" in data:
                if data["encoding"] == "base64":
                    return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
                else:
                    return data["content"]
            return None
        except Exception as e:
            logger.error(f"Error fetching file content from {url}: {e}")
            return None

    def analyze_strategy_code(self, code: str) -> dict | None:
        try:
            tree = ast.parse(code)
            visitor = StrategyVisitor()
            visitor.visit(tree)

            if visitor.is_strategy:
                # Basic heuristic check for suspicious terms
                suspicious = ["martingale", "grid"]
                is_suspicious = any(term in code.lower() for term in suspicious)

                return {
                    "is_strategy": True,
                    "metadata": visitor.metadata,
                    "has_indicators": visitor.has_indicators,
                    "has_entry": visitor.has_entry,
                    "has_exit": visitor.has_exit,
                    "docstring": visitor.docstring,
                    "is_suspicious": is_suspicious
                }
        except Exception as e:
            logger.debug(f"Failed to parse code: {e}")
        return None

    def scan_repository(self, repo: dict) -> list[dict]:
        owner = repo["owner"]["login"]
        repo_name = repo["name"]
        full_name = repo["full_name"]

        logger.info(f"Scanning {full_name}...")

        strategies = []

        # Look in common paths
        paths_to_check = ["user_data/strategies", "strategies", "."]

        # Avoid redundant checks if folders are nested
        checked_files = set()

        for path in paths_to_check:
            contents = self.get_repo_contents(owner, repo_name, path)
            for item in contents:
                if item["type"] == "file" and item["name"].endswith(".py"):
                    if item["path"] in checked_files:
                        continue
                    checked_files.add(item["path"])

                    # Fetch content
                    logger.info(f"  Analyzing {item['path']}...")
                    code = self.get_file_content(item["url"])
                    if code:
                        analysis = self.analyze_strategy_code(code)
                        if analysis:
                            strategies.append({
                                "repo_url": repo["html_url"],
                                "repo_name": full_name,
                                "file_path": item["path"],
                                "file_url": item["html_url"],
                                "download_url": item["download_url"],
                                "analysis": analysis,
                                "stats": {
                                    "stars": repo["stargazers_count"],
                                    "forks": repo["forks_count"],
                                    "updated_at": repo["updated_at"],
                                    "license": repo.get("license", {}).get("name") if repo.get("license") else "None"
                                }
                            })
                            # Stop after finding a few strategies per repo to save API calls
                            if len(strategies) >= 3:
                                break
            if len(strategies) >= 3:
                break

        return strategies

    def score_strategy(self, strategy: dict) -> int:
        score = 0
        stats = strategy["stats"]
        analysis = strategy["analysis"]
        metadata = analysis["metadata"]

        # Recency
        try:
            updated_at = datetime.datetime.strptime(stats["updated_at"], "%Y-%m-%dT%H:%M:%SZ")
            age_days = (datetime.datetime.now() - updated_at).days
            if age_days < 90:
                score += 10
            elif age_days < 180:
                score += 5
        except ValueError:
            pass

        # Stars
        stars = stats.get("stars", 0)
        score += min(20, stars // 100)

        # Risk Controls
        if metadata.get("stoploss"):
            score += 5
        if metadata.get("minimal_roi"):
            score += 5

        # Content
        if analysis.get("docstring"):
            score += 5
        if analysis.get("has_indicators"):
             score += 2
        if analysis.get("has_entry") and analysis.get("has_exit"):
            score += 5

        # Suspicious
        if analysis.get("is_suspicious"):
            score -= 50

        return score

    def generate_report(self, strategies: list[dict]) -> None:
        report_dir = Path("user_data/reports")
        report_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d")
        report_file = report_dir / f"strategy_shortlist_{timestamp}.md"

        with open(report_file, "w") as f:
            f.write(f"# Freqtrade Strategy Shortlist - {timestamp}\n\n")
            f.write(f"Generated by Strategy Scout. Found {len(strategies)} strategies.\n\n")

            f.write("## Top 10 Strategies\n\n")
            f.write("| Rank | Strategy | Repo | Stars | Updated | Score | Risk Controls |\n")
            f.write("|---|---|---|---|---|---|---|\n")

            for i, strategy in enumerate(strategies[:10]):
                stats = strategy["stats"]
                metadata = strategy["analysis"]["metadata"]
                risk = []
                if metadata.get("stoploss"): risk.append("SL")
                if metadata.get("minimal_roi"): risk.append("ROI")
                risk_str = ", ".join(risk) if risk else "None"

                name = Path(strategy["file_path"]).stem
                repo_link = f"[{strategy['repo_name']}]({strategy['repo_url']})"

                f.write(f"| {i+1} | {name} | {repo_link} | {stats['stars']} | {stats['updated_at'].split('T')[0]} | {strategy['score']} | {risk_str} |\n")

            if len(strategies) > 10:
                f.write("\n## Runners Up\n\n")
                f.write("| Rank | Strategy | Repo | Stars | Updated | Score | Risk Controls |\n")
                f.write("|---|---|---|---|---|---|---|\n")

                for i, strategy in enumerate(strategies[10:30]):
                    stats = strategy["stats"]
                    metadata = strategy["analysis"]["metadata"]
                    risk = []
                    if metadata.get("stoploss"): risk.append("SL")
                    if metadata.get("minimal_roi"): risk.append("ROI")
                    risk_str = ", ".join(risk) if risk else "None"

                    name = Path(strategy["file_path"]).stem
                    repo_link = f"[{strategy['repo_name']}]({strategy['repo_url']})"

                    f.write(f"| {11+i} | {name} | {repo_link} | {stats['stars']} | {stats['updated_at'].split('T')[0]} | {strategy['score']} | {risk_str} |\n")

            f.write("\n## Strategy Details\n\n")
            for i, strategy in enumerate(strategies[:10]):
                name = Path(strategy["file_path"]).stem
                analysis = strategy["analysis"]
                metadata = analysis["metadata"]

                f.write(f"### {i+1}. {name}\n")
                f.write(f"- **Repository**: {strategy['repo_url']}\n")
                f.write(f"- **File**: `{strategy['file_path']}`\n")
                f.write(f"- **License**: {strategy['stats']['license']}\n")
                f.write(f"- **Score**: {strategy['score']}\n")
                f.write(f"- **Timeframe**: {metadata.get('timeframe')}\n")
                f.write(f"- **Can Short**: {metadata.get('can_short')}\n")
                f.write(f"- **Risk Controls**: Stoploss: {metadata.get('stoploss')}, ROI: {metadata.get('minimal_roi')}\n")

                if analysis.get("docstring"):
                    f.write(f"\n**Description**:\n```\n{analysis['docstring']}\n```\n")

                f.write("\n")

        logger.info(f"Report generated at {report_file}")

    def vendor_strategies(self, strategies: list[dict], count: int = 5) -> None:
        vendor_dir = Path("user_data/strategies_vendor")
        vendor_dir.mkdir(parents=True, exist_ok=True)

        for strategy in strategies[:count]:
            repo_name = strategy["repo_name"].split("/")[-1]
            repo_owner = strategy["repo_name"].split("/")[0]
            target_dir = vendor_dir / f"{repo_owner}_{repo_name}"
            target_dir.mkdir(parents=True, exist_ok=True)

            # Download file
            file_name = Path(strategy["file_path"]).name
            target_file = target_dir / file_name

            content = None
            try:
                resp = requests.get(strategy["download_url"])
                if resp.status_code == 200:
                    content = resp.text
            except Exception as e:
                logger.error(f"Failed to download {strategy['file_path']}: {e}")

            if content:
                with open(target_file, "w") as f:
                    f.write(content)

                # Add LICENSE_NOTE.md
                license_note = (
                    f"# License Note\n\n"
                    f"This strategy was vendored from [{strategy['repo_name']}]({strategy['repo_url']}).\n"
                    f"Original file: `{strategy['file_path']}`\n"
                    f"License: {strategy['stats']['license']}\n\n"
                    f"Please respect the original license terms.\n"
                )
                with open(target_dir / "LICENSE_NOTE.md", "w") as f:
                    f.write(license_note)

                logger.info(f"Vendored {file_name} to {target_dir}")

    def run(self, vendor: bool = False):
        queries = [
            "freqtrade strategy",
            "freqtrade-strategies",
            "FreqAI strategy",
            "crypto trading strategy python freqtrade",
        ]
        repos = self.search_repos(queries)

        # Explicitly ensure freqtrade/freqtrade-strategies is in the list
        official_repo_name = "freqtrade/freqtrade-strategies"
        found_official = any(r["full_name"] == official_repo_name for r in repos)
        if not found_official:
            try:
                logger.info(f"Explicitly fetching {official_repo_name}...")
                resp = self.session.get(f"{self.base_url}/repos/{official_repo_name}")
                if resp.status_code == 200:
                    official_repo = resp.json()
                    repos.insert(0, official_repo)
            except Exception as e:
                logger.error(f"Failed to fetch {official_repo_name}: {e}")

        logger.info(f"Found {len(repos)} unique repositories.")

        all_strategies = []

        for repo in repos:
            # Skip repos with no license if we are strict, but let's just score them lower later
            # User constraint: "Only use public repos with clear licenses ... Reject 'no license'"
            license_info = repo.get("license")
            if not license_info or not license_info.get("key"):
                 logger.info(f"Skipping {repo['full_name']} (no license)")
                 continue

            repo_strategies = self.scan_repository(repo)
            all_strategies.extend(repo_strategies)

        print(f"Found {len(all_strategies)} potential strategies.")

        # Score strategies
        for strategy in all_strategies:
            strategy["score"] = self.score_strategy(strategy)

        # Sort by score desc
        all_strategies.sort(key=lambda x: x["score"], reverse=True)

        # Generate Report
        self.generate_report(all_strategies)

        # Vendor if requested
        if vendor:
            self.vendor_strategies(all_strategies)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(description="Freqtrade Strategy Scout")
    parser.add_argument("--token", help="GitHub API Token", default=None)
    parser.add_argument("--limit", help="Max repositories to analyze", type=int, default=20)
    parser.add_argument("--vendor", help="Vendor top strategies", action="store_true")

    args = parser.parse_args()

    scout = StrategyScout(token=args.token, limit=args.limit)
    scout.run(vendor=args.vendor)


if __name__ == "__main__":
    main()
