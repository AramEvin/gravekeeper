# How dashboard views are counted

Grafana OSS has no API for "how often was this dashboard opened". Gravekeeper gets the answer from Grafana's **own request logs**, stored in Loki. In other words, it uses the LGTM stack to observe Grafana itself.

## 1. Turn on request logging

```ini
# grafana.ini
[server]
router_logging = true
```

or `GF_SERVER_ROUTER_LOGGING=true`. Every HTTP request then produces a line like this (real output from Grafana 12.1.1):

```
logger=context userId=1 orgId=1 uname=admin t=2026-10-11T14:35:00Z level=info msg="Request Completed"
method=GET path=/api/dashboards/uid/gk-legacy status=200 remote_addr=172.18.0.1 time_ms=5 ...
```

## 2. Ship the logs to Loki

Any agent works. The demo uses Grafana Alloy (`demo/config.alloy`):

```alloy
local.file_match "grafana" {
  path_targets = [{"__path__" = "/var/log/grafana/*.log", "job" = "grafana"}]
}
loki.source.file "grafana" {
  targets    = local.file_match.grafana.targets
  forward_to = [loki.write.local.receiver]
}
```

## 3. What counts as a view

When someone opens a dashboard in the browser, Grafana 12.1 logs these requests:

```
GET /d/gk-legacy                                   page load (only on full reload)
GET /api/dashboards/uid/gk-legacy                  ← the dashboard itself: counted
GET /api/folders/sandbox
GET /api/dashboards/uid/gk-legacy/public-dashboards   sub-resource: NOT counted
GET /api/annotations
POST /api/ds/query                                 panel data
```

Gravekeeper counts exactly one line per visit: `GET /api/dashboards/uid/<uid>`, or the app-platform equivalent `/apis/dashboard.grafana.app/<version>/namespaces/<ns>/dashboards/<uid>/dto`. Sub-resources such as `/public-dashboards` or `/versions` are ignored.

Requests from **service accounts** (`uname=sa-...`), including Gravekeeper's own scans, are excluded with `usage.exclude_users_regex`. Otherwise every scan would keep every dashboard "alive".

## 4. The query

```logql
sum by (uid) (count_over_time(
  {job="grafana"} |~ "path=/apis?/dashboard" | logfmt | uname!~"sa-.*"
  | regexp `path=/(?:api/dashboards/uid|apis/dashboard\.grafana\.app/[^/]+/namespaces/[^/]+/dashboards)/(?P<uid>[^/ ?"]+)(?:/dto)?(?:\?\S*)? `
  | uid!="" [30d]))
```

Print the exact query for your config with:

```bash
python -c "from gravekeeper.usage import build_query; print(build_query('{job=\"grafana\"}', 'sa-.*', 30))"
```

Paste it into Grafana → Explore → Loki, set **Type: Instant**, and use the **Table** view to see views per dashboard.

Long windows are split into 30-day chunks, because Loki's default `max_query_length` is 30 days. With many dashboards, raise Loki's `limits_config.max_query_series` (default 500).

## Tips

- Collect a few weeks of logs before trusting C01. Until then, keep `usage.source: none`.
- On Grafana Enterprise / Cloud, usage insights are another source. Support is on the roadmap.
