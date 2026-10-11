"""Collect dashboards, run the detectors, and score each dashboard."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone

from . import __version__
from .client import Grafana

CAUSES = {
    "C01": "Abandoned: no views in the usage window",
    "C02": "Stale: not edited for a long time",
    "C03": "Orphaned datasource: panel uses a datasource that no longer exists",
    "C04": "Broken datasource: datasource fails its health check",
    "C07": "Legacy panel: Angular panel type removed in recent Grafana",
    "C08": "Duplicate: same queries as another dashboard",
    "C09": "Ownerless: no owner tag and the creator is no longer in the org",
    "C10": "Empty shell: no data panels",
}

# Angular panels that no longer render in Grafana 11/12, and their replacement.
LEGACY_PANELS = {
    "graph": "timeseries",
    "singlestat": "stat",
    "table-old": "table",
    "grafana-singlestat-panel": "stat",
    "grafana-piechart-panel": "piechart",
    "grafana-worldmap-panel": "geomap",
    "grafana-clock-panel": "text or clock (React version)",
    "natel-discrete-panel": "state-timeline",
    "michaeldmoore-annunciator-panel": "stat",
    "briangann-gauge-panel": "gauge",
    "vonage-status-panel": "stat or polystat",
}

# Datasource references that are not real datasources.
SPECIAL_DS = {
    "-- Grafana --",
    "-- Mixed --",
    "-- Dashboard --",
    "grafana",
    "__expr__",
    "mixed",
    "dashboard",
    "datasource",
}
NON_DATA_PANELS = {"row", "text", "news", "dashlist", "welcome", "gettingstarted"}


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def iter_panels(panels):
    for p in panels or []:
        yield p
        yield from iter_panels(p.get("panels"))  # panels inside collapsed rows


def _ds_refs(panel: dict) -> list:
    refs = [panel.get("datasource")]
    refs += [t.get("datasource") for t in panel.get("targets", []) or []]
    unique, seen = [], set()
    for r in refs:
        key = r.get("uid") if isinstance(r, dict) else r
        if r and key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def _resolve_ds(ref, by_uid: dict, by_name: dict):
    """Return (key, exists). key is None when the ref should be ignored."""
    if isinstance(ref, dict):
        uid = ref.get("uid")
        if not uid or str(uid).startswith("$") or uid in SPECIAL_DS:
            return None, True
        return uid, uid in by_uid
    if isinstance(ref, str):
        if ref.startswith("$") or ref in SPECIAL_DS:
            return None, True
        if ref in by_name:
            return by_name[ref]["uid"], True
        return ref, ref in by_uid
    return None, True


def fingerprint(panels: list[dict]) -> str:
    """Hash of the normalized queries, used to find duplicate dashboards."""
    queries = []
    for p in panels:
        for t in p.get("targets", []) or []:
            q = t.get("expr") or t.get("query") or t.get("rawSql") or t.get("target")
            if q:
                queries.append(re.sub(r"\s+", " ", str(q)).strip())
    if not queries:
        return ""
    return hashlib.sha256("\n".join(sorted(queries)).encode()).hexdigest()[:16]


def status_for(score: int, bands: dict) -> str:
    if score >= bands["healthy"]:
        return "Healthy"
    if score >= bands["at_risk"]:
        return "At Risk"
    if score >= bands["terminal"]:
        return "Terminal"
    return "Deceased"


def scan(cfg: dict, grafana: Grafana, views: dict[str, int] | None, log=print) -> dict:
    now = datetime.now(timezone.utc)
    th = cfg["thresholds"]
    protect = set(cfg["protect_tags"])
    owner_prefix = cfg["owner_tag_prefix"]

    health = grafana.health()
    log(f"Connected to Grafana {health.get('version', '?')} at {grafana.url}")

    # --- datasources -------------------------------------------------------
    datasources = grafana.datasources()
    by_uid = {d["uid"]: d for d in datasources}
    by_name = {d["name"]: d for d in datasources}
    ds_health: dict[str, dict] = {}
    for d in datasources:
        ok, msg = (True, "not checked")
        if cfg.get("check_datasource_health", True):
            ok, msg = grafana.datasource_health(d["uid"])
        ds_health[d["uid"]] = {
            "name": d["name"],
            "type": d["type"],
            "uid": d["uid"],
            "ok": ok,
            "message": msg,
            "panels": 0,
            "dashboards": set(),
        }
    log(f"Found {len(datasources)} datasources ({sum(1 for h in ds_health.values() if not h['ok'])} unhealthy)")

    org_logins = grafana.org_user_logins()
    if org_logins is None:
        log("Note: cannot list org users (needs Admin role); ownerless check (C09) skipped.")

    # --- dashboards ----------------------------------------------------------
    hits = grafana.search_dashboards()
    log(f"Found {len(hits)} dashboards, scanning...")
    dashboards, skipped = [], []
    for hit in hits:
        uid = hit["uid"]
        data = grafana.dashboard(uid)
        dash, meta = data["dashboard"], data["meta"]
        tags = set(dash.get("tags") or [])
        base = {
            "uid": uid,
            "title": dash.get("title", uid),
            "folder": meta.get("folderTitle") or "General",
            "url": grafana.url + (meta.get("url") or f"/d/{uid}"),
            "created": meta.get("created", ""),
            "updated": meta.get("updated", ""),
            "created_by": meta.get("createdBy", ""),
            "updated_by": meta.get("updatedBy", ""),
            "version": dash.get("version", meta.get("version", "")),
            "tags": sorted(tags),
        }
        if meta.get("provisioned"):
            skipped.append({**base, "reason": "Provisioned (managed as code)"})
            continue
        if tags & protect:
            skipped.append({**base, "reason": f"Protected tag: {', '.join(sorted(tags & protect))}"})
            continue

        panels = list(iter_panels(dash.get("panels")))
        data_panels = [p for p in panels if p.get("type") not in NON_DATA_PANELS]
        owner_tags = [t[len(owner_prefix) :] for t in tags if t.startswith(owner_prefix)]
        findings: list[dict] = []
        evidence: list[dict] = []
        legacy: list[dict] = []

        created = _parse_time(meta.get("created"))
        updated = _parse_time(meta.get("updated"))
        age_days = (now - created).days if created else None
        idle_days = (now - updated).days if updated else None
        view_count = None if views is None else views.get(uid, 0)

        # C01 abandoned
        if views is not None and view_count == 0 and (age_days is None or age_days >= th["min_age_days"]):
            findings.append({"code": "C01", "detail": f"0 views in the last {th['abandoned_days']} days"})
        # C02 stale
        if idle_days is not None and idle_days > th["stale_days"]:
            findings.append({"code": "C02", "detail": f"Not edited for {idle_days} days"})

        missing, broken = set(), set()
        for p in panels:
            ptitle = p.get("title") or f"Panel {p.get('id', '?')}"
            for ref in _ds_refs(p):
                key, exists = _resolve_ds(ref, by_uid, by_name)
                if key is None:
                    continue
                if not exists:
                    missing.add(key)
                    evidence.append(
                        {
                            "panel": ptitle,
                            "type": p.get("type", ""),
                            "datasource": key,
                            "result": "Datasource does not exist",
                        }
                    )
                else:
                    h = ds_health[key]
                    h["panels"] += 1
                    h["dashboards"].add(uid)
                    if not h["ok"]:
                        broken.add(h["name"])
                        evidence.append(
                            {
                                "panel": ptitle,
                                "type": p.get("type", ""),
                                "datasource": h["name"],
                                "result": f"Datasource unhealthy: {h['message']}"[:160],
                            }
                        )
            if p.get("type") in LEGACY_PANELS:
                legacy.append({"panel": ptitle, "type": p["type"], "replacement": LEGACY_PANELS[p["type"]]})
                evidence.append(
                    {
                        "panel": ptitle,
                        "type": p["type"],
                        "datasource": "-",
                        "result": f"Legacy panel, migrate to {LEGACY_PANELS[p['type']]}",
                    }
                )

        # C03 / C04 / C07 / C10
        if missing:
            findings.append({"code": "C03", "detail": "Missing datasource(s): " + ", ".join(sorted(missing))})
        if broken:
            findings.append({"code": "C04", "detail": "Unhealthy datasource(s): " + ", ".join(sorted(broken))})
        if legacy:
            findings.append(
                {
                    "code": "C07",
                    "detail": f"{len(legacy)} legacy panel(s): " + ", ".join(sorted({item["type"] for item in legacy})),
                }
            )
        if not data_panels:
            findings.append({"code": "C10", "detail": f"{len(panels)} panel(s), none showing data"})
        # C09 ownerless
        if org_logins is not None and not owner_tags:
            creator = meta.get("createdBy", "")
            if creator not in org_logins:
                findings.append(
                    {
                        "code": "C09",
                        "detail": f"Creator '{creator or 'unknown'}' is not in the org "
                        f"and there is no '{owner_prefix}' tag",
                    }
                )

        dashboards.append(
            {
                **base,
                "owner": owner_tags[0] if owner_tags else (meta.get("createdBy") or "unknown"),
                "panel_count": len(panels),
                "views": view_count,
                "age_days": age_days,
                "idle_days": idle_days,
                "fingerprint": fingerprint(panels),
                "findings": findings,
                "evidence": evidence,
                "legacy": legacy,
            }
        )

    # C08 duplicates: keep the most viewed / most recently edited of each group
    groups = defaultdict(list)
    for d in dashboards:
        if d["fingerprint"]:
            groups[d["fingerprint"]].append(d)
    clusters = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda d: (d["views"] or 0, d["updated"]), reverse=True)
        keeper = members[0]
        clusters.append(
            {
                "id": f"DUP-{len(clusters) + 1}",
                "keep": keeper["title"],
                "keep_uid": keeper["uid"],
                "others": [m["title"] for m in members[1:]],
            }
        )
        for m in members[1:]:
            m["findings"].append(
                {"code": "C08", "detail": f"Same queries as '{keeper['title']}' ({keeper['uid']}), which is kept"}
            )

    # Scoring
    w, bands = cfg["weights"], cfg["status_bands"]
    for d in dashboards:
        penalty = 0
        for f in d["findings"]:
            if f["code"] == "C07":
                penalty += min(w.get("C07", 10) * len(d["legacy"]), cfg["legacy_cap"])
            else:
                penalty += w.get(f["code"], 10)
        d["score"] = max(0, 100 - penalty)
        d["status"] = status_for(d["score"], bands)
        for f in d["findings"]:
            f["name"] = CAUSES[f["code"]]
        d["findings"].sort(key=lambda f: -w.get(f["code"], 10))

    dashboards.sort(key=lambda d: (d["score"], d["title"].lower()))

    for h in ds_health.values():
        h["dashboards"] = len(h["dashboards"])

    return {
        "tool": f"gravekeeper {__version__}",
        "scanned_at": now.isoformat(timespec="seconds"),
        "grafana_url": grafana.url,
        "grafana_version": health.get("version", "unknown"),
        "usage_source": cfg["usage"]["source"] if views is not None else "none",
        "config": {
            k: cfg[k] for k in ("thresholds", "weights", "legacy_cap", "status_bands", "grace_days", "protect_tags")
        },
        "dashboards": dashboards,
        "skipped": skipped,
        "datasources": sorted(ds_health.values(), key=lambda h: (h["ok"], h["name"].lower())),
        "duplicate_clusters": clusters,
    }


def save(result: dict, path) -> None:
    with open(path, "w") as f:
        json.dump(result, f, indent=2, default=str)
