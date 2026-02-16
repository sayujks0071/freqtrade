#!/usr/bin/env python3
import json
import argparse
import sys
import os
from datetime import datetime
import urllib.request
import urllib.error

GITHUB_API = "https://api.github.com/search/repositories"

def search_strategies(token=None, limit=10):
    query = "freqtrade strategy language:python"
    # URL encode the query
    from urllib.parse import quote
    encoded_query = quote(query)
    url = f"{GITHUB_API}?q={encoded_query}&sort=updated&order=desc"

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Freqtrade-Strategy-Scout"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return data.get('items', [])[:limit]
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print("Rate limit exceeded. Provide a token.")
        else:
            print(f"Error searching GitHub: {e}")
        return []
    except Exception as e:
        print(f"Error searching GitHub: {e}")
        return []

def check_license(repo):
    # Check if license exists and is open source
    license_info = repo.get('license')
    if license_info and license_info.get('key') in ['mit', 'apache-2.0', 'gpl-3.0', 'bsd-3-clause', 'cc0-1.0', 'unlicense']:
        return True
    return False

def generate_report(strategies, filename):
    # ensure dir exists
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with open(filename, 'w') as f:
        f.write(f"# Strategy Scout Report ({datetime.now().date()})\n\n")
        if not strategies:
            f.write("No strategies found matching criteria.\n")
            return

        for s in strategies:
            full_name = s.get('full_name', 'Unknown')
            html_url = s.get('html_url', '#')
            description = s.get('description', 'No description')
            stars = s.get('stargazers_count', 0)
            forks = s.get('forks_count', 0)
            license_info = s.get('license')
            license_name = license_info['name'] if license_info else 'None'
            updated_at = s.get('updated_at', 'Unknown')

            f.write(f"## {full_name}\n")
            f.write(f"- URL: {html_url}\n")
            f.write(f"- Description: {description}\n")
            f.write(f"- Stars: {stars} | Forks: {forks}\n")
            f.write(f"- License: {license_name}\n")
            f.write(f"- Updated: {updated_at}\n\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", help="GitHub API Token")
    parser.add_argument("--out", default="user_data/reports/strategy_shortlist.md")
    args = parser.parse_args()

    print("Searching GitHub for Freqtrade strategies...")
    strategies = search_strategies(args.token)
    valid_strategies = [s for s in strategies if check_license(s)]

    generate_report(valid_strategies, args.out)
    print(f"Found {len(valid_strategies)} valid strategies. Report saved to {args.out}")
