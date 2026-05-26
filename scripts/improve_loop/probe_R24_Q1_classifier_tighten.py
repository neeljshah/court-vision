"""probe_R24_Q1_classifier_tighten.py — verify the median-distance
tiebreaker added to `classify_market_tier()` correctly handles the
Vassell + Dort cases R23_P5's audit surfaced, and persists pre/post
counts for downstream regression tracking.

What the probe does
-------------------
1. Runs the synthetic Vassell + Dort fixtures directly through
   `classify_market_tier()` to confirm the new ordering crowns the
   mid-ladder rung (the realistic NBA line) instead of the perfectly
   balanced symmetric low-line alt rung.
2. Re-runs R23_P5's audit on whatever line snapshots are on disk to
   recompute (a) the total false-arbs blocked by R20_M1+R24_Q1 and
   (b) any remaining "suspect" survivors whose primary leg sits >= 3
   points from the cluster median (the heuristic-failure signal).
3. Loads any existing R23_P5 result file so we can express the
   pre/post delta in the output payload.

Output
------
``data/cache/probe_R24_Q1_results.json``::

    {
      "probe": "R24_Q1_classifier_tighten",
      "vassell_correct": true|false,
      "dort_correct": true|false,
      "n_real_arbs_post_R24_Q1": int,
      "n_remaining_suspect_arbs_post_R24_Q1": int,
      "delta_vs_R23_P5": {...},
      "ship_gate_pass": bool
    }

Ship gate
---------
* vassell_correct AND dort_correct
* n_remaining_suspect_arbs_post_R24_Q1 <= R23_P5 baseline (don't make
  it worse).

Run
---
    python scripts/improve_loop/probe_R24_Q1_classifier_tighten.py
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
                         "probe_R24_Q1_results.json")
R23_P5_RESULTS = os.path.join(PROJECT_DIR, "data", "cache",
                                "probe_R23_P5_results.json")

LOOKBACK_DAYS = 2
SCAN_BACK = 5


# ---------- direct fixture checks (the two failing cases from P5) ----------

def _check_vassell():
    """Devin Vassell PTS — bov 3.5@-115/-115 + pin 13.5@-113.
    Post R24_Q1: the 13.5 line must be the primary, NOT the symmetric
    edge alt at 3.5.
    """
    rows = [
        {"line": 3.5, "over_price": -115, "under_price": -115},
        {"line": 13.5, "over_price": -113, "under_price": -107},
    ]
    mfd.classify_market_tier(rows, csv_alt_present=False)
    prim = next((r for r in rows if r["market_tier"] == "primary"), None)
    return {
        "rung_3_5_tier": next(r["market_tier"] for r in rows if r["line"] == 3.5),
        "rung_13_5_tier": next(r["market_tier"] for r in rows if r["line"] == 13.5),
        "primary_line": prim["line"] if prim else None,
        "correct": prim is not None and prim["line"] == 13.5,
    }


def _check_dort():
    """Luguentz Dort PTS — bov 0.5@-115/-115 + pin 5.5@-126.
    Post R24_Q1: the 5.5 line must be the primary.
    """
    rows = [
        {"line": 0.5, "over_price": -115, "under_price": -115},
        {"line": 5.5, "over_price": -126, "under_price": 104},
    ]
    mfd.classify_market_tier(rows, csv_alt_present=False)
    prim = next((r for r in rows if r["market_tier"] == "primary"), None)
    return {
        "rung_0_5_tier": next(r["market_tier"] for r in rows if r["line"] == 0.5),
        "rung_5_5_tier": next(r["market_tier"] for r in rows if r["line"] == 5.5),
        "primary_line": prim["line"] if prim else None,
        "correct": prim is not None and prim["line"] == 5.5,
    }


# ---------- audit re-run (mirrors R23_P5's logic) ----------

def _recent_dates_with_books(books=mfd.BOOKS, lookback_days=LOOKBACK_DAYS,
                              scan_back=SCAN_BACK):
    out = []
    today = _date.today()
    for delta in range(0, scan_back + 1):
        d = today - timedelta(days=delta)
        for book in books:
            path = os.path.join(LINES_DIR, f"{d.isoformat()}_{book}.csv")
            if os.path.exists(path):
                out.append(d.isoformat())
                break
        if len(out) >= lookback_days:
            break
    return out


def _book_ladder_median(index, player, stat, book):
    rows = index.get((player, stat), {}).get(book, [])
    lines = sorted(float(r["line"]) for r in rows
                   if r.get("line") is not None)
    if not lines:
        return None
    return lines[len(lines) // 2]


def _classify_suspect(m, index, max_dist=3.0):
    player = m["player"]; stat = m["stat"]
    over_med = _book_ladder_median(index, player, stat, m["over_book"])
    under_med = _book_ladder_median(index, player, stat, m["under_book"])
    over_dist = (abs(float(m["over_line"]) - over_med)
                  if over_med is not None else 0.0)
    under_dist = (abs(float(m["under_line"]) - under_med)
                    if under_med is not None else 0.0)
    return (over_dist >= max_dist) or (under_dist >= max_dist)


def _audit():
    """Returns (n_real_arbs, n_suspect, n_blocked) for the recent
    on-disk snapshots, using the now-tightened classifier.
    """
    dates = _recent_dates_with_books()
    n_real = 0
    n_susp = 0
    n_blocked = 0
    for date_str in dates:
        index = mfd.load_latest_snapshots(date_str, lines_dir=LINES_DIR)
        middles_pre = mfd.find_middles(
            index, min_width=0.5, max_juice_each_side=-135,
            allow_alt_lines=True)
        middles_post = mfd.find_middles(
            index, min_width=0.5, max_juice_each_side=-135,
            allow_alt_lines=False)
        free_pre = [m for m in middles_pre if m.get("free_arb")]
        free_post = [m for m in middles_post if m.get("free_arb")]
        n_real += len(free_post)
        n_blocked += max(0, len(free_pre) - len(free_post))
        for m in free_post:
            if _classify_suspect(m, index):
                n_susp += 1
    return {"dates_scanned": dates,
            "n_real_arbs": n_real,
            "n_suspect_remaining": n_susp,
            "n_blocked_false_arbs": n_blocked}


def _load_p5_baseline():
    if not os.path.exists(R23_P5_RESULTS):
        return None
    try:
        with open(R23_P5_RESULTS, encoding="utf-8") as f:
            d = json.load(f)
        return {
            "n_real_arbs_post_M1": d.get("n_real_arbs_post_M1"),
            "n_would_be_false_arbs_pre_M1": d.get("n_would_be_false_arbs_pre_M1"),
            "n_remaining_suspect_arbs": d.get("n_remaining_suspect_arbs"),
        }
    except Exception:
        return None


def run_probe():
    vass = _check_vassell()
    dort = _check_dort()
    audit = _audit()
    baseline = _load_p5_baseline()

    delta = None
    if baseline is not None:
        delta = {
            "real_arbs_change": (audit["n_real_arbs"]
                                  - (baseline["n_real_arbs_post_M1"] or 0)),
            "suspect_change": (audit["n_suspect_remaining"]
                                - (baseline["n_remaining_suspect_arbs"] or 0)),
        }

    baseline_suspects = (baseline.get("n_remaining_suspect_arbs")
                         if baseline else 0) or 0
    ship_gate_pass = bool(
        vass["correct"]
        and dort["correct"]
        and audit["n_suspect_remaining"] <= baseline_suspects
    )

    payload = {
        "probe": "R24_Q1_classifier_tighten",
        "vassell": vass,
        "dort": dort,
        "vassell_correct": vass["correct"],
        "dort_correct": dort["correct"],
        "audit_post_R24_Q1": audit,
        "R23_P5_baseline": baseline,
        "delta_vs_R23_P5": delta,
        "ship_gate": ("vassell_correct AND dort_correct AND "
                       "suspect_count_not_worse_than_R23_P5"),
        "ship_gate_pass": ship_gate_pass,
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if ship_gate_pass else 1


if __name__ == "__main__":
    sys.exit(run_probe())
