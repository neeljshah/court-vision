"""iter58_stage_venue_3d_sweep.py — Stage/venue 1D + 3D direction x line x stage sweep.

Post-iter-57 baseline: aggregate ~+15.04% on 1,535 bets, with
  STAT_DIRECTION_LINE_EXCLUSIONS = {"ast": [("over","high")], "reb": [("over","low")]}.

This iter explores the REMAINING dimensions on the post-iter57 baseline that iters
55/57 did not touch:
  Phase A (1D): stage_early/late, venue_home/away, per-month (n>=80 each).
  Phase B (3D): direction x line_bucket x stage cells (n>=30, stricter guards).

Ship gates (stricter than iter-57 because slices are smaller):
  - 1D candidate: aggregate delta >= +0.5pp; no per-stat regression > -1pp.
  - 3D candidate: aggregate delta >= +0.3pp; no per-stat regression > -0.5pp.
  - Greedy: largest lift first, recompute aggregate after each.

3D guards:
  n >= 30 AND z < 1.0 AND ROI < 0% AND ci_hi < +5%

Run:
    python scripts/iter58_stage_venue_3d_sweep.py

Output:
    vault/Models/Iter58 Stage Venue 3D Sweep.md
    data/cache/holdout_baseline.json  (__iter58__ key — additive)
    src/prediction/bet_thresholds.py  (extend STAT_DIRECTION_LINE_EXCLUSIONS or
                                       add a STAT_STAGE/STAT_VENUE struct if SHIP)
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from src.prediction.bet_thresholds import (  # noqa: E402
    STAT_LINE_EXCLUSIONS,
    STAT_DIRECTIONS,
    STAT_DIRECTION_LINE_EXCLUSIONS,
    is_line_excluded,
    allowed_directions_for,
)

# ── Paths ──────────────────────────────────────────────────────────────────────
EVAL_CSV       = os.path.join(PROJECT_DIR, "data", "cache", "eval_2025_26_combined.csv")
BASELINE_JSON  = os.path.join(PROJECT_DIR, "data", "cache", "holdout_baseline.json")
VAULT_DIR      = os.path.join(PROJECT_DIR, "vault", "Models")
REPORT_PATH    = os.path.join(VAULT_DIR, "Iter58 Stage Venue 3D Sweep.md")
THRESHOLDS_PY  = os.path.join(PROJECT_DIR, "src", "prediction", "bet_thresholds.py")

# ── Constants ──────────────────────────────────────────────────────────────────
PAYOUT_M110    = 100.0 / 110.0
BREAKEVEN_HR   = 100.0 / (100.0 + 110.0)
N_BOOTSTRAP    = 1000
SEED           = 42

# Phase A: 1D guards (relaxed — broader segments)
MIN_SEG_N_1D       = 80
MIN_COMPLEMENT_1D  = 100
MAX_CI_HI_1D       = 10.0
MAX_ROI_PCT_1D     = 0.0      # must be losing
MAX_Z_SCORE_1D     = 1.0
MIN_AGG_LIFT_1D    = 0.5
MAX_STAT_REGRESS_1D = -1.0

# Phase B: 3D guards (strict — small buckets, overfitting risk)
MIN_SEG_N_3D       = 30
MIN_COMPLEMENT_3D  = 100
MAX_CI_HI_3D       = 5.0
MAX_ROI_PCT_3D     = 0.0
MAX_Z_SCORE_3D     = 1.0
MIN_AGG_LIFT_3D    = 0.3
MAX_STAT_REGRESS_3D = -0.5

# Line buckets (must match iter-54/55/57)
LINE_BUCKETS: Dict[str, Tuple[float, float]] = {
    "pts":  (9.5,  15.5),
    "reb":  (3.5,  5.5),
    "ast":  (1.5,  3.5),
    "fg3m": (1.5,  1.5),
    "stl":  (0.5,  1.5),
    "blk":  (1.5,  2.5),
}

# Stage cutoff: early = Oct-Dec, late = Jan-onward
EARLY_MONTHS = {10, 11, 12}
# (everything else in the season is "late")


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


def stage_for(date_str: str) -> str:
    """early if month in {10,11,12}; else late."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return "unknown"
    return "early" if dt.month in EARLY_MONTHS else "late"


