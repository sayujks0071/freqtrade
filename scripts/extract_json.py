#!/usr/bin/env python3
import sys
import json
import re

def main():
    content = sys.stdin.read()
    # Attempt to find JSON array within potential logs
    # Using regex to find the last occurrence of a JSON-like array structure
    # This assumes the list-markets output ends with the JSON array or contains it clearly.
    # Note: re.DOTALL allows matching across newlines if the JSON is pretty-printed.

    # Simple strategy: find [ ... ]
    match = re.search(r'\[.*\]', content, re.DOTALL)

    if match:
        json_str = match.group(0)
        try:
            data = json.loads(json_str)
            print(json.dumps(data))
            return
        except json.JSONDecodeError:
            pass # Continue if simple regex fails

    # Fallback: try to parse the last few lines or look for specific markers
    # If standard output is mixed with logs, it's tricky.
    # But --print-json usually outputs clean JSON on stdout if logging is configured correctly (stderr for logs).
    # Assuming freqtrade sends logs to stderr and JSON to stdout.

    # If the regex fails, try parsing the whole content as JSON (maybe no logs)
    try:
        data = json.loads(content)
        print(json.dumps(data))
        return
    except json.JSONDecodeError:
        pass

    # If all fails
    print("[]")

if __name__ == "__main__":
    main()
