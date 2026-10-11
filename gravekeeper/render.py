"""Render the scan result into DOCX files using docxtpl templates."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from docxtpl import DocxTemplate

from .scanner import CAUSES

BUILTIN_TEMPLATES = Path(__file__).parent / "templates"
STATUS_COLORS = {"Healthy": "BBF7D0", "At Risk": "FEF08A", "Terminal": "FED7AA", "Deceased": "FECACA"}


def _short(ts: str) -> str:
    return (ts or "")[:10] or "unknown"


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()[:50] or "dashboard"


def _template(templates_dir: Path | None, name: str) -> DocxTemplate:
    for base in (templates_dir, BUILTIN_TEMPLATES):
        if base and (base / name).exists():
            return DocxTemplate(str(base / name))
    raise FileNotFoundError(f"Template {name} not found. Run: python -m gravekeeper.build_templates")


def _decorate(result: dict) -> dict:
    for d in result["dashboards"]:
        d["color"] = STATUS_COLORS[d["status"]]
        d["codes"] = ", ".join(f["code"] for f in d["findings"]) or "—"
        d["views_text"] = "n/a" if d["views"] is None else str(d["views"])
        d["created_short"] = _short(d["created"])
        d["updated_short"] = _short(d["updated"])
    for s in result["datasources"]:
        s["state"] = "OK" if s["ok"] else f"FAILING: {s['message']}"[:70]
        s["color"] = "BBF7D0" if s["ok"] else "FECACA"
    return result


def _common(result: dict) -> dict:
    return {
        "tool": result["tool"],
        "scanned_at": result["scanned_at"],
        "scanned_date": result["scanned_at"][:10],
        "grafana_url": result["grafana_url"],
        "grafana_version": result["grafana_version"],
        "usage_source": result["usage_source"],
        "config": result["config"],
    }


def render_estate_report(result: dict, out: Path, templates_dir: Path | None = None) -> Path:
    result = _decorate(result)
    dashboards = result["dashboards"]
    counts = {"healthy": 0, "at_risk": 0, "terminal": 0, "deceased": 0}
    for d in dashboards:
        counts[d["status"].lower().replace(" ", "_")] += 1
    weights = result["config"]["weights"]
    causes = []
    for code, name in CAUSES.items():
        n = sum(1 for d in dashboards if any(f["code"] == code for f in d["findings"]))
        causes.append({"code": code, "name": name, "count": n, "weight": weights.get(code, "-")})
    legacy = [{"dashboard": d["title"], **item} for d in dashboards for item in d["legacy"]]
    total = len(dashboards)
    cleanup = counts["terminal"] + counts["deceased"]
    ctx = {
        **_common(result),
        "dashboards": dashboards,
        "datasources": result["datasources"],
        "duplicate_clusters": result["duplicate_clusters"],
        "skipped": result["skipped"],
        "counts": counts,
        "causes": causes,
        "legacy": legacy,
        "total": total + len(result["skipped"]),
        "cleanup": cleanup,
        "cleanup_pct": round(100 * cleanup / total) if total else 0,
    }
    tpl = _template(templates_dir, "estate-report.docx")
    tpl.render(ctx, autoescape=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    tpl.save(str(out))
    return out


def render_certificates(result: dict, out_dir: Path, templates_dir: Path | None = None) -> list[Path]:
    result = _decorate(result)
    out_dir.mkdir(parents=True, exist_ok=True)
    scanned = datetime.fromisoformat(result["scanned_at"])
    paths = []
    for d in result["dashboards"]:
        if d["status"] not in ("Terminal", "Deceased") or not d["findings"]:
            continue
        grace = result["config"]["grace_days"]["deceased" if d["status"] == "Deceased" else "terminal"]
        ctx = {
            **_common(result),
            "d": d,
            "primary": d["findings"][0],
            "contributing": d["findings"][1:],
            "grace_days": grace,
            "burial_date": (scanned + timedelta(days=grace)).strftime("%Y-%m-%d"),
        }
        tpl = _template(templates_dir, "death-certificate.docx")
        tpl.render(ctx, autoescape=True)
        path = out_dir / f"death-certificate-{_slug(d['title'])}-{d['uid']}.docx"
        tpl.save(str(path))
        paths.append(path)
    return paths
