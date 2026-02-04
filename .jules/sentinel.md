## 2025-02-18 - Default JWT Secret Key Vulnerability
**Vulnerability:** The application defaulted to "super-secret" for JWT signing if no key was provided in config. This allows attackers to forge tokens.
**Learning:** Checking for substrings (`in "string1, string2"`) instead of checking against a list/tuple (`in ("string1", "string2")`) can lead to incorrect logic and false negatives/positives.
**Prevention:** Always verify default configuration values and auto-generate secure secrets if missing, rather than falling back to weak hardcoded defaults.
