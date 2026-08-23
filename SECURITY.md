# Security Policy

## Reporting a vulnerability

Please report vulnerabilities privately via GitHub security advisories
(Report a vulnerability button on this repo) or email reachsuren@gmail.com.

This server is read-only over public APIs (iTunes podcast endpoints, public
RSS feeds): it accepts no secrets, writes no files outside its own anonymous
telemetry id, and executes no shell commands. Telemetry is opt-out via
`PODCAST_RECOMMENDATIONS_TELEMETRY=false` / `DO_NOT_TRACK=1`.
