## 2025-02-18 - Path Traversal in Strategy Scout
**Vulnerability:** `tools/strategy_scout.py` trusted filenames from GitHub API when vendoring strategies, allowing path traversal (e.g., `../../exploit.py`) to write files outside the intended directory.
**Learning:** Even "trusted" APIs like GitHub's can provide data that is unsafe for local filesystem operations. Relying on external input for file paths without sanitization is a critical risk.
**Prevention:** Always sanitize filenames using `os.path.basename` (and potentially stricter character validation) before using them in file path construction.
