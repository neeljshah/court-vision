"""iter57_post55_resweep.py — Re-sweep 2D direction x line filters against post-Iter55 baseline.

Iter-55 shipped STAT_DIRECTION_LINE_EXCLUSIONS = {"ast": [("over","high")]} which lifted
the aggregate ROI by +1.33pp on the post-iter-54 bet set.

That iter-55 wiring CHANGED the distribution of remaining AST bets in production, so all
per-stat reference baselines for sub-segment ROIs need to be re-measured.

This iter probes additional 2D direction x line_bucket sub-segments on the NEW
post-iter-55 baseline. Primary candidate is REB direction_over x line_low (iter-55
diagnostics surfaced n=105, ROI=-12.73%, z=-0.391, CI [-30.91, +3.68]).

Compound-bonus check: any 2D segment with n >= 50, ROI < +5%, z < 1.5, CI upper
bound < +10% (stricter than iter-55 to avoid over-filtering at this depth).

METHOD:
  1. Load eval CSV.
  2. Apply CURRENT PRODUCTION FILTERS (now including iter-55's STAT_DIRECTION_LINE_EXCLUSIONS):
       - STAT_DIRECTIONS["blk"] = ["under"]   (Iter-51)
       - STAT_LINE_EXCLUSIONS                  (Iter-54)
       - STAT_DIRECTION_LINE_EXCLUSIONS        (Iter-55)
     This produces the POST-ITER-55 BASELINE.
  3. For each stat x direction x line_bucket 2D slice with n >= 50, bootstrap (1000 trials)
     to get ROI 95% CI + z-score on the post-iter-55 bet set.
  4. Flag as "zero-EV candidate" if: n >= 50 AND z < 1.5 AND ROI < +5% AND ci_hi < +10%
     (stricter ci_hi than iter-55's +5% so we don't over-filter weak negative slices,
      but allow ROI to be merely "uninspiring" rather than strongly negative).
  5. Greedy: pick candidates whose addition lifts aggregate >= +0.3pp with no per-stat
     regression > -1pp.
  6. Ship gate: aggregate delta >= +0.5pp on post-iter-55 baseline AND no per-stat
     regression > -1pp. If only REB ships alone, lower threshold to +0.3pp.

Run:
    python scripts/iter57_post55_resweep.py

Output:
    vault/Models/Iter57 Post-Iter55 Resweep.md
    data/cache/holdout_baseline.json  (__iter57__ key — additive)
    src/prediction/bet_thresholds.py  (extend STAT_DIRECTION_LINE_EXCLUSIONS if SHIP)
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

# Import current production filters (read-only — we consume them, may extend the dict below).
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
REPORT_PATH    = os.path.join(VAULT_DIR, "Iter57 Post-Iter55 Resweep.md")
THRESHOLDS_PY  = os.path.join(PROJECT_DIR, "src", "prediction", "bet_thresholds.py")

# ── Constants ──────────────────────────────────────────────────────────────────
PAYOUT_M110    = 100.0 / 110.0
BREAKEVEN_HR   = 100.0 / (100.0 + 110.0)
N_BOOTSTRAP    = 1000
SEED           = 42

# ── Bias guards for iter-57 (stricter than iter-55) ────────────────────────────
MIN_SEG_N           = 50
MIN_COMPLEMENT_N    = 100
MAX_CI_HI           = 10.0   # stricter than iter-55's +5%? Actually iter-55 was +5%.
                              # Per prompt: "CI upper bound < +10%" — so use +10% here.
MAX_ROI_PCT         = 5.0    # ROI < +5% qualifies as zero-EV candidate
MAX_Z_SCORE         = 1.5    # z < 1.5 qualifies (no strong positive signal)

# Line bucket boundaries (must match iter-54/55)
LINE_BUCKETS: Dict[str, Tuple[float, float]] = {
    "pts":  (9.5,  15.5),
    "reb":  (3.5,  5.5),
    "ast":  (1.5,  3.5),
    "fg3m": (1.5,  1.5),
    "stl":  (0.5,  1.5),
    "blk":  (1.5,  2.5),
}

# Ship constraints
MIN_AGG_LIFT_DEFAULT = 0.5
MIN_AGG_LIFT_REB_SOLO = 0.3   # REB-only ship gets a lower threshold per prompt
MAX_STAT_REGRESS     = -1.0


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

            # Same direction heuristic as iter-54/55
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

def apply_production_filters(
    rows: List[Dict],
    extra_subseg_filters: Optional[Dict[str, List[Tuple[str, str]]]] = None,
) -> List[Dict]:
    """Apply current production filters PLUS any iter-57 candidate sub-segment additions.

    Current production filters (as of iter-55):
      - STAT_DIRECTIONS (iter-51 BLK direction)
      - STAT_LINE_EXCLUSIONS (iter-54)
      - STAT_DIRECTION_LINE_EXCLUSIONS (iter-55)
    """
    # Merge iter-55 baseline with any extra (additive — don't mutate the original dict)
    combined: Dict[str, List[Tuple[str, str]]] = {
        k: list(v) for k, v in STAT_DIRECTION_LINE_EXCLUSIONS.items()
    }
    if extra_subseg_filters:
        for stat, slices in extra_subseg_filters.items():
            combined.setdefault(stat, [])
            for s in slices:
                if s not in combined[stat]:
                    combined[stat].append(s)

    out: List[Dict] = []
    for r in rows:
        stat = r["stat"]
        if r["bet_direction"] not in allowed_directions_for(stat):
            continue
        if is_line_excluded(stat, r["closing_line"]):
            continue
        # iter-55: STAT_DIRECTION_LINE_EXCLUSIONS + iter-57 additions
        slices = combined.get(stat, [])
        dropped = False
        for drop_dir, drop_bucket in slices:
            if r["bet_direction"] == drop_dir and r["line_bucket"] == drop_bucket:
                dropped = True
                break
        if dropped:
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


# ── Sub-segment evaluation ─────────────────────────────────────────────────────

def evaluate_sub_segments(rows: List[Dict]) -> Dict[str, Dict]:
    """For each stat, compute metrics on each (direction, line_bucket) 2D slice."""
    out: Dict[str, Dict] = {}
    by_stat: Dict[str, List[Dict]] = {}
    for r in rows:
        by_stat.setdefault(r["stat"], []).append(r)

    for stat, rows_s in by_stat.items():
        slices: Dict = {}
        for direction in ("over", "under"):
            for bucket in ("low", "mid", "high"):
                sub = [r for r in rows_s if r["bet_direction"] == direction and r["line_bucket"] == bucket]
                slices[(direction, bucket)] = compute_metrics(sub)
        out[stat] = slices
    return out


def is_candidate_zero_ev(seg: Dict, complement_n: int) -> bool:
    """Iter-57 candidate gate: n>=50, complement>=100, z<1.5, ROI<+5%, ci_hi<+10%."""
    n = seg["n"]
    if n < MIN_SEG_N:
        return False
    if complement_n < MIN_COMPLEMENT_N:
        return False
    if seg["z_score"] >= MAX_Z_SCORE:
        return False
    if seg["roi_pct"] >= MAX_ROI_PCT:
        return False
    if seg["ci_hi"] >= MAX_CI_HI:
        return False
    return True


# ── Greedy compound search ─────────────────────────────────────────────────────

def greedy_compose(
    all_rows: List[Dict],
    pre57_agg: Dict,
    pre57_per_stat: Dict[str, Dict],
    candidates: List[Tuple[str, str, str, Dict]],
) -> Tuple[Dict[str, List[Tuple[str, str]]], List[str]]:
    """Greedily try adding candidates one-by-one. Pick those that lift aggregate >= +0.3pp
    with no per-stat regression > -1pp relative to the rolling baseline.

    candidates: list of (stat, direction, bucket, seg_metrics) sorted by ROI ascending
                (worst-first so we try most-negative first).
    """
    picked: Dict[str, List[Tuple[str, str]]] = {}
    log: List[str] = []

    # Sort worst-ROI-first
    candidates_sorted = sorted(candidates, key=lambda c: c[3]["roi_pct"])

    # Rolling state
    rolling_per_stat = deepcopy(pre57_per_stat)
    rolling_agg      = deepcopy(pre57_agg)

    for stat, direction, bucket, seg in candidates_sorted:
        trial_filters = {k: list(v) for k, v in picked.items()}
        trial_filters.setdefault(stat, []).append((direction, bucket))

        trial_rows = apply_production_filters(all_rows, extra_subseg_filters=trial_filters)
        trial_agg  = aggregate_metrics(trial_rows)
        trial_per_stat = per_stat_metrics(trial_rows)

        agg_delta = trial_agg["roi_pct"] - rolling_agg["roi_pct"]

        regressions = []
        for s in ("pts", "reb", "ast", "fg3m", "stl", "blk"):
            pre = rolling_per_stat.get(s, {}).get("roi_pct", 0.0)
            post = trial_per_stat.get(s, {}).get("roi_pct", 0.0)
            d = post - pre
            if d < MAX_STAT_REGRESS:
                regressions.append(f"{s}: {d:+.4f}pp")

        if agg_delta >= 0.3 and not regressions:
            picked = trial_filters
            rolling_per_stat = trial_per_stat
            rolling_agg = trial_agg
            log.append(
                f"  ACCEPT {stat}/{direction}x{bucket}: seg(n={seg['n']}, "
                f"ROI={seg['roi_pct']:+.2f}%, z={seg['z_score']:+.3f}) "
                f"=> agg_delta={agg_delta:+.4f}pp"
            )
        else:
            reason = (f"agg_delta {agg_delta:+.4f}pp < +0.3pp"
                      if agg_delta < 0.3 else f"regressions: {regressions}")
            log.append(
                f"  REJECT {stat}/{direction}x{bucket}: seg(n={seg['n']}, "
                f"ROI={seg['roi_pct']:+.2f}%, z={seg['z_score']:+.3f}) "
                f"=> {reason}"
            )

    return picked, log


# ── Main run ───────────────────────────────────────────────────────────────────

def run() -> Dict:
    print("\n" + "=" * 78)
    print("  ITER-57: POST-ITER-55 RESWEEP OF 2D direction x line FILTERS")
    print("=" * 78)
    print(f"  MIN_SEG_N={MIN_SEG_N}  z<{MAX_Z_SCORE}  ROI<+{MAX_ROI_PCT}%  ci_hi<+{MAX_CI_HI}%")
    print(f"  Current iter-55 STAT_DIRECTION_LINE_EXCLUSIONS = "
          f"{ {k: v for k, v in STAT_DIRECTION_LINE_EXCLUSIONS.items() if v} }")
    print()

    STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk"]
    all_rows: List[Dict] = []
    for stat in STATS:
        all_rows.extend(load_eval_rows(stat))
    print(f"  Total eval rows: {len(all_rows)}")

    # ── Post-iter-55 baseline (NO extra filters, current production state) ────
    post55_rows = apply_production_filters(all_rows, extra_subseg_filters=None)
    pre57_per_stat = per_stat_metrics(post55_rows)
    pre57_agg      = aggregate_metrics(post55_rows)
    print(f"\n  POST-ITER-55 BASELINE (= pre-iter-57):")
    print(f"    aggregate: n={pre57_agg['n']}, ROI={pre57_agg['roi_pct']:+.4f}%, "
          f"hit={pre57_agg['hit_rate_pct']:.2f}%, z={pre57_agg['z_score']:.3f}")
    for stat in STATS:
        m = pre57_per_stat.get(stat, {"n": 0, "roi_pct": 0.0, "hit_rate_pct": 0.0, "z_score": 0.0})
        print(f"    {stat.upper():<5} n={m['n']:>4} ROI={m['roi_pct']:>+8.4f}%  "
              f"hit={m['hit_rate_pct']:>5.2f}%  z={m['z_score']:>+6.3f}")

    # ── 2D sub-segment sweep on post-iter-55 bet set ───────────────────────────
    print("\n" + "-" * 78)
    print("  2D SUB-SEGMENTS (direction x line_bucket) ON POST-ITER-55 BET SET")
    print("-" * 78)
    sub_segs = evaluate_sub_segments(post55_rows)

    candidate_diagnostics: Dict[str, Dict] = {}
    candidates: List[Tuple[str, str, str, Dict]] = []
    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk"]:
        slices = sub_segs.get(stat, {})
        stat_total = pre57_per_stat.get(stat, {}).get("n", 0)
        if stat_total == 0:
            continue
        print(f"\n  {stat.upper()} sub-segments (post-iter-55 set, total n={stat_total}):")
        print(f"    {'segment':<20} {'n':>5} {'hit%':>6} {'ROI%':>8} {'z':>7}  "
              f"{'95% CI':>20}  candidate?")
        print("    " + "-" * 84)
        for (direction, bucket), seg in sorted(slices.items()):
            complement = stat_total - seg["n"]
            is_cand = is_candidate_zero_ev(seg, complement)
            ci_str = f"[{seg['ci_lo']:+.1f}%, {seg['ci_hi']:+.1f}%]"
            flag = " <-- CANDIDATE" if is_cand else ""
            print(f"    {direction:<5} x {bucket:<10} {seg['n']:>5}  {seg['hit_rate_pct']:>5.2f}%  "
                  f"{seg['roi_pct']:>+7.3f}%  {seg['z_score']:>+6.3f}  {ci_str:>20}{flag}")
            if is_cand:
                candidates.append((stat, direction, bucket, seg))
        candidate_diagnostics[stat] = {
            f"{d}_{b}": {
                "n": seg["n"], "roi_pct": seg["roi_pct"], "z_score": seg["z_score"],
                "ci_lo": seg["ci_lo"], "ci_hi": seg["ci_hi"], "hit_rate_pct": seg["hit_rate_pct"],
                "is_candidate": is_candidate_zero_ev(seg, stat_total - seg["n"]),
            }
            for (d, b), seg in slices.items()
        }

    print(f"\n  Total candidates: {len(candidates)}")
    for stat, d, b, seg in sorted(candidates, key=lambda c: c[3]["roi_pct"]):
        print(f"    {stat.upper()} {d}x{b}: n={seg['n']}, ROI={seg['roi_pct']:+.2f}%, "
              f"z={seg['z_score']:+.3f}, ci_hi={seg['ci_hi']:+.2f}%")

    # ── Greedy compose ─────────────────────────────────────────────────────────
    print("\n" + "-" * 78)
    print("  GREEDY COMPOSITION (worst-ROI candidate first)")
    print("-" * 78)
    picked, log = greedy_compose(all_rows, pre57_agg, pre57_per_stat, candidates)
    for ln in log:
        print(ln)

    # ── Apply final filters ───────────────────────────────────────────────────
    if picked:
        post57_rows     = apply_production_filters(all_rows, extra_subseg_filters=picked)
        post57_per_stat = per_stat_metrics(post57_rows)
        post57_agg      = aggregate_metrics(post57_rows)
    else:
        post57_rows     = post55_rows
        post57_per_stat = pre57_per_stat
        post57_agg      = pre57_agg

    print("\n" + "=" * 78)
    print("  POST-ITER-57 METRICS")
    print("=" * 78)
    agg_delta = post57_agg["roi_pct"] - pre57_agg["roi_pct"]
    print(f"  aggregate: n={post57_agg['n']}, ROI={post57_agg['roi_pct']:+.4f}%, "
          f"delta_vs_pre57={agg_delta:+.4f}pp")
    print(f"  {'Stat':<5} {'pre_n':>6} {'post_n':>7} {'pre_roi%':>10} {'post_roi%':>11} {'delta_pp':>10}")
    for stat in STATS:
        pre_m  = pre57_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        post_m = post57_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        d_pp   = post_m["roi_pct"] - pre_m["roi_pct"]
        print(f"  {stat.upper():<5} {pre_m['n']:>6} {post_m['n']:>7} "
              f"{pre_m['roi_pct']:>+9.4f}% {post_m['roi_pct']:>+10.4f}% "
              f"{d_pp:>+9.4f}pp")

    # ── Ship decision ─────────────────────────────────────────────────────────
    regressions: List[str] = []
    improvements: List[str] = []
    for stat in STATS:
        pre_m  = pre57_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        post_m = post57_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        d_pp   = post_m["roi_pct"] - pre_m["roi_pct"]
        if d_pp < MAX_STAT_REGRESS:
            regressions.append(f"{stat}: {d_pp:+.4f}pp")
        if d_pp > 0.5:
            improvements.append(f"{stat}: {d_pp:+.4f}pp")

    # Threshold logic: REB-only ship uses +0.3pp, otherwise +0.5pp.
    is_reb_only = (
        len(picked) == 1 and
        list(picked.keys()) == ["reb"] and
        picked.get("reb") == [("over", "low")]
    )
    threshold = MIN_AGG_LIFT_REB_SOLO if is_reb_only else MIN_AGG_LIFT_DEFAULT

    agg_passes     = agg_delta >= threshold
    no_regressions = len(regressions) == 0

    if agg_passes and no_regressions and picked:
        decision = "SHIP"
        detail = (
            f"Aggregate delta {agg_delta:+.4f}pp >= +{threshold}pp AND no per-stat "
            f"regression > {MAX_STAT_REGRESS}pp. Filters added: {dict(picked)}."
        )
    elif not picked:
        decision = "REVERT"
        detail = (
            f"No sub-segment candidates passed greedy gate "
            f"(n>={MIN_SEG_N}, z<{MAX_Z_SCORE}, ROI<+{MAX_ROI_PCT}%, ci_hi<+{MAX_CI_HI}% "
            f"and lift >= +0.3pp w/ no -1pp regression). No filters to wire."
        )
    elif not agg_passes:
        decision = "REVERT"
        detail = f"Aggregate delta {agg_delta:+.4f}pp below +{threshold}pp ship threshold."
    else:
        decision = "REVERT"
        detail = f"Per-stat regression(s): {regressions}."

    print("\n" + "=" * 78)
    print(f"  DECISION: {decision}")
    print("=" * 78)
    print(f"  Detail:       {detail}")
    print(f"  Agg delta:    {agg_delta:+.4f}pp (threshold {threshold:+.1f}pp; "
          f"reb-solo? {is_reb_only})")
    print(f"  Regressions:  {regressions if regressions else 'none'}")
    print(f"  Improvements: {improvements if improvements else 'none'}")

    # ── Wire filters if SHIP ──────────────────────────────────────────────────
    filters_wired: List = []
    if decision == "SHIP":
        _wire_filters_into_thresholds(picked, agg_delta, post57_agg, pre57_agg)
        filters_wired = [
            [stat, [list(s) for s in slices]]
            for stat, slices in picked.items()
        ]

    # ── Build result ──────────────────────────────────────────────────────────
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = {
        "iter":            57,
        "generated_at":    now_utc,
        "approach":        "post_iter55_resweep_2d_direction_x_line",
        "n_bets_pre":      pre57_agg["n"],
        "n_bets_post":     post57_agg["n"],
        "pre57_agg_roi":   round(pre57_agg["roi_pct"], 4),
        "post57_agg_roi":  round(post57_agg["roi_pct"], 4),
        "delta_agg_pp":    round(agg_delta, 4),
        "ship_threshold_pp": threshold,
        "is_reb_only":     is_reb_only,
        "decision":        decision,
        "decision_detail": detail,
        "regressions":     regressions,
        "improvements":    improvements,
        "filters_wired":   filters_wired,
        "greedy_log":      log,
        "per_stat": {
            stat: {
                "pre_n":     pre57_per_stat.get(stat, {}).get("n", 0),
                "post_n":    post57_per_stat.get(stat, {}).get("n", 0),
                "pre_roi":   round(pre57_per_stat.get(stat, {}).get("roi_pct", 0.0), 4),
                "post_roi":  round(post57_per_stat.get(stat, {}).get("roi_pct", 0.0), 4),
                "delta_roi": round(
                    post57_per_stat.get(stat, {}).get("roi_pct", 0.0)
                    - pre57_per_stat.get(stat, {}).get("roi_pct", 0.0), 4),
                "filter":    [list(s) for s in picked.get(stat, [])] or None,
            }
            for stat in STATS
        },
        "candidate_diagnostics": candidate_diagnostics,
        "params": {
            "min_seg_n":          MIN_SEG_N,
            "min_complement_n":   MIN_COMPLEMENT_N,
            "max_ci_hi_pct":      MAX_CI_HI,
            "max_roi_pct":        MAX_ROI_PCT,
            "max_z_score":        MAX_Z_SCORE,
            "min_agg_lift_pp_default": MIN_AGG_LIFT_DEFAULT,
            "min_agg_lift_pp_reb_solo": MIN_AGG_LIFT_REB_SOLO,
            "max_stat_regress":   MAX_STAT_REGRESS,
            "n_bootstrap":        N_BOOTSTRAP,
            "seed":               SEED,
        },
    }

    # ── Persist to holdout_baseline.json (read-modify-write) ──────────────────
    baseline: Dict = {}
    if os.path.exists(BASELINE_JSON):
        baseline = json.load(open(BASELINE_JSON, encoding="utf-8"))
    baseline["__iter57__"] = result
    baseline["__updated_at__"] = now_utc
    with open(BASELINE_JSON, "w", encoding="utf-8") as fh:
        json.dump(baseline, fh, indent=2)
    print(f"\n  holdout_baseline.json -> updated with __iter57__ (other keys preserved)")

    # ── Vault report ──────────────────────────────────────────────────────────
    _write_vault_report(result, sub_segs, pre57_per_stat, post57_per_stat)

    return result


# ── Wiring ─────────────────────────────────────────────────────────────────────

def _wire_filters_into_thresholds(
    new_filters: Dict[str, List[Tuple[str, str]]],
    agg_delta: float,
    post_agg: Dict,
    pre_agg: Dict,
) -> None:
    """Extend STAT_DIRECTION_LINE_EXCLUSIONS in bet_thresholds.py with iter-57 picks.

    Strategy: read the file, find the STAT_DIRECTION_LINE_EXCLUSIONS dict literal,
    and rewrite each affected stat's list with the combined (iter-55 + iter-57) slices.
    We do NOT remove iter-55 entries — we APPEND to them.
    """
    with open(THRESHOLDS_PY, encoding="utf-8") as fh:
        content = fh.read()

    # Build the new combined dict (iter-55 + iter-57)
    combined: Dict[str, List[Tuple[str, str]]] = {
        k: list(v) for k, v in STAT_DIRECTION_LINE_EXCLUSIONS.items()
    }
    for stat, slices in new_filters.items():
        combined.setdefault(stat, [])
        for s in slices:
            if s not in combined[stat]:
                combined[stat].append(s)

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Rebuild the dict literal
    new_lines = []
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        slices = combined.get(stat, [])
        if not slices:
            new_lines.append(f'    "{stat}":  [],')
        else:
            slice_strs = ", ".join([f'("{d}", "{b}")' for d, b in slices])
            # Note which iter each came from
            iter55_set = set(STAT_DIRECTION_LINE_EXCLUSIONS.get(stat, []))
            iter57_set = set(new_filters.get(stat, []))
            origin_tags = []
            for s in slices:
                if s in iter55_set and s in iter57_set:
                    origin_tags.append("iter-55+57")
                elif s in iter57_set:
                    origin_tags.append("iter-57")
                else:
                    origin_tags.append("iter-55")
            tag_str = "/".join(sorted(set(origin_tags)))
            new_lines.append(f'    "{stat}":  [{slice_strs}],   # {tag_str}')

    # Locate the existing dict definition and replace just the body
    start_marker = "STAT_DIRECTION_LINE_EXCLUSIONS: dict[str, list[tuple[str, str]]] = {"
    start_idx = content.find(start_marker)
    if start_idx < 0:
        print("  [warn] could not find STAT_DIRECTION_LINE_EXCLUSIONS dict in bet_thresholds.py")
        return
    # Find matching closing brace
    body_start = start_idx + len(start_marker)
    end_idx = content.find("}", body_start)
    if end_idx < 0:
        print("  [warn] could not find closing brace of STAT_DIRECTION_LINE_EXCLUSIONS")
        return

    new_body = "\n" + "\n".join(new_lines) + "\n"
    new_content = content[:body_start] + new_body + content[end_idx:]

    # Prepend an iter-57 comment block above the dict (insert before start_idx line)
    # Find the line start
    line_start = content.rfind("\n", 0, start_idx) + 1
    # Walk back to find the existing iter-55 comment header start
    header_search_start = content.rfind(
        "# ── Iter-55: Per-stat 2D direction x line-bucket exclusions",
        0, start_idx,
    )
    iter57_comment = (
        f"# ── Iter-57: Post-Iter55 resweep additions ─────────────────────────────────\n"
        f"# Re-ran the 2D direction x line_bucket sweep on the post-iter-55 bet set.\n"
        f"# Date: {now_str}.\n"
        f"# Pre-iter-57 baseline: n_bets={pre_agg['n']}, ROI={pre_agg['roi_pct']:+.4f}%.\n"
        f"# Post-iter-57:         n_bets={post_agg['n']}, ROI={post_agg['roi_pct']:+.4f}%.\n"
        f"# Aggregate delta: {agg_delta:+.4f}pp.\n"
        f"# Filters ADDED by iter-57 (appended — iter-55 entries preserved):\n"
    )
    for stat, slices in new_filters.items():
        for d, b in slices:
            iter57_comment += f"#   {stat}: ({d}, {b})\n"

    # Re-locate dict literal in new_content (offsets may have shifted)
    new_start_idx = new_content.find(start_marker)
    new_line_start = new_content.rfind("\n", 0, new_start_idx) + 1
    # Insert iter57 comment block above the STAT_DIRECTION_LINE_EXCLUSIONS line
    final_content = (
        new_content[:new_line_start] + iter57_comment + new_content[new_line_start:]
    )

    with open(THRESHOLDS_PY, "w", encoding="utf-8") as fh:
        fh.write(final_content)
    print(f"  bet_thresholds.py -> STAT_DIRECTION_LINE_EXCLUSIONS extended with iter-57 picks")


# ── Vault report ───────────────────────────────────────────────────────────────

def _write_vault_report(
    result: Dict,
    sub_segs: Dict,
    pre57_per_stat: Dict[str, Dict],
    post57_per_stat: Dict[str, Dict],
) -> None:
    os.makedirs(VAULT_DIR, exist_ok=True)
    now_str  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    decision = result["decision"]

    lines = [
        f"# Iter-57 Post-Iter55 Resweep ({now_str})",
        "",
        "**Goal:** Re-run iter-55-style 2D direction x line_bucket sub-segment refinement "
        "on the NEW post-iter-55 baseline. Iter-55's STAT_DIRECTION_LINE_EXCLUSIONS = "
        "{'ast': [('over','high')]} shifted the bet-set distribution, so all per-stat "
        "reference baselines for sub-segment ROIs need re-measurement.",
        "",
        f"**Baseline:** post-iter-55 ROI = {result['pre57_agg_roi']:+.4f}% on "
        f"{result['n_bets_pre']} bets (real outcome-preserved simulation against eval CSV).",
        "",
        "---",
        "",
        "## Method",
        "",
        "1. Load `data/cache/eval_2025_26_combined.csv` and compute bet direction + hit/roi "
        "per row using the iter-54/55 devig heuristic.",
        "2. Apply CURRENT PRODUCTION FILTERS:",
        "   - `STAT_DIRECTIONS['blk'] = ['under']`  (Iter-51)",
        "   - `STAT_LINE_EXCLUSIONS`                 (Iter-54)",
        "   - `STAT_DIRECTION_LINE_EXCLUSIONS`       (Iter-55: AST over x high)",
        "   This yields the post-iter-55 baseline.",
        f"3. For each stat x (direction, line_bucket) 2D slice with n >= {MIN_SEG_N}, "
        f"compute metrics + bootstrap CI ({N_BOOTSTRAP} resamples).",
        f"4. Mark as candidate if n >= {MIN_SEG_N} AND z < {MAX_Z_SCORE} AND "
        f"ROI < +{MAX_ROI_PCT}% AND ci_hi < +{MAX_CI_HI}%.",
        "5. Greedy compose worst-ROI candidate first — accept if it lifts aggregate "
        "by >= +0.3pp with no per-stat regression > -1pp.",
        f"6. Ship gate: aggregate delta >= +{MIN_AGG_LIFT_DEFAULT}pp (or +{MIN_AGG_LIFT_REB_SOLO}pp "
        "if only REB over x low ships alone) AND no per-stat regression > -1pp.",
        "",
        "---",
        "",
        "## 2D Sub-Segment Diagnostics (post-iter-55 bet set)",
        "",
    ]

    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk"]:
        slices = sub_segs.get(stat, {})
        if not slices:
            continue
        stat_n = pre57_per_stat.get(stat, {}).get("n", 0)
        lines += [
            f"### {stat.upper()} (post-iter-55: n={stat_n}, "
            f"ROI={pre57_per_stat.get(stat,{}).get('roi_pct',0):+.2f}%)",
            "",
            "| direction x bucket | n | hit% | ROI% | z | 95% CI | candidate? |",
            "|--------------------|---|------|------|---|--------|-----------|",
        ]
        for (direction, bucket), seg in sorted(slices.items()):
            complement = stat_n - seg["n"]
            cand = is_candidate_zero_ev(seg, complement)
            ci_str = f"[{seg['ci_lo']:+.1f}%, {seg['ci_hi']:+.1f}%]"
            lines.append(
                f"| {direction} x {bucket} | {seg['n']} | {seg['hit_rate_pct']:.2f}% | "
                f"{seg['roi_pct']:+.3f}% | {seg['z_score']:+.3f} | {ci_str} | "
                f"{'**YES**' if cand else 'no'} |"
            )
        lines.append("")

    lines += [
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
        "## Per-Stat Filter Impact",
        "",
        "| Stat | Iter-57 Filter Added | pre_n | post_n | pre_ROI | post_ROI | delta |",
        "|------|---------------------|-------|--------|---------|----------|-------|",
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
        f"**{result['pre57_agg_roi']:+.4f}%** | **{result['post57_agg_roi']:+.4f}%** | "
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
        f"(ship threshold: +{result['ship_threshold_pp']:.1f}pp, "
        f"reb-only ship? {result['is_reb_only']})",
        f"- Regressions: {result['regressions'] if result['regressions'] else 'none'}",
        f"- Improvements: {result['improvements'] if result['improvements'] else 'none'}",
        "",
    ]

    if decision == "SHIP" and result["filters_wired"]:
        lines += [
            "**Wired to `bet_thresholds.py` STAT_DIRECTION_LINE_EXCLUSIONS (APPENDED to iter-55 entries):**",
            "",
        ]
        for stat, slices in result["filters_wired"]:
            slice_strs = ", ".join([f"({s[0]}, {s[1]})" for s in slices])
            lines.append(f"- {stat.upper()}: drop {slice_strs}")
        lines.append("")

    lines += [
        "---",
        "",
        "## Key Finding",
        "",
    ]
    if decision == "SHIP":
        lines.append(
            "After iter-55 shifted the distribution of remaining bets, the post-iter-55 "
            "re-sweep surfaced additional zero/negative-ROI 2D sub-segments that justify "
            f"filtering. Combined ship lifted aggregate ROI by {result['delta_agg_pp']:+.4f}pp."
        )
    else:
        lines.append(
            "On the post-iter-55 bet set, no additional 2D direction x line sub-segment passed "
            f"the relaxed candidate gate (n>={MIN_SEG_N}, z<{MAX_Z_SCORE}, ROI<+{MAX_ROI_PCT}%, "
            f"ci_hi<+{MAX_CI_HI}%) AND the greedy ship criterion. Iter-55's filtering may have "
            "already absorbed the obvious zero-EV slices; remaining candidates either lack "
            "sample size, have CIs extending too far into positive territory, or fail to lift "
            "the aggregate by +0.3pp under outcome-preserved simulation."
        )

    lines += [
        "",
        "---",
        "",
        f"*Generated by `scripts/iter57_post55_resweep.py` on {now_str}.*",
        "*Refs: [[Iter55 Subsegment Refinement]] | [[Iter54 Segmentation Sweep]] | [[Engineering Knowledge]]*",
    ]

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"  Vault report -> {REPORT_PATH}")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = run()
    print("\n" + "=" * 78)
    print("  ITER-57 COMPLETE")
    print("=" * 78)
    print(f"  Decision:        {result['decision']}")
    print(f"  Aggregate delta: {result['delta_agg_pp']:+.4f}pp")
    print(f"  Pre/post ROI:    {result['pre57_agg_roi']:+.4f}% -> {result['post57_agg_roi']:+.4f}% "
          f"({result['n_bets_pre']} -> {result['n_bets_post']} bets)")
    if result["filters_wired"]:
        print(f"  Filters wired:   {result['filters_wired']}")
    else:
        print("  Filters wired:   none")
    print()
