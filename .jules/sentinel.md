## 2026-02-19 - [Secure Defaults for JWT Secret]
**Vulnerability:** The API server defaulted to a hardcoded "super-secret" key for JWT generation if `jwt_secret_key` was missing or set to default values in the configuration. This allowed anyone to forge tokens and access the API on default installations.
**Learning:** Hardcoded fallbacks for cryptographic secrets are dangerous because users often stick to defaults.
**Prevention:** Instead of falling back to a known weak key, generate a cryptographically secure random key at runtime using `secrets.token_urlsafe(32)`. This ensures security even if the user misconfigures the application, at the cost of session invalidation on restart (which is a safe fail-state).
