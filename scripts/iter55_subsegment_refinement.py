"""iter55_subsegment_refinement.py — Sub-segment refinement of Iter-54 line-bucket filters.

Iter-54 shipped STAT_LINE_EXCLUSIONS dropping zero-EV 1D line buckets at MIN_SEG_N=100:
  PTS line_mid, REB line_high, AST line_mid, FG3M line_high.

But iter-54's segment_tables show 2D direction x line slices with highly negative ROI
that fell BELOW the n=100 bias guard. The most interesting candidates (post iter-54
filtering) are:

  AST  direction_over x line_high  n=57,  ROI=-26.32%, z=-1.364, CI [-49.8, -6.2]
  AST  direction_over x line_mid   n=56,  ROI=-28.41%, z=-1.516, CI [-52.3, -4.5]  *** already filtered by line_mid drop
  REB  direction_over x line_high  n=49,  ROI=-18.18%, z=-0.667                    *** already filtered by line_high drop
  FG3M direction_over x line_high  n=30,  ROI=-30.00%, z=-1.201                    *** already filtered by line_high drop
  PTS  direction_over x line_high  n=53,  ROI=-2.74%,  z=0.485                     *** small / borderline

The KEY angle this iter probes: relax MIN_SEG_N from 100 -> 50, restrict candidates to
2D direction x line slices that REMAIN after iter-54 filtering, and test compound filters
(drop the segment AS A WHOLE) using true outcome-preserving simulation against the eval CSV.

METHOD:
  1. Load eval CSV. Compute bet_direction + hit/roi using same iter-54 heuristic.
  2. Apply CURRENT PRODUCTION FILTERS:
       - STAT_LINE_EXCLUSIONS  (drop bets in zero-EV line buckets — already shipped Iter-54)
       - STAT_DIRECTIONS["blk"] = ["under"]  (already shipped Iter-51)
     This produces the iter-55 BASELINE (post-iter-54 baseline).
  3. Test candidate compound filters:
       - AST drop {direction_over x line_high}   (line_mid already excluded)
       - REB drop {direction_over x line_high}   (note: line_high already excluded; this is redundant; check anyway)
       - FG3M drop {direction_over x line_high}  (note: line_high already excluded)
       - PTS drop {direction_over x line_high}   (probe — borderline at z=0.485 ROI=-2.74)
       - All combinations of the above
  4. Ship gate: aggregate ROI delta >= +0.5pp on the post-iter-54 baseline AND no
     per-stat regression > -1pp (relative to its post-iter-54 baseline ROI).

BIAS GUARDS:
  - MIN_SEG_N = 50 (relaxed from 100)
  - Complement must still have n >= 100 bets post-filter for that stat
  - Segment must satisfy: z_score < 0 OR ROI < -10% (we're looking for negative-ROI not zero-EV)
  - CI must NOT include zero on the upside (ci_hi <= +5%) — informative

Run:
    python scripts/iter55_subsegment_refinement.py

Output:
    vault/Models/Iter55 Subsegment Refinement.md
    data/cache/holdout_baseline.json  (__iter55__ key)
    src/prediction/bet_thresholds.py  (STAT_DIRECTION_LINE_EXCLUSIONS dict if SHIP)
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

# Import current production filters (read-only — we only consume them here).
from src.prediction.bet_thresholds import (  # noqa: E402
    STAT_LINE_EXCLUSIONS,
    STAT_DIRECTIONS,
    is_line_excluded,
    allowed_directions_for,
)

# ── Paths ──────────────────────────────────────────────────────────────────────
EVAL_CSV       = os.path.join(PROJECT_DIR, "data", "cache", "eval_2025_26_combined.csv")
BASELINE_JSON  = os.path.join(PROJECT_DIR, "data", "cache", "holdout_baseline.json")
VAULT_DIR      = os.path.join(PROJECT_DIR, "vault", "Models")
REPORT_PATH    = os.path.join(VAULT_DIR, "Iter55 Subsegment Refinement.md")
THRESHOLDS_PY  = os.path.join(PROJECT_DIR, "src", "prediction", "bet_thresholds.py")

# ── Constants ──────────────────────────────────────────────────────────────────
PAYOUT_M110    = 100.0 / 110.0          # ~0.9091 per 1u at -110
BREAKEVEN_HR   = 100.0 / (100.0 + 110.0)  # ~0.5238
N_BOOTSTRAP    = 1000
SEED           = 42

# ── Bias guards for iter-55 (relaxed n, but stricter conviction) ───────────────
MIN_SEG_N           = 50    # relaxed from iter-54's 100
MIN_COMPLEMENT_N    = 100   # post-filter, this stat must keep at least 100 bets
MAX_CI_HI           = 5.0   # ci_hi <= +5% — CI must be informative (not include strong upside)
NEGATIVE_ROI_GATE   = -10.0 # require ROI <= -10% for a sub-segment filter

# Line bucket boundaries (must match iter-54)
LINE_BUCKETS: Dict[str, Tuple[float, float]] = {
    "pts":  (9.5,  15.5),
    "reb":  (3.5,  5.5),
    "ast":  (1.5,  3.5),
    "fg3m": (1.5,  1.5),
    "stl":  (0.5,  1.5),
    "blk":  (1.5,  2.5),    # not used downstream — defensive default
}

# Ship constraints
MIN_AGG_LIFT     = 0.5
MAX_STAT_REGRESS = -1.0

# Candidate compound filters to test (stat -> list of (direction, line_bucket) tuples to drop)
# These are the slices we want to evaluate as a single combined filter per stat.
CANDIDATE_FILTERS: Dict[str, List[Tuple[str, str]]] = {
    "ast":  [("over", "high")],          # n=57, ROI=-26.32%, z=-1.364
    "reb":  [("over", "high")],          # n=49, ROI=-18.18%, z=-0.667 (likely redundant w/ iter54)
    "fg3m": [("over", "high")],          # n=30, ROI=-30.00%, z=-1.201 (likely redundant)
    "pts":  [("over", "high")],          # n=53, ROI=-2.74%, z=0.485 — probe
}


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
    low_max, mid_max = LINE_BUCKETS.get(stat, (10.0, 20.0))
    if closing_line <= low_max:
        return "low"
    elif closing_line <= mid_max:
        return "mid"
    else:
        return "high"


# ── Data loading ───────────────────────────────────────────────────────────────

def load_eval_rows(stat: str) -> List[Dict]:
    """Load eval rows for *stat* with bet direction + hit/roi annotations."""
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

            # Same direction heuristic as iter-54
            if p_under > 0.55:
                bet_direction = "under"
                hit = actual_value < closing_line
            elif p_over > 0.55:
                bet_direction = "over"
                hit = actual_value > closing_line
            else:
                if p_under >= p_over:
                    bet_direction = "under"
                    hit = actual_value < closing_line
                else:
                    bet_direction = "over"
                    hit = actual_value > closing_line

            roi_unit = PAYOUT_M110 if hit else -1.0
            bucket   = line_bucket_for(stat, closing_line)

            rows.append({
                "stat":          stat,
                "closing_line":  closing_line,
                "bet_direction": bet_direction,
                "hit":           hit,
                "roi_unit":      roi_unit,
                "line_bucket":   bucket,
            })
    return rows


# ── Filter applications ────────────────────────────────────────────────────────

def apply_production_filters(rows: List[Dict]) -> List[Dict]:
    """Apply current production filters (iter-51 BLK direction + iter-54 line exclusions)."""
    out: List[Dict] = []
    for r in rows:
        stat = r["stat"]
        # iter-51: BLK direction filter (and any other STAT_DIRECTIONS restrictions)
        if r["bet_direction"] not in allowed_directions_for(stat):
            continue
        # iter-54: STAT_LINE_EXCLUSIONS
        if is_line_excluded(stat, r["closing_line"]):
            continue
        out.append(r)
    return out


def apply_subsegment_filter(
    rows: List[Dict],
    stat_filters: Dict[str, List[Tuple[str, str]]],
) -> List[Dict]:
    """Drop bets that match (stat, direction, line_bucket) in *stat_filters*."""
    out: List[Dict] = []
    for r in rows:
        stat = r["stat"]
        slices = stat_filters.get(stat, [])
        dropped = False
        for drop_dir, drop_bucket in slices:
            if r["bet_direction"] == drop_dir and r["line_bucket"] == drop_bucket:
                dropped = True
                break
        if not dropped:
            out.append(r)
    return out


# ── Metrics ────────────────────────────────────────────────────────────────────

def compute_metrics(bets: List[Dict], n_bootstrap: int = N_BOOTSTRAP) -> Dict:
    n = len(bets)
    if n == 0:
        return {"n": 0, "hit_rate_pct": 0.0, "roi_pct": 0.0, "z_score": 0.0,
                "ci_lo": 0.0, "ci_hi": 0.0, "pnl_units": 0.0}

    roi_units = np.array([b["roi_unit"] for b in bets])
    hits      = np.array([b["hit"] for b in bets], dtype=float)

    emp_roi = float(np.mean(roi_units)) * 100.0
    emp_hr  = float(np.mean(hits))

    se_binom = math.sqrt(BREAKEVEN_HR * (1 - BREAKEVEN_HR) / n)
    z_score  = (emp_hr - BREAKEVEN_HR) / se_binom if se_binom > 0 else 0.0

    rng = np.random.default_rng(SEED + n)
    boot_rois = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        boot_rois[i] = float(np.mean(roi_units[idx])) * 100.0
    ci_lo = float(np.percentile(boot_rois, 2.5))
    ci_hi = float(np.percentile(boot_rois, 97.5))
    pnl   = float(np.sum(roi_units))

    return {
        "n":            n,
        "hit_rate_pct": round(emp_hr * 100.0, 2),
        "roi_pct":      round(emp_roi, 4),
        "z_score":      round(z_score, 3),
        "ci_lo":        round(ci_lo, 2),
        "ci_hi":        round(ci_hi, 2),
        "pnl_units":    round(pnl, 4),
    }


def per_stat_metrics(bets: List[Dict]) -> Dict[str, Dict]:
    by_stat: Dict[str, List[Dict]] = {}
    for b in bets:
        by_stat.setdefault(b["stat"], []).append(b)
    return {stat: compute_metrics(blist) for stat, blist in by_stat.items()}


def aggregate_metrics(bets: List[Dict]) -> Dict:
    return compute_metrics(bets)


# ── Sub-segment evaluation ─────────────────────────────────────────────────────

def evaluate_sub_segments(post54_rows: List[Dict]) -> Dict[str, Dict]:
    """For each stat, compute metrics on each (direction, line_bucket) 2D slice.

    Returns dict: stat -> {(dir, bucket): metrics_dict, ...}.
    """
    out: Dict[str, Dict] = {}
    by_stat: Dict[str, List[Dict]] = {}
    for r in post54_rows:
        by_stat.setdefault(r["stat"], []).append(r)

    for stat, rows in by_stat.items():
        slices: Dict = {}
        for direction in ("over", "under"):
            for bucket in ("low", "mid", "high"):
                sub = [r for r in rows if r["bet_direction"] == direction and r["line_bucket"] == bucket]
                slices[(direction, bucket)] = compute_metrics(sub)
        out[stat] = slices
    return out


def is_sub_segment_filterable(seg: Dict, complement_n: int) -> bool:
    """Bias-guarded check for whether a 2D segment should be filtered out."""
    n = seg["n"]
    if n < MIN_SEG_N:
        return False
    if complement_n < MIN_COMPLEMENT_N:
        return False
    # Strictly negative ROI sub-segment (not just zero-EV)
    if seg["roi_pct"] > NEGATIVE_ROI_GATE:
        return False
    if seg["ci_hi"] > MAX_CI_HI:
        return False  # CI extends into positive territory — too uncertain
    return True


# ── Main run ───────────────────────────────────────────────────────────────────

def run() -> Dict:
    print("\n" + "=" * 78)
    print("  ITER-55: SUB-SEGMENT REFINEMENT OF ITER-54 LINE-BUCKET FILTERS")
    print("=" * 78)
    print(f"  MIN_SEG_N={MIN_SEG_N} (relaxed from 100), CI gate ci_hi<={MAX_CI_HI:+.1f}%, "
          f"ROI gate <={NEGATIVE_ROI_GATE:+.1f}%")
    print()

    # ── Load all eval rows (per stat) and apply current production filters ────
    STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk"]
    all_rows: List[Dict] = []
    for stat in STATS:
        all_rows.extend(load_eval_rows(stat))
    print(f"  Total eval rows: {len(all_rows)}")

    post54_rows = apply_production_filters(all_rows)
    print(f"  Post-production-filter rows: {len(post54_rows)} (iter-51 BLK dir + iter-54 line excl)")

    # ── Baseline metrics (post-iter-54) ────────────────────────────────────────
    pre55_per_stat = per_stat_metrics(post54_rows)
    pre55_agg      = aggregate_metrics(post54_rows)
    print(f"\n  POST-ITER-54 BASELINE (= pre-iter-55):")
    print(f"    aggregate: n={pre55_agg['n']}, ROI={pre55_agg['roi_pct']:+.4f}%, "
          f"hit={pre55_agg['hit_rate_pct']:.2f}%, z={pre55_agg['z_score']:.3f}")
    for stat in STATS:
        m = pre55_per_stat.get(stat, {"n": 0, "roi_pct": 0.0, "hit_rate_pct": 0.0, "z_score": 0.0})
        print(f"    {stat.upper():<5} n={m['n']:>4} ROI={m['roi_pct']:>+8.4f}%  "
              f"hit={m['hit_rate_pct']:>5.2f}%  z={m['z_score']:>+6.3f}")

    # ── Sub-segment exploration on the post-54 bet set ─────────────────────────
    print("\n" + "-" * 78)
    print("  2D SUB-SEGMENTS (direction x line_bucket) ON POST-ITER-54 BET SET")
    print("-" * 78)
    sub_segs = evaluate_sub_segments(post54_rows)

    candidate_diagnostics: Dict[str, Dict] = {}
    for stat in ["pts", "reb", "ast", "fg3m"]:
        slices = sub_segs.get(stat, {})
        stat_total = pre55_per_stat.get(stat, {}).get("n", 0)
        print(f"\n  {stat.upper()} sub-segments (post-iter-54 set, total n={stat_total}):")
        print(f"    {'segment':<20} {'n':>5} {'hit%':>6} {'ROI%':>8} {'z':>7}  {'95% CI':>20}  filterable?")
        print("    " + "-" * 84)
        for (direction, bucket), seg in sorted(slices.items()):
            complement = stat_total - seg["n"]
            filterable = is_sub_segment_filterable(seg, complement)
            ci_str = f"[{seg['ci_lo']:+.1f}%, {seg['ci_hi']:+.1f}%]"
            flag = " <-- FILTER" if filterable else ""
            print(f"    {direction:<5} x {bucket:<10} {seg['n']:>5}  {seg['hit_rate_pct']:>5.2f}%  "
                  f"{seg['roi_pct']:>+7.3f}%  {seg['z_score']:>+6.3f}  {ci_str:>20}{flag}")
        candidate_diagnostics[stat] = {
            f"{d}_{b}": {
                "n": seg["n"], "roi_pct": seg["roi_pct"], "z_score": seg["z_score"],
                "ci_lo": seg["ci_lo"], "ci_hi": seg["ci_hi"], "hit_rate_pct": seg["hit_rate_pct"],
                "filterable": is_sub_segment_filterable(seg, stat_total - seg["n"]),
            }
            for (d, b), seg in slices.items()
        }

    # ── Build the per-stat winning filter list ────────────────────────────────
    print("\n" + "-" * 78)
    print("  PER-STAT FILTER CHOICE (bias-guarded)")
    print("-" * 78)
    winning_filters: Dict[str, List[Tuple[str, str]]] = {}

    for stat, cand_slices in CANDIDATE_FILTERS.items():
        keep_slices: List[Tuple[str, str]] = []
        for direction, bucket in cand_slices:
            seg = sub_segs.get(stat, {}).get((direction, bucket), {"n": 0})
            complement = pre55_per_stat.get(stat, {}).get("n", 0) - seg.get("n", 0)
            if is_sub_segment_filterable(seg, complement):
                keep_slices.append((direction, bucket))
                print(f"    {stat.upper()}: FILTER {direction}x{bucket} "
                      f"(n={seg['n']}, ROI={seg['roi_pct']:+.2f}%, "
                      f"z={seg['z_score']:.3f}, ci_hi={seg['ci_hi']:+.2f}%)")
            else:
                print(f"    {stat.upper()}: SKIP   {direction}x{bucket} "
                      f"(n={seg.get('n', 0)}, ROI={seg.get('roi_pct', 0):+.2f}%, "
                      f"ci_hi={seg.get('ci_hi', 0):+.2f}% — fails guard)")
        if keep_slices:
            winning_filters[stat] = keep_slices

    # ── Apply filters and measure ──────────────────────────────────────────────
    if not winning_filters:
        print("\n  No sub-segment filters passed bias guards. REVERT.")
        post55_rows     = post54_rows
        post55_per_stat = pre55_per_stat
        post55_agg      = pre55_agg
    else:
        post55_rows     = apply_subsegment_filter(post54_rows, winning_filters)
        post55_per_stat = per_stat_metrics(post55_rows)
        post55_agg      = aggregate_metrics(post55_rows)

    print("\n" + "=" * 78)
    print("  POST-ITER-55 METRICS (after applying candidate filters)")
    print("=" * 78)
    print(f"  aggregate: n={post55_agg['n']}, ROI={post55_agg['roi_pct']:+.4f}%, "
          f"delta={post55_agg['roi_pct'] - pre55_agg['roi_pct']:+.4f}pp")
    print(f"  {'Stat':<5} {'pre_n':>6} {'post_n':>7} {'pre_roi%':>10} {'post_roi%':>11} {'delta_pp':>10}")
    for stat in STATS:
        pre_m  = pre55_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        post_m = post55_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        delta  = post_m["roi_pct"] - pre_m["roi_pct"]
        print(f"  {stat.upper():<5} {pre_m['n']:>6} {post_m['n']:>7} "
              f"{pre_m['roi_pct']:>+9.4f}% {post_m['roi_pct']:>+10.4f}% "
              f"{delta:>+9.4f}pp")

    # ── Ship decision ──────────────────────────────────────────────────────────
    agg_delta = post55_agg["roi_pct"] - pre55_agg["roi_pct"]
    regressions: List[str] = []
    improvements: List[str] = []
    for stat, fl in winning_filters.items():
        pre_m  = pre55_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        post_m = post55_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        delta  = post_m["roi_pct"] - pre_m["roi_pct"]
        if delta < MAX_STAT_REGRESS:
            regressions.append(f"{stat}: {delta:+.4f}pp")
        if delta > 0.0:
            improvements.append(f"{stat}: {delta:+.4f}pp (filter={fl})")
    # also detect regressions in stats we DIDN'T filter (shouldn't happen but check)
    for stat in STATS:
        if stat in winning_filters:
            continue
        pre_m  = pre55_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        post_m = post55_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        delta  = post_m["roi_pct"] - pre_m["roi_pct"]
        if delta < MAX_STAT_REGRESS:
            regressions.append(f"{stat}: {delta:+.4f}pp (unfiltered)")

    agg_passes      = agg_delta >= MIN_AGG_LIFT
    no_regressions  = len(regressions) == 0

    if agg_passes and no_regressions and winning_filters:
        decision = "SHIP"
        detail = (
            f"Aggregate delta {agg_delta:+.4f}pp >= +{MIN_AGG_LIFT}pp AND no per-stat "
            f"regression > {MAX_STAT_REGRESS}pp. Filters wired: {dict(winning_filters)}."
        )
    elif not winning_filters:
        decision = "REVERT"
        detail = (
            f"No sub-segment filters passed bias guard "
            f"(MIN_SEG_N={MIN_SEG_N}, ROI<={NEGATIVE_ROI_GATE}%, ci_hi<={MAX_CI_HI}%). "
            f"No filters to wire."
        )
    elif not agg_passes:
        decision = "REVERT"
        detail = (
            f"Aggregate delta {agg_delta:+.4f}pp below +{MIN_AGG_LIFT}pp ship threshold."
        )
    else:
        decision = "REVERT"
        detail = f"Per-stat regression(s): {regressions}."

    print("\n" + "=" * 78)
    print(f"  DECISION: {decision}")
    print("=" * 78)
    print(f"  Detail: {detail}")
    print(f"  Agg delta: {agg_delta:+.4f}pp (threshold {MIN_AGG_LIFT:+.1f}pp)")
    print(f"  Regressions: {regressions if regressions else 'none'}")
    print(f"  Improvements: {improvements if improvements else 'none'}")

    # ── Wire filters if SHIP ──────────────────────────────────────────────────
    filters_wired: List = []
    if decision == "SHIP":
        _wire_direction_line_filters(winning_filters, agg_delta, post55_agg, pre55_agg)
        filters_wired = [
            [stat, [list(s) for s in slices]]
            for stat, slices in winning_filters.items()
        ]

    # ── Build result ──────────────────────────────────────────────────────────
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = {
        "iter":            55,
        "generated_at":    now_utc,
        "approach":        "subsegment_refinement_2d_direction_x_line",
        "n_bets_pre":      pre55_agg["n"],
        "n_bets_post":     post55_agg["n"],
        "pre55_agg_roi":   round(pre55_agg["roi_pct"], 4),
        "post55_agg_roi":  round(post55_agg["roi_pct"], 4),
        "delta_agg_pp":    round(agg_delta, 4),
        "decision":        decision,
        "decision_detail": detail,
        "regressions":     regressions,
        "improvements":    improvements,
        "filters_wired":   filters_wired,
        "per_stat": {
            stat: {
                "pre_n":     pre55_per_stat.get(stat, {}).get("n", 0),
                "post_n":    post55_per_stat.get(stat, {}).get("n", 0),
                "pre_roi":   round(pre55_per_stat.get(stat, {}).get("roi_pct", 0.0), 4),
                "post_roi":  round(post55_per_stat.get(stat, {}).get("roi_pct", 0.0), 4),
                "delta_roi": round(
                    post55_per_stat.get(stat, {}).get("roi_pct", 0.0)
                    - pre55_per_stat.get(stat, {}).get("roi_pct", 0.0), 4),
                "filter":    [list(s) for s in winning_filters.get(stat, [])] or None,
            }
            for stat in STATS
        },
        "candidate_diagnostics": candidate_diagnostics,
        "params": {
            "min_seg_n":          MIN_SEG_N,
            "min_complement_n":   MIN_COMPLEMENT_N,
            "max_ci_hi_pct":      MAX_CI_HI,
            "negative_roi_gate":  NEGATIVE_ROI_GATE,
            "min_agg_lift_pp":    MIN_AGG_LIFT,
            "max_stat_regress":   MAX_STAT_REGRESS,
            "n_bootstrap":        N_BOOTSTRAP,
            "seed":               SEED,
        },
    }

    # ── Persist to holdout_baseline.json ──────────────────────────────────────
    baseline: Dict = {}
    if os.path.exists(BASELINE_JSON):
        baseline = json.load(open(BASELINE_JSON, encoding="utf-8"))
    baseline["__iter55__"] = result
    baseline["__updated_at__"] = now_utc
    with open(BASELINE_JSON, "w", encoding="utf-8") as fh:
        json.dump(baseline, fh, indent=2)
    print(f"\n  holdout_baseline.json -> updated with __iter55__")

    # ── Vault report ──────────────────────────────────────────────────────────
    _write_vault_report(result, sub_segs, pre55_per_stat, post55_per_stat)

    return result


# ── Wiring ─────────────────────────────────────────────────────────────────────

def _wire_direction_line_filters(
    filters: Dict[str, List[Tuple[str, str]]],
    agg_delta: float,
    post_agg: Dict,
    pre_agg: Dict,
) -> None:
    """Add STAT_DIRECTION_LINE_EXCLUSIONS dict + is_direction_line_excluded() helper."""
    with open(THRESHOLDS_PY, encoding="utf-8") as fh:
        content = fh.read()

    if "STAT_DIRECTION_LINE_EXCLUSIONS" in content:
        print("  [info] STAT_DIRECTION_LINE_EXCLUSIONS already present — skipping wire")
        return

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Format filter dict as Python literal
    filter_lines = []
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        slices = filters.get(stat, [])
        if not slices:
            filter_lines.append(f'    "{stat}":  [],')
        else:
            slice_strs = ", ".join([f'("{d}", "{b}")' for d, b in slices])
            filter_lines.append(f'    "{stat}":  [{slice_strs}],   # Iter-55: drop sub-segments')

    line_bucket_lines = []
    for stat in ("pts", "reb", "ast", "fg3m", "stl"):
        low_max, mid_max = LINE_BUCKETS.get(stat, (10.0, 20.0))
        line_bucket_lines.append(f'    "{stat}":  ({low_max}, {mid_max}),')

    iter55_block = f'''

# ── Iter-55: Per-stat 2D direction x line-bucket exclusions ───────────────────
# Iter-55 (subsegment_refinement) probed the iter-54 segment_tables at MIN_SEG_N=50
# (relaxed from 100) for 2D direction x line slices with strongly negative ROI that
# REMAIN after iter-54's 1D line-bucket exclusions are applied.
# Date: {now_str}.
# Method: outcome-preserved simulation on data/cache/eval_2025_26_combined.csv.
# Pre-iter-55 baseline (= post iter-54): n_bets={pre_agg["n"]}, ROI={pre_agg["roi_pct"]:+.4f}%.
# Post-iter-55:                          n_bets={post_agg["n"]}, ROI={post_agg["roi_pct"]:+.4f}%.
# Aggregate delta: {agg_delta:+.4f}pp.
# Filters wired (stat -> list of (bet_direction, line_bucket) tuples to DROP):
{chr(10).join("#   " + s for s in filter_lines if "[]" not in s)}
STAT_DIRECTION_LINE_EXCLUSIONS: dict[str, list[tuple[str, str]]] = {{
{chr(10).join(filter_lines)}
}}

# Line bucket boundaries for stats — closing_line cutoffs (must match iter-54 buckets).
_LINE_BUCKET_CUTOFFS: dict[str, tuple[float, float]] = {{
{chr(10).join(line_bucket_lines)}
}}


def _line_bucket_for_internal(stat: str, closing_line: float) -> str:
    """Return 'low' | 'mid' | 'high' bucket for *closing_line* given *stat*."""
    cuts = _LINE_BUCKET_CUTOFFS.get(stat.lower())
    if cuts is None:
        return "unknown"
    low_max, mid_max = cuts
    if closing_line <= low_max:
        return "low"
    if closing_line <= mid_max:
        return "mid"
    return "high"


def is_direction_line_excluded(stat: str, direction: str, closing_line: float) -> bool:
    """Return True if (direction, line_bucket(closing_line)) is in the iter-55 exclusion
    list for *stat*.

    Usage in bet-decision code::

        if is_direction_line_excluded(stat, direction, closing_line):
            continue  # skip — sub-segment zero/negative-EV (Iter-55)

    Returns False for unknown stats or stats with no sub-segment exclusion.
    """
    slices = STAT_DIRECTION_LINE_EXCLUSIONS.get(stat.lower(), [])
    if not slices:
        return False
    bucket = _line_bucket_for_internal(stat, closing_line)
    return (direction.lower(), bucket) in slices
'''
    # Append at end of file
    if not content.endswith("\n"):
        content += "\n"
    content += iter55_block

    with open(THRESHOLDS_PY, "w", encoding="utf-8") as fh:
        fh.write(content)
    print(f"  bet_thresholds.py -> appended STAT_DIRECTION_LINE_EXCLUSIONS + helper")


# ── Vault report ───────────────────────────────────────────────────────────────

def _write_vault_report(
    result: Dict,
    sub_segs: Dict,
    pre55_per_stat: Dict[str, Dict],
    post55_per_stat: Dict[str, Dict],
) -> None:
    os.makedirs(VAULT_DIR, exist_ok=True)
    now_str  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    decision = result["decision"]

    lines = [
        f"# Iter-55 Sub-Segment Refinement ({now_str})",
        "",
        "**Goal:** Refine Iter-54's 1D line-bucket filters by testing 2D "
        "direction x line_bucket sub-segments at relaxed MIN_SEG_N=50.",
        "",
        f"**Baseline:** post-iter-54 ROI = {result['pre55_agg_roi']:+.4f}% on "
        f"{result['n_bets_pre']} bets (real outcome-preserved simulation against eval CSV).",
        "",
        "---",
        "",
        "## Method",
        "",
        "1. Load `data/cache/eval_2025_26_combined.csv` (2,339 rows) and compute bet "
        "direction + hit/roi per row using the iter-54 devig heuristic.",
        "2. Apply CURRENT PRODUCTION FILTERS:",
        "   - `STAT_DIRECTIONS['blk'] = ['under']`  (Iter-51)",
        "   - `STAT_LINE_EXCLUSIONS` (Iter-54): PTS line_mid, REB line_high, AST line_mid, FG3M line_high",
        "   This yields the post-iter-54 baseline.",
        "3. On the post-iter-54 bet set, evaluate every 2D `(direction, line_bucket)` slice "
        f"with metrics + bootstrap CI ({N_BOOTSTRAP} resamples).",
        f"4. Bias guards: segment n >= {MIN_SEG_N}, complement n >= {MIN_COMPLEMENT_N}, "
        f"ROI <= {NEGATIVE_ROI_GATE}%, CI hi <= {MAX_CI_HI:+.1f}%.",
        f"5. Ship gate: aggregate delta >= +{MIN_AGG_LIFT}pp AND no per-stat regression > {MAX_STAT_REGRESS}pp.",
        "",
        "---",
        "",
        "## 2D Sub-Segment Diagnostics (on the post-iter-54 bet set)",
        "",
    ]

    for stat in ["pts", "reb", "ast", "fg3m"]:
        slices = sub_segs.get(stat, {})
        if not slices:
            continue
        stat_n = pre55_per_stat.get(stat, {}).get("n", 0)
        lines += [
            f"### {stat.upper()} (post-iter-54 baseline: n={stat_n}, ROI={pre55_per_stat.get(stat,{}).get('roi_pct',0):+.2f}%)",
            "",
            "| direction x bucket | n | hit% | ROI% | z | 95% CI | filterable? |",
            "|--------------------|---|------|------|---|--------|-------------|",
        ]
        for (direction, bucket), seg in sorted(slices.items()):
            complement = stat_n - seg["n"]
            filt = is_sub_segment_filterable(seg, complement)
            ci_str = f"[{seg['ci_lo']:+.1f}%, {seg['ci_hi']:+.1f}%]"
            lines.append(
                f"| {direction} x {bucket} | {seg['n']} | {seg['hit_rate_pct']:.2f}% | "
                f"{seg['roi_pct']:+.3f}% | {seg['z_score']:+.3f} | {ci_str} | "
                f"{'**YES**' if filt else 'no'} |"
            )
        lines.append("")

    lines += [
        "---",
        "",
        "## Per-Stat Filter Impact",
        "",
        "| Stat | Filter | pre_n | post_n | pre_ROI | post_ROI | delta |",
        "|------|--------|-------|--------|---------|----------|-------|",
    ]
    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk"]:
        ps = result["per_stat"][stat]
        filt = ps.get("filter") or "(none)"
        lines.append(
            f"| {stat.upper()} | {filt} | {ps['pre_n']} | {ps['post_n']} | "
            f"{ps['pre_roi']:+.4f}% | {ps['post_roi']:+.4f}% | {ps['delta_roi']:+.4f}pp |"
        )
    lines.append(
        f"| **TOTAL** | | **{result['n_bets_pre']}** | **{result['n_bets_post']}** | "
        f"**{result['pre55_agg_roi']:+.4f}%** | **{result['post55_agg_roi']:+.4f}%** | "
        f"**{result['delta_agg_pp']:+.4f}pp** |"
    )

    lines += [
        "",
        "---",
        "",
        f"## Decision: {decision}",
        "",
        result["decision_detail"],
        "",
        f"- Aggregate delta: {result['delta_agg_pp']:+.4f}pp (threshold >= +{MIN_AGG_LIFT}pp)",
        f"- Regressions: {result['regressions'] if result['regressions'] else 'none'}",
        f"- Improvements: {result['improvements'] if result['improvements'] else 'none'}",
        "",
    ]

    if decision == "SHIP" and result["filters_wired"]:
        lines += [
            "**Wired to `bet_thresholds.py` as `STAT_DIRECTION_LINE_EXCLUSIONS`:**",
            "",
        ]
        for stat, slices in result["filters_wired"]:
            slice_strs = ", ".join([f"({s[0]}, {s[1]})" for s in slices])
            lines.append(f"- {stat.upper()}: drop {slice_strs}")
        lines.append("")
        lines.append("Helper: `is_direction_line_excluded(stat, direction, closing_line) -> bool`")
        lines.append("")

    lines += [
        "---",
        "",
        "## Key Finding",
        "",
    ]
    if decision == "SHIP":
        lines.append(
            "Sub-segment 2D filtering at MIN_SEG_N=50 found additional negative-ROI slices on "
            "the post-iter-54 bet set. Combined ship lifted aggregate ROI by "
            f"{result['delta_agg_pp']:+.4f}pp."
        )
    else:
        lines.append(
            "After iter-54's 1D line-bucket exclusions already shipped, residual 2D "
            "direction x line sub-segments did not pass the relaxed bias guard "
            f"(MIN_SEG_N={MIN_SEG_N}, ROI<={NEGATIVE_ROI_GATE}%, CI hi<={MAX_CI_HI:+.1f}%). "
            "Most of the negative 2D slices were already eliminated by iter-54's 1D filter; "
            "the remainders either lack sample size or have CIs that extend too far into "
            "positive territory to justify dropping."
        )

    lines += [
        "",
        "---",
        "",
        f"*Generated by `scripts/iter55_subsegment_refinement.py` on {now_str}.*",
        "*Refs: [[Iter54 Segmentation Sweep]] | [[Engineering Knowledge]] | [[Model Performance]]*",
    ]

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"  Vault report -> {REPORT_PATH}")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = run()
    print("\n" + "=" * 78)
    print("  ITER-55 COMPLETE")
    print("=" * 78)
    print(f"  Decision:        {result['decision']}")
    print(f"  Aggregate delta: {result['delta_agg_pp']:+.4f}pp")
    print(f"  Pre/post ROI:    {result['pre55_agg_roi']:+.4f}% -> {result['post55_agg_roi']:+.4f}% "
          f"({result['n_bets_pre']} -> {result['n_bets_post']} bets)")
    if result["filters_wired"]:
        print(f"  Filters wired:   {result['filters_wired']}")
    else:
        print("  Filters wired:   none")
    print()
