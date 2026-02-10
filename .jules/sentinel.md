## 2026-02-10 - Fixed Weak JWT Secret Check
**Vulnerability:** The warning logic for default JWT secret keys checked if the key was a substring of `"super-secret, somethingrandom"`, causing false positives (e.g., "super", "secret") and failing to identify precise default values correctly.
**Learning:** Implicit string concatenation or typos in tuple definitions (missing quotes) can lead to subtle security logic bugs where substring matching is performed instead of set membership.
**Prevention:** Use explicit tuples `("a", "b")` and verify `in` operator behavior. Added explicit length check for secrets.
