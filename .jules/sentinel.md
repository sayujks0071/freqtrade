# Sentinel's Journal

## 2025-02-18 - Default JWT Secret Security Gap
**Vulnerability:** The application used a hardcoded default `jwt_secret_key` ("super-secret") if one was not provided in the configuration, leading to a potential security risk where anyone could generate valid tokens if they knew the default.
**Learning:** Relying on default configuration values for security-critical parameters (like secrets) creates a "secure by default" gap. Users often skip configuration steps, leaving them vulnerable.
**Prevention:** Automatically generate strong, random secrets at runtime if the user hasn't provided one. Warn the user that this is happening and that persistence (sessions) will be lost on restart unless they configure a static key.
