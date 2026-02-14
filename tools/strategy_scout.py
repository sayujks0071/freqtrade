#!/usr/bin/env python3
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone


GITHUB_API = "https://api.github.com/search/repositories"


def search_github(query, sort="updated", order="desc", limit=30):
    params = {"q": query, "sort": sort, "order": order, "per_page": limit}
    qs = urllib.parse.urlencode(params)
    url = f"{GITHUB_API}?{qs}"

    req = urllib.request.Request(url)
    # Add User-Agent to avoid 403
    req.add_header("User-Agent", "Freqtrade-Strategy-Scout")

    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                return json.loads(response.read().decode())
    except Exception as e:
        print(f"Error searching GitHub: {e}")
        return None


def get_repo_content(owner, repo, path=""):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Freqtrade-Strategy-Scout")
    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                return json.loads(response.read().decode())
    except:
        return None


def evaluate_repo(repo):
    score = 0
    reasons = []

    # 1. License Check
    license_info = repo.get("license")
    if not license_info or license_info.get("key") not in [
        "mit",
        "apache-2.0",
        "bsd-3-clause",
        "gpl-3.0",
        "mpl-2.0",
    ]:
        return 0, ["No valid open source license"]

    # 2. Recency
    updated_at = datetime.strptime(repo["updated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    days_since_update = (datetime.now(timezone.utc) - updated_at).days

    if days_since_update < 30:
        score += 50
        reasons.append("Recently updated (<30 days)")
    elif days_since_update < 90:
        score += 20
        reasons.append("Updated within 90 days")

    # 3. Popularity
    stars = repo["stargazers_count"]
    score += min(stars, 50)  # Cap at 50
    reasons.append(f"Stars: {stars}")

    # 4. Content Heuristics (expensive API call, maybe skip for scout or do for top N)
    # Just use description for now
    desc = (repo["description"] or "").lower()
    if "freqtrade" in desc and "strategy" in desc:
        score += 10

    return score, reasons


def main():
    print("Scouting for strategies...")
    results = search_github("freqtrade strategy", sort="updated")

    if not results or "items" not in results:
        print("No results found.")
        return

    candidates = []
    for item in results["items"]:
        score, reasons = evaluate_repo(item)
        if score > 0:
            candidates.append(
                {
                    "name": item["full_name"],
                    "url": item["html_url"],
                    "score": score,
                    "stars": item["stargazers_count"],
                    "updated": item["updated_at"],
                    "desc": item["description"],
                    "reasons": reasons,
                }
            )

    # Sort by score
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Generate Report
    report_file = (
        f"user_data/reports/strategy_shortlist_{datetime.now(timezone.utc).strftime('%Y%m%d')}.md"
    )
    os.makedirs(os.path.dirname(report_file), exist_ok=True)

    with open(report_file, "w") as f:
        f.write("# Strategy Scout Report\n\n")
        f.write(f"Date: {datetime.now(timezone.utc)}\n\n")
        f.write("| Rank | Name | Score | Stars | Updated | Description |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- |\n")

        for i, c in enumerate(candidates[:20]):  # Top 20
            desc = (c["desc"] or "").replace("|", "-").replace("\n", " ")[:100]
            f.write(
                f"| {i + 1} | [{c['name']}]({c['url']}) | {c['score']} | {c['stars']} | {c['updated'][:10]} | {desc} |\n"
            )

    print(f"Report written to {report_file}")


if __name__ == "__main__":
    main()
