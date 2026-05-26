"""probe_R23_P5_middle_finder_audit.py — backwards-looking 24h audit of the
R20_M1 alt-line classifier and the (post-M1) arb engine.

What the probe does
-------------------
1. Inventory line snapshots: ``data/lines/<date>_<book>.csv`` for the last 24h
   worth of data we have on disk. Today + the most recent 1-2 prior days that
   actually contain fd/bov/pin rows (the snapshot directory is currently
   empty for this build).
2. For each snapshot date, run the R20_M1 classifier via
   ``middle_finder_daemon.load_latest_snapshots`` — this tags every loaded
   row with ``is_alt_line`` and ``market_tier`` (primary/alt).
3. Run the post-M1 arb engine (``find_middles(..., allow_alt_lines=False)``)
   on the tagged data. Count surviving ``free_arb`` middles — these are the
   REAL free arbs the operator should chase.
4. Run a synthetic pre-M1 comparison: ``find_middles(..., allow_alt_lines=True)``
   — same data, gate disabled. Count free arbs that WOULD have appeared.
   The delta is the number of false-arbs the M1 classifier blocked.
5. Per-book breakdown: for each blocked false-arb, which book provided the
   over leg and which provided the under leg.
6. Hand-check each surviving (post-M1) free_arb: walk the full per-book
   ladder for the (player, stat) pair and verify the OVER and UNDER rows
   marked ``primary`` are in fact the realistic anchor rungs (i.e. NOT
   ladder outliers that happened to be priced symmetrically).
   A remaining free_arb is flagged ``suspect`` if either leg's rung sits
   far from the cluster median of its own book ladder (>= 3.0 points away
   for PTS/REB/AST counts, indicating it is almost certainly an alt rung
   the heuristic miscrowned).

Output
------
``data/cache/probe_R23_P5_results.json`` with:
    n_snapshots_audited
    n_rows_tagged_primary
    n_rows_tagged_alt
    n_real_arbs_post_M1
    n_would_be_false_arbs_pre_M1
    n_remaining_suspect_arbs
    per_book_breakdown

Ship gate
---------
* ``n_would_be_false_arbs_pre_M1 > n_real_arbs_post_M1``  — proves M1 saves us
* ``n_remaining_suspect_arbs == 0``  — preferred, but if > 0 the audit still
  ships as a follow-up signal (R23_P5 is a probe, not a fix).

Run
---
    python scripts/improve_loop/probe_R23_P5_middle_finder_audit.py
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
                         "probe_R23_P5_results.json")

# Lookback window (24h ~= today + yesterday once we are mid-day; we scan a
# wider window and keep dates that actually have at least one book CSV).
LOOKBACK_DAYS = 2
SCAN_BACK = 5  # how many calendar days to walk back looking for files


def _recent_dates_with_books(books=mfd.BOOKS, lookback_days=LOOKBACK_DAYS,
                              scan_back=SCAN_BACK):
    """Return up to `lookback_days` ISO dates that have at least one
    fd/bov/pin CSV on disk, walking back from today."""
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


def _count_rows_by_tier(index):
    n_primary = 0
    n_alt = 0
    by_book = {}
    for _pkey, bdict in index.items():
        for book, rows in bdict.items():
            stats = by_book.setdefault(book, {"primary": 0, "alt": 0,
                                                "total": 0})
            for r in rows:
                stats["total"] += 1
                if r.get("is_alt_line"):
                    n_alt += 1
                    stats["alt"] += 1
                else:
                    n_primary += 1
                    stats["primary"] += 1
    return n_primary, n_alt, by_book


def _book_ladder_median(index, player, stat, book):
    """Return the median line value for (player, stat) on `book` — used to
    sanity-check whether a 'primary'-tagged row actually anchors near the
    cluster center or is an outlier rung."""
    rows = index.get((player, stat), {}).get(book, [])
    lines = sorted(float(r["line"]) for r in rows if r.get("line") is not None)
    if not lines:
        return None
    return lines[len(lines) // 2]


def _classify_suspect(m, index, max_dist=3.0):
    """A surviving free_arb is suspect if either leg's line is >= max_dist
    points away from the median of its own book's ladder for that
    (player, stat). The R20_M1 classifier picked the rung with the lowest
    over/under spread, but a perfectly-symmetric alt rung (e.g. -115/-115
    on a points-3.5 line for a 25-ppg starter) can game that heuristic;
    the realistic anchor sits closer to the per-book ladder median."""
    player = m["player"]; stat = m["stat"]
    over_med = _book_ladder_median(index, player, stat, m["over_book"])
    under_med = _book_ladder_median(index, player, stat, m["under_book"])
    over_dist = (abs(float(m["over_line"]) - over_med)
                  if over_med is not None else 0.0)
    under_dist = (abs(float(m["under_line"]) - under_med)
                    if under_med is not None else 0.0)
    suspect = (over_dist >= max_dist) or (under_dist >= max_dist)
    return suspect, {"over_book_median": over_med,
                      "under_book_median": under_med,
                      "over_dist_from_median": over_dist,
                      "under_dist_from_median": under_dist}


def _per_book_breakdown(blocked_middles):
    """For each blocked false-arb, attribute by over_book and under_book."""
    over_counts = {}
    under_counts = {}
    pair_counts = {}
    stat_counts = {}
    for m in blocked_middles:
        over_counts[m["over_book"]] = over_counts.get(m["over_book"], 0) + 1
        under_counts[m["under_book"]] = under_counts.get(m["under_book"], 0) + 1
        pair = f"{m['over_book']}-OVER/{m['under_book']}-UNDER"
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
        stat_counts[m["stat"]] = stat_counts.get(m["stat"], 0) + 1
    return {"over_leg_by_book": over_counts,
            "under_leg_by_book": under_counts,
            "pair_breakdown": pair_counts,
            "stat_breakdown": stat_counts}


def _middle_key(m):
    return (m["player"], m["stat"], m["over_book"], m["over_line"],
            m["under_book"], m["under_line"])


def run_probe():
    dates = _recent_dates_with_books()
    per_date = []
    n_primary_total = 0
    n_alt_total = 0
    n_real_arbs_post_m1 = 0
    n_would_be_false_arbs_pre_m1 = 0
    n_remaining_suspect = 0
    all_blocked = []
    all_remaining_suspect = []
    all_real_arbs_post = []

    for date_str in dates:
        index = mfd.load_latest_snapshots(date_str, lines_dir=LINES_DIR)
        n_pri, n_alt, by_book = _count_rows_by_tier(index)
        n_primary_total += n_pri
        n_alt_total += n_alt

        middles_pre = mfd.find_middles(
            index, min_width=0.5, max_juice_each_side=-135,
            allow_alt_lines=True)
        middles_post = mfd.find_middles(
            index, min_width=0.5, max_juice_each_side=-135,
            allow_alt_lines=False)

        free_pre = [m for m in middles_pre if m.get("free_arb")]
        free_post = [m for m in middles_post if m.get("free_arb")]
        post_keys = {_middle_key(m) for m in middles_post}
        blocked = [m for m in free_pre if _middle_key(m) not in post_keys]
        all_blocked.extend(blocked)

        # Hand-check each surviving free_arb for suspect alt-rung crowning.
        date_suspects = []
        for m in free_post:
            suspect, diag = _classify_suspect(m, index)
            if suspect:
                rec = dict(m)
                rec.update(diag)
                rec["date"] = date_str
                date_suspects.append(rec)
        n_remaining_suspect += len(date_suspects)
        all_remaining_suspect.extend(date_suspects)

        for m in free_post:
            rec = dict(m); rec["date"] = date_str
            all_real_arbs_post.append(rec)

        n_real_arbs_post_m1 += len(free_post)
        n_would_be_false_arbs_pre_m1 += len(blocked)

        per_date.append({
            "date": date_str,
            "n_player_stats": len(index),
            "rows_by_book": by_book,
            "n_primary": n_pri,
            "n_alt": n_alt,
            "n_middles_pre_m1": len(middles_pre),
            "n_middles_post_m1": len(middles_post),
            "n_free_arbs_pre_m1": len(free_pre),
            "n_free_arbs_post_m1": len(free_post),
            "n_false_arbs_blocked": len(blocked),
            "n_suspect_remaining": len(date_suspects),
            "sample_blocked": [
                {"player": m["player"], "stat": m["stat"],
                 "over": f"{m['over_book']} {m['over_line']}@{m['over_price']}",
                 "under": f"{m['under_book']} {m['under_line']}@{m['under_price']}",
                 "width": m["middle_width"],
                 "arb_pct": m.get("arb_profit_pct")}
                for m in blocked
            ][:10],
            "sample_suspect_remaining": [
                {"player": m["player"], "stat": m["stat"],
                 "over": f"{m['over_book']} {m['over_line']}@{m['over_price']}",
                 "under": f"{m['under_book']} {m['under_line']}@{m['under_price']}",
                 "over_dist_from_median": m["over_dist_from_median"],
                 "under_dist_from_median": m["under_dist_from_median"]}
                for m in date_suspects
            ][:10],
        })

    breakdown = _per_book_breakdown(all_blocked)
    payload = {
        "probe": "R23_P5_middle_finder_audit",
        "dates_scanned": dates,
        "n_snapshots_audited": len(dates),
        "n_rows_tagged_primary": n_primary_total,
        "n_rows_tagged_alt": n_alt_total,
        "n_real_arbs_post_M1": n_real_arbs_post_m1,
        "n_would_be_false_arbs_pre_M1": n_would_be_false_arbs_pre_m1,
        "n_remaining_suspect_arbs": n_remaining_suspect,
        "per_book_breakdown": breakdown,
        "per_date": per_date,
        "real_arbs_post_M1": [
            {"date": m["date"], "player": m["player"], "stat": m["stat"],
             "over": f"{m['over_book']} {m['over_line']}@{m['over_price']}",
             "under": f"{m['under_book']} {m['under_line']}@{m['under_price']}",
             "width": m["middle_width"],
             "arb_pct": m.get("arb_profit_pct")}
            for m in all_real_arbs_post
        ],
        "remaining_suspect_arbs": [
            {"date": m["date"], "player": m["player"], "stat": m["stat"],
             "over": f"{m['over_book']} {m['over_line']}@{m['over_price']}",
             "under": f"{m['under_book']} {m['under_line']}@{m['under_price']}",
             "over_book_median": m["over_book_median"],
             "under_book_median": m["under_book_median"],
             "over_dist_from_median": m["over_dist_from_median"],
             "under_dist_from_median": m["under_dist_from_median"]}
            for m in all_remaining_suspect
        ],
        "ship_gate": ("n_would_be_false_arbs_pre_M1 > n_real_arbs_post_M1 "
                       "AND (preferred) n_remaining_suspect_arbs == 0"),
        "ship_gate_pass": (n_would_be_false_arbs_pre_m1 > n_real_arbs_post_m1),
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(json.dumps({k: v for k, v in payload.items()
                       if k not in ("per_date", "real_arbs_post_M1",
                                     "remaining_suspect_arbs")},
                      indent=2, default=str))
    return 0 if payload["ship_gate_pass"] else 1


if __name__ == "__main__":
    sys.exit(run_probe())
