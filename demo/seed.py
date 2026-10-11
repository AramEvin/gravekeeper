#!/usr/bin/env python3
"""Seed the demo Grafana with healthy and "zombie" dashboards.

Creates:
  * a service account "gravekeeper" (Admin role) and prints its token
  * 12 dashboards via the API, each one built to trigger specific causes
  * a former employee who creates a dashboard and is then deleted (ownerless)
  * a few "views" of the healthy dashboards, so they are not Abandoned

Usage:  python demo/seed.py [--url http://localhost:3000] [--user admin --password admin]
"""

from __future__ import annotations

import argparse
import sys
import time

import requests

PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
PROM_OLD = {"type": "prometheus", "uid": "prometheus-old"}  # provisioned, but unreachable
INFLUX_GONE = {"type": "influxdb", "uid": "influx-legacy"}  # does not exist at all


def ts(title, expr, ds=PROM, ptype="timeseries", pid=1, y=0):
    target = {"refId": "A", "datasource": ds}
    target["expr" if ds.get("type") in ("prometheus", "loki") else "query"] = expr
    return {
        "id": pid,
        "type": ptype,
        "title": title,
        "datasource": ds,
        "targets": [target],
        "gridPos": {"h": 8, "w": 12, "x": 12 * ((pid - 1) % 2), "y": y},
    }


def text(title, content, pid=1):
    return {
        "id": pid,
        "type": "text",
        "title": title,
        "options": {"content": content, "mode": "markdown"},
        "gridPos": {"h": 6, "w": 24, "x": 0, "y": 0},
    }


NODE_PANELS = [
    ts("Targets up", "up", pid=1),
    ts("Scrape duration", "scrape_duration_seconds", pid=2),
    ts("Samples scraped", "scrape_samples_scraped", pid=3, y=8),
]

# (uid, title, folder, tags, panels, visits)
DASHBOARDS = [
    ("gk-node-overview", "Node Overview", "platform", ["owner:platform"], NODE_PANELS, 5),
    (
        "gk-loki-ingest",
        "Loki Log Volume",
        "platform",
        ["owner:platform"],
        [ts("Log lines by job", 'sum by (job) (count_over_time({job=~".+"}[5m]))', ds=LOKI)],
        3,
    ),
    (
        "gk-billing",
        "Team Billing",
        "billing",
        ["owner:billing"],
        [ts("Prometheus HTTP requests", "sum(rate(prometheus_http_requests_total[5m]))")],
        2,
    ),
    ("gk-node-copy", "Copy of Node Overview", "platform", [], NODE_PANELS, 0),
    ("gk-node-copy2", "Copy of Copy of Node Overview (old)", "sandbox", [], NODE_PANELS, 0),
    (
        "gk-legacy",
        "Legacy Server Stats",
        "sandbox",
        ["owner:ops"],
        [
            ts("CPU (old graph)", "rate(process_cpu_seconds_total[5m])", ptype="graph", pid=1),
            ts("Uptime", "time() - process_start_time_seconds", ptype="singlestat", pid=2),
            ts("Targets", "up", ptype="table-old", pid=3, y=8),
        ],
        0,
    ),
    (
        "gk-influx",
        "InfluxDB Metrics (migrated?)",
        "sandbox",
        ["owner:data"],
        [
            ts("Writes per second", 'SELECT mean("writes") FROM "db"', ds=INFLUX_GONE, pid=1),
            ts("Shards", 'SELECT count("shard") FROM "db"', ds=INFLUX_GONE, pid=2),
        ],
        0,
    ),
    (
        "gk-prom-old",
        "Old Prometheus Cluster",
        "platform",
        ["owner:platform"],
        [ts("Old cluster up", "up", ds=PROM_OLD, pid=1)],
        0,
    ),
    (
        "gk-empty-shell",
        "TODO: Team Dashboard",
        "sandbox",
        [],
        [text("Coming soon", "We will add panels here later.")],
        0,
    ),
    ("gk-untitled", "Untitled Experiment", "sandbox", [], [], 0),
    ("gk-payments", "Critical: Payments", "billing", ["critical"], [ts("Payments (legacy)", "up", ptype="graph")], 0),
]
EX_EMPLOYEE_DASHBOARD = (
    "gk-ex-employee",
    "Alex's Debug Dashboard",
    "sandbox",
    [],
    [ts("Debug", "up", ptype="graph"), ts("More debug", "go_goroutines", pid=2)],
    0,
)
FOLDERS = {"platform": "Platform", "billing": "Billing", "sandbox": "Sandbox"}


