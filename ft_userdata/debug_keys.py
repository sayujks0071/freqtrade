import sys
import json
import zipfile


def inspect_json(filepath):
    try:
        if filepath.endswith(".zip"):
            with zipfile.ZipFile(filepath, "r") as z:
                json_files = [
                    f
                    for f in z.namelist()
                    if f.endswith(".json") and not f.endswith(".meta.json")
                ]
                if not json_files:
                    print("Error: No result JSON found in ZIP.")
                    sys.exit(1)
                with z.open(json_files[0]) as f:
                    data = json.load(f)
        else:
            with open(filepath, "r") as f:
                data = json.load(f)

        # Print top level keys
        print("Top Level Keys:", list(data.keys()))

        if "strategy" in data:
            strat_name = list(data["strategy"].keys())[0]
            print(f"Strategy: {strat_name}")
            stats = data["strategy"][strat_name]
            print("Stats Keys:", list(stats.keys()))

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    inspect_json(sys.argv[1])
