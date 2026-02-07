# Sentinel's Journal

## 2026-02-07 - Secure Default Configuration for JWT Keys
**Vulnerability:** The `ApiServer` used a hardcoded default string ("super-secret") as the `jwt_secret_key` when none was provided in the configuration. This allowed attackers to forge valid JWT tokens for any instance running with the default configuration.
**Learning:** Relying on users to override insecure defaults is a critical failure mode. "Secure by default" requires the application to protect itself even when misconfigured by the user.
**Prevention:** Implement checks for default or weak secrets on startup. If detected, automatically generate a cryptographically secure random value (using `secrets.token_hex`) to ensure session security, accepting the trade-off that sessions will not persist across restarts until the user configures a persistent key.
