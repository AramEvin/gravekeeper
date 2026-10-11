"""A tiny fake Grafana API, built from the same dashboards as demo/seed.py.

Lets you run Gravekeeper end-to-end without Docker:
    python tests/mock_grafana.py            # serves on http://localhost:3999
"""

from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "demo"))
import seed  # noqa: E402

FOLDERS = {"platform": "Platform", "billing": "Billing", "sandbox": "Sandbox"}
NOW = datetime.now(timezone.utc)


def _iso(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def build_state() -> dict:
    dashboards = {}
    for uid, title, folder, tags, panels, _ in seed.DASHBOARDS:
        created_by = "admin"
        dashboards[uid] = (title, folder, tags, panels, created_by, False)
    uid, title, folder, tags, panels, _ = seed.EX_EMPLOYEE_DASHBOARD
    dashboards[uid] = (title, folder, tags, panels, "alex.former", False)
    prov = json.loads((ROOT / "demo/grafana/dashboards/prometheus-self.json").read_text())
    dashboards[prov["uid"]] = (prov["title"], "provisioned", prov["tags"], prov["panels"], "admin", True)

    # Ages: most dashboards are old; "Copy of Copy" has not been edited for 400 days.
    ages = {"gk-node-copy2": 400, "gk-untitled": 250}
    state = {}
    for uid, (title, folder, tags, panels, created_by, provisioned) in dashboards.items():
        idle = ages.get(uid, 20)
        state[uid] = {
            "dashboard": {"uid": uid, "title": title, "tags": tags, "panels": panels, "version": 3},
            "meta": {
                "folderTitle": FOLDERS.get(folder, "Provisioned"),
                "folderUid": folder,
                "url": f"/d/{uid}/{title.lower().replace(' ', '-')}",
                "created": _iso(idle + 100),
                "updated": _iso(idle),
                "createdBy": created_by,
                "updatedBy": created_by,
                "provisioned": provisioned,
                "version": 3,
            },
        }
    return state


DATASOURCES = [
    {"uid": "prometheus", "name": "Prometheus", "type": "prometheus"},
    {"uid": "loki", "name": "Loki", "type": "loki"},
    {"uid": "prometheus-old", "name": "Prometheus (old cluster)", "type": "prometheus"},
]


class Handler(BaseHTTPRequestHandler):
    state = build_state()

    def log_message(self, *args):  # keep test output quiet
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if self.headers.get("Authorization") != "Bearer test-token" and path != "/api/health":
            return self._send(401, {"message": "Unauthorized"})
        if path == "/api/health":
            return self._send(200, {"database": "ok", "version": "12.1.1-mock"})
        if path == "/api/search":
            return self._send(
                200, [{"uid": u, "title": d["dashboard"]["title"], "type": "dash-db"} for u, d in self.state.items()]
            )
        if path.startswith("/api/dashboards/uid/"):
            uid = path.rsplit("/", 1)[-1]
            if uid in self.state:
                return self._send(200, self.state[uid])
            return self._send(404, {"message": "Dashboard not found"})
        if path == "/api/datasources":
            return self._send(200, DATASOURCES)
        if path.startswith("/api/datasources/uid/") and path.endswith("/health"):
            uid = path.split("/")[4]
            if uid == "prometheus-old":
                msg = "dial tcp: lookup prometheus-old-cluster: no such host"
                return self._send(400, {"status": "ERROR", "message": msg})
            return self._send(200, {"status": "OK", "message": "Successfully queried the Prometheus API."})
        if path == "/api/org/users":
            return self._send(200, [{"login": "admin"}, {"login": "sa-1-gravekeeper"}])
        return self._send(404, {"message": "not found"})


def start(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


if __name__ == "__main__":
    srv, url = start(3999)
    print(f"Mock Grafana on {url}  (token: test-token). Ctrl+C to stop.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()
