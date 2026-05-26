"""probe_R30_W4_data_freshness.py — local probe for the Data Freshness section.

Runs fetch_data_freshness against the real cache/lines/lineups/backups/vault
directories, then renders the section HTML so the operator can eyeball it.
Persists a JSON summary to ``data/cache/probe_R30_W4_results.json``.

LOCAL ONLY — no SSH, no RunPod, no live writes. Read-only against the
existing data dirs.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if os.path.join(_ROOT, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "scripts"))

import operator_dashboard as od  # noqa: E402

PROBE_RESULTS_PATH = os.path.join(
    _ROOT, "data", "cache", "probe_R30_W4_results.json"
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_probe() -> Dict[str, Any]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fresh = od.fetch_data_freshness(today=today)

    # Render the HTML so the result is auditable.
    section_html = od._section_data_freshness(fresh)

    # Smoke-render the full dashboard with the freshness section wired in.
    full_html = ""
    full_html_bytes = 0
    full_render_error = None
    try:
        full_html = od.collect_and_render(
            today=today,
            # Disable the heavy optional sections so the probe stays fast
            # and never depends on optional engine modules.
            include_live_recs=False,
            include_rec_perf=False,
            include_settlement_health=False,
            include_feature_drift=False,
            include_data_freshness=True,
        )
        full_html_bytes = len(full_html)
    except Exception as exc:  # noqa: BLE001
        full_render_error = repr(exc)
        traceback.print_exc()

    sources_summary = [
        {
            "name": s["name"],
            "status": s["status"],
            "exists": s["exists"],
            "age_sec": (round(s["age_sec"], 1)
                        if s["age_sec"] is not None else None),
            "threshold_sec": s["threshold_sec"],
        }
        for s in fresh.get("sources", [])
    ]

    result: Dict[str, Any] = {
        "probe_id": "R30_W4",
        "timestamp_utc": _iso_now(),
        "today": today,
        "n_total": fresh.get("n_total", 0),
        "n_green": fresh.get("n_green", 0),
        "n_yellow": fresh.get("n_yellow", 0),
        "n_red": fresh.get("n_red", 0),
        "sources": sources_summary,
        "section_html_bytes": len(section_html),
        "section_renders": (
            "<h2>Data Freshness</h2>" in section_html
        ),
        "full_html_bytes": full_html_bytes,
        "full_dashboard_includes_freshness": (
            "<h2>Data Freshness</h2>" in full_html
        ),
        "full_render_error": full_render_error,
        "ship": (
            fresh.get("n_total", 0) == 13
            and "<h2>Data Freshness</h2>" in section_html
            and full_render_error is None
        ),
    }
    return result


def main() -> int:
    os.makedirs(os.path.dirname(PROBE_RESULTS_PATH), exist_ok=True)
    try:
        result = _run_probe()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        result = {
            "probe_id": "R30_W4",
            "timestamp_utc": _iso_now(),
            "ship": False,
            "error": repr(exc),
        }
    with open(PROBE_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ship") else 1


if __name__ == "__main__":
    sys.exit(main())
