"""Command line interface.

gravekeeper check   -c gravekeeper.yaml   # test connections and permissions
gravekeeper scan    -c gravekeeper.yaml   # write out/findings.json
gravekeeper report  -c gravekeeper.yaml   # render DOCX from out/findings.json
gravekeeper run     -c gravekeeper.yaml   # scan + report
gravekeeper templates --out my-templates  # copy templates for restyling
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .client import Grafana, GrafanaError
from .config import load_config
from .render import BUILTIN_TEMPLATES, render_certificates, render_estate_report
from .scanner import save, scan
from .usage import UsageError, dashboard_views, loki_ready


def _views(cfg):
    if cfg["usage"]["source"] != "loki":
        return None
    days = cfg["thresholds"]["abandoned_days"]
    print(f"Counting dashboard views in Loki for the last {days} days...")
    views = dashboard_views(cfg, days)
    print(f"Found views for {len(views)} dashboards")
    return views


def cmd_check(cfg) -> int:
    ok = True
    g = Grafana(cfg)
    print(f"Grafana URL : {g.url}")
    print(f"Token       : {'set' if g.has_token else 'MISSING (set ' + cfg['grafana']['token_env'] + ')'}")
    try:
        h = g.health()
        print(f"Grafana     : OK, version {h.get('version')}")
        n = len(g.search_dashboards())
        print(f"Dashboards  : OK, {n} visible")
        ds = g.datasources()
        print(f"Datasources : OK, {len(ds)} visible")
        users = g.org_user_logins()
        print(f"Org users   : {'OK' if users is not None else 'not readable (C09 ownerless check will be skipped)'}")
    except GrafanaError as e:
        print(f"Grafana     : FAILED - {e}")
        ok = False
    if cfg["usage"]["source"] == "loki":
        ready, msg = loki_ready(cfg)
        print(f"Loki        : {'OK' if ready else 'FAILED'} ({cfg['usage']['loki_url']}: {msg})")
        ok = ok and ready
        if ready:
            try:
                views = dashboard_views(cfg, 1)
                print(
                    f"View logs   : {len(views)} dashboards viewed in the last 24h"
                    + ("" if views else "  <- if you expect views, check router_logging and the selector")
                )
            except Exception as e:  # noqa: BLE001
                print(f"View logs   : FAILED - {e}")
                ok = False
    else:
        print("Loki        : disabled (usage.source = none); abandoned check C01 will be skipped")
    print("\nAll checks passed." if ok else "\nSome checks failed.")
    return 0 if ok else 1


def cmd_scan(cfg, out: Path) -> dict:
    g = Grafana(cfg)
    result = scan(cfg, g, _views(cfg))
    out.mkdir(parents=True, exist_ok=True)
    save(result, out / "findings.json")
    statuses = {}
    for d in result["dashboards"]:
        statuses[d["status"]] = statuses.get(d["status"], 0) + 1
    print(
        f"\nScanned {len(result['dashboards'])} dashboards, skipped {len(result['skipped'])}: "
        + ", ".join(f"{k} {v}" for k, v in sorted(statuses.items()))
    )
    for d in result["dashboards"]:
        codes = ",".join(f["code"] for f in d["findings"]) or "-"
        print(f"  {d['score']:>3}  {d['status']:<9} {d['title'][:45]:<45} {codes}")
    print(f"Findings written to {out / 'findings.json'}")
    return result


def cmd_report(cfg, out: Path, result: dict | None, templates: Path | None) -> None:
    if result is None:
        f = out / "findings.json"
        if not f.exists():
            raise SystemExit(f"{f} not found. Run 'gravekeeper scan' first.")
        result = json.loads(f.read_text())
    report = render_estate_report(json.loads(json.dumps(result)), out / "estate-health-report.docx", templates)
    certs = render_certificates(json.loads(json.dumps(result)), out / "certificates", templates)
    print(f"Estate report    : {report}")
    print(f"Death certificates: {len(certs)} in {out / 'certificates'}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="gravekeeper", description="Find dead Grafana dashboards (read-only).")
    ap.add_argument("--version", action="version", version=f"gravekeeper {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "scan", "report", "run"):
        p = sub.add_parser(name)
        p.add_argument("-c", "--config", default="gravekeeper.yaml")
        p.add_argument("-o", "--out", default=None, help="output directory (default: output_dir from config)")
        p.add_argument("--templates", default=None, help="directory with customised .docx templates")
    t = sub.add_parser("templates", help="copy the DOCX templates so you can restyle them in Word")
    t.add_argument("--out", default="templates")
    args = ap.parse_args(argv)

    if args.cmd == "templates":
        dest = Path(args.out)
        dest.mkdir(parents=True, exist_ok=True)
        for f in BUILTIN_TEMPLATES.glob("*.docx"):
            shutil.copy(f, dest / f.name)
            print("copied", dest / f.name)
        return 0

    cfg = load_config(args.config if Path(args.config).exists() or args.config != "gravekeeper.yaml" else None)
    out = Path(args.out or cfg["output_dir"])
    templates = Path(args.templates) if args.templates else None
    try:
        if args.cmd == "check":
            return cmd_check(cfg)
        if args.cmd == "scan":
            cmd_scan(cfg, out)
        elif args.cmd == "report":
            cmd_report(cfg, out, None, templates)
        elif args.cmd == "run":
            cmd_report(cfg, out, cmd_scan(cfg, out), templates)
    except (GrafanaError, UsageError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
