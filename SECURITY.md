# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | ✅ |

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Report them privately through [GitHub Security Advisories](../../security/advisories/new) or by email to **YOUR_CONTACT_EMAIL**. You can expect an answer within 7 days.

## How Gravekeeper handles credentials

- Tokens are read from environment variables (`GRAFANA_TOKEN`, `LOKI_TOKEN`) and never written to disk, logs or reports.
- v0.1 only sends `GET` requests to Grafana. It never changes, archives or deletes anything.
- Use a dedicated service account, and rotate its token if it leaks.
- Generated reports contain dashboard titles, owners and URLs. Treat them as internal documents.