def dashboard_body(uid, title, panels, tags):
    return {
        "uid": uid,
        "title": title,
        "tags": tags,
        "panels": panels,
        "schemaVersion": 39,
        "time": {"from": "now-6h", "to": "now"},
    }


class Api:
    def __init__(self, url, auth):
        self.url, self.s = url.rstrip("/"), requests.Session()
        self.s.auth = auth

    def call(self, method, path, ok=(200,), **kw):
        r = self.s.request(method, self.url + path, timeout=30, **kw)
        if r.status_code not in ok:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:200]}")
        return r.json() if r.text else {}


def wait_for(url):
    for _ in range(60):
        try:
            if requests.get(url + "/api/health", timeout=3).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    sys.exit(f"Grafana not reachable at {url}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:3000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin")
    a = ap.parse_args()
    wait_for(a.url)
    api = Api(a.url, (a.user, a.password))

    for uid, title in FOLDERS.items():
        api.call("POST", "/api/folders", ok=(200, 409, 412), json={"uid": uid, "title": title})

    def put(api_, d):
        uid, title, folder, tags, panels, _ = d
        api_.call(
            "POST",
            "/api/dashboards/db",
            json={"dashboard": dashboard_body(uid, title, panels, tags), "folderUid": folder, "overwrite": True},
        )

    for d in DASHBOARDS:
        put(api, d)
        print(f"  dashboard  {d[1]}")

    # Former employee: creates a dashboard, then leaves the company.
    login = "alex.former"
    r = api.s.get(a.url + f"/api/users/lookup?loginOrEmail={login}", timeout=10)
    if r.status_code == 200:
        api.call("DELETE", f"/api/admin/users/{r.json()['id']}")
    user = api.call(
        "POST",
        "/api/admin/users",
        json={"name": "Alex Former", "login": login, "email": "alex@example.com", "password": "demo-password-123"},
    )
    api.call("PATCH", f"/api/org/users/{user['id']}", json={"role": "Editor"})
    put(Api(a.url, (login, "demo-password-123")), EX_EMPLOYEE_DASHBOARD)
    api.call("DELETE", f"/api/admin/users/{user['id']}")
    print(f"  dashboard  {EX_EMPLOYEE_DASHBOARD[1]}  (creator deleted)")

    # Simulate people opening the healthy dashboards.
    for uid, _title, *_, visits in DASHBOARDS:
        for _ in range(visits):
            api.call("GET", f"/api/dashboards/uid/{uid}")

    # Service account for Gravekeeper.
    found = api.call("GET", "/api/serviceaccounts/search?query=gravekeeper")
    sa = next((s for s in found.get("serviceAccounts", []) if s["name"] == "gravekeeper"), None)
    if not sa:
        sa = api.call("POST", "/api/serviceaccounts", ok=(200, 201), json={"name": "gravekeeper", "role": "Admin"})
    token = api.call(
        "POST",
        f"/api/serviceaccounts/{sa['id']}/tokens",
        ok=(200, 201),
        json={"name": f"gravekeeper-{int(time.time())}"},
    )["key"]
    print("\nDemo seeded. Service account token for Gravekeeper:\n")
    print(f"  export GRAFANA_TOKEN={token}\n")


if __name__ == "__main__":
    main()
