# Causes of death

Every dashboard starts with a score of **100**. Each cause found subtracts its weight. Weights can be changed in `gravekeeper.yaml`.

| Code | Name | Default weight | How it is detected |
|---|---|---|---|
| C01 | Abandoned | 40 | Zero views in `thresholds.abandoned_days`, counted from Grafana's request logs in Loki. Needs `usage.source: loki`. Dashboards younger than `thresholds.min_age_days` are never abandoned. |
| C02 | Stale | 15 | `meta.updated` is older than `thresholds.stale_days`. |
| C03 | Orphaned datasource | 25 | A panel or query references a datasource UID or name that does not exist. Template variables (`$ds`) and built-in sources (`-- Grafana --`, `-- Mixed --`, `-- Dashboard --`, expressions) are ignored. |
| C04 | Broken datasource | 20 | The datasource exists but `GET /api/datasources/uid/<uid>/health` fails. Plugins without a health check are not flagged. |
| C05 | Erroring panels | — | *Planned for v0.2*: replay panel queries through `/api/ds/query`. |
| C06 | Empty panels | — | *Planned for v0.2*. |
| C07 | Legacy panel | 10 per panel, max 30 (`legacy_cap`) | Panel types built on AngularJS, which Grafana 11/12 no longer supports: `graph`, `singlestat`, `table-old`, `grafana-piechart-panel`, `grafana-worldmap-panel`, and others. Each finding names the replacement. |
| C08 | Duplicate | 20 | Same set of normalized queries as another dashboard. The most viewed (then most recently edited) copy is kept; the others are flagged. |
| C09 | Ownerless | 15 | No `owner:` tag, and `meta.createdBy` is not a current org user. Needs a token that can read `/api/org/users`. |
| C10 | Empty shell | 50 | No panels that show data (only rows, text or list panels, or no panels at all). |

## Status bands

| Score | Status | Death Certificate? |
|---|---|---|
| 80–100 | Healthy | No |
| 50–79 | At Risk | No, listed in the report only |
| 20–49 | Terminal | Yes, `grace_days.terminal` (30) |
| 0–19 | Deceased | Yes, `grace_days.deceased` (14) |

## Never flagged

- **Provisioned** dashboards (`meta.provisioned: true`): they are managed as code, so fix them in your repo.
- Dashboards tagged with any of `protect_tags` (default `keep-alive`, `critical`).

## Example

`Alex's Debug Dashboard`: never opened (C01 −40), creator deleted and no owner tag (C09 −15), one `graph` panel (C07 −10).
Score: 100 − 40 − 15 − 10 = **35, Terminal**.
