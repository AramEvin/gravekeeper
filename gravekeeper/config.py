"""Load gravekeeper.yaml and merge it over safe defaults."""

from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

DEFAULTS: dict = {
    "grafana": {
        "url": "http://localhost:3000",
        "token_env": "GRAFANA_TOKEN",
        "verify_tls": True,
        "timeout_seconds": 30,
    },
    "usage": {
        # loki  -> count dashboard views from Grafana's own request logs in Loki
        # none  -> skip the "abandoned" (C01) check
        "source": "none",
        "loki_url": "http://localhost:3100",
        "loki_token_env": "LOKI_TOKEN",
        "loki_tenant": "",
        "selector": '{job="grafana"}',
        # Requests from these users are not counted as views (service accounts,
        # including Gravekeeper itself, log in as "sa-...").
        "exclude_users_regex": "sa-.*",
    },
    "thresholds": {
        "abandoned_days": 90,  # C01: no views in this many days
        "stale_days": 180,  # C02: not edited in this many days
        "min_age_days": 30,  # dashboards younger than this are never "abandoned"
    },
    "weights": {
        "C01": 40,  # abandoned
        "C02": 15,  # stale
        "C03": 25,  # missing datasource
        "C04": 20,  # broken datasource
        "C07": 10,  # legacy panel (per panel, capped)
        "C08": 20,  # duplicate
        "C09": 15,  # ownerless
        "C10": 50,  # empty shell
    },
    "legacy_cap": 30,
    "status_bands": {"healthy": 80, "at_risk": 50, "terminal": 20},
    "grace_days": {"terminal": 30, "deceased": 14},
    "protect_tags": ["keep-alive", "critical"],
    "owner_tag_prefix": "owner:",
    "check_datasource_health": True,
    "output_dir": "out",
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: str | None) -> dict:
    data: dict = {}
    if path:
        p = Path(path)
        if not p.exists():
            raise SystemExit(f"Config file not found: {p}")
        data = yaml.safe_load(p.read_text()) or {}
    cfg = _merge(DEFAULTS, data)
    # Allow quick overrides from the environment.
    if os.environ.get("GRAFANA_URL"):
        cfg["grafana"]["url"] = os.environ["GRAFANA_URL"]
    if os.environ.get("LOKI_URL"):
        cfg["usage"]["loki_url"] = os.environ["LOKI_URL"]
    return cfg