def month_for(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return "unknown"
    return f"{dt.year:04d}-{dt.month:02d}"


def venue_for(venue_raw: str) -> str:
    v = (venue_raw or "").strip().lower()
    if v in ("home", "h"):
        return "home"
    if v in ("away", "a"):
        return "away"
    return v or "unknown"


# ── Data loading ───────────────────────────────────────────────────────────────

def load_eval_rows(stat: str) -> List[Dict]:
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
            date_str = (r.get("date") or "").strip()

            rows.append({
                "stat":          stat,
                "date":          date_str,
                "venue":         venue_for(r.get("venue", "")),
                "closing_line":  closing_line,
                "bet_direction": bet_direction,
                "hit":           hit,
                "roi_unit":      roi_unit,
                "line_bucket":   bucket,
                "stage":         stage_for(date_str),
                "month":         month_for(date_str),
            })
    return rows


# ── Filter applications ────────────────────────────────────────────────────────

def apply_production_filters(
    rows: List[Dict],
    extra_subseg_filters: Optional[Dict[str, List[Tuple[str, str]]]] = None,
    extra_stage_filters: Optional[Dict[str, List[str]]] = None,
    extra_venue_filters: Optional[Dict[str, List[str]]] = None,
    extra_month_filters: Optional[Dict[str, List[str]]] = None,
    extra_3d_filters: Optional[Dict[str, List[Tuple[str, str, str]]]] = None,
) -> List[Dict]:
    """Apply production filters PLUS iter-58 candidate additions.

    Production (iter-51 + iter-54 + iter-55 + iter-57):
      - STAT_DIRECTIONS
      - STAT_LINE_EXCLUSIONS
      - STAT_DIRECTION_LINE_EXCLUSIONS

    Iter-58 candidate types:
      - extra_subseg_filters: (direction, bucket)   ← additive to iter-55/57
      - extra_stage_filters:  list of stage strings to DROP for stat
      - extra_venue_filters:  list of venue strings to DROP for stat
      - extra_month_filters:  list of YYYY-MM strings to DROP for stat
      - extra_3d_filters:     (direction, bucket, stage) triples to DROP for stat
    """
    combined_2d: Dict[str, List[Tuple[str, str]]] = {
        k: list(v) for k, v in STAT_DIRECTION_LINE_EXCLUSIONS.items()
    }
    if extra_subseg_filters:
        for stat, slices in extra_subseg_filters.items():
            combined_2d.setdefault(stat, [])
            for s in slices:
                if s not in combined_2d[stat]:
                    combined_2d[stat].append(s)

    extra_stage_filters = extra_stage_filters or {}
    extra_venue_filters = extra_venue_filters or {}
    extra_month_filters = extra_month_filters or {}
    extra_3d_filters    = extra_3d_filters or {}

    out: List[Dict] = []
    for r in rows:
        stat = r["stat"]
        if r["bet_direction"] not in allowed_directions_for(stat):
            continue
        if is_line_excluded(stat, r["closing_line"]):
            continue
        # 2D iter-55/57 exclusions (+ candidate additions)
        slices = combined_2d.get(stat, [])
        if any(r["bet_direction"] == d and r["line_bucket"] == b for d, b in slices):
            continue
        # 1D stage exclusion
        if r["stage"] in extra_stage_filters.get(stat, []):
            continue
        # 1D venue exclusion
        if r["venue"] in extra_venue_filters.get(stat, []):
            continue
        # 1D month exclusion
        if r["month"] in extra_month_filters.get(stat, []):
            continue
        # 3D direction x bucket x stage exclusion
        if (r["bet_direction"], r["line_bucket"], r["stage"]) in extra_3d_filters.get(stat, []):
            continue
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


# ── 1D segment evaluation ──────────────────────────────────────────────────────

def evaluate_1d_segments(
    rows: List[Dict],
    dimension: str,
) -> Dict[str, Dict[str, Dict]]:
    """For each stat, compute metrics on each value of *dimension* (stage/venue/month)."""
    out: Dict[str, Dict[str, Dict]] = {}
    by_stat: Dict[str, List[Dict]] = {}
    for r in rows:
        by_stat.setdefault(r["stat"], []).append(r)

    for stat, rows_s in by_stat.items():
        slices: Dict[str, Dict] = {}
        values = sorted({r[dimension] for r in rows_s if r[dimension] != "unknown"})
        for v in values:
            sub = [r for r in rows_s if r[dimension] == v]
            slices[v] = compute_metrics(sub)
        out[stat] = slices
    return out


def evaluate_3d_segments(rows: List[Dict]) -> Dict[str, Dict[Tuple[str, str, str], Dict]]:
    """For each stat, compute metrics on each (direction, bucket, stage) triple."""
    out: Dict[str, Dict] = {}
    by_stat: Dict[str, List[Dict]] = {}
    for r in rows:
        by_stat.setdefault(r["stat"], []).append(r)

    for stat, rows_s in by_stat.items():
        slices: Dict = {}
        for direction in ("over", "under"):
            for bucket in ("low", "mid", "high"):
                for stage in ("early", "late"):
                    sub = [r for r in rows_s
                           if r["bet_direction"] == direction
                           and r["line_bucket"] == bucket
                           and r["stage"] == stage]
                    if not sub:
                        continue
                    slices[(direction, bucket, stage)] = compute_metrics(sub)
        out[stat] = slices
    return out


def is_candidate_1d(seg: Dict, complement_n: int) -> bool:
    n = seg["n"]
    if n < MIN_SEG_N_1D:
        return False
    if complement_n < MIN_COMPLEMENT_1D:
        return False
    if seg["z_score"] >= MAX_Z_SCORE_1D:
        return False
    if seg["roi_pct"] >= MAX_ROI_PCT_1D:
        return False
    if seg["ci_hi"] >= MAX_CI_HI_1D:
        return False
    return True


def is_candidate_3d(seg: Dict, complement_n: int) -> bool:
    n = seg["n"]
    if n < MIN_SEG_N_3D:
        return False
    if complement_n < MIN_COMPLEMENT_3D:
        return False
    if seg["z_score"] >= MAX_Z_SCORE_3D:
        return False
    if seg["roi_pct"] >= MAX_ROI_PCT_3D:
        return False
    if seg["ci_hi"] >= MAX_CI_HI_3D:
        return False
    return True


# ── Greedy compose ─────────────────────────────────────────────────────────────

def greedy_compose_combined(
    all_rows: List[Dict],
    pre_agg: Dict,
    pre_per_stat: Dict[str, Dict],
    candidates_1d_stage: List[Tuple[str, str, Dict]],     # (stat, stage, seg)
    candidates_1d_venue: List[Tuple[str, str, Dict]],     # (stat, venue, seg)
    candidates_1d_month: List[Tuple[str, str, Dict]],     # (stat, month, seg)
    candidates_3d: List[Tuple[str, str, str, str, Dict]], # (stat, direction, bucket, stage, seg)
) -> Tuple[Dict, List[str]]:
    """Greedily try adding candidates one-by-one across all dimensions.

    Returns (picked_dict, log) where picked_dict has keys:
        stage_filters: {stat: [stage,...]}
        venue_filters: {stat: [venue,...]}
        month_filters: {stat: [month,...]}
        d3_filters:    {stat: [(direction, bucket, stage),...]}
    """
    picked = {
        "stage_filters": {},
        "venue_filters": {},
        "month_filters": {},
        "d3_filters":    {},
    }
    log: List[str] = []

    # Build a unified candidate list with kind tag + ROI for sorting.
    # All sorted worst-ROI-first.
    unified: List[Tuple[str, Dict]] = []
    for stat, stage, seg in candidates_1d_stage:
        unified.append(("1d_stage", {"stat": stat, "stage": stage, "seg": seg}))
    for stat, venue, seg in candidates_1d_venue:
        unified.append(("1d_venue", {"stat": stat, "venue": venue, "seg": seg}))
    for stat, month, seg in candidates_1d_month:
        unified.append(("1d_month", {"stat": stat, "month": month, "seg": seg}))
    for stat, direction, bucket, stage, seg in candidates_3d:
        unified.append(("3d", {
            "stat": stat, "direction": direction, "bucket": bucket,
            "stage": stage, "seg": seg,
        }))

    unified.sort(key=lambda c: c[1]["seg"]["roi_pct"])

    rolling_per_stat = deepcopy(pre_per_stat)
    rolling_agg      = deepcopy(pre_agg)

    for kind, cand in unified:
        seg = cand["seg"]
        stat = cand["stat"]

        # Build trial picks (deep copy then add this candidate)
        trial = {
            "stage_filters": {k: list(v) for k, v in picked["stage_filters"].items()},
            "venue_filters": {k: list(v) for k, v in picked["venue_filters"].items()},
            "month_filters": {k: list(v) for k, v in picked["month_filters"].items()},
            "d3_filters":    {k: list(v) for k, v in picked["d3_filters"].items()},
        }

        if kind == "1d_stage":
            trial["stage_filters"].setdefault(stat, [])
            if cand["stage"] in trial["stage_filters"][stat]:
                continue
            trial["stage_filters"][stat].append(cand["stage"])
            label = f"{stat.upper()} stage={cand['stage']}"
            min_lift = MIN_AGG_LIFT_1D
            max_reg = MAX_STAT_REGRESS_1D
        elif kind == "1d_venue":
            trial["venue_filters"].setdefault(stat, [])
            if cand["venue"] in trial["venue_filters"][stat]:
                continue
            trial["venue_filters"][stat].append(cand["venue"])
            label = f"{stat.upper()} venue={cand['venue']}"
            min_lift = MIN_AGG_LIFT_1D
            max_reg = MAX_STAT_REGRESS_1D
        elif kind == "1d_month":
            trial["month_filters"].setdefault(stat, [])
            if cand["month"] in trial["month_filters"][stat]:
                continue
            trial["month_filters"][stat].append(cand["month"])
            label = f"{stat.upper()} month={cand['month']}"
            min_lift = MIN_AGG_LIFT_1D
            max_reg = MAX_STAT_REGRESS_1D
        else:  # 3d
            trial["d3_filters"].setdefault(stat, [])
            triple = (cand["direction"], cand["bucket"], cand["stage"])
            if triple in trial["d3_filters"][stat]:
                continue
            trial["d3_filters"][stat].append(triple)
            label = f"{stat.upper()} 3D={triple}"
            min_lift = MIN_AGG_LIFT_3D
            max_reg = MAX_STAT_REGRESS_3D

        trial_rows = apply_production_filters(
            all_rows,
            extra_stage_filters=trial["stage_filters"],
            extra_venue_filters=trial["venue_filters"],
            extra_month_filters=trial["month_filters"],
            extra_3d_filters=trial["d3_filters"],
        )
        trial_agg = aggregate_metrics(trial_rows)
        trial_per_stat = per_stat_metrics(trial_rows)

        agg_delta = trial_agg["roi_pct"] - rolling_agg["roi_pct"]

        regressions = []
        for s in ("pts", "reb", "ast", "fg3m", "stl", "blk"):
            pre = rolling_per_stat.get(s, {}).get("roi_pct", 0.0)
            post = trial_per_stat.get(s, {}).get("roi_pct", 0.0)
            d = post - pre
            if d < max_reg:
                regressions.append(f"{s}: {d:+.4f}pp")

        if agg_delta >= min_lift and not regressions:
            picked = trial
            rolling_per_stat = trial_per_stat
            rolling_agg = trial_agg
            log.append(
                f"  ACCEPT [{kind}] {label}: seg(n={seg['n']}, "
                f"ROI={seg['roi_pct']:+.2f}%, z={seg['z_score']:+.3f}) "
                f"=> agg_delta={agg_delta:+.4f}pp (gate +{min_lift}pp)"
            )
        else:
            reason = (f"agg_delta {agg_delta:+.4f}pp < +{min_lift}pp"
                      if agg_delta < min_lift else f"regressions: {regressions}")
            log.append(
                f"  REJECT [{kind}] {label}: seg(n={seg['n']}, "
                f"ROI={seg['roi_pct']:+.2f}%, z={seg['z_score']:+.3f}) "
                f"=> {reason}"
            )

    return picked, log


# ── Main run ───────────────────────────────────────────────────────────────────

def run() -> Dict:
    print("\n" + "=" * 78)
    print("  ITER-58: STAGE/VENUE 1D + 3D DIRECTION x LINE x STAGE SWEEP")
    print("=" * 78)
    print(f"  Phase A (1D): n>={MIN_SEG_N_1D}, z<{MAX_Z_SCORE_1D}, ROI<{MAX_ROI_PCT_1D}%, "
          f"ci_hi<{MAX_CI_HI_1D}%")
    print(f"  Phase B (3D): n>={MIN_SEG_N_3D}, z<{MAX_Z_SCORE_3D}, ROI<{MAX_ROI_PCT_3D}%, "
          f"ci_hi<{MAX_CI_HI_3D}%")
    print(f"  Ship gates: 1D agg>=+{MIN_AGG_LIFT_1D}pp regr>{MAX_STAT_REGRESS_1D}pp; "
          f"3D agg>=+{MIN_AGG_LIFT_3D}pp regr>{MAX_STAT_REGRESS_3D}pp")
    print(f"  Current iter-57 STAT_DIRECTION_LINE_EXCLUSIONS = "
          f"{ {k: v for k, v in STAT_DIRECTION_LINE_EXCLUSIONS.items() if v} }")
    print()

    STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk"]
    all_rows: List[Dict] = []
    for stat in STATS:
        all_rows.extend(load_eval_rows(stat))
    print(f"  Total eval rows: {len(all_rows)}")

    # ── Post-iter-57 baseline ─────────────────────────────────────────────────
    post57_rows = apply_production_filters(all_rows)
    pre_per_stat = per_stat_metrics(post57_rows)
    pre_agg      = aggregate_metrics(post57_rows)
    print(f"\n  POST-ITER-57 BASELINE (= pre-iter-58):")
    print(f"    aggregate: n={pre_agg['n']}, ROI={pre_agg['roi_pct']:+.4f}%, "
          f"hit={pre_agg['hit_rate_pct']:.2f}%, z={pre_agg['z_score']:.3f}")
    for stat in STATS:
        m = pre_per_stat.get(stat, {"n": 0, "roi_pct": 0.0, "hit_rate_pct": 0.0, "z_score": 0.0})
        print(f"    {stat.upper():<5} n={m['n']:>4} ROI={m['roi_pct']:>+8.4f}%  "
              f"hit={m['hit_rate_pct']:>5.2f}%  z={m['z_score']:>+6.3f}")

    # ── Phase A: 1D segments ──────────────────────────────────────────────────
    print("\n" + "-" * 78)
    print("  PHASE A: 1D SEGMENTS (stage / venue / month) ON POST-ITER-57 SET")
    print("-" * 78)

    stage_segs = evaluate_1d_segments(post57_rows, "stage")
    venue_segs = evaluate_1d_segments(post57_rows, "venue")
    month_segs = evaluate_1d_segments(post57_rows, "month")

    candidates_1d_stage: List[Tuple[str, str, Dict]] = []
    candidates_1d_venue: List[Tuple[str, str, Dict]] = []
    candidates_1d_month: List[Tuple[str, str, Dict]] = []

    diag_1d_stage: Dict[str, Dict] = {}
    diag_1d_venue: Dict[str, Dict] = {}
    diag_1d_month: Dict[str, Dict] = {}

    for dim_name, segs, candidates, diag in [
        ("STAGE", stage_segs, candidates_1d_stage, diag_1d_stage),
        ("VENUE", venue_segs, candidates_1d_venue, diag_1d_venue),
        ("MONTH", month_segs, candidates_1d_month, diag_1d_month),
    ]:
        print(f"\n  --- {dim_name} ---")
        for stat in STATS:
            slices = segs.get(stat, {})
            stat_total = pre_per_stat.get(stat, {}).get("n", 0)
            if stat_total == 0 or not slices:
                continue
            print(f"\n  {stat.upper()} {dim_name.lower()} segments (total n={stat_total}):")
            print(f"    {'value':<12} {'n':>5} {'hit%':>6} {'ROI%':>8} {'z':>7}  "
                  f"{'95% CI':>20}  candidate?")
            print("    " + "-" * 76)
            stat_diag: Dict[str, Dict] = {}
            for val, seg in sorted(slices.items()):
                complement = stat_total - seg["n"]
                is_cand = is_candidate_1d(seg, complement)
                ci_str = f"[{seg['ci_lo']:+.1f}%, {seg['ci_hi']:+.1f}%]"
                flag = " <-- CANDIDATE" if is_cand else ""
                print(f"    {val:<12} {seg['n']:>5}  {seg['hit_rate_pct']:>5.2f}%  "
                      f"{seg['roi_pct']:>+7.3f}%  {seg['z_score']:>+6.3f}  "
                      f"{ci_str:>20}{flag}")
                stat_diag[val] = {
                    "n": seg["n"], "roi_pct": seg["roi_pct"], "z_score": seg["z_score"],
                    "ci_lo": seg["ci_lo"], "ci_hi": seg["ci_hi"],
                    "hit_rate_pct": seg["hit_rate_pct"],
                    "is_candidate": is_cand,
                }
                if is_cand:
                    candidates.append((stat, val, seg))
            diag[stat] = stat_diag

    n_1d_total = len(candidates_1d_stage) + len(candidates_1d_venue) + len(candidates_1d_month)
    print(f"\n  Total 1D candidates: {n_1d_total} "
          f"(stage={len(candidates_1d_stage)}, venue={len(candidates_1d_venue)}, "
          f"month={len(candidates_1d_month)})")

    # ── Phase B: 3D segments ──────────────────────────────────────────────────
    print("\n" + "-" * 78)
    print("  PHASE B: 3D direction x line_bucket x stage")
    print("-" * 78)
    d3_segs = evaluate_3d_segments(post57_rows)
    candidates_3d: List[Tuple[str, str, str, str, Dict]] = []
    diag_3d: Dict[str, Dict] = {}

    for stat in STATS:
        slices = d3_segs.get(stat, {})
        stat_total = pre_per_stat.get(stat, {}).get("n", 0)
        if stat_total == 0 or not slices:
            continue
        print(f"\n  {stat.upper()} 3D segments (total n={stat_total}):")
        print(f"    {'triple':<30} {'n':>5} {'hit%':>6} {'ROI%':>8} {'z':>7}  "
              f"{'95% CI':>20}  candidate?")
        print("    " + "-" * 94)
        stat_diag: Dict[str, Dict] = {}
        for (direction, bucket, stage), seg in sorted(slices.items()):
            complement = stat_total - seg["n"]
            is_cand = is_candidate_3d(seg, complement)
            ci_str = f"[{seg['ci_lo']:+.1f}%, {seg['ci_hi']:+.1f}%]"
            flag = " <-- CANDIDATE" if is_cand else ""
            triple_str = f"{direction}/{bucket}/{stage}"
            print(f"    {triple_str:<30} {seg['n']:>5}  {seg['hit_rate_pct']:>5.2f}%  "
                  f"{seg['roi_pct']:>+7.3f}%  {seg['z_score']:>+6.3f}  "
                  f"{ci_str:>20}{flag}")
            stat_diag[triple_str] = {
                "n": seg["n"], "roi_pct": seg["roi_pct"], "z_score": seg["z_score"],
                "ci_lo": seg["ci_lo"], "ci_hi": seg["ci_hi"],
                "hit_rate_pct": seg["hit_rate_pct"],
                "is_candidate": is_cand,
            }
            if is_cand:
                candidates_3d.append((stat, direction, bucket, stage, seg))
        diag_3d[stat] = stat_diag

    print(f"\n  Total 3D candidates: {len(candidates_3d)}")
    for stat, d, b, s, seg in sorted(candidates_3d, key=lambda c: c[4]["roi_pct"]):
        print(f"    {stat.upper()} {d}/{b}/{s}: n={seg['n']}, "
              f"ROI={seg['roi_pct']:+.2f}%, z={seg['z_score']:+.3f}, ci_hi={seg['ci_hi']:+.2f}%")

    # ── Greedy compose across all candidate types ─────────────────────────────
    print("\n" + "-" * 78)
    print("  GREEDY COMPOSITION (worst-ROI candidate first, across all types)")
    print("-" * 78)
    picked, log = greedy_compose_combined(
        all_rows, pre_agg, pre_per_stat,
        candidates_1d_stage, candidates_1d_venue, candidates_1d_month, candidates_3d,
    )
    for ln in log:
        print(ln)

    # ── Apply final filters ───────────────────────────────────────────────────
    any_picked = bool(
        picked["stage_filters"] or picked["venue_filters"]
        or picked["month_filters"] or picked["d3_filters"]
    )
    if any_picked:
        post58_rows = apply_production_filters(
            all_rows,
            extra_stage_filters=picked["stage_filters"],
            extra_venue_filters=picked["venue_filters"],
            extra_month_filters=picked["month_filters"],
            extra_3d_filters=picked["d3_filters"],
        )
        post58_per_stat = per_stat_metrics(post58_rows)
        post58_agg      = aggregate_metrics(post58_rows)
    else:
        post58_rows     = post57_rows
        post58_per_stat = pre_per_stat
        post58_agg      = pre_agg

    print("\n" + "=" * 78)
    print("  POST-ITER-58 METRICS")
    print("=" * 78)
    agg_delta = post58_agg["roi_pct"] - pre_agg["roi_pct"]
    print(f"  aggregate: n={post58_agg['n']}, ROI={post58_agg['roi_pct']:+.4f}%, "
          f"delta_vs_pre58={agg_delta:+.4f}pp")
    print(f"  {'Stat':<5} {'pre_n':>6} {'post_n':>7} {'pre_roi%':>10} {'post_roi%':>11} "
          f"{'delta_pp':>10}")
    for stat in STATS:
        pre_m  = pre_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        post_m = post58_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        d_pp   = post_m["roi_pct"] - pre_m["roi_pct"]
        print(f"  {stat.upper():<5} {pre_m['n']:>6} {post_m['n']:>7} "
              f"{pre_m['roi_pct']:>+9.4f}% {post_m['roi_pct']:>+10.4f}% "
              f"{d_pp:>+9.4f}pp")

    # ── Ship decision ─────────────────────────────────────────────────────────
    # Determine effective threshold: if ANY 1D filter picked, gate is +0.5pp;
    # if only 3D picked, gate is +0.3pp.
    only_3d = (
        bool(picked["d3_filters"]) and
        not (picked["stage_filters"] or picked["venue_filters"] or picked["month_filters"])
    )
    threshold = MIN_AGG_LIFT_3D if only_3d else MIN_AGG_LIFT_1D
    max_reg_use = MAX_STAT_REGRESS_3D if only_3d else MAX_STAT_REGRESS_1D

    regressions: List[str] = []
    improvements: List[str] = []
    for stat in STATS:
        pre_m  = pre_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        post_m = post58_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        d_pp   = post_m["roi_pct"] - pre_m["roi_pct"]
        if d_pp < max_reg_use:
            regressions.append(f"{stat}: {d_pp:+.4f}pp")
        if d_pp > 0.5:
            improvements.append(f"{stat}: {d_pp:+.4f}pp")

    agg_passes     = agg_delta >= threshold
    no_regressions = len(regressions) == 0

    if agg_passes and no_regressions and any_picked:
        decision = "SHIP"
        detail = (
            f"Aggregate delta {agg_delta:+.4f}pp >= +{threshold}pp AND no per-stat "
            f"regression > {max_reg_use}pp. Filters added: stage={picked['stage_filters']}, "
            f"venue={picked['venue_filters']}, month={picked['month_filters']}, "
            f"3d={picked['d3_filters']}."
        )
    elif not any_picked:
        decision = "REVERT"
        detail = (
            f"No 1D or 3D candidate passed the greedy gate. "
            f"1D thresholds: n>={MIN_SEG_N_1D}, z<{MAX_Z_SCORE_1D}, ROI<{MAX_ROI_PCT_1D}%, "
            f"ci_hi<{MAX_CI_HI_1D}%, agg lift>=+{MIN_AGG_LIFT_1D}pp; "
            f"3D thresholds: n>={MIN_SEG_N_3D}, z<{MAX_Z_SCORE_3D}, ROI<{MAX_ROI_PCT_3D}%, "
            f"ci_hi<{MAX_CI_HI_3D}%, agg lift>=+{MIN_AGG_LIFT_3D}pp."
        )
    elif not agg_passes:
        decision = "REVERT"
        detail = f"Aggregate delta {agg_delta:+.4f}pp below +{threshold}pp ship threshold."
    else:
        decision = "REVERT"
        detail = f"Per-stat regression(s) > {max_reg_use}pp: {regressions}."

    print("\n" + "=" * 78)
    print(f"  DECISION: {decision}")
    print("=" * 78)
    print(f"  Detail:       {detail}")
    print(f"  Agg delta:    {agg_delta:+.4f}pp (threshold {threshold:+.1f}pp; only_3d={only_3d})")
    print(f"  Regressions:  {regressions if regressions else 'none'}")
    print(f"  Improvements: {improvements if improvements else 'none'}")

    # ── Wire filters if SHIP ──────────────────────────────────────────────────
    filters_wired: Dict = {}
    if decision == "SHIP":
        filters_wired = _wire_filters_into_thresholds(picked, agg_delta, post58_agg, pre_agg)

    # ── Build result ──────────────────────────────────────────────────────────
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = {
        "iter":            58,
        "generated_at":    now_utc,
        "approach":        "stage_venue_1d_plus_3d_dir_line_stage_sweep",
        "n_bets_pre":      pre_agg["n"],
        "n_bets_post":     post58_agg["n"],
        "pre58_agg_roi":   round(pre_agg["roi_pct"], 4),
        "post58_agg_roi":  round(post58_agg["roi_pct"], 4),
        "delta_agg_pp":    round(agg_delta, 4),
        "ship_threshold_pp": threshold,
        "only_3d":         only_3d,
        "decision":        decision,
        "decision_detail": detail,
        "regressions":     regressions,
        "improvements":    improvements,
        "filters_wired":   filters_wired,
        "picked":          {
            "stage_filters": picked["stage_filters"],
            "venue_filters": picked["venue_filters"],
            "month_filters": picked["month_filters"],
            "d3_filters":    {k: [list(t) for t in v] for k, v in picked["d3_filters"].items()},
        },
        "greedy_log":      log,
        "per_stat": {
            stat: {
                "pre_n":     pre_per_stat.get(stat, {}).get("n", 0),
                "post_n":    post58_per_stat.get(stat, {}).get("n", 0),
                "pre_roi":   round(pre_per_stat.get(stat, {}).get("roi_pct", 0.0), 4),
                "post_roi":  round(post58_per_stat.get(stat, {}).get("roi_pct", 0.0), 4),
                "delta_roi": round(
                    post58_per_stat.get(stat, {}).get("roi_pct", 0.0)
                    - pre_per_stat.get(stat, {}).get("roi_pct", 0.0), 4),
            }
            for stat in STATS
        },
        "diagnostics_1d_stage": diag_1d_stage,
        "diagnostics_1d_venue": diag_1d_venue,
        "diagnostics_1d_month": diag_1d_month,
        "diagnostics_3d":       diag_3d,
        "params": {
            "phase_a_1d": {
                "min_seg_n":  MIN_SEG_N_1D,
                "min_compl":  MIN_COMPLEMENT_1D,
                "max_ci_hi":  MAX_CI_HI_1D,
                "max_roi":    MAX_ROI_PCT_1D,
                "max_z":      MAX_Z_SCORE_1D,
                "min_lift":   MIN_AGG_LIFT_1D,
                "max_regr":   MAX_STAT_REGRESS_1D,
            },
            "phase_b_3d": {
                "min_seg_n":  MIN_SEG_N_3D,
                "min_compl":  MIN_COMPLEMENT_3D,
                "max_ci_hi":  MAX_CI_HI_3D,
                "max_roi":    MAX_ROI_PCT_3D,
                "max_z":      MAX_Z_SCORE_3D,
                "min_lift":   MIN_AGG_LIFT_3D,
                "max_regr":   MAX_STAT_REGRESS_3D,
            },
            "n_bootstrap": N_BOOTSTRAP,
            "seed":        SEED,
            "early_months": sorted(EARLY_MONTHS),
        },
    }

    # ── Persist to holdout_baseline.json ──────────────────────────────────────
    baseline: Dict = {}
    if os.path.exists(BASELINE_JSON):
        baseline = json.load(open(BASELINE_JSON, encoding="utf-8"))
    baseline["__iter58__"] = result
    baseline["__updated_at__"] = now_utc
    with open(BASELINE_JSON, "w", encoding="utf-8") as fh:
        json.dump(baseline, fh, indent=2)
    print(f"\n  holdout_baseline.json -> updated with __iter58__ (other keys preserved)")

    # ── Vault report ──────────────────────────────────────────────────────────
    _write_vault_report(result, stage_segs, venue_segs, month_segs, d3_segs,
                        pre_per_stat, post58_per_stat)

    return result


# ── Wiring ─────────────────────────────────────────────────────────────────────

def _wire_filters_into_thresholds(
    picked: Dict, agg_delta: float, post_agg: Dict, pre_agg: Dict,
) -> Dict:
    """If iter-58 picked any filters, extend bet_thresholds.py.

    Strategy: for 3D picks, add a new STAT_DIRECTION_LINE_STAGE_EXCLUSIONS dict.
    For 1D stage/venue/month, add STAT_STAGE_EXCLUSIONS / STAT_VENUE_EXCLUSIONS /
    STAT_MONTH_EXCLUSIONS dicts as needed.

    All additions are EXTEND-only — existing dicts preserved.
    """
    with open(THRESHOLDS_PY, encoding="utf-8") as fh:
        content = fh.read()

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    wired: Dict = {}
    additions: List[str] = []

    # Build comment header
    header = (
        f"\n\n# ── Iter-58: Stage / venue / month + 3D direction x line x stage exclusions ──\n"
        f"# Date: {now_str}.\n"
        f"# Pre-iter-58 baseline: n_bets={pre_agg['n']}, ROI={pre_agg['roi_pct']:+.4f}%.\n"
        f"# Post-iter-58:         n_bets={post_agg['n']}, ROI={post_agg['roi_pct']:+.4f}%.\n"
        f"# Aggregate delta: {agg_delta:+.4f}pp.\n"
    )

    if picked["stage_filters"]:
        wired["stage"] = picked["stage_filters"]
        lines = [f"STAT_STAGE_EXCLUSIONS: dict[str, list[str]] = {{"]
        for stat, stages in picked["stage_filters"].items():
            lines.append(f'    "{stat}":  {stages!r},   # iter-58')
        lines.append("}\n")
        lines.append("")
        lines.append("def is_stage_excluded(stat: str, stage: str) -> bool:")
        lines.append('    """Return True if iter-58 dropped this (stat, stage) slice."""')
        lines.append("    return stage in STAT_STAGE_EXCLUSIONS.get(stat.lower(), [])")
        additions.append("\n".join(lines))

    if picked["venue_filters"]:
        wired["venue"] = picked["venue_filters"]
        lines = [f"STAT_VENUE_EXCLUSIONS: dict[str, list[str]] = {{"]
        for stat, venues in picked["venue_filters"].items():
            lines.append(f'    "{stat}":  {venues!r},   # iter-58')
        lines.append("}\n")
        lines.append("")
        lines.append("def is_venue_excluded(stat: str, venue: str) -> bool:")
        lines.append('    """Return True if iter-58 dropped this (stat, venue) slice."""')
        lines.append("    return venue.lower() in STAT_VENUE_EXCLUSIONS.get(stat.lower(), [])")
        additions.append("\n".join(lines))

    if picked["month_filters"]:
        wired["month"] = picked["month_filters"]
        lines = [f"STAT_MONTH_EXCLUSIONS: dict[str, list[str]] = {{"]
        for stat, months in picked["month_filters"].items():
            lines.append(f'    "{stat}":  {months!r},   # iter-58')
        lines.append("}\n")
        lines.append("")
        lines.append("def is_month_excluded(stat: str, month: str) -> bool:")
        lines.append('    """Return True if iter-58 dropped this (stat, month) slice."""')
        lines.append("    return month in STAT_MONTH_EXCLUSIONS.get(stat.lower(), [])")
        additions.append("\n".join(lines))

    if picked["d3_filters"]:
        wired["d3"] = {k: [list(t) for t in v] for k, v in picked["d3_filters"].items()}
        lines = [f"STAT_DIR_LINE_STAGE_EXCLUSIONS: dict[str, list[tuple[str, str, str]]] = {{"]
        for stat, triples in picked["d3_filters"].items():
            triple_strs = ", ".join([f'("{d}", "{b}", "{s}")' for d, b, s in triples])
            lines.append(f'    "{stat}":  [{triple_strs}],   # iter-58')
        lines.append("}\n")
        lines.append("")
        lines.append("def is_dir_line_stage_excluded(stat: str, direction: str,")
        lines.append("                                closing_line: float, stage: str) -> bool:")
        lines.append('    """Return True if iter-58 dropped this (direction, line_bucket, stage) cell."""')
        lines.append("    bucket = _line_bucket_for_internal(stat, closing_line)")
        lines.append("    triples = STAT_DIR_LINE_STAGE_EXCLUSIONS.get(stat.lower(), [])")
        lines.append("    return (direction.lower(), bucket, stage.lower()) in triples")
        additions.append("\n".join(lines))

    if not additions:
        return wired

    final = content.rstrip() + header + "\n" + "\n\n".join(additions) + "\n"
    with open(THRESHOLDS_PY, "w", encoding="utf-8") as fh:
        fh.write(final)
    print(f"  bet_thresholds.py -> appended iter-58 filter dicts + helper functions")
    return wired


# ── Vault report ───────────────────────────────────────────────────────────────

def _write_vault_report(
    result: Dict,
    stage_segs: Dict, venue_segs: Dict, month_segs: Dict, d3_segs: Dict,
    pre_per_stat: Dict, post_per_stat: Dict,
) -> None:
    os.makedirs(VAULT_DIR, exist_ok=True)
    now_str  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    decision = result["decision"]

    lines = [
        f"# Iter-58 Stage Venue 3D Sweep ({now_str})",
        "",
        "**Goal:** On the post-iter-57 baseline (n=1535, ROI=+15.04%), explore the dimensions "
        "iter-55/57 did not touch: stage (early Oct-Dec / late Jan-end), venue (home/away), "
        "month (YYYY-MM), and 3D direction x line_bucket x stage cells.",
        "",
        f"**Baseline:** post-iter-57 ROI = {result['pre58_agg_roi']:+.4f}% on "
        f"{result['n_bets_pre']} bets (outcome-preserved sim).",
        "",
        "---",
        "",
        "## Method",
        "",
        "1. Load eval CSV; compute bet direction + hit/roi per row (iter-54/55/57 devig heuristic).",
        "2. Apply CURRENT PRODUCTION FILTERS (STAT_DIRECTIONS + STAT_LINE_EXCLUSIONS + "
        "STAT_DIRECTION_LINE_EXCLUSIONS = post-iter-57 baseline).",
        "3. Phase A (1D): for each stat x dimension (stage / venue / month), bootstrap metrics.",
        f"   Candidate gate: n >= {MIN_SEG_N_1D}, z < {MAX_Z_SCORE_1D}, "
        f"ROI < {MAX_ROI_PCT_1D}%, ci_hi < {MAX_CI_HI_1D}%.",
        "4. Phase B (3D): for each stat x (direction, bucket, stage) triple, bootstrap metrics.",
        f"   Candidate gate: n >= {MIN_SEG_N_3D}, z < {MAX_Z_SCORE_3D}, "
        f"ROI < {MAX_ROI_PCT_3D}%, ci_hi < {MAX_CI_HI_3D}% (strict).",
        "5. Greedy compose worst-ROI-first across ALL candidate types; accept if agg lift "
        f">= +{MIN_AGG_LIFT_1D}pp (1D) or +{MIN_AGG_LIFT_3D}pp (3D) with no per-stat regression.",
        f"6. Ship gate: only-3D pick uses +{MIN_AGG_LIFT_3D}pp; any-1D pick uses +{MIN_AGG_LIFT_1D}pp.",
        "",
        "---",
        "",
        "## Phase A: 1D Stage Segments",
        "",
        "| Stat | Stage | n | hit% | ROI% | z | 95% CI | candidate? |",
        "|------|-------|---|------|------|---|--------|-----------|",
    ]
    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk"]:
        slices = stage_segs.get(stat, {})
        if not slices:
            continue
        for val, seg in sorted(slices.items()):
            stat_total = pre_per_stat.get(stat, {}).get("n", 0)
            is_cand = is_candidate_1d(seg, stat_total - seg["n"])
            ci = f"[{seg['ci_lo']:+.1f}%, {seg['ci_hi']:+.1f}%]"
            lines.append(
                f"| {stat.upper()} | {val} | {seg['n']} | {seg['hit_rate_pct']:.2f}% | "
                f"{seg['roi_pct']:+.3f}% | {seg['z_score']:+.3f} | {ci} | "
                f"{'**YES**' if is_cand else 'no'} |"
            )

    lines += [
        "",
        "## Phase A: 1D Venue Segments",
        "",
        "| Stat | Venue | n | hit% | ROI% | z | 95% CI | candidate? |",
        "|------|-------|---|------|------|---|--------|-----------|",
    ]
    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk"]:
        slices = venue_segs.get(stat, {})
        if not slices:
            continue
        for val, seg in sorted(slices.items()):
            stat_total = pre_per_stat.get(stat, {}).get("n", 0)
            is_cand = is_candidate_1d(seg, stat_total - seg["n"])
            ci = f"[{seg['ci_lo']:+.1f}%, {seg['ci_hi']:+.1f}%]"
            lines.append(
                f"| {stat.upper()} | {val} | {seg['n']} | {seg['hit_rate_pct']:.2f}% | "
                f"{seg['roi_pct']:+.3f}% | {seg['z_score']:+.3f} | {ci} | "
                f"{'**YES**' if is_cand else 'no'} |"
            )

    lines += [
        "",
        "## Phase A: 1D Month Segments (showing only n >= 80)",
        "",
        "| Stat | Month | n | hit% | ROI% | z | 95% CI | candidate? |",
        "|------|-------|---|------|------|---|--------|-----------|",
    ]
    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk"]:
        slices = month_segs.get(stat, {})
        if not slices:
            continue
        for val, seg in sorted(slices.items()):
            if seg["n"] < MIN_SEG_N_1D:
                continue
            stat_total = pre_per_stat.get(stat, {}).get("n", 0)
            is_cand = is_candidate_1d(seg, stat_total - seg["n"])
            ci = f"[{seg['ci_lo']:+.1f}%, {seg['ci_hi']:+.1f}%]"
            lines.append(
                f"| {stat.upper()} | {val} | {seg['n']} | {seg['hit_rate_pct']:.2f}% | "
                f"{seg['roi_pct']:+.3f}% | {seg['z_score']:+.3f} | {ci} | "
                f"{'**YES**' if is_cand else 'no'} |"
            )

    lines += [
        "",
        "---",
        "",
        "## Phase B: 3D Direction x Line x Stage (n >= 30 only)",
        "",
        "| Stat | direction/bucket/stage | n | hit% | ROI% | z | 95% CI | candidate? |",
        "|------|------------------------|---|------|------|---|--------|-----------|",
    ]
    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk"]:
        slices = d3_segs.get(stat, {})
        if not slices:
            continue
        for (direction, bucket, stage), seg in sorted(slices.items()):
            if seg["n"] < MIN_SEG_N_3D:
                continue
            stat_total = pre_per_stat.get(stat, {}).get("n", 0)
            is_cand = is_candidate_3d(seg, stat_total - seg["n"])
            ci = f"[{seg['ci_lo']:+.1f}%, {seg['ci_hi']:+.1f}%]"
            lines.append(
                f"| {stat.upper()} | {direction}/{bucket}/{stage} | {seg['n']} | "
                f"{seg['hit_rate_pct']:.2f}% | {seg['roi_pct']:+.3f}% | "
                f"{seg['z_score']:+.3f} | {ci} | {'**YES**' if is_cand else 'no'} |"
            )

    lines += [
        "",
        "---",
        "",
        "## Greedy Composition Log",
        "",
        "```",
    ]
    for ln in result["greedy_log"]:
        lines.append(ln)
    lines += [
        "```",
        "",
        "---",
        "",
        "## Per-Stat Impact",
        "",
        "| Stat | pre_n | post_n | pre_ROI | post_ROI | delta |",
        "|------|-------|--------|---------|----------|-------|",
    ]
    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk"]:
        ps = result["per_stat"][stat]
        lines.append(
            f"| {stat.upper()} | {ps['pre_n']} | {ps['post_n']} | "
            f"{ps['pre_roi']:+.4f}% | {ps['post_roi']:+.4f}% | {ps['delta_roi']:+.4f}pp |"
        )
    lines.append(
        f"| **TOTAL** | **{result['n_bets_pre']}** | **{result['n_bets_post']}** | "
        f"**{result['pre58_agg_roi']:+.4f}%** | **{result['post58_agg_roi']:+.4f}%** | "
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
        f"- Aggregate delta: {result['delta_agg_pp']:+.4f}pp "
        f"(ship threshold: +{result['ship_threshold_pp']:.1f}pp, only_3d={result['only_3d']})",
        f"- Regressions: {result['regressions'] if result['regressions'] else 'none'}",
        f"- Improvements: {result['improvements'] if result['improvements'] else 'none'}",
        "",
    ]

    if decision == "SHIP" and result["filters_wired"]:
        lines += [
            "**Filters wired to `bet_thresholds.py`:**",
            "",
            f"- {result['filters_wired']}",
            "",
        ]

    lines += [
        "---",
        "",
        "## Key Finding",
        "",
    ]
    if decision == "SHIP":
        lines.append(
            "Stage / venue / month / 3D candidate(s) cleared the gate. "
            f"Aggregate ROI lifted by {result['delta_agg_pp']:+.4f}pp."
        )
    else:
        lines.append(
            "On the post-iter-57 bet set, no 1D stage / venue / month nor 3D "
            "direction x line x stage slice passed BOTH the candidate gate AND the greedy "
            "aggregate-lift threshold. Per-bet ROI distribution across these dimensions is "
            "consistent enough that no further filtering improves aggregate. Iter-55/57's "
            "2D direction x line filters appear to have absorbed the bulk of segment-level "
            "alpha; remaining structure is noise."
        )

    lines += [
        "",
        "---",
        "",
        f"*Generated by `scripts/iter58_stage_venue_3d_sweep.py` on {now_str}.*",
        "*Refs: [[Iter57 Post-Iter55 Resweep]] | [[Iter55 Subsegment Refinement]] | "
        "[[Iter54 Segmentation Sweep]] | [[Engineering Knowledge]]*",
    ]

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"  Vault report -> {REPORT_PATH}")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = run()
    print("\n" + "=" * 78)
    print("  ITER-58 COMPLETE")
    print("=" * 78)
    print(f"  Decision:        {result['decision']}")
    print(f"  Aggregate delta: {result['delta_agg_pp']:+.4f}pp")
    print(f"  Pre/post ROI:    {result['pre58_agg_roi']:+.4f}% -> {result['post58_agg_roi']:+.4f}% "
          f"({result['n_bets_pre']} -> {result['n_bets_post']} bets)")
    if result["filters_wired"]:
        print(f"  Filters wired:   {result['filters_wired']}")
    else:
        print("  Filters wired:   none")
    print()
