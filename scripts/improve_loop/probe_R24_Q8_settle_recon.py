"""probe_R24_Q8_settle_recon.py — viability probe for R24_Q8.

Runs scripts/reconcile_settlements.reconcile() against the REAL ledger
(``data/pnl_ledger.csv``) over the last N days (default 7) and dumps a
small headline payload to ``data/cache/probe_R24_Q8_results.json``.

Read-only on the ledger; never writes to it.

SHIP gate
---------
  * reconcile() completes without raising
  * payload includes the four headline counts
  * if 100% of in-window settled bets are synthetic, ship anyway with the
    `all_synthetic` flag set (the harness handles offseason / data-light
    weeks).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.reconcile_settlements import (  # noqa: E402
    reconcile,
    DEFAULT_LEDGER,
    DEFAULT_OUT_DIR,
)
from scripts.auto_settle_daemon import DEFAULT_QB_DIR  # noqa: E402

RESULTS_PATH = PROJECT_DIR / "data" / "cache" / "probe_R24_Q8_results.json"


def run_probe(days: int = 7,
              ledger_path: Path = DEFAULT_LEDGER,
              qb_dir: Path = DEFAULT_QB_DIR,
              ) -> Dict[str, Any]:
    ledger_path = Path(ledger_path)
    qb_dir = Path(qb_dir)

    gate_reasons = []
    try:
        report = reconcile(days=days, ledger_path=ledger_path,
                            qb_dir=qb_dir, include_synthetic=False)
    except Exception as exc:  # noqa: BLE001
        return {
            "probe": "R24_Q8",
            "ran_at": _dt.datetime.utcnow().isoformat(timespec="seconds"),
            "ship": False,
            "ship_blockers": [f"reconcile() raised: {exc}"],
            "error": str(exc),
        }

    for k in ("n_real_settled", "n_verified", "n_matched", "n_mismatched"):
        if k not in report:
            gate_reasons.append(f"missing key {k} in report")

    if report.get("n_total_settled", 0) == 0:
        # No ledger / empty ledger — ship anyway with a note. This is the
        # local-worktree case where data/pnl_ledger.csv is absent.
        note = "ledger empty / missing — nothing to reconcile"
    elif report.get("all_synthetic"):
        note = ("all in-window settled bets are synthetic — shipping anyway "
                "with empty mismatches per spec")
    else:
        note = ""

    # Compute match-rate over verified bets (boxscore-missing excluded).
    n_verified = int(report.get("n_verified", 0) or 0)
    n_matched  = int(report.get("n_matched", 0) or 0)
    match_rate = (n_matched / n_verified) if n_verified > 0 else None

    result = {
        "probe":            "R24_Q8",
        "ran_at":           _dt.datetime.utcnow().isoformat(timespec="seconds"),
        "window_days":      int(days),
        "ledger_path":      str(ledger_path),
        "qb_dir":           str(qb_dir),
        "n_total_settled":  report.get("n_total_settled", 0),
        "n_in_window":      report.get("n_in_window", 0),
        "n_real_settled":   report.get("n_real_settled", 0),
        "n_verified":       n_verified,
        "n_unverified":     report.get("n_real_settled", 0) - n_verified,
        "n_matched":        n_matched,
        "n_mismatched":     report.get("n_mismatched", 0),
        "match_rate":       match_rate,
        "mismatch_categories": report.get("mismatch_categories", {}),
        "sample_mismatches": (report.get("mismatches") or [])[:5],
        "all_synthetic":    bool(report.get("all_synthetic", False)),
        "note":             note,
        "ship":             len(gate_reasons) == 0,
        "ship_blockers":    gate_reasons,
    }
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--ledger", type=str, default=str(DEFAULT_LEDGER))
    ap.add_argument("--qb-dir", type=str, default=str(DEFAULT_QB_DIR))
    args = ap.parse_args()

    result = run_probe(
        days=args.days,
        ledger_path=Path(args.ledger),
        qb_dir=Path(args.qb_dir),
    )
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = RESULTS_PATH.with_suffix(RESULTS_PATH.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    os.replace(tmp, RESULTS_PATH)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["ship"] else 1


if __name__ == "__main__":
    sys.exit(main())
