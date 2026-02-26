# Sentinel Journal

## 2026-02-27 - [Default JWT Secret and Buggy Warning Check]
**Vulnerability:** The API server allowed using default JWT secrets ("super-secret") and contained a buggy check `if key in ("super-secret, somethingrandom")` which only matched if the key was literally that string.
**Learning:** Security checks must be robust and tested. Default configurations should be secure by default where possible.
**Prevention:** Always use `secrets` module for cryptographic keys. Validate configuration logic with tests.
