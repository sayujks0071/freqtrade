#!/usr/bin/env python3
import base64
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Strategy Scout: Finds open-source Freqtrade strategies on GitHub
# Disclaimer: This is a discovery tool. All strategies must be audited.

GITHUB_API_URL = "https://api.github.com/search/repositories"
QUERY = "freqtrade strategy language:python created:>2023-01-01"


def get_json(url):
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Freqtrade-Scout")
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None


def check_repo_safety(repo_full_name):
    """
    Heuristic check of README for risk keywords.
    """
    url = f"https://api.github.com/repos/{repo_full_name}/readme"
    data = get_json(url)
    if data and "content" in data:
        try:
            content = base64.b64decode(data["content"]).decode(
                "utf-8", errors="ignore"
            )
            score = 0
            content_lower = content.lower()
            if "stoploss" in content_lower:
                score += 1
            if "risk" in content_lower:
                score += 1
            if "futures" in content_lower:
                score += 1
            return score
        except Exception:
            pass
    return 0


def search_strategies():
    print(f"Searching GitHub for: {QUERY}")

    # Manual query construction
    params = f"?q={urllib.parse.quote(QUERY)}&sort=stars&order=desc&per_page=20"
    url = GITHUB_API_URL + params

    data = get_json(url)
    if not data:
        return []

    results = []
    for item in data.get("items", []):
        repo_name = item["full_name"]
        print(f"Inspecting {repo_name}...")
        risk_score = check_repo_safety(repo_name)

        repo = {
            "name": item["name"],
            "full_name": repo_name,
            "url": item["html_url"],
            "stars": item["stargazers_count"],
            "updated_at": item["updated_at"],
            "description": item["description"],
            "license": item["license"]["name"] if item["license"] else "None",
            "risk_score": risk_score,
        }

        # Filter for license
        if repo["license"] == "None":
            continue

        results.append(repo)

    return results


def generate_report(strategies):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")  # noqa: UP017
    report = f"# Strategy Scout Report ({now})\n\n"
    report += "Top open-source Freqtrade strategies found on GitHub (with licenses).\n"
    report += "Risk score based on keywords (stoploss, risk, futures) in README.\n\n"

    report += "| Name | Stars | Updated | License | Risk Score | Description |\n"
    report += "|---|---|---|---|---|---|\n"

    for s in strategies:
        desc = (s["description"] or "").replace("|", "-")[:100]
        report += (
            f"| [{s['full_name']}]({s['url']}) | {s['stars']} | "
            f"{s['updated_at'][:10]} | {s['license']} | {s['risk_score']} | {desc} |\n"
        )

    filename = f"user_data/reports/strategy_shortlist_{now}.md"
    try:
        with Path(filename).open("w") as f:
            f.write(report)
        print(f"Report saved to {filename}")
    except Exception as e:
        print(f"Error saving report: {e}")


if __name__ == "__main__":
    strategies = search_strategies()
    if strategies:
        generate_report(strategies)
    else:
        print("No strategies found.")
