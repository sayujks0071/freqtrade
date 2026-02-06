## 2026-02-06 - Insecure Default API Configuration
**Vulnerability:** The API server defaulted to `0.0.0.0` and used a hardcoded JWT secret ("somethingrandom") in sample configs. Additionally, the code check for default secrets had a bug: `in ("super-secret, somethingrandom")` (string) instead of a tuple, making the check ineffective against "super-secret".
**Learning:** Python tuple syntax `("a")` is just a parenthesized string. Always use a trailing comma `("a",)` or multiple elements `("a", "b")` for tuples. Security checks must be rigorously tested.
**Prevention:** Use `secrets.compare_digest` for string comparisons and ensure correct data structures for allow/deny lists. Enforce secure defaults in code (auto-generation) rather than relying on config files.
