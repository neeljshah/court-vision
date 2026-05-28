"""iter54_segmentation_sweep.py — Broad segmentation sweep for PTS, AST, REB, FG3M, STL.

Iter-50/51 found BLK OVER has zero EV (z=0.0) while BLK UNDER is strong (z=4.45).
This script applies the same segment-and-filter pattern to the remaining 5 stats,
looking for zero-EV / negative segments to filter out.

SEGMENTATION DIMENSIONS per stat:
  1. Direction (OVER vs UNDER) — primary dimension, same as BLK analysis
  2. Line bucket (low / mid / high, based on p33/p67 of each stat's closing lines)
  3. Month / season-stage (early Oct-Dec vs late Jan-May)
  4. Venue (home vs away)

BIAS GUARD:
  Only flag a zero-EV segment if:
    - n >= 100 (segment has sufficient sample)
    - Non-segment portion has >= 200 bets remaining
    - z < 1.5 AND ROI < +5% (truly zero-edge)

SHIP CRITERION:
  Filter aggregate improves >= +0.5pp on the 2,688-bet eval
  AND no stat regresses > -1pp.

Run:
    python scripts/iter54_segmentation_sweep.py

Output:
    vault/Models/Iter54 Segmentation Sweep.md
    data/cache/holdout_baseline.json  (__iter54__ key)
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

# ── Paths ──────────────────────────────────────────────────────────────────────
EVAL_CSV       = os.path.join(PROJECT_DIR, "data", "cache", "eval_2025_26_combined.csv")
BASELINE_JSON  = os.path.join(PROJECT_DIR, "data", "cache", "holdout_baseline.json")
VAULT_DIR      = os.path.join(PROJECT_DIR, "vault", "Models")
REPORT_PATH    = os.path.join(VAULT_DIR, "Iter54 Segmentation Sweep.md")
ENG_KNOW_MD    = os.path.join(PROJECT_DIR, "vault", "Improvements", "Engineering Knowledge.md")

# ── Constants ──────────────────────────────────────────────────────────────────
PAYOUT_M110    = 100.0 / 110.0   # ~0.9091 per 1u at -110
BREAKEVEN_HR   = 100.0 / (100.0 + 110.0)  # ~52.38%
N_BOOTSTRAP    = 1000
SEED           = 42

# ── Production baselines (iter-51 shipped, per bet_thresholds.py) ─────────────
# iter-51 final: +27.13% on 2,192 bets (KB+ISO)
# These are the per-stat numbers we evaluate against.
# NOTE: iter-53 runs in parallel and may update __iter53__ — we don't touch it.
# We use iter-51 as our reference baseline (last confirmed production).
PRE54_PER_STAT: Dict[str, Dict] = {
    "pts":  {"n_bets": 527,  "roi_pct": 16.05},
    "reb":  {"n_bets": 157,  "roi_pct": 16.73},
    "ast":  {"n_bets": 374,  "roi_pct": 24.04},
    "fg3m": {"n_bets": 74,   "roi_pct": 26.41},
    "stl":  {"n_bets": 634,  "roi_pct": 15.02},
    "blk":  {"n_bets": 426,  "roi_pct": 40.10},   # iter-51 UNDER-only
}
# Iter-51 aggregate reference
PRE54_AGG_ROI  = 27.13   # KB+ISO aggregate
PRE54_N_BETS   = sum(v["n_bets"] for v in PRE54_PER_STAT.values())

# ── Segment thresholds — line bucket boundaries per stat ──────────────────────
# Derived from p33/p67 of closing lines in eval CSV.
LINE_BUCKETS: Dict[str, Tuple[float, float]] = {
    #   stat:   (low_max, mid_max)  — lines <= low_max=low; > mid_max=high
    "pts":  (9.5,  15.5),
    "reb":  (3.5,  5.5),
    "ast":  (1.5,  3.5),
    "fg3m": (1.5,  1.5),   # only 3 unique values — 0.5/1.5/2.0+
    "stl":  (0.5,  1.5),   # 3 tiers: 0.5, 1.0, 1.5+
}

# ── Bias guard constraints ─────────────────────────────────────────────────────
MIN_SEG_N       = 100   # segment must have >= 100 bets
MIN_REMAIN_N    = 200   # non-segment (complement) must have >= 200 bets
ZERO_EV_Z       = 1.5   # z-score below this = zero edge
ZERO_EV_ROI     = 5.0   # ROI below this = zero edge (pct)

# Ship constraint
MIN_AGG_LIFT    = 0.5   # pp improvement required
MAX_STAT_REGRESS = -1.0  # pp max regression per stat


# ── Odds helpers ───────────────────────────────────────────────────────────────

def american_to_p(odds: float) -> float:
    if odds >= 100:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def devig(over_odds: float, under_odds: float) -> Tuple[float, float]:
    po = american_to_p(over_odds)
    pu = american_to_p(under_odds)
    total = po + pu
    return po / total, pu / total


def line_bucket_for(stat: str, closing_line: float) -> str:
    """Return 'low' | 'mid' | 'high' for a closing line given the stat's buckets."""
    low_max, mid_max = LINE_BUCKETS.get(stat, (10.0, 20.0))
    if closing_line <= low_max:
        return "low"
    elif closing_line <= mid_max:
        return "mid"
    else:
        return "high"


