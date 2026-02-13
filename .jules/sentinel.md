## 2026-02-13 - Insecure Default JWT Secret
**Vulnerability:** The API Server used a hardcoded default secret "super-secret" for JWT signing when `jwt_secret_key` was missing from configuration. This allowed attackers to forge valid tokens if they knew the default.
**Learning:** Hardcoded defaults for security-critical parameters (like secrets) are dangerous. Even if documented as "change this", users often forget.
**Prevention:** Fail secure or auto-generate secure defaults. In this case, we auto-generate a random secret at runtime if missing, which is safe (invalidates sessions on restart) and secure.
