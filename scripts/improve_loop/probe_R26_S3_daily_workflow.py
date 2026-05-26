"""probe_R26_S3_daily_workflow.py — end-to-end probe for the daily orchestrator.

Procedure
---------
1. Run ``daily_workflow --dry-run evening`` AND ``--dry-run morning``
   into a tmp dir. Assert each subcommand returns 0 critical failures.
2. Run a REAL evening stage (still scoped to a tmp dir) with a fake
   ``live_recommendation_engine.run_engine`` injection so the snapshot
   file is produced without touching the real predictions cache.
3. Verify the snapshot file exists + has the expected schema.
4. Verify the dashboard cache HTML was written.
5. Persist the probe summary to ``data/cache/probe_R26_S3_results.json``.

LOCAL ONLY — no SSH, no RunPod, no real-money side effect.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts import daily_workflow as dw  # noqa: E402

PROBE_RESULTS_PATH = os.path.join(
    _ROOT, "data", "cache", "probe_R26_S3_results.json"
)

# Synthetic future date that never collides with any real cached snapshot.
DATE = "2099-01-15"
YEST = "2099-01-14"


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fake_run_engine(*, bankroll, top, date, min_edge):
    """Stub the live recommendation engine so the probe never depends on
    a present predictions parquet."""
    return {
        "date": date, "bankroll": bankroll, "top": top, "min_edge": min_edge,
        "engine_version": "probe_R26_S3", "reason": "probe synthetic",
        "n_recs": 2,
        "recommendations": [
            {"player": "Probe Alpha", "stat": "pts", "line": 22.5,
             "side": "OVER", "book": "bov", "odds": -110,
             "edge": 0.08, "stake_dollars": 30.0},
            {"player": "Probe Beta", "stat": "reb", "line": 5.5,
             "side": "UNDER", "book": "fd", "odds": -105,
             "edge": 0.06, "stake_dollars": 22.0},
        ],
    }


def _stub_dashboard(**_kw) -> str:
    return "<!DOCTYPE html><html><body>PROBE STUB DASHBOARD</body></html>"


def _stub_alert(message, level="info", tag=None, source=None,
                  fields=None, **_):
    return {"discord_sent": False, "file_written": True,
            "vault_appended": True, "stubbed": True}


def _run_probe() -> Dict[str, Any]:
    """Drive the orchestrator through every code path the cron job will hit."""
    tmp = Path(tempfile.mkdtemp(prefix="R26_S3_probe_"))
    snap_dir = tmp / "snap"
    cache    = tmp / "operator_dashboard.html"
    log_path = tmp / "log.md"
    settled  = tmp / "rec_settled.parquet"
    qb_dir   = tmp / "qb"

    # Inject the fake engine so the snapshot is built deterministically.
    from scripts import live_recommendation_engine as lre  # noqa: PLC0415
    prev_engine = getattr(lre, "run_engine", None)
    lre.run_engine = _fake_run_engine  # type: ignore[assignment]

    out: Dict[str, Any] = {
        "probe":         "R26_S3",
        "started_at":    _iso_now(),
        "tmp":           str(tmp),
    }
    try:
        # ---- (1) Evening dry-run ----
        ev_dry = dw.run_evening(
            snapshot_dir=snap_dir, dashboard_cache=cache,
            log_path=log_path, dry_run=True, today=DATE,
            alert_fn=_stub_alert, collect_fn=_stub_dashboard,
        )
        out["evening_dryrun"] = {
            "n_critical_failures": ev_dry["n_critical_failures"],
            "steps":              [s["name"] for s in ev_dry["steps"]],
            "dry_run":            ev_dry["dry_run"],
        }
        out["evening_dryrun_ok"] = (
            ev_dry["n_critical_failures"] == 0
            and ev_dry["dry_run"] is True
            and not cache.exists()      # confirm zero side effects
            and not log_path.exists()
        )

        # ---- (2) Morning dry-run ----
        mo_dry = dw.run_morning(
            snapshot_dir=snap_dir, settled_path=settled, qb_dir=qb_dir,
            dashboard_cache=cache, log_path=log_path,
            reconcile_days=1, report_days=1,
            dry_run=True, yesterday=YEST,
            alert_fn=_stub_alert, collect_fn=_stub_dashboard,
        )
        out["morning_dryrun"] = {
            "n_critical_failures": mo_dry["n_critical_failures"],
            "steps":              [s["name"] for s in mo_dry["steps"]],
            "dry_run":            mo_dry["dry_run"],
        }
        out["morning_dryrun_ok"] = (
            mo_dry["n_critical_failures"] == 0
            and mo_dry["dry_run"] is True
        )

        # ---- (3) REAL evening (still tmp-scoped) ----
        ev_real = dw.run_evening(
            snapshot_dir=snap_dir, dashboard_cache=cache,
            log_path=log_path, dry_run=False, today=DATE,
            alert_fn=_stub_alert, collect_fn=_stub_dashboard,
        )
        snap_files = list(snap_dir.glob("rec_snapshot_*.json"))
        snap_payload: Dict[str, Any] = {}
        if snap_files:
            try:
                snap_payload = json.loads(snap_files[0].read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                snap_payload = {}
        out["evening_real"] = {
            "n_critical_failures": ev_real["n_critical_failures"],
            "snapshot_files":     [str(p) for p in snap_files],
            "snapshot_n_recs":    snap_payload.get("n_recs"),
            "snapshot_date":      snap_payload.get("date"),
            "cache_exists":       cache.exists(),
            "log_exists":         log_path.exists(),
        }
        out["evening_real_ok"] = bool(
            ev_real["n_critical_failures"] == 0
            and len(snap_files) == 1
            and snap_payload.get("date") == DATE
            and snap_payload.get("n_recs") == 2
            and cache.exists()
            and log_path.exists()
        )

        # ---- (4) Summary parses what we wrote ----
        s = dw.summary(log_path=log_path, days=7)
        out["summary_n_total"]     = s["n_total"]
        out["summary_n_in_window"] = s["n_in_window"]
        out["summary_ok"]          = bool(s["n_total"] >= 1)

    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        out["error"] = repr(exc)
    finally:
        # Always restore the real engine.
        if prev_engine is not None:
            lre.run_engine = prev_engine  # type: ignore[assignment]

    out["ended_at"] = _iso_now()
    out["ship_ok"] = bool(
        out.get("evening_dryrun_ok")
        and out.get("morning_dryrun_ok")
        and out.get("evening_real_ok")
        and out.get("summary_ok")
    )
    return out


def main() -> int:
    os.makedirs(os.path.dirname(PROBE_RESULTS_PATH), exist_ok=True)
    try:
        result = _run_probe()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        result = {
            "probe":     "R26_S3",
            "timestamp": _iso_now(),
            "ship_ok":   False,
            "error":     repr(exc),
        }
    with open(PROBE_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ship_ok") else 1


if __name__ == "__main__":
    sys.exit(main())