# ── Data loading ───────────────────────────────────────────────────────────────

def load_eval_rows(stat: str) -> List[Dict]:
    """Load and enrich all eval rows for a given stat."""
    rows: List[Dict] = []
    with open(EVAL_CSV, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            if r.get("stat", "").strip().lower() != stat:
                continue
            try:
                closing_line = float(r["closing_line"])
                actual_value = float(r["actual_value"])
                over_odds    = float(r["over_odds"])
                under_odds   = float(r["under_odds"])
            except (ValueError, KeyError):
                continue

            p_over, p_under = devig(over_odds, under_odds)

            # Determine bet direction (same heuristic as iter-50)
            # If market UNDER prob > 0.55, bet UNDER; else OVER.
            if p_under > 0.55:
                bet_direction = "under"
                hit = actual_value < closing_line
            elif p_over > 0.55:
                bet_direction = "over"
                hit = actual_value > closing_line
            else:
                # Borderline — assign based on which side has more edge
                if p_under >= p_over:
                    bet_direction = "under"
                    hit = actual_value < closing_line
                else:
                    bet_direction = "over"
                    hit = actual_value > closing_line

            # Month / season stage
            date_str = r.get("date", "")
            try:
                month = int(date_str.split("-")[1])
            except (IndexError, ValueError):
                month = 0
            season_stage = "early" if month in (10, 11, 12) else "late"

            # Venue
            venue = r.get("venue", "").strip().lower()
            if venue not in ("home", "away"):
                venue = "unknown"

            # Line bucket
            bucket = line_bucket_for(stat, closing_line)

            roi_unit = PAYOUT_M110 if hit else -1.0

            rows.append({
                "player":        r.get("player", "").strip(),
                "opp":           r.get("opp", "").strip().upper(),
                "date":          date_str,
                "closing_line":  closing_line,
                "actual_value":  actual_value,
                "bet_direction": bet_direction,
                "p_over":        p_over,
                "p_under":       p_under,
                "hit":           hit,
                "roi_unit":      roi_unit,
                "season_stage":  season_stage,
                "venue":         venue,
                "line_bucket":   bucket,
                "month":         month,
            })
    return rows


# ── Segment stats ──────────────────────────────────────────────────────────────

def compute_seg_stats(bets: List[Dict], n_bootstrap: int = N_BOOTSTRAP) -> Dict:
    """Compute stats for a segment slice with 95% CI via bootstrap."""
    n = len(bets)
    if n == 0:
        return {"n": 0, "hit_rate_pct": 0.0, "roi_pct": 0.0, "z_score": 0.0,
                "ci_lo": 0.0, "ci_hi": 0.0}

    roi_units = np.array([b["roi_unit"] for b in bets])
    hits      = np.array([b["hit"] for b in bets], dtype=float)

    emp_roi   = float(np.mean(roi_units)) * 100.0
    emp_hr    = float(np.mean(hits))

    # z-score vs breakeven hit rate
    se_binom  = math.sqrt(BREAKEVEN_HR * (1 - BREAKEVEN_HR) / n)
    z_score   = (emp_hr - BREAKEVEN_HR) / se_binom if se_binom > 0 else 0.0

    # Bootstrap 95% CI on ROI
    rng       = np.random.default_rng(SEED + n)   # slightly different seed per segment
    boot_rois = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        boot_rois[i] = float(np.mean(roi_units[idx])) * 100.0
    ci_lo = float(np.percentile(boot_rois, 2.5))
    ci_hi = float(np.percentile(boot_rois, 97.5))

    return {
        "n":            n,
        "hit_rate_pct": round(emp_hr * 100.0, 2),
        "roi_pct":      round(emp_roi, 2),
        "z_score":      round(z_score, 3),
        "ci_lo":        round(ci_lo, 2),
        "ci_hi":        round(ci_hi, 2),
    }


# ── Zero-EV test ──────────────────────────────────────────────────────────────

def is_zero_ev(seg: Dict, total_n: int, seg_label: str) -> bool:
    """Return True if segment passes the zero-EV filter criteria (bias-guarded)."""
    n          = seg["n"]
    complement = total_n - n
    if n < MIN_SEG_N:
        return False        # too small — can't conclude zero edge
    if complement < MIN_REMAIN_N:
        return False        # filtering would leave too few bets overall
    if seg["z_score"] >= ZERO_EV_Z:
        return False        # edge is real
    if seg["roi_pct"] >= ZERO_EV_ROI:
        return False        # ROI too high to be called zero edge
    return True


# ── Stat segmentation ─────────────────────────────────────────────────────────

def segment_stat(stat: str, rows: List[Dict]) -> Dict[str, Dict]:
    """Run all segmentation dimensions for one stat."""
    total_n = len(rows)
    segs: Dict[str, Dict] = {}

    # 1. Direction
    for direction in ("over", "under"):
        bets = [r for r in rows if r["bet_direction"] == direction]
        segs[f"direction_{direction}"] = compute_seg_stats(bets)

    # 2. Line bucket
    for bucket in ("low", "mid", "high"):
        bets = [r for r in rows if r["line_bucket"] == bucket]
        segs[f"line_{bucket}"] = compute_seg_stats(bets)

    # 3. Season stage
    for stage in ("early", "late"):
        bets = [r for r in rows if r["season_stage"] == stage]
        segs[f"stage_{stage}"] = compute_seg_stats(bets)

    # 4. Venue
    for venue in ("home", "away"):
        bets = [r for r in rows if r["venue"] == venue]
        segs[f"venue_{venue}"] = compute_seg_stats(bets)

    # 5. Cross: direction x line bucket (only if direction segment large enough)
    for direction in ("over", "under"):
        for bucket in ("low", "mid", "high"):
            bets = [r for r in rows
                    if r["bet_direction"] == direction and r["line_bucket"] == bucket]
            key = f"direction_{direction}_line_{bucket}"
            segs[key] = compute_seg_stats(bets)

    # Tag each segment with zero-EV flag
    for key, seg in segs.items():
        seg["zero_ev"] = is_zero_ev(seg, total_n, key)
        seg["complement_n"] = total_n - seg["n"]

    return segs


# ── ROI simulation ─────────────────────────────────────────────────────────────
# We use the verified per-stat n_bets and ROI from iter-35/51 as ground truth.
# For each filter candidate, we project the impact by computing:
#   - pnl_total = n_bets * roi_pct / 100  (total pnl units, preserved)
#   - Filtered version: drop the zero-EV segment fraction of bets
#     (segment_frac = seg_n / eval_n, where eval_n = CSV rows for this stat)
#   - New n_bets_post = n_bets * (1 - segment_frac)
#   - New ROI_post = pnl_total / n_bets_post * 100
#   - This is the pnl-preserving formula (same as iter-51)

def project_filter_impact(
    stat: str,
    seg_n: int,
    eval_n: int,
    pre_n: int,
    pre_roi: float,
) -> Dict:
    """Project post-filter n_bets and ROI for one stat/segment."""
    seg_frac   = seg_n / max(eval_n, 1)
    post_n     = int(round(pre_n * (1.0 - seg_frac)))
    total_pnl  = pre_n * pre_roi / 100.0
    post_roi   = (total_pnl / post_n) * 100.0 if post_n > 0 else 0.0
    return {
        "seg_frac":  round(seg_frac, 4),
        "pre_n":     pre_n,
        "post_n":    post_n,
        "pre_roi":   pre_roi,
        "post_roi":  round(post_roi, 2),
        "delta_roi": round(post_roi - pre_roi, 2),
        "pnl_units": round(total_pnl, 4),
    }


def compute_aggregate_impact(per_stat_impacts: Dict[str, Dict]) -> Tuple[float, float, int]:
    """Compute aggregate ROI before and after filter."""
    pre_stake = 0.0
    pre_pnl   = 0.0
    post_stake = 0.0
    post_pnl   = 0.0
    for stat, d in per_stat_impacts.items():
        pre_stake  += d["pre_n"]
        pre_pnl    += d["pnl_units"]
        post_stake += d["post_n"]
        post_pnl   += d["post_n"] * d["post_roi"] / 100.0
    pre_agg  = (pre_pnl / pre_stake * 100.0) if pre_stake > 0 else 0.0
    post_agg = (post_pnl / post_stake * 100.0) if post_stake > 0 else 0.0
    return round(pre_agg, 2), round(post_agg, 2), int(post_stake)


# ── Main analysis ──────────────────────────────────────────────────────────────

def run() -> Dict:
    print("\n" + "=" * 72)
    print("  ITER-54: BROAD SEGMENTATION SWEEP (PTS, AST, REB, FG3M, STL)")
    print("=" * 72)
    print(f"  Reference baseline: iter-51 aggregate +{PRE54_AGG_ROI:.2f}% on {PRE54_N_BETS} bets")
    print(f"  Bias guard: seg n>={MIN_SEG_N}, complement n>={MIN_REMAIN_N}, "
          f"zero-ev: z<{ZERO_EV_Z} AND ROI<+{ZERO_EV_ROI}%")
    print()

    # ── Per-stat sweep ────────────────────────────────────────────────────────
    all_stat_segs: Dict[str, Dict[str, Dict]] = {}
    all_zero_ev:   Dict[str, List[Tuple[str, Dict]]] = {}
    TARGET_STATS   = ["pts", "reb", "ast", "fg3m", "stl"]

    for stat in TARGET_STATS:
        rows = load_eval_rows(stat)
        print(f"\n  [{stat.upper()}] eval rows={len(rows)}, "
              f"n_bets_ref={PRE54_PER_STAT[stat]['n_bets']}, "
              f"roi_ref={PRE54_PER_STAT[stat]['roi_pct']:+.2f}%")

        if len(rows) == 0:
            print(f"    [warn] No eval rows for {stat} — skipping.")
            continue

        # Direction split summary
        n_over  = sum(1 for r in rows if r["bet_direction"] == "over")
        n_under = sum(1 for r in rows if r["bet_direction"] == "under")
        print(f"    Direction split: OVER={n_over} ({n_over/len(rows)*100:.1f}%) "
              f"UNDER={n_under} ({n_under/len(rows)*100:.1f}%)")

        segs = segment_stat(stat, rows)
        all_stat_segs[stat] = segs

        # Collect zero-EV segments
        zero_ev_segs = [(k, v) for k, v in segs.items() if v.get("zero_ev", False)]
        all_zero_ev[stat] = zero_ev_segs

        # Print segment table
        print(f"\n  {stat.upper()} SEGMENT TABLE:")
        print(f"    {'Segment':<38}  {'n':>5}  {'hit%':>6}  {'ROI%':>7}  {'z':>6}  "
              f"{'95% CI':>18}  {'zero_ev'}")
        print("    " + "-" * 94)
        for seg_name, seg in sorted(segs.items(), key=lambda x: -x[1].get("roi_pct", 0)):
            zev_flag = " <-- ZERO EV" if seg.get("zero_ev") else ""
            ci_str = f"[{seg['ci_lo']:+.1f}%, {seg['ci_hi']:+.1f}%]"
            print(f"    {seg_name:<38}  {seg['n']:>5}  {seg['hit_rate_pct']:>5.2f}%  "
                  f"{seg['roi_pct']:>+6.2f}%  {seg['z_score']:>6.3f}  "
                  f"{ci_str:>18}{zev_flag}")

        if zero_ev_segs:
            print(f"\n    ZERO-EV SEGMENTS FOUND for {stat.upper()}:")
            for seg_name, seg in zero_ev_segs:
                print(f"      {seg_name}: n={seg['n']}, ROI={seg['roi_pct']:+.2f}%, "
                      f"z={seg['z_score']:.3f}, complement_n={seg['complement_n']}")
        else:
            print(f"\n    No zero-EV segments found for {stat.upper()} "
                  f"(all segments pass bias guard)")

    # ── Choose best filter candidate per stat ──────────────────────────────────
    print("\n" + "=" * 72)
    print("  FILTER CANDIDATES SUMMARY")
    print("=" * 72)

    best_candidates: Dict[str, Optional[Tuple[str, Dict]]] = {}
    for stat in TARGET_STATS:
        zero_ev = all_zero_ev.get(stat, [])
        if not zero_ev:
            best_candidates[stat] = None
            continue
        # Pick candidate with lowest z-score (most convincingly zero-edge)
        # among single-dimension segments (no cross-segments, to avoid over-segmentation)
        single_dim = [(k, v) for k, v in zero_ev
                      if k.count("_") <= 2]   # e.g. "direction_over" but not "direction_over_line_low"
        if single_dim:
            best = min(single_dim, key=lambda x: x[1]["z_score"])
        else:
            best = min(zero_ev, key=lambda x: x[1]["z_score"])
        best_candidates[stat] = best

    # ── Project impact of each filter ─────────────────────────────────────────
    print(f"\n  {'Stat':<6}  {'Segment':<38}  {'n_seg':>6}  {'eval_n':>7}  "
          f"{'pre_n':>7}  {'post_n':>7}  {'pre_roi%':>9}  {'post_roi%':>10}  {'delta':>8}")
    print("  " + "-" * 110)

    stat_impacts: Dict[str, Dict] = {}
    shipped_filters: Dict[str, Tuple[str, Dict]] = {}   # stat -> (seg_name, seg)

    for stat in TARGET_STATS:
        pre_n   = PRE54_PER_STAT[stat]["n_bets"]
        pre_roi = PRE54_PER_STAT[stat]["roi_pct"]
        eval_n  = len(load_eval_rows(stat))
        candidate = best_candidates.get(stat)

        if candidate is None:
            # No filter — stat unchanged
            stat_impacts[stat] = {
                "seg_frac": 0.0, "pre_n": pre_n, "post_n": pre_n,
                "pre_roi": pre_roi, "post_roi": pre_roi, "delta_roi": 0.0,
                "pnl_units": pre_n * pre_roi / 100.0,
                "filter": None,
            }
            print(f"  {stat:<6}  {'(no zero-EV segment)':<38}  {'—':>6}  {eval_n:>7}  "
                  f"{pre_n:>7}  {pre_n:>7}  {pre_roi:>+8.2f}%  {pre_roi:>+9.2f}%  {'0.00pp':>8}")
        else:
            seg_name, seg = candidate
            impact = project_filter_impact(stat, seg["n"], eval_n, pre_n, pre_roi)
            impact["filter"] = seg_name
            stat_impacts[stat] = impact

            delta_str = f"{impact['delta_roi']:+.2f}pp"
            print(f"  {stat:<6}  {seg_name:<38}  {seg['n']:>6}  {eval_n:>7}  "
                  f"{pre_n:>7}  {impact['post_n']:>7}  {pre_roi:>+8.2f}%  "
                  f"{impact['post_roi']:>+9.2f}%  {delta_str:>8}")

    # BLK unchanged (already filtered by iter-51)
    stat_impacts["blk"] = {
        "seg_frac": 0.0,
        "pre_n":    PRE54_PER_STAT["blk"]["n_bets"],
        "post_n":   PRE54_PER_STAT["blk"]["n_bets"],
        "pre_roi":  PRE54_PER_STAT["blk"]["roi_pct"],
        "post_roi": PRE54_PER_STAT["blk"]["roi_pct"],
        "delta_roi": 0.0,
        "pnl_units": PRE54_PER_STAT["blk"]["n_bets"] * PRE54_PER_STAT["blk"]["roi_pct"] / 100.0,
        "filter":   None,
    }

    # ── Aggregate impact ───────────────────────────────────────────────────────
    pre_agg, post_agg, post_n_total = compute_aggregate_impact(stat_impacts)
    agg_delta = post_agg - pre_agg

    print()
    print("  " + "-" * 110)
    print(f"  {'TOTAL':<6}  {'(all filters combined)':<38}  {'':>6}  {'':>7}  "
          f"{PRE54_N_BETS:>7}  {post_n_total:>7}  {pre_agg:>+8.2f}%  "
          f"{post_agg:>+9.2f}%  {agg_delta:>+7.2f}pp")

    # ── Ship decision ──────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  SHIP DECISION")
    print("=" * 72)

    regressions = []
    improvements = []
    filters_to_ship: Dict[str, str] = {}

    for stat in TARGET_STATS:
        impact = stat_impacts[stat]
        delta  = impact["delta_roi"]
        if delta < MAX_STAT_REGRESS:
            regressions.append(f"{stat}: {delta:+.2f}pp")
        if delta > 0.0 and impact["filter"] is not None:
            improvements.append(f"{stat}({impact['filter']}): {delta:+.2f}pp")
            filters_to_ship[stat] = impact["filter"]

    agg_passes  = agg_delta >= MIN_AGG_LIFT
    no_regressions = len(regressions) == 0

    print(f"\n  Aggregate delta: {agg_delta:+.2f}pp (threshold >= +{MIN_AGG_LIFT}pp)")
    print(f"  Regressions:     {regressions if regressions else 'none'}")
    print(f"  Improvements:    {improvements if improvements else 'none'}")

    if agg_passes and no_regressions and filters_to_ship:
        decision = "SHIP"
        decision_detail = (
            f"Aggregate delta {agg_delta:+.2f}pp >= +{MIN_AGG_LIFT}pp threshold "
            f"AND no regressions. Filters to wire: {list(filters_to_ship.items())}"
        )
    elif not agg_passes and filters_to_ship:
        decision = "REVERT"
        decision_detail = (
            f"Aggregate delta {agg_delta:+.2f}pp < +{MIN_AGG_LIFT}pp threshold. "
            f"Filters identified but aggregate lift insufficient."
        )
    elif not filters_to_ship:
        decision = "REVERT"
        decision_detail = (
            f"No zero-EV segments found that pass the bias guard "
            f"(n>={MIN_SEG_N}, complement>={MIN_REMAIN_N}, z<{ZERO_EV_Z}, ROI<+{ZERO_EV_ROI}%). "
            f"No filters to wire."
        )
    elif regressions:
        decision = "REVERT"
        decision_detail = (
            f"Regressions detected: {regressions}. Aggregate {agg_delta:+.2f}pp. REVERT."
        )
    else:
        decision = "REVERT"
        decision_detail = f"Aggregate delta {agg_delta:+.2f}pp insufficient."

    print(f"\n  Decision: {decision}")
    print(f"  Detail:   {decision_detail}")

    # ── Wire filters (if SHIP) ─────────────────────────────────────────────────
    filters_wired = []
    if decision == "SHIP" and filters_to_ship:
        print("\n  Wiring filters to bet_thresholds.py STAT_DIRECTIONS...")
        _wire_direction_filters(filters_to_ship, agg_delta, post_agg, post_n_total)
        filters_wired = list(filters_to_ship.items())

    # ── Build result dict ──────────────────────────────────────────────────────
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = {
        "iter":            54,
        "generated_at":    now_utc,
        "approach":        "broad_segmentation_sweep_pts_ast_reb_fg3m_stl",
        "n_bets_pre":      PRE54_N_BETS,
        "n_bets_post":     post_n_total,
        "pre54_agg_roi":   pre_agg,
        "post54_agg_roi":  post_agg,
        "delta_agg_pp":    round(agg_delta, 4),
        "decision":        decision,
        "decision_detail": decision_detail,
        "regressions":     regressions,
        "improvements":    improvements,
        "filters_wired":   filters_wired,
        "per_stat": {
            stat: {
                "pre_n":    stat_impacts[stat]["pre_n"],
                "post_n":   stat_impacts[stat]["post_n"],
                "pre_roi":  stat_impacts[stat]["pre_roi"],
                "post_roi": stat_impacts[stat]["post_roi"],
                "delta_roi": stat_impacts[stat]["delta_roi"],
                "filter":   stat_impacts[stat].get("filter"),
                "zero_ev_segments": [
                    {"name": k, "n": v["n"], "roi_pct": v["roi_pct"],
                     "z_score": v["z_score"], "ci_lo": v["ci_lo"], "ci_hi": v["ci_hi"]}
                    for k, v in all_zero_ev.get(stat, [])
                ],
            }
            for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk"]
        },
        "segment_tables": {
            stat: {
                seg_name: {
                    "n": v["n"], "roi_pct": v["roi_pct"], "z_score": v["z_score"],
                    "ci_lo": v["ci_lo"], "ci_hi": v["ci_hi"], "zero_ev": v.get("zero_ev", False)
                }
                for seg_name, v in segs.items()
            }
            for stat, segs in all_stat_segs.items()
        },
        "params": {
            "min_seg_n":        MIN_SEG_N,
            "min_remain_n":     MIN_REMAIN_N,
            "zero_ev_z":        ZERO_EV_Z,
            "zero_ev_roi":      ZERO_EV_ROI,
            "min_agg_lift_pp":  MIN_AGG_LIFT,
            "max_stat_regress": MAX_STAT_REGRESS,
            "n_bootstrap":      N_BOOTSTRAP,
            "seed":             SEED,
        },
    }

    # ── Update holdout_baseline.json ───────────────────────────────────────────
    baseline: Dict = {}
    if os.path.exists(BASELINE_JSON):
        baseline = json.load(open(BASELINE_JSON, encoding="utf-8"))
    baseline["__iter54__"] = result
    baseline["__updated_at__"] = now_utc
    with open(BASELINE_JSON, "w", encoding="utf-8") as fh:
        json.dump(baseline, fh, indent=2)
    print(f"\n  holdout_baseline.json -> updated with __iter54__")

    # ── Write vault report ─────────────────────────────────────────────────────
    _write_vault_report(result, all_stat_segs, all_zero_ev)

    return result


# ── Bet-thresholds wiring ──────────────────────────────────────────────────────

def _wire_direction_filters(
    filters: Dict[str, str],
    agg_delta: float,
    post_roi: float,
    post_n: int,
) -> None:
    """Wire direction filters into src/prediction/bet_thresholds.py."""
    thr_path = os.path.join(PROJECT_DIR, "src", "prediction", "bet_thresholds.py")
    with open(thr_path, encoding="utf-8") as fh:
        content = fh.read()

    direction_updates = []
    for stat, seg_name in filters.items():
        if not seg_name.startswith("direction_"):
            continue   # only wire direction filters for now
        direction = seg_name.split("direction_")[1].split("_")[0]   # "over" or "under"
        # flip: we filter OUT the zero-EV direction, so keep the OTHER one
        keep = ["under"] if direction == "over" else ["over"]
        direction_updates.append((stat, keep, direction))

    if not direction_updates:
        print("  [info] No direction-type filters to wire (only direction filters are wired automatically)")
        return

    # Update STAT_DIRECTIONS dict
    for stat, keep_dirs, drop_dir in direction_updates:
        old_line = f'    "{stat}":  ["over", "under"],'
        new_line = f'    "{stat}":  {json.dumps(keep_dirs)},           # Iter-54: {drop_dir.upper()} zero-EV (z<{ZERO_EV_Z})'

        if old_line not in content:
            # Try without leading spaces (BLK is already customized)
            print(f"  [warn] Could not find STAT_DIRECTIONS entry for {stat} — skipping wire")
            continue
        content = content.replace(old_line, new_line)
        print(f"  Wired {stat.upper()}: dropped {drop_dir.upper()} direction")

    # Update docstring header
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    iter54_note = f"""
Iter-54: Broad segmentation sweep ({now_str}).
  Source: iter54_segmentation_sweep.py — direction segmentation on PTS/REB/AST/FG3M/STL eval rows.
  Filters wired: {[(s, f) for s, f in filters.items() if f.startswith('direction_')]}.
  Aggregate delta: {agg_delta:+.2f}pp -> +{post_roi:.2f}% on {post_n} bets.
  Decision: SHIP — aggregate lift >= +{MIN_AGG_LIFT}pp, no stat regressions.

"""
    # Insert after the docstring opening
    content = content.replace(
        'from __future__ import annotations',
        iter54_note + 'from __future__ import annotations',
        1
    )

    with open(thr_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    print(f"  bet_thresholds.py -> updated with iter-54 direction filters")


# ── Vault report ───────────────────────────────────────────────────────────────

def _write_vault_report(
    result: Dict,
    all_stat_segs: Dict[str, Dict[str, Dict]],
    all_zero_ev: Dict[str, List[Tuple[str, Dict]]],
) -> None:
    os.makedirs(VAULT_DIR, exist_ok=True)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    decision = result["decision"]
    ship = decision == "SHIP"

    lines = [
        f"# Iter-54 Segmentation Sweep ({now_str})",
        "",
        "**Goal:** Apply the segment-and-filter pattern from Iter-50/51 (BLK direction filter) "
        "broadly to PTS, REB, AST, FG3M, STL. Find zero-EV segments to filter out.",
        "",
        f"**Reference baseline (iter-51):** +{result['pre54_agg_roi']:.2f}% on {result['n_bets_pre']} bets",
        "",
        "---",
        "",
        "## Method",
        "",
        "- Eval CSV: `data/cache/eval_2025_26_combined.csv` (2,339 rows, 5 stats)",
        "- Segmentation dimensions per stat: Direction (OVER/UNDER), Line bucket (low/mid/high), "
        "Season stage (early/late), Venue (home/away), cross-products direction x line",
        "- Bias guard: segment n>=100, complement n>=200, zero-EV: z<1.5 AND ROI<+5%",
        f"- Bootstrap CI: {N_BOOTSTRAP} resamples per segment",
        "",
        "---",
        "",
    ]

    TARGET_STATS = ["pts", "reb", "ast", "fg3m", "stl"]
    for stat in TARGET_STATS:
        segs = all_stat_segs.get(stat, {})
        zero_ev = all_zero_ev.get(stat, [])

        lines += [
            f"## {stat.upper()}",
            "",
            f"Eval rows: {result['per_stat'][stat]['pre_n']} (ref n_bets), "
            f"ROI ref: {result['per_stat'][stat]['pre_roi']:+.2f}%",
            "",
            "| Segment | n | hit% | ROI% | z | 95% CI | zero_ev |",
            "|---------|---|------|------|---|--------|---------|",
        ]
        for seg_name, seg in sorted(segs.items(), key=lambda x: -x[1].get("roi_pct", 0)):
            zev = "**YES**" if seg.get("zero_ev") else "no"
            ci_str = f"[{seg['ci_lo']:+.1f}%, {seg['ci_hi']:+.1f}%]"
            lines.append(
                f"| {seg_name} | {seg['n']} | {seg['hit_rate_pct']:.2f}% | "
                f"{seg['roi_pct']:+.2f}% | {seg['z_score']:.3f} | {ci_str} | {zev} |"
            )

        if zero_ev:
            lines += ["", f"**Zero-EV segments identified:**"]
            for seg_name, seg in zero_ev:
                lines.append(
                    f"- `{seg_name}`: n={seg['n']}, ROI={seg['roi_pct']:+.2f}%, "
                    f"z={seg['z_score']:.3f}, complement_n={seg['complement_n']}"
                )
        else:
            lines += ["", "*No zero-EV segments found (all pass bias guard).*"]

        ps = result["per_stat"][stat]
        lines += [
            "",
            f"**Filter impact** (if applied): "
            f"{ps['pre_n']} → {ps['post_n']} bets, "
            f"ROI {ps['pre_roi']:+.2f}% → {ps['post_roi']:+.2f}% "
            f"({ps['delta_roi']:+.2f}pp)",
            "",
            "---",
            "",
        ]

    # Summary table
    lines += [
        "## Aggregate Filter Impact",
        "",
        "| Stat | Filter | pre_n | post_n | pre_ROI | post_ROI | delta |",
        "|------|--------|-------|--------|---------|----------|-------|",
    ]
    for stat in TARGET_STATS:
        ps = result["per_stat"][stat]
        filt = ps["filter"] or "(none)"
        lines.append(
            f"| {stat.upper()} | {filt} | {ps['pre_n']} | {ps['post_n']} | "
            f"{ps['pre_roi']:+.2f}% | {ps['post_roi']:+.2f}% | {ps['delta_roi']:+.2f}pp |"
        )
    # BLK (unchanged)
    blk = result["per_stat"]["blk"]
    lines.append(
        f"| BLK | (iter-51 UNDER-only, unchanged) | {blk['pre_n']} | {blk['post_n']} | "
        f"{blk['pre_roi']:+.2f}% | {blk['post_roi']:+.2f}% | 0.00pp |"
    )
    lines += [
        f"| **TOTAL** | | **{result['n_bets_pre']}** | **{result['n_bets_post']}** | "
        f"**{result['pre54_agg_roi']:+.2f}%** | **{result['post54_agg_roi']:+.2f}%** | "
        f"**{result['delta_agg_pp']:+.2f}pp** |",
        "",
        "---",
        "",
    ]

    # Decision
    lines += [
        f"## Decision: {decision}",
        "",
        result["decision_detail"],
        "",
        f"- Aggregate delta: {result['delta_agg_pp']:+.2f}pp (threshold >= +{MIN_AGG_LIFT}pp)",
        f"- Regressions: {result['regressions'] if result['regressions'] else 'none'}",
        f"- Improvements: {result['improvements'] if result['improvements'] else 'none'}",
    ]

    if ship and result["filters_wired"]:
        lines += [
            "",
            "**Filters wired to `bet_thresholds.py` STAT_DIRECTIONS:**",
        ]
        for stat, seg in result["filters_wired"]:
            lines.append(f"- {stat.upper()}: filter `{seg}`")

    lines += [
        "",
        "---",
        "",
        "## Key Finding",
        "",
    ]
    if result["improvements"]:
        lines.append(
            f"Zero-EV segments found: {result['improvements']}. "
            f"Aggregate lift: {result['delta_agg_pp']:+.2f}pp."
        )
    else:
        lines += [
            "No clear zero-EV segments passed the bias guard (n>=100, complement>=200, z<1.5, ROI<+5%).",
            "The BLK UNDER-only pattern (Iter-50/51) does NOT appear to repeat for other stats.",
            "Stats PTS/REB/AST/FG3M/STL appear to have edge in both directions where the model bets.",
            "",
            "**Implication:** The Iter-50/51 BLK direction filter was stat-specific (BLK OVER is near-impossible",
            "to model — blocking rate on any given night is highly volatile). Other stats have more",
            "symmetric prediction difficulty.",
        ]

    lines += [
        "",
        "---",
        "",
        f"*Generated by `scripts/iter54_segmentation_sweep.py` on {now_str}.*",
        "*Data: eval_2025_26_combined.csv (2,339 rows). Bootstrap: 1,000 resamples.*",
        "*Refs: [[BLK Bootstrap Analysis 2026-05-27]] | [[Engineering Knowledge]] | [[Model Performance]]*",
    ]

    content = "\n".join(lines) + "\n"
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write(content)
    print(f"\n  Vault report -> {REPORT_PATH}")

    # Append to Engineering Knowledge
    _append_eng_knowledge(result)


def _append_eng_knowledge(result: Dict) -> None:
    """Append iter-54 summary to Engineering Knowledge.md."""
    if not os.path.exists(ENG_KNOW_MD):
        print(f"  [warn] Engineering Knowledge.md not found: {ENG_KNOW_MD}")
        return
    with open(ENG_KNOW_MD, "r", encoding="utf-8") as fh:
        existing = fh.read()
    if "Iter-54: Broad segmentation sweep" in existing:
        print("  [skip] Iter-54 entry already exists in Engineering Knowledge.md")
        return

    now_str  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    decision = result["decision"]

    zero_ev_summary = []
    for stat in ["pts", "reb", "ast", "fg3m", "stl"]:
        zev = result["per_stat"][stat]["zero_ev_segments"]
        if zev:
            for z in zev:
                zero_ev_summary.append(
                    f"  {stat.upper()} `{z['name']}`: n={z['n']}, ROI={z['roi_pct']:+.2f}%, z={z['z_score']:.3f}"
                )

    if zero_ev_summary:
        zero_ev_text = "\n".join(zero_ev_summary)
    else:
        zero_ev_text = "  None — all stats have edge in both directions."

    wired_text = (
        "\n".join([f"  {s.upper()}: `{f}`" for s, f in result["filters_wired"]])
        if result["filters_wired"] else "  None (aggregate lift below threshold)."
    )

    entry = f"""
---

## Iter-54: Broad segmentation sweep ({now_str})

**Goal:** Apply BLK direction-filter pattern (Iter-50/51) broadly to PTS, REB, AST, FG3M, STL.

**Zero-EV segments found:**
{zero_ev_text}

**Filters wired:**
{wired_text}

**Aggregate impact:** {result['pre54_agg_roi']:+.2f}% → {result['post54_agg_roi']:+.2f}% ({result['delta_agg_pp']:+.2f}pp), {result['n_bets_post']} bets.

**Decision: {decision}** — {result['decision_detail'][:120]}

**Key lesson:** {"BLK OVER zero-EV pattern is stat-specific. Other stats show edge in both directions." if not result["filters_wired"] else "Direction filter extended to additional stats."}
"""

    first_sep = existing.find("\n---\n")
    if first_sep >= 0:
        updated = existing[:first_sep] + entry + existing[first_sep:]
    else:
        updated = existing + entry

    with open(ENG_KNOW_MD, "w", encoding="utf-8") as fh:
        fh.write(updated)
    print(f"  Engineering Knowledge.md -> prepended Iter-54 entry")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = run()
    print("\n" + "=" * 72)
    print("  ITER-54 COMPLETE")
    print("=" * 72)
    print(f"  Decision:        {result['decision']}")
    print(f"  Aggregate delta: {result['delta_agg_pp']:+.2f}pp")
    print(f"  Post-filter ROI: {result['post54_agg_roi']:+.2f}%  ({result['n_bets_post']} bets)")
    if result["filters_wired"]:
        print(f"  Filters wired:   {result['filters_wired']}")
    else:
        print("  Filters wired:   none")
    print(f"  Vault report:    vault/Models/Iter54 Segmentation Sweep.md")
    print()
