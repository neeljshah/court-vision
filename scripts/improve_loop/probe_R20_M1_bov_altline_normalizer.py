"""probe_R20_M1_bov_altline_normalizer.py — end-to-end PTS-OVER-3.5 false-arb fix.

What the probe does
-------------------
1. Locate the most-recent 3 on-disk Bov-bearing snapshots:
     data/lines/<date>_bov.csv  (today + up to 2 prior days that exist)
2. For each date, run the *legacy* arb engine path: same load_latest_snapshots
   call but with `allow_alt_lines=True` so the buggy behaviour is reproduced.
   Count `free_arb=True` results — this is the BEFORE number.
3. Run the *fixed* arb engine path: `allow_alt_lines=False` (the default,
   plus the R20_M1 classifier that tags alt rungs on FD/Pin/legacy-bov).
   Count `free_arb=True` results — this is the AFTER number.
4. Specifically assert: zero `free_arb=True` middles where the bov leg has
   over_line <= 5.0 on a PTS market (the literal PTS-OVER-3.5 pattern).
5. Write the results to ``data/cache/probe_R20_M1_results.json`` and to stdout.

Pass criterion
--------------
* AFTER count of bogus PTS<=5.0 over-leg free arbs == 0, AND
* AFTER total free-arb count <= BEFORE total free-arb count

Run
---
    python scripts/improve_loop/probe_R20_M1_bov_altline_normalizer.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date as _date
from datetime import timedelta

PROJECT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))

import middle_finder_daemon as mfd  # noqa: E402

LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
OUT_JSON = os.path.join(PROJECT_DIR, "data", "cache",
                         "probe_R20_M1_results.json")


def _recent_bov_dates(max_days=3):
    """Return up to `max_days` ISO date strings that have a bov CSV on disk."""
    out = []
    today = _date.today()
    for delta in range(0, 14):  # scan up to 2 weeks back to find 3 files
        d = today - timedelta(days=delta)
        path = os.path.join(LINES_DIR, f"{d.isoformat()}_bov.csv")
        if os.path.exists(path):
            out.append(d.isoformat())
            if len(out) >= max_days:
                break
    return out


def _count_free_arbs(middles):
    return sum(1 for m in middles if m.get("free_arb"))


def _count_bogus_pts_alt_arbs(middles):
    """Count free_arbs where the OVER leg is on a PTS market at line<=5.0.
    This is the literal 'PTS OVER 3.5'-style false arb pattern."""
    return sum(1 for m in middles
               if m.get("free_arb")
               and m.get("stat", "").lower() == "pts"
               and float(m.get("over_line", 0)) <= 5.0)


def run_probe():
    dates = _recent_bov_dates(max_days=3)
    per_date = []
    total_before = 0
    total_after = 0
    bogus_pts_after = 0
    bogus_pts_before = 0

    for date_str in dates:
        index = mfd.load_latest_snapshots(date_str, lines_dir=LINES_DIR)
        # BEFORE: include alt rungs (reproduces the buggy behaviour).
        middles_before = mfd.find_middles(
            index, min_width=0.5, max_juice_each_side=-135,
            allow_alt_lines=True,
        )
        # AFTER: primary-only (the fix).
        middles_after = mfd.find_middles(
            index, min_width=0.5, max_juice_each_side=-135,
            allow_alt_lines=False,
        )
        n_before = _count_free_arbs(middles_before)
        n_after = _count_free_arbs(middles_after)
        bp_before = _count_bogus_pts_alt_arbs(middles_before)
        bp_after = _count_bogus_pts_alt_arbs(middles_after)
        total_before += n_before
        total_after += n_after
        bogus_pts_before += bp_before
        bogus_pts_after += bp_after
        per_date.append({
            "date": date_str,
            "n_player_stats": len(index),
            "n_middles_before": len(middles_before),
            "n_middles_after": len(middles_after),
            "free_arbs_before": n_before,
            "free_arbs_after": n_after,
            "bogus_pts_arbs_before": bp_before,
            "bogus_pts_arbs_after": bp_after,
            "sample_bogus_before": [
                {"player": m["player"], "stat": m["stat"],
                 "over": f"{m['over_book']} {m['over_line']} @ {m['over_price']}",
                 "under": f"{m['under_book']} {m['under_line']} @ {m['under_price']}",
                 "arb_pct": m.get("arb_profit_pct")}
                for m in middles_before
                if m.get("free_arb")
                and m.get("stat", "").lower() == "pts"
                and float(m.get("over_line", 0)) <= 5.0
            ][:5],
        })

    passed = (bogus_pts_after == 0) and (total_after <= total_before)
    payload = {
        "probe": "R20_M1_bov_altline_normalizer",
        "dates_scanned": dates,
        "n_dates": len(dates),
        "totals": {
            "free_arbs_before": total_before,
            "free_arbs_after": total_after,
            "bogus_pts_arbs_before": bogus_pts_before,
            "bogus_pts_arbs_after": bogus_pts_after,
        },
        "per_date": per_date,
        "pass": passed,
        "ship_gate": ("AFTER bogus PTS-OVER-<=5 free-arbs == 0 AND "
                      "AFTER total free-arbs <= BEFORE"),
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(run_probe())
