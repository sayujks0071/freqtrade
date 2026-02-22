## 2025-02-12 - Insecure Default Configuration Check
**Vulnerability:** The configuration check for `jwt_secret_key` used a string containment check `in ("super-secret, somethingrandom")` which incorrectly allowed any substring (like "secret") to pass as a default, and also allowed the insecure defaults to be used (just logging a warning).
**Learning:** Python string vs tuple syntax in `in` operator can be tricky. Also, simply warning about insecure defaults is often insufficient; auto-remediation (generating a secure value) is safer.
**Prevention:** Use explicit tuples/sets for membership checks. Implement "secure by default" by generating secrets if missing or insecure.
