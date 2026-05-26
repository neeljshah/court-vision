"""probe_R19_L8_bankroll_dashboard_filter.py - R19 loop L8.

Verifies the synthetic-row filter for the bankroll monitor + mobile HTML
dashboard. Real ``data/pnl_ledger.csv`` is read-only; we never mutate it.

Steps
-----
1. Load real ledger (read-only).
2. Run ``tick()`` WITHOUT the filter -> capture baseline metrics.
3. Run ``tick()`` WITH ``exclude_synthetic=True`` and
   ``start_date=2026-05-25`` -> capture filtered metrics.
4. Write ``data/cache/probe_R19_L8_results.json`` with status + deltas.

Outputs JSON keys
-----------------
status, n_synth_excluded, n_real_kept, pnl_unfiltered, pnl_filtered,
roi_unfiltered, roi_filtered, summary.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "scripts"))

import pandas as pd

from bankroll_monitor_daemon import (  # noqa: E402
    compute_metrics,
    compute_roi,
    filter_ledger,
    is_synthetic_row,
    load_ledger,
    tick,
)

LEDGER = PROJECT_DIR / "data" / "pnl_ledger.csv"
RESULTS = PROJECT_DIR / "data" / "cache" / "probe_R19_L8_results.json"


def main() -> int:
    if not LEDGER.exists():
        result = {"status": "no_ledger", "summary": f"ledger missing at {LEDGER}"}
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        RESULTS.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 1

    ledger = load_ledger(LEDGER)
    n_total = len(ledger)
    print(f"[probe] loaded ledger n={n_total}")

    # Unfiltered baseline
    unfilt = filter_ledger(ledger, exclude_synthetic=False, start_date=None)
    metrics_unf = compute_metrics(unfilt["filtered"], start_bankroll=1000.0)
    roi_unf = compute_roi(unfilt["filtered"])

    # Filtered (exclude synth + after 2026-05-25)
    filt = filter_ledger(ledger, exclude_synthetic=True, start_date="2026-05-25")
    metrics_filt = compute_metrics(filt["filtered"], start_bankroll=1000.0)
    roi_filt = compute_roi(filt["filtered"])

    # Sanity: hand-count synthetic rows
    syn_handcount = int(ledger.apply(is_synthetic_row, axis=1).sum())

    # Full tick to writable temp paths (don't disturb live state file)
    with tempfile.TemporaryDirectory() as td:
        td_p = Path(td)
        state_p = td_p / "bankroll_state.json"
        dash_p = td_p / "dashboard.md"
        alerts_p = td_p / "risk_alerts.md"
        tick_metrics = tick(
            start_bankroll=1000.0,
            ledger_path=LEDGER,
            state_path=state_p,
            dashboard_path=dash_p,
            alerts_path=alerts_p,
            exclude_synthetic=True,
            start_date="2026-05-25",
        )
        # Verify state JSON has filter_info + roi blocks
        state_blob = json.loads(state_p.read_text(encoding="utf-8"))
        assert "filter_info" in state_blob, "filter_info missing from state"
        assert "roi" in state_blob, "roi missing from state"
        dashboard_text = dash_p.read_text(encoding="utf-8")

    pnl_unfiltered = metrics_unf["current_bankroll"] - metrics_unf["start_bankroll"]
    pnl_filtered = metrics_filt["current_bankroll"] - metrics_filt["start_bankroll"]

    ship = (
        filt["n_synth_excluded"] == syn_handcount
        and filt["n_kept"] < unfilt["n_kept"]
        and roi_filt["n_bets"] != roi_unf["n_bets"]
    )

    summary_lines = [
        f"unfiltered: {unfilt['n_kept']} rows, PnL=${pnl_unfiltered:,.2f}, "
        f"ROI={roi_unf['roi_pct']:+.2f}%",
        f"filtered:   {filt['n_kept']} rows, PnL=${pnl_filtered:,.2f}, "
        f"ROI={roi_filt['roi_pct']:+.2f}%",
        f"synth excluded: {filt['n_synth_excluded']} (hand-count match: {syn_handcount})",
        f"date excluded:  {filt['n_date_excluded']}",
        f"tick wrote state w/ filter_info + roi: OK",
    ]
    summary = " | ".join(summary_lines)

    result = {
        "status": "ship" if ship else "fail",
        "n_synth_excluded": int(filt["n_synth_excluded"]),
        "n_real_kept": int(filt["n_kept"]),
        "n_date_excluded": int(filt["n_date_excluded"]),
        "n_total": int(filt["n_total"]),
        "syn_handcount": syn_handcount,
        "pnl_unfiltered": float(pnl_unfiltered),
        "pnl_filtered": float(pnl_filtered),
        "roi_unfiltered": float(roi_unf["roi_pct"]),
        "roi_filtered": float(roi_filt["roi_pct"]),
        "n_settled_unfiltered": int(roi_unf["n_bets"]),
        "n_settled_filtered": int(roi_filt["n_bets"]),
        "current_bankroll_unfiltered": float(metrics_unf["current_bankroll"]),
        "current_bankroll_filtered": float(metrics_filt["current_bankroll"]),
        "tick_state_has_filter_info": True,
        "dashboard_excerpt": dashboard_text.split("\n", 3)[0],
        "summary": summary,
    }

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if ship else 2


if __name__ == "__main__":
    sys.exit(main())
