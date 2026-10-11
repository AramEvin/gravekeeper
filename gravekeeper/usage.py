"""Dashboard view counts from Grafana's own request logs stored in Loki.

Grafana must run with router logging on ([server] router_logging = true, or
GF_SERVER_ROUTER_LOGGING=true) and its logs must be shipped to Loki (for
example with Grafana Alloy). Each dashboard view then produces a log line like:

  logger=context userId=1 orgId=1 uname=admin ... msg="Request Completed"
  method=GET path=/api/dashboards/uid/abc123 status=200 ...

Grafana 12 can also load dashboards through the app-platform API
(/apis/dashboard.grafana.app/<ver>/namespaces/<ns>/dashboards/<uid>/dto),
so both paths are counted.
"""

from __future__ import annotations

import os
import time

import requests

from . import __version__

# Loki rejects queries longer than max_query_length (30d by default), so long
# windows are split into chunks of this size and summed.
CHUNK_DAYS = 30

UID_REGEX = (
    r"path=/(?:api/dashboards/uid|apis/dashboard\.grafana\.app/[^/]+/namespaces/[^/]+/dashboards)"
    r"/(?P<uid>[^/ ?\"]+)(?:/dto)?(?:\?\S*)? "
)
# The trailing space matters: sub-resources such as
# /api/dashboards/uid/<uid>/public-dashboards or /versions are loaded on the
# same visit and must not be counted as extra views.


def build_query(selector: str, exclude_users_regex: str, days: int) -> str:
    user_filter = f' | uname!~"{exclude_users_regex}"' if exclude_users_regex else ""
    return (
        "sum by (uid) (count_over_time("
        f'{selector} |~ "path=/apis?/dashboard" | logfmt{user_filter}'
        f' | regexp `{UID_REGEX}` | uid!=""'
        f" [{days}d]))"
    )


class UsageError(RuntimeError):
    """Loki could not be queried; the message is shown to the user as-is."""


def dashboard_views(cfg: dict, days: int, now: float | None = None) -> dict[str, int]:
    u = cfg["usage"]
    base = u["loki_url"].rstrip("/")
    headers = {"User-Agent": f"gravekeeper/{__version__}"}
    token = os.environ.get(u.get("loki_token_env", "LOKI_TOKEN"), "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if u.get("loki_tenant"):
        headers["X-Scope-OrgID"] = u["loki_tenant"]

    now = now or time.time()
    views: dict[str, int] = {}
    remaining, end = days, now
    while remaining > 0:
        chunk = min(CHUNK_DAYS, remaining)
        q = build_query(u["selector"], u.get("exclude_users_regex", ""), chunk)
        try:
            r = requests.get(
                f"{base}/loki/api/v1/query", params={"query": q, "time": int(end * 1e9)}, headers=headers, timeout=60
            )
        except requests.RequestException as e:
            raise UsageError(
                f"Cannot reach Loki at {base} ({e.__class__.__name__}). "
                "Start Loki, fix usage.loki_url, or set usage.source: none to skip view counts."
            ) from e
        if r.status_code != 200:
            raise UsageError(f"Loki query failed ({r.status_code}): {r.text[:300]}")
        for series in r.json().get("data", {}).get("result", []):
            uid = series["metric"].get("uid")
            if uid:
                views[uid] = views.get(uid, 0) + int(float(series["value"][1]))
        remaining -= chunk
        end -= chunk * 86400
    return views


def loki_ready(cfg: dict) -> tuple[bool, str]:
    base = cfg["usage"]["loki_url"].rstrip("/")
    try:
        r = requests.get(f"{base}/ready", timeout=10)
        return r.status_code == 200, r.text.strip()[:80]
    except requests.RequestException as e:
        return False, str(e)
