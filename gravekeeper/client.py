"""Thin read-only wrapper around the Grafana HTTP API."""

from __future__ import annotations

import os

import requests

from . import __version__

USER_AGENT = f"gravekeeper/{__version__}"


class GrafanaError(RuntimeError):
    pass


class Grafana:
    def __init__(self, cfg: dict):
        g = cfg["grafana"]
        self.url = g["url"].rstrip("/")
        token = os.environ.get(g.get("token_env", "GRAFANA_TOKEN"), "")
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.session.verify = g.get("verify_tls", True)
        self.timeout = g.get("timeout_seconds", 30)
        self.has_token = bool(token)

    def get(self, path: str, **params):
        try:
            r = self.session.get(self.url + path, params=params or None, timeout=self.timeout)
        except requests.RequestException as e:
            raise GrafanaError(f"Cannot reach Grafana at {self.url}: {e}") from e
        if r.status_code == 401:
            raise GrafanaError("401 Unauthorized: check the service account token (GRAFANA_TOKEN).")
        if r.status_code == 403:
            raise GrafanaError(f"403 Forbidden on {path}: the service account needs a higher role.")
        r.raise_for_status()
        return r.json()

    def try_get(self, path: str, **params):
        """Return (status_code, json_or_None) without raising on HTTP errors."""
        try:
            r = self.session.get(self.url + path, params=params or None, timeout=self.timeout)
        except requests.RequestException:
            return 0, None
        try:
            body = r.json()
        except ValueError:
            body = None
        return r.status_code, body

    # --- convenience calls -------------------------------------------------
    def health(self) -> dict:
        return self.get("/api/health")

    def search_dashboards(self) -> list[dict]:
        results, page = [], 1
        while True:
            batch = self.get("/api/search", type="dash-db", limit=1000, page=page)
            results.extend(batch)
            if len(batch) < 1000:
                return results
            page += 1

    def dashboard(self, uid: str) -> dict:
        return self.get(f"/api/dashboards/uid/{uid}")

    def datasources(self) -> list[dict]:
        return self.get("/api/datasources")

    def datasource_health(self, uid: str) -> tuple[bool, str]:
        code, body = self.try_get(f"/api/datasources/uid/{uid}/health")
        msg = (body or {}).get("message", "") if isinstance(body, dict) else ""
        if code != 200 and "not implemented" in msg.lower():
            return True, "health check not supported by this plugin"
        return code == 200, msg or f"HTTP {code}"

    def org_user_logins(self) -> set[str] | None:
        code, body = self.try_get("/api/org/users")
        if code != 200 or not isinstance(body, list):
            return None
        return {u.get("login", "") for u in body}
