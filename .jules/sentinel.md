## 2026-02-02 - Hardcoded JWT Secret Remediation
**Vulnerability:** The API server defaulted to 'super-secret' for JWT signing if `jwt_secret_key` was missing from configuration. This allowed attackers to forge authentication tokens.
**Learning:** Default values for security-critical parameters (like secrets) should never be hardcoded constants in the codebase.
**Prevention:** Enforce mandatory configuration for secrets or generate secure random values at runtime if missing (fail-secure or secure-default).
