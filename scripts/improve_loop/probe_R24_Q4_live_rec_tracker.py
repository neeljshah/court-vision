"""probe_R24_Q4_live_rec_tracker.py - viability probe for R24_Q4.

Demonstrates the live-rec-tracker end-to-end on disposable test data:

  * --snapshot mode: writes today's snapshot to a TEMP dir (never touches the
    real data/cache/rec_tracker dir).
  * --settle mode: simulates a settle on a synthetic 5-rec snapshot using a
    synthetic boxscore (covers WIN/LOSS/PUSH/UNDER/missing-player paths).
  * --report mode: aggregates the synthetic settled parquet and emits a
    summary.

Persists the combined result to:
    data/cache/probe_R24_Q4_results.json

SHIP gate
---------
  - snapshot call returns a path that exists and parses as JSON
  - settle yields the expected mix of WIN/LOSS/PUSH for synthetic recs
  - report aggregates returns ok=True with non-zero n
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts import live_rec_tracker as lrt  # noqa: E402

_RESULTS_PATH = os.path.join(PROJECT_DIR, "data", "cache", "probe_R24_Q4_results.json")


def _mk_rec(player: str, stat: str, line: float, side: str,
            edge: float = 0.07, odds: int = -110,
            stake_dollars: float = 25.0, book: str = "bov") -> Dict[str, Any]:
    return {
        "player": player, "stat": stat, "line": line, "side": side,
        "book": book, "odds": odds, "edge": edge,
        "stake_dollars": stake_dollars,
    }


def _synth_recs() -> List[Dict[str, Any]]:
    return [
        _mk_rec("Alpha One",   "pts", 18.5, "OVER",  edge=0.10),
        _mk_rec("Bravo Two",   "pts", 18.5, "OVER",  edge=0.04),
        _mk_rec("Charlie",     "pts", 18.5, "OVER",  edge=0.07),  # PUSH (actual=18.5)
        _mk_rec("Delta Four",  "reb",  8.5, "UNDER", edge=0.12),
        _mk_rec("Echo Five",   "reb",  8.5, "UNDER", edge=0.06),
        _mk_rec("Foxtrot Mid", "ast",  5.5, "OVER",  edge=0.09),  # missing player
    ]


def _synth_box() -> Dict[str, Dict[str, float]]:
    return {
        "Alpha One":  {"pts": 25.0},  # OVER 18.5 -> WIN
        "Bravo Two":  {"pts": 12.0},  # OVER 18.5 -> LOSS
        "Charlie":    {"pts": 18.5},  # OVER 18.5 -> PUSH
        "Delta Four": {"reb":  6.0},  # UNDER 8.5 -> WIN
        "Echo Five":  {"reb": 11.0},  # UNDER 8.5 -> LOSS
        # Foxtrot Mid intentionally absent
    }


def _loader_for(box: Dict[str, Dict[str, float]]):
    def _l(date_str: str, qb_dir: str) -> Dict[str, Dict[str, float]]:
        return {lrt._player_key(k): v for k, v in box.items()}
    return _l


def run_probe() -> Dict[str, Any]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    synthetic_date = "2099-01-15"

    # Sandbox dir for snapshot + settled parquet — NEVER touch the real one.
    sandbox = tempfile.mkdtemp(prefix="probe_R24_Q4_")
    snap_dir = os.path.join(sandbox, "rec_tracker")
    os.makedirs(snap_dir, exist_ok=True)
    settled_path = os.path.join(snap_dir, "rec_settled.parquet")

    result: Dict[str, Any] = {
        "probe":          "R24_Q4",
        "ran_at":         datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sandbox":        sandbox,
        "today":          today,
        "synthetic_date": synthetic_date,
    }
    gate_reasons: List[str] = []

    # ---------------------------------------------------------------- snapshot
    try:
        snap = lrt.run_snapshot(
            bankroll=1000.0, top=10, date_str=today,
            snapshot_dir=snap_dir, min_edge=0.05,
        )
        path_exists = os.path.exists(snap.get("path", ""))
        result["snapshot"] = {
            "ok":          True,
            "path":        snap.get("path"),
            "exists":      path_exists,
            "n_recs":      snap.get("n_recs"),
            "reason":      snap.get("reason", ""),
        }
        if not path_exists:
            gate_reasons.append("snapshot file did not exist after write")
        else:
            # parse JSON to validate it
            with open(snap["path"], "r", encoding="utf-8") as fh:
                parsed = json.load(fh)
            if "recommendations" not in parsed:
                gate_reasons.append("snapshot file missing 'recommendations'")
    except Exception as exc:  # noqa: BLE001
        result["snapshot"] = {"ok": False, "reason": f"snapshot raised: {exc}"}
        gate_reasons.append(f"snapshot raised: {exc}")

    # ----------------------------------------------------------------- settle
    try:
        # Write a synthetic snapshot for the synthetic date and settle it.
        payload = {
            "recommendations": _synth_recs(),
            "date":            synthetic_date,
            "bankroll":        1000.0,
            "top":             10,
            "min_edge":        0.05,
            "engine_version":  "R23_P8",
            "reason":          "probe synthetic payload",
        }
        lrt.snapshot(payload, snapshot_dir=snap_dir, date_str=synthetic_date)
        out = lrt.settle(
            date_str=synthetic_date, snapshot_dir=snap_dir,
            settled_path=settled_path, boxscore_loader=_loader_for(_synth_box()),
        )
        # Idempotency check: run settle again and ensure no new rows.
        out2 = lrt.settle(
            date_str=synthetic_date, snapshot_dir=snap_dir,
            settled_path=settled_path, boxscore_loader=_loader_for(_synth_box()),
        )
        result["settle"] = {
            "ok":            out.get("ok", False),
            "n_settled":     out.get("n_settled"),
            "wins":          out.get("wins"),
            "losses":        out.get("losses"),
            "pushes":        out.get("pushes"),
            "ungraded":      out.get("ungraded"),
            "missing_player": out.get("n_missing_player"),
            "n_settled_2nd_pass": out2.get("n_settled"),
            "n_skipped_2nd_pass": out2.get("n_skipped"),
        }
        if out.get("wins")   != 2: gate_reasons.append(f"expected 2 wins, got {out.get('wins')}")
        if out.get("losses") != 2: gate_reasons.append(f"expected 2 losses, got {out.get('losses')}")
        if out.get("pushes") != 1: gate_reasons.append(f"expected 1 push, got {out.get('pushes')}")
        if out.get("n_missing_player") != 1:
            gate_reasons.append(f"expected 1 missing player, got {out.get('n_missing_player')}")
        if out2.get("n_settled") != 0:
            gate_reasons.append(f"idempotency failed: second pass added {out2.get('n_settled')}")
    except Exception as exc:  # noqa: BLE001
        result["settle"] = {"ok": False, "reason": f"settle raised: {exc}"}
        gate_reasons.append(f"settle raised: {exc}")

    # ----------------------------------------------------------------- report
    try:
        rpt = lrt.report(settled_path=settled_path, days="all")
        result["report"] = {
            "ok":            rpt.get("ok", False),
            "n":             rpt.get("n"),
            "n_graded":      rpt.get("n_graded"),
            "wins":          rpt.get("wins"),
            "losses":        rpt.get("losses"),
            "pushes":        rpt.get("pushes"),
            "win_rate":      rpt.get("win_rate"),
            "roi":           rpt.get("roi"),
            "mean_edge_win": rpt.get("mean_edge_win"),
            "mean_edge_loss": rpt.get("mean_edge_loss"),
            "by_stat":       rpt.get("by_stat"),
        }
        if not rpt.get("ok"):
            gate_reasons.append(f"report not ok: {rpt.get('reason')}")
        elif rpt.get("n", 0) == 0:
            gate_reasons.append("report returned n=0")
    except Exception as exc:  # noqa: BLE001
        result["report"] = {"ok": False, "reason": f"report raised: {exc}"}
        gate_reasons.append(f"report raised: {exc}")

    result["ship"] = len(gate_reasons) == 0
    result["ship_blockers"] = gate_reasons
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    result = run_probe()
    os.makedirs(os.path.dirname(_RESULTS_PATH), exist_ok=True)
    with open(_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["ship"] else 1


if __name__ == "__main__":
    sys.exit(main())
