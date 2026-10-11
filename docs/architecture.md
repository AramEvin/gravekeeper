# Architecture

```
            ┌──────────────┐     ┌──────────────────────┐
            │ Grafana API  │     │ Loki                 │
            │ dashboards,  │     │ Grafana's own request│
            │ datasources, │     │ logs → view counts   │
            │ org users    │     └──────────┬───────────┘
            └──────┬───────┘                │
                   ▼                        ▼
              client.py                 usage.py
                   └──────────┬─────────────┘
                              ▼
                         scanner.py      detectors C01–C10, duplicate clusters, scoring
                              │
                              ▼
                     out/findings.json   all raw results (stable JSON, usable in CI)
                              │
                              ▼
                          render.py      docxtpl + Word templates
                              │
              ┌───────────────┴────────────────┐
              ▼                                ▼
  estate-health-report.docx      certificates/death-certificate-*.docx
```

`cli.py` ties it together: `scan` runs the top half, `report` the bottom half, `run` both.

## Design principles

1. **Read-only by default.** v0.1 only sends `GET` requests. Destructive features (archive, delete) will be opt-in, dry-run first, and always archive to Git before anything is removed.
2. **Never trust our own traffic.** Service-account requests are not views.
3. **Templates are documents, not code.** Reports are Word files with Jinja2 tags, so anyone can restyle them in Word (`gravekeeper templates --out my-templates`).
4. **Findings first.** `findings.json` is the contract between scanning and rendering, so other outputs (Slack, Markdown, a Grafana dashboard) can be added without touching the detectors.

## APIs used

| Call | Purpose |
|---|---|
| `GET /api/health` | Version, connectivity |
| `GET /api/search?type=dash-db` | List dashboards (paged) |
| `GET /api/dashboards/uid/<uid>` | Dashboard JSON and metadata |
| `GET /api/datasources` | Datasources |
| `GET /api/datasources/uid/<uid>/health` | Datasource health (C04) |
| `GET /api/org/users` | Current org users (C09) |
| Loki `GET /loki/api/v1/query` | View counts (C01) |
