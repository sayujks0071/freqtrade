## 2026-02-11 - [JWT Secret Validation Fix]
**Vulnerability:** The `jwt_secret_key` validation check incorrectly used substring matching `if key in "string"`, causing false positives (e.g., "om" in "somethingrandom") and failing to detect short keys.
**Learning:** Checking for membership in a string ("abc") vs a tuple ("a", "b", "c") is a subtle but critical distinction in Python.
**Prevention:** Always use explicit tuples or lists for membership checks. Always enforce minimum length requirements for secrets.
