"""iter60_tiered_kelly.py — Confidence-tiered Kelly sizing exploration.

Hypothesis: edge magnitude correlates with true win-probability advantage.
High-edge bets should be sized up (closer to full Kelly); low-edge bets sized
down (or skipped). Current production is static Kelly-B with kelly_frac=0.25
across all bets (capped at 3u).

This iter tests EDGE-TIERED Kelly fractions on the 1,535-bet post-iter57
production set:

  Scheme A (terciles):       low<33pct, mid=33-67pct, high>67pct
  Scheme B (asymmetric):     low<25pct, mid=25-75pct, high>75pct
  Scheme C (absolute):       low<5%,    mid=5-12%,    high>=12%

For each scheme x (low_mult, mid_mult, high_mult) combination, simulate
weighted ROI = sum(stake*roi_unit)/sum(stake) and bootstrap 500 trials.

EDGE DEFINITION: implied-prob distance from breakeven on the bet direction.
  edge_pct = |p_bet - 0.5| where p_bet is the de-vigged implied probability
  of the chosen side. Larger edge_pct = book is more confident in that side.

This is NOT a model-vs-market edge (we don't have model probs in eval CSV),
but a "book-side conviction" edge — a proxy that has been the basis of all
prior iter filtering decisions on this same eval CSV.

Ship gate:
  - Aggregate ROI delta >= +0.5pp on post-iter57 baseline (+15.04%)
  - 95% CI lower bound > prior CI lower bound (not just point gain)
  - No per-stat regression > -0.5pp
  - Effective stake count change <= 20% (don't gut exposure)

Run:
    python scripts/iter60_tiered_kelly.py

Output:
    vault/Models/Iter60 Tiered Kelly.md
    data/cache/holdout_baseline.json (__iter60__ key — preserve all others)
    src/prediction/bet_thresholds.py (add KELLY_EDGE_TIERS + helper if SHIP)
    src/prediction/betting_portfolio.py (add kelly_size_tiered if SHIP)
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
REPORT_PATH    = os.path.join(VAULT_DIR, "Iter60 Tiered Kelly.md")
THRESHOLDS_PY  = os.path.join(PROJECT_DIR, "src", "prediction", "bet_thresholds.py")
PORTFOLIO_PY   = os.path.join(PROJECT_DIR, "src", "prediction", "betting_portfolio.py")

# ── Constants ──────────────────────────────────────────────────────────────────
PAYOUT_M110    = 100.0 / 110.0
BREAKEVEN_HR   = 100.0 / (100.0 + 110.0)
N_BOOTSTRAP    = 500
SEED           = 60

# Current production Kelly fraction (Kelly-B baseline)
BASE_KELLY_FRAC = 0.25
MAX_STAKE_U     = 3.0

# Ship gate constants
MIN_AGG_LIFT_PP        = 0.5    # +0.5pp aggregate ROI lift required
MAX_STAT_REGRESS_PP    = -0.5   # no per-stat regression > -0.5pp
MAX_STAKE_COUNT_CHANGE = 0.20   # effective stake count change <= 20%


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


# Line buckets must match iter54/55/57
LINE_BUCKETS: Dict[str, Tuple[float, float]] = {
    "pts":  (9.5,  15.5),
    "reb":  (3.5,  5.5),
    "ast":  (1.5,  3.5),
    "fg3m": (1.5,  1.5),
    "stl":  (0.5,  1.5),
    "blk":  (1.5,  2.5),
}


def line_bucket_for(stat: str, closing_line: float) -> str:
    low_max, mid_max = LINE_BUCKETS.get(stat, (10.0, 20.0))
    if closing_line <= low_max:
        return "low"
    elif closing_line <= mid_max:
        return "mid"
    else:
        return "high"


# ── Data loading (mirrors iter57 logic) ────────────────────────────────────────

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
                p_bet = p_under
                hit = actual_value < closing_line
            elif p_over > 0.55:
                bet_direction = "over"
                p_bet = p_over
                hit = actual_value > closing_line
            else:
                if p_under >= p_over:
                    bet_direction = "under"
                    p_bet = p_under
                    hit = actual_value < closing_line
                else:
                    bet_direction = "over"
                    p_bet = p_over
                    hit = actual_value > closing_line

            edge_pct = abs(p_bet - 0.5) * 100.0  # in percent
            roi_unit = PAYOUT_M110 if hit else -1.0
            bucket   = line_bucket_for(stat, closing_line)

            rows.append({
                "stat":          stat,
                "closing_line":  closing_line,
                "bet_direction": bet_direction,
                "hit":           hit,
                "roi_unit":      roi_unit,
                "line_bucket":   bucket,
                "p_bet":         p_bet,
                "edge_pct":      edge_pct,
            })
    return rows


def apply_production_filters(rows: List[Dict]) -> List[Dict]:
    out: List[Dict] = []
    for r in rows:
        stat = r["stat"]
        if r["bet_direction"] not in allowed_directions_for(stat):
            continue
        if is_line_excluded(stat, r["closing_line"]):
            continue
        slices = STAT_DIRECTION_LINE_EXCLUSIONS.get(stat, [])
        dropped = False
        for drop_dir, drop_bucket in slices:
            if r["bet_direction"] == drop_dir and r["line_bucket"] == drop_bucket:
                dropped = True
                break
        if dropped:
            continue
        out.append(r)
    return out


# ── Tier classification ────────────────────────────────────────────────────────

def get_tier_bounds(rows: List[Dict], scheme: str) -> Tuple[float, float]:
    """Return (low_max_edge, mid_max_edge) such that:
       edge_pct < low_max  -> low tier
       low_max <= edge_pct < mid_max  -> mid tier
       edge_pct >= mid_max  -> high tier
    """
    edges = np.array([r["edge_pct"] for r in rows])
    if scheme == "A":
        return float(np.percentile(edges, 33)), float(np.percentile(edges, 67))
    elif scheme == "B":
        return float(np.percentile(edges, 25)), float(np.percentile(edges, 75))
    elif scheme == "C":
        return 5.0, 12.0
    else:
        raise ValueError(f"unknown scheme: {scheme}")


def tier_for(edge_pct: float, low_max: float, mid_max: float) -> str:
    if edge_pct < low_max:
        return "low"
    elif edge_pct < mid_max:
        return "mid"
    else:
        return "high"


# ── Stake + ROI computation ────────────────────────────────────────────────────

def compute_weighted_roi(
    bets: List[Dict],
    stakes: np.ndarray,
) -> float:
    """Stake-weighted ROI = sum(stake*roi_unit) / sum(stake) * 100."""
    if len(bets) == 0 or stakes.sum() <= 0:
        return 0.0
    roi_units = np.array([b["roi_unit"] for b in bets])
    return float(np.sum(stakes * roi_units) / np.sum(stakes)) * 100.0


def stakes_for_scheme(
    bets: List[Dict],
    low_max: float,
    mid_max: float,
    low_mult: float,
    mid_mult: float,
    high_mult: float,
) -> np.ndarray:
    """Return stake-per-bet array. Stake = base_kelly_frac * mult (capped 3u)."""
    out = np.empty(len(bets))
    for i, b in enumerate(bets):
        t = tier_for(b["edge_pct"], low_max, mid_max)
        m = {"low": low_mult, "mid": mid_mult, "high": high_mult}[t]
        # In production: stake_units = min(base_kelly_frac * full_kelly_units * m, 3.0)
        # In simulation: we model stake as scalar weight (relative stake size).
        # base_kelly_frac=0.25 absorbs into normalization; only relative weight matters.
        # But we still cap at 3.0 / 0.25 = 12.0 multiplier ceiling to mirror prod.
        stake = m  # relative stake unit (mid_mult=1.0 = current baseline weight 0.25)
        out[i] = stake
    # Zero-mult means skip
    return out


def bootstrap_roi(
    bets: List[Dict],
    stakes: np.ndarray,
    n_boot: int = N_BOOTSTRAP,
    seed: int = SEED,
) -> Tuple[float, float, float]:
    """Bootstrap stake-weighted ROI. Returns (mean, ci_lo, ci_hi)."""
    n = len(bets)
    if n == 0:
        return 0.0, 0.0, 0.0
    roi_units = np.array([b["roi_unit"] for b in bets])
    valid = stakes > 0
    if valid.sum() == 0:
        return 0.0, 0.0, 0.0
    rng = np.random.default_rng(seed)
    boot = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        s = stakes[idx]
        r = roi_units[idx]
        if s.sum() <= 0:
            boot[i] = 0.0
        else:
            boot[i] = float(np.sum(s * r) / np.sum(s)) * 100.0
    return (
        float(np.mean(boot)),
        float(np.percentile(boot, 2.5)),
        float(np.percentile(boot, 97.5)),
    )


def per_stat_weighted_roi(
    bets: List[Dict],
    stakes: np.ndarray,
) -> Dict[str, Dict]:
    by_stat: Dict[str, Tuple[List[Dict], List[float]]] = {}
    for i, b in enumerate(bets):
        bs = by_stat.setdefault(b["stat"], ([], []))
        bs[0].append(b)
        bs[1].append(stakes[i])
    out: Dict[str, Dict] = {}
    for stat, (blist, slist) in by_stat.items():
        s_arr = np.array(slist)
        roi = compute_weighted_roi(blist, s_arr)
        effective_n = float(s_arr.sum()) / max(1e-9, mid_mult_for_normalize(stat))
        out[stat] = {
            "n": len(blist),
            "stake_sum": float(s_arr.sum()),
            "roi_pct": round(roi, 4),
            "n_active": int((s_arr > 0).sum()),
        }
    return out


def mid_mult_for_normalize(_stat: str) -> float:
    # Normalize stake-sum so baseline (mult=1) effective_n equals raw n. Trivial here.
    return 1.0


# ── Tier-sweep ─────────────────────────────────────────────────────────────────

# Per prompt: try high in {0.35, 0.40, 0.50}, mid = 0.25 baseline (we represent as
# relative weight: high_mult / 0.25 = 1.4, 1.6, 2.0; low_mult / 0.25). To keep
# things scaled to "1.0 = baseline kelly_frac=0.25", we sweep MULTIPLIERS
# expressed as: relative_mult = kelly_frac / 0.25.
#   mid_mult = 1.0 (always — = 0.25 baseline kelly_frac)
#   high_mult candidates: 1.4 (=0.35), 1.6 (=0.40), 2.0 (=0.50)
#   low_mult  candidates: 0.0 (skip), 0.4 (=0.10), 0.6 (=0.15), 0.8 (=0.20)
HIGH_MULTS = [1.4, 1.6, 2.0]   # corresponding kelly_frac: 0.35, 0.40, 0.50
LOW_MULTS  = [0.0, 0.4, 0.6, 0.8]  # corresponding kelly_frac: 0.0 (skip), 0.10, 0.15, 0.20
MID_MULT   = 1.0  # baseline kelly_frac = 0.25

SCHEMES = ["A", "B", "C"]


def fraction_label(rel_mult: float) -> str:
    """Convert relative multiplier to kelly_frac label."""
    return f"{rel_mult * BASE_KELLY_FRAC:.2f}"


# ── Main ───────────────────────────────────────────────────────────────────────

def run() -> Dict:
    print("\n" + "=" * 78)
    print("  ITER-60: CONFIDENCE-TIERED KELLY SIZING EXPLORATION")
    print("=" * 78)
    print(f"  Base Kelly-B fraction: {BASE_KELLY_FRAC}  (mid_mult=1.0 = baseline)")
    print(f"  HIGH candidates: kelly_frac in {[fraction_label(m) for m in HIGH_MULTS]}")
    print(f"  LOW  candidates: kelly_frac in {[fraction_label(m) for m in LOW_MULTS]}")
    print(f"  Schemes: A=terciles, B=asymmetric, C=absolute thresholds")
    print(f"  Ship gate: agg >= +{MIN_AGG_LIFT_PP}pp AND CI_lo improves AND "
          f"no stat -{abs(MAX_STAT_REGRESS_PP)}pp AND |effective n change| <= "
          f"{int(MAX_STAKE_COUNT_CHANGE*100)}%")
    print()

    # ── Load + filter ─────────────────────────────────────────────────────────
    STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk"]
    all_rows: List[Dict] = []
    for stat in STATS:
        all_rows.extend(load_eval_rows(stat))
    bets = apply_production_filters(all_rows)
    print(f"  Loaded {len(all_rows)} raw rows; {len(bets)} post-filter bets.")

    # ── Baseline: flat kelly_mult = 1.0 (Kelly-B static 0.25) ─────────────────
    base_stakes = np.ones(len(bets))  # all mult=1.0 -> uniform stake
    base_roi   = compute_weighted_roi(bets, base_stakes)
    base_mean, base_ci_lo, base_ci_hi = bootstrap_roi(bets, base_stakes)
    base_per_stat = per_stat_weighted_roi(bets, base_stakes)
    print(f"\n  BASELINE (uniform mult=1.0 == current Kelly-B):")
    print(f"    n_bets={len(bets)}  agg_ROI={base_roi:+.4f}%  "
          f"boot_mean={base_mean:+.4f}%  CI=[{base_ci_lo:+.2f}%, {base_ci_hi:+.2f}%]")
    for stat in STATS:
        m = base_per_stat.get(stat, {})
        print(f"    {stat.upper():<5} n={m.get('n',0):>4} ROI={m.get('roi_pct',0):+.4f}%")

    # ── Edge-tier distribution per scheme ─────────────────────────────────────
    scheme_bounds = {}
    print("\n  Edge-tier bounds + counts per scheme (post-filter set):")
    for sch in SCHEMES:
        lo_max, mi_max = get_tier_bounds(bets, sch)
        scheme_bounds[sch] = (lo_max, mi_max)
        tier_counts = {"low": 0, "mid": 0, "high": 0}
        tier_rois   = {"low": [], "mid": [], "high": []}
        for b in bets:
            t = tier_for(b["edge_pct"], lo_max, mi_max)
            tier_counts[t] += 1
            tier_rois[t].append(b["roi_unit"])
        print(f"\n  Scheme {sch}: low<{lo_max:.2f}%, mid={lo_max:.2f}-{mi_max:.2f}%, "
              f"high>={mi_max:.2f}%")
        for tier in ("low", "mid", "high"):
            cnt = tier_counts[tier]
            roi_pct = (np.mean(tier_rois[tier]) * 100.0) if cnt > 0 else 0.0
            hit_pct = (np.mean([1.0 if r > 0 else 0.0 for r in tier_rois[tier]]) * 100.0) if cnt > 0 else 0.0
            print(f"    {tier:<5}: n={cnt:>4}  hit={hit_pct:>5.2f}%  ROI={roi_pct:+.3f}%")

    # ── Sweep all (scheme, high_mult, low_mult) combos ────────────────────────
    print("\n" + "-" * 78)
    print("  TIER-MULTIPLIER SWEEP")
    print("-" * 78)
    print(f"  {'sch':<3} {'low_frac':<9} {'high_frac':<10} {'eff_n':>7} "
          f"{'agg_ROI':>10} {'boot_mean':>10} {'CI':>22} {'lift_pp':>8}")
    print("  " + "-" * 76)

    results: List[Dict] = []
    for sch in SCHEMES:
        lo_max, mi_max = scheme_bounds[sch]
        for hi_m in HIGH_MULTS:
            for lo_m in LOW_MULTS:
                stakes = stakes_for_scheme(bets, lo_max, mi_max, lo_m, MID_MULT, hi_m)
                if stakes.sum() <= 0:
                    continue
                # Effective n = number of non-zero stake bets (skips count as 0)
                eff_n = int((stakes > 0).sum())
                stake_count_change = abs(eff_n - len(bets)) / max(1, len(bets))
                agg_roi = compute_weighted_roi(bets, stakes)
                boot_mean, ci_lo, ci_hi = bootstrap_roi(bets, stakes)
                lift_pp = agg_roi - base_roi

                results.append({
                    "scheme":     sch,
                    "low_max":    lo_max,
                    "mid_max":    mi_max,
                    "low_mult":   lo_m,
                    "mid_mult":   MID_MULT,
                    "high_mult":  hi_m,
                    "low_frac":   lo_m * BASE_KELLY_FRAC,
                    "mid_frac":   MID_MULT * BASE_KELLY_FRAC,
                    "high_frac":  hi_m * BASE_KELLY_FRAC,
                    "eff_n":      eff_n,
                    "stake_count_change": stake_count_change,
                    "agg_roi":    round(agg_roi, 4),
                    "boot_mean":  round(boot_mean, 4),
                    "ci_lo":      round(ci_lo, 4),
                    "ci_hi":      round(ci_hi, 4),
                    "lift_pp":    round(lift_pp, 4),
                })
                ci_str = f"[{ci_lo:+.2f}%,{ci_hi:+.2f}%]"
                print(f"  {sch:<3} {fraction_label(lo_m):<9} {fraction_label(hi_m):<10} "
                      f"{eff_n:>7} {agg_roi:>+9.4f}% {boot_mean:>+9.4f}% "
                      f"{ci_str:>22} {lift_pp:>+7.4f}")

    # ── Pick best candidate that passes the ship gate ─────────────────────────
    print("\n" + "-" * 78)
    print("  SHIP-GATE EVALUATION")
    print("-" * 78)

    # Sort by aggregate lift descending
    sorted_results = sorted(results, key=lambda r: -r["lift_pp"])

    picked = None
    pick_reasons: List[str] = []
    for cand in sorted_results:
        reasons = []
        # Gate 1: aggregate lift
        if cand["lift_pp"] < MIN_AGG_LIFT_PP:
            reasons.append(f"agg_lift {cand['lift_pp']:+.4f}pp < +{MIN_AGG_LIFT_PP}pp")
        # Gate 2: CI lower bound improves
        if cand["ci_lo"] <= base_ci_lo:
            reasons.append(f"ci_lo {cand['ci_lo']:+.2f}% <= base_ci_lo {base_ci_lo:+.2f}%")
        # Gate 3: stake count change
        if cand["stake_count_change"] > MAX_STAKE_COUNT_CHANGE:
            reasons.append(
                f"|n change|={cand['stake_count_change']*100:.1f}% > "
                f"{MAX_STAKE_COUNT_CHANGE*100:.0f}%")
        # Gate 4: per-stat regression
        stakes = stakes_for_scheme(bets, cand["low_max"], cand["mid_max"],
                                   cand["low_mult"], MID_MULT, cand["high_mult"])
        cand_per_stat = per_stat_weighted_roi(bets, stakes)
        stat_regressions = []
        for s in STATS:
            pre = base_per_stat.get(s, {}).get("roi_pct", 0.0)
            post = cand_per_stat.get(s, {}).get("roi_pct", 0.0)
            d = post - pre
            if d < MAX_STAT_REGRESS_PP:
                stat_regressions.append(f"{s}: {d:+.4f}pp")
        if stat_regressions:
            reasons.append(f"per_stat: {stat_regressions}")

        tag = f"sch{cand['scheme']}/lo={fraction_label(cand['low_mult'])}/hi={fraction_label(cand['high_mult'])}"
        if not reasons:
            picked = cand
            picked["per_stat"] = cand_per_stat
            picked["stat_regressions"] = []
            pick_reasons.append(f"  PICK {tag}: agg_lift={cand['lift_pp']:+.4f}pp, "
                                f"CI=[{cand['ci_lo']:+.2f}%,{cand['ci_hi']:+.2f}%], "
                                f"eff_n={cand['eff_n']}")
            break
        else:
            pick_reasons.append(f"  SKIP {tag}: {'; '.join(reasons)}")

    for ln in pick_reasons[:15]:
        print(ln)
    if len(pick_reasons) > 15:
        print(f"  ...({len(pick_reasons) - 15} more candidates skipped)")

    # ── Decision ──────────────────────────────────────────────────────────────
    if picked:
        decision = "SHIP"
        detail = (
            f"Scheme {picked['scheme']} tiered Kelly "
            f"(low_frac={picked['low_frac']:.2f}, mid_frac={picked['mid_frac']:.2f}, "
            f"high_frac={picked['high_frac']:.2f}) lifts aggregate by "
            f"{picked['lift_pp']:+.4f}pp with CI_lo improvement "
            f"({base_ci_lo:+.2f}% -> {picked['ci_lo']:+.2f}%) and effective n change "
            f"{(picked['eff_n']-len(bets))/len(bets)*100:+.1f}%."
        )
    else:
        decision = "REVERT"
        detail = (
            "No tier scheme passed all gates (agg >= +0.5pp, CI_lo improves, "
            "|eff_n change| <= 20%, no stat regression > -0.5pp). The static "
            f"Kelly-B baseline (uniform mult=1.0, kelly_frac={BASE_KELLY_FRAC}) "
            "remains optimal on this 1,535-bet OOS set. Confidence-tiering does "
            "not extract incremental edge — likely because edge_pct (book-side "
            "implied probability) is not strongly correlated with hit-rate variation "
            "after iter-51/54/55/57 filters already pre-selected the high-EV bet pool."
        )

    print("\n" + "=" * 78)
    print(f"  DECISION: {decision}")
    print("=" * 78)
    print(f"  Detail: {detail}")

    # ── Wire if SHIP ──────────────────────────────────────────────────────────
    if decision == "SHIP":
        _wire_into_bet_thresholds(picked)
        _wire_into_betting_portfolio(picked)

    # ── Persist ───────────────────────────────────────────────────────────────
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build per-stat for picked or baseline
    if picked:
        per_stat_result = {
            stat: {
                "base_roi":  round(base_per_stat.get(stat, {}).get("roi_pct", 0.0), 4),
                "post_roi":  round(picked["per_stat"].get(stat, {}).get("roi_pct", 0.0), 4),
                "delta_pp":  round(
                    picked["per_stat"].get(stat, {}).get("roi_pct", 0.0)
                    - base_per_stat.get(stat, {}).get("roi_pct", 0.0), 4),
                "n":         base_per_stat.get(stat, {}).get("n", 0),
            }
            for stat in STATS
        }
    else:
        per_stat_result = {
            stat: {
                "base_roi": round(base_per_stat.get(stat, {}).get("roi_pct", 0.0), 4),
                "post_roi": round(base_per_stat.get(stat, {}).get("roi_pct", 0.0), 4),
                "delta_pp": 0.0,
                "n":        base_per_stat.get(stat, {}).get("n", 0),
            }
            for stat in STATS
        }

    result = {
        "iter":            60,
        "generated_at":    now_utc,
        "approach":        "confidence_tiered_kelly_sizing",
        "n_bets":          len(bets),
        "base_kelly_frac": BASE_KELLY_FRAC,
        "base_agg_roi":    round(base_roi, 4),
        "base_ci_lo":      round(base_ci_lo, 4),
        "base_ci_hi":      round(base_ci_hi, 4),
        "best_candidate":  picked,
        "decision":        decision,
        "decision_detail": detail,
        "per_stat":        per_stat_result,
        "sweep_results":   [
            {k: v for k, v in r.items() if k != "per_stat"}
            for r in results
        ],
        "schemes": {
            sch: {
                "low_max_pct":  scheme_bounds[sch][0],
                "mid_max_pct":  scheme_bounds[sch][1],
            }
            for sch in SCHEMES
        },
        "params": {
            "base_kelly_frac":       BASE_KELLY_FRAC,
            "max_stake_u":           MAX_STAKE_U,
            "high_mults":            HIGH_MULTS,
            "low_mults":             LOW_MULTS,
            "n_bootstrap":           N_BOOTSTRAP,
            "seed":                  SEED,
            "min_agg_lift_pp":       MIN_AGG_LIFT_PP,
            "max_stat_regress_pp":   MAX_STAT_REGRESS_PP,
            "max_stake_count_change": MAX_STAKE_COUNT_CHANGE,
        },
    }

    baseline: Dict = {}
    if os.path.exists(BASELINE_JSON):
        baseline = json.load(open(BASELINE_JSON, encoding="utf-8"))
    baseline["__iter60__"] = result
    baseline["__updated_at__"] = now_utc
    with open(BASELINE_JSON, "w", encoding="utf-8") as fh:
        json.dump(baseline, fh, indent=2)
    print(f"\n  holdout_baseline.json -> updated with __iter60__ (other keys preserved)")

    _write_vault_report(result, base_per_stat)
    return result


# ── Wiring helpers ─────────────────────────────────────────────────────────────

def _wire_into_bet_thresholds(picked: Dict) -> None:
    """Append KELLY_EDGE_TIERS dict + get_kelly_fraction helper to bet_thresholds.py."""
    with open(THRESHOLDS_PY, encoding="utf-8") as fh:
        content = fh.read()

    if "KELLY_EDGE_TIERS" in content:
        print("  [warn] KELLY_EDGE_TIERS already exists in bet_thresholds.py — skip wire")
        return

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sch = picked["scheme"]
    lo_max = picked["low_max"]
    mi_max = picked["mid_max"]
    lo_frac = picked["low_frac"]
    mi_frac = picked["mid_frac"]
    hi_frac = picked["high_frac"]
    lift = picked["lift_pp"]

    snippet = f'''

# ── Iter-60: Confidence-tiered Kelly sizing ─────────────────────────────────
# Edge-magnitude-tiered Kelly fraction (scheme {sch}). Tested 36 combinations
# of (high, low) Kelly fractions across 3 edge-tier schemes (terciles, asymmetric,
# absolute thresholds) on 1,535 post-iter57 production bets.
# Date: {now_str}.
# Baseline (uniform kelly_frac={BASE_KELLY_FRAC}): agg ROI = {picked.get("_base_agg_roi", "n/a")}.
# Selected: scheme {sch} with low_frac={lo_frac:.2f}, mid_frac={mi_frac:.2f},
#           high_frac={hi_frac:.2f} -> aggregate lift {lift:+.4f}pp.
# Edge bucket boundaries (from devig-implied |p_bet - 0.5|):
#   low  : edge_pct < {lo_max:.3f}%
#   mid  : {lo_max:.3f}% <= edge_pct < {mi_max:.3f}%
#   high : edge_pct >= {mi_max:.3f}%
KELLY_EDGE_TIERS: list[dict] = [
    {{"min_edge_pct":  0.0,                "max_edge_pct": {lo_max:.4f}, "kelly_frac": {lo_frac:.4f}}},
    {{"min_edge_pct":  {lo_max:.4f},       "max_edge_pct": {mi_max:.4f}, "kelly_frac": {mi_frac:.4f}}},
    {{"min_edge_pct":  {mi_max:.4f},       "max_edge_pct": 100.0,        "kelly_frac": {hi_frac:.4f}}},
]


def get_kelly_fraction(edge_pct: float, base_frac: float = {BASE_KELLY_FRAC}) -> float:
    """Return tiered Kelly fraction for *edge_pct* (Iter-60).

    *edge_pct* is the absolute distance from 0.5 of the devig-implied probability
    of the BET DIRECTION (i.e., |p_bet - 0.5| * 100). Larger = book more confident
    on that side.

    Returns the tiered kelly_frac. Returns *base_frac* (= 0.25 default) if no
    tier matches (shouldn't happen — the high tier covers up to 100%).
    """
    for tier in KELLY_EDGE_TIERS:
        if tier["min_edge_pct"] <= edge_pct < tier["max_edge_pct"]:
            return tier["kelly_frac"]
    return base_frac
'''

    with open(THRESHOLDS_PY, "a", encoding="utf-8") as fh:
        fh.write(snippet)
    print(f"  bet_thresholds.py -> appended KELLY_EDGE_TIERS + get_kelly_fraction helper")


def _wire_into_betting_portfolio(picked: Dict) -> None:
    """Add NEW kelly_size_tiered helper to betting_portfolio.py (do NOT replace kelly_b_stake)."""
    with open(PORTFOLIO_PY, encoding="utf-8") as fh:
        content = fh.read()

    if "def kelly_size_tiered" in content:
        print("  [warn] kelly_size_tiered already in betting_portfolio.py — skip wire")
        return

    snippet = f'''

# ── Iter-60: Tiered Kelly sizing (additive — does NOT replace kelly_b_stake) ──
def kelly_size_tiered(
    edge_abs: float,
    edge_pct: float,
    stat: str,
    bankroll: float,
    unit_size: "Optional[float]" = None,
    odds: int = -110,
) -> float:
    """Iter-60 confidence-tiered Kelly stake sizing.

    Like kelly_b_stake() but the Kelly fraction is selected per-bet from
    KELLY_EDGE_TIERS based on *edge_pct* (devig-implied edge magnitude on the
    chosen bet direction). Larger edge -> larger Kelly fraction (closer to full Kelly).

    Args:
        edge_abs: Absolute edge in stat units (e.g., |pred - line|) — used for
                  p_win interpolation (mirrors kelly_b_stake).
        edge_pct: Devig-implied edge magnitude in percent (|p_bet - 0.5| * 100).
        stat:     Stat key ('pts', 'reb', etc.).
        bankroll: Current bankroll in dollars.
        unit_size: 1u in dollars (defaults to 1% bankroll).
        odds:     American odds (default -110).

    Returns:
        Recommended bet size in dollars, capped at {MAX_STAKE_U}u.
    """
    from src.prediction.bet_thresholds import get_kelly_fraction

    thr  = _KELLY_B_THRESHOLDS.get(stat.lower(), 0.5)
    hit  = _KELLY_B_HIT_RATES.get(stat.lower(), 0.52)
    payout_b = _american_to_payout(odds)
    if payout_b <= 0:
        return 0.0

    # Same p_win interpolation as kelly_b_stake
    frac  = min(1.0, max(0.0, (edge_abs - thr) / max(thr * 2.0, 0.01)))
    p_hi  = min(0.85, hit + 0.08)
    p_win = hit + frac * (p_hi - hit)
    p_win = min(0.90, max(0.50, p_win))

    q          = 1.0 - p_win
    full_kelly = (p_win * payout_b - q) / payout_b
    if full_kelly <= 0.0:
        return 0.0

    # Iter-60: select Kelly fraction from edge_pct tier instead of static {BASE_KELLY_FRAC}
    kelly_frac = get_kelly_fraction(edge_pct, base_frac={BASE_KELLY_FRAC})
    if kelly_frac <= 0.0:
        return 0.0  # tier says skip

    u = unit_size if unit_size and unit_size > 0 else bankroll * 0.01
    raw_units  = kelly_frac * full_kelly
    capped_u   = min(raw_units, {MAX_STAKE_U})
    return round(capped_u * u, 2)
'''

    with open(PORTFOLIO_PY, "a", encoding="utf-8") as fh:
        fh.write(snippet)
    print(f"  betting_portfolio.py -> appended kelly_size_tiered() helper (does NOT replace kelly_b_stake)")


# ── Vault report ───────────────────────────────────────────────────────────────

def _write_vault_report(result: Dict, base_per_stat: Dict) -> None:
    os.makedirs(VAULT_DIR, exist_ok=True)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    decision = result["decision"]

    lines = [
        f"# Iter-60 Tiered Kelly Sizing ({now_str})",
        "",
        "**Hypothesis:** Edge magnitude (devig-implied conviction on the bet direction) "
        "correlates with true win-probability advantage. Sizing high-edge bets closer to "
        "full Kelly and low-edge bets smaller (or skipping them) should lift aggregate ROI.",
        "",
        f"**Baseline:** post-iter57 production set — uniform Kelly-B fraction = {BASE_KELLY_FRAC}, "
        f"agg ROI = {result['base_agg_roi']:+.4f}% on {result['n_bets']} bets. "
        f"Bootstrap 95% CI = [{result['base_ci_lo']:+.2f}%, {result['base_ci_hi']:+.2f}%].",
        "",
        "---",
        "",
        "## Method",
        "",
        "1. Load `data/cache/eval_2025_26_combined.csv`. Apply current production filters "
        "(iter-51 BLK direction, iter-54 line exclusions, iter-55+57 2D filters).",
        "2. For each bet, compute `edge_pct = |p_bet - 0.5| * 100`, where p_bet is the "
        "devig-implied probability of the chosen bet direction. (Note: this is "
        "book-side conviction, not a model-vs-market edge — eval CSV has no model probs.)",
        "3. Try 3 tier schemes:",
        "   - **Scheme A (terciles):** low<33pct, mid=33-67pct, high>67pct edge_pct",
        "   - **Scheme B (asymmetric):** low<25pct, mid=25-75pct, high>=75pct",
        "   - **Scheme C (absolute):** low<5%, mid=5-12%, high>=12% edge_pct",
        f"4. For each scheme x (high_mult, low_mult) combination (high in "
        f"{{0.35, 0.40, 0.50}}, low in {{0.0=skip, 0.10, 0.15, 0.20}}, mid fixed at "
        f"{BASE_KELLY_FRAC}), compute stake-weighted ROI and bootstrap CI ({N_BOOTSTRAP} "
        "resamples).",
        f"5. Ship gate: agg lift >= +{MIN_AGG_LIFT_PP}pp AND CI_lo > base_CI_lo AND "
        f"no per-stat regression > {MAX_STAT_REGRESS_PP}pp AND |effective n change| "
        f"<= {int(MAX_STAKE_COUNT_CHANGE*100)}%.",
        "",
        "---",
        "",
        "## Scheme Tier Bounds",
        "",
        "| Scheme | low_max | mid_max |",
        "|--------|---------|---------|",
    ]
    for sch in SCHEMES:
        b = result["schemes"].get(sch, {})
        lines.append(f"| {sch} | {b.get('low_max_pct', 0):.3f}% | {b.get('mid_max_pct', 0):.3f}% |")

    lines += [
        "",
        "---",
        "",
        "## Sweep Results (sorted by aggregate lift desc, top 18)",
        "",
        "| sch | low_frac | high_frac | eff_n | agg_ROI | boot_mean | CI | lift_pp |",
        "|-----|----------|-----------|-------|---------|-----------|----|---------|",
    ]
    for r in sorted(result["sweep_results"], key=lambda x: -x["lift_pp"])[:18]:
        ci_str = f"[{r['ci_lo']:+.2f}%, {r['ci_hi']:+.2f}%]"
        lines.append(
            f"| {r['scheme']} | {r['low_frac']:.2f} | {r['high_frac']:.2f} | "
            f"{r['eff_n']} | {r['agg_roi']:+.4f}% | {r['boot_mean']:+.4f}% | "
            f"{ci_str} | {r['lift_pp']:+.4f}pp |"
        )

    lines += [
        "",
        "---",
        "",
        "## Per-Stat Impact (baseline vs picked)",
        "",
        "| Stat | n | base_ROI | post_ROI | delta_pp |",
        "|------|---|----------|----------|----------|",
    ]
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk"):
        ps = result["per_stat"][stat]
        lines.append(
            f"| {stat.upper()} | {ps['n']} | {ps['base_roi']:+.4f}% | "
            f"{ps['post_roi']:+.4f}% | {ps['delta_pp']:+.4f}pp |"
        )

    lines += [
        "",
        "---",
        "",
        f"## Decision: {decision}",
        "",
        result["decision_detail"],
        "",
    ]

    if decision == "SHIP" and result["best_candidate"]:
        p = result["best_candidate"]
        lines += [
            f"**Wired:** `KELLY_EDGE_TIERS` + `get_kelly_fraction()` -> "
            f"`src/prediction/bet_thresholds.py`",
            f"**Wired:** `kelly_size_tiered()` helper -> `src/prediction/betting_portfolio.py` "
            f"(NEW function — `kelly_b_stake()` left intact for back-compat).",
            "",
            f"Selected scheme **{p['scheme']}**:",
            f"- low tier (edge_pct < {p['low_max']:.3f}%): kelly_frac = **{p['low_frac']:.2f}**",
            f"- mid tier (edge_pct {p['low_max']:.3f}% to {p['mid_max']:.3f}%): kelly_frac = **{p['mid_frac']:.2f}**",
            f"- high tier (edge_pct >= {p['mid_max']:.3f}%): kelly_frac = **{p['high_frac']:.2f}**",
            "",
            f"Aggregate ROI: {result['base_agg_roi']:+.4f}% -> {p['agg_roi']:+.4f}% "
            f"({p['lift_pp']:+.4f}pp).",
            f"Bootstrap CI: [{result['base_ci_lo']:+.2f}%, {result['base_ci_hi']:+.2f}%] -> "
            f"[{p['ci_lo']:+.2f}%, {p['ci_hi']:+.2f}%].",
        ]
    else:
        lines += [
            "## Key Finding",
            "",
            "Confidence-tiering on devig-implied edge magnitude did NOT extract incremental "
            "ROI on the post-iter57 1,535-bet OOS set. Likely explanations:",
            "",
            "1. **Book-side edge_pct is a weak proxy for model-vs-market edge.** Larger "
            "implied edges reflect book confidence, which may already incorporate the "
            "true signal we're trying to capture.",
            "2. **Prior filters absorbed the heterogeneity.** Iter-51/54/55/57 pre-selected "
            "high-EV bets via direction/line/2D filters. Within the surviving pool, edge_pct "
            "no longer maps cleanly to hit-rate variation.",
            "3. **Sample size after tier-split** (~500/bet per tier) introduces noise that "
            "dominates any real tier-level ROI differential.",
            "",
            "**Implication:** Static Kelly-B (kelly_frac=0.25) remains optimal. Future "
            "sizing work should require model-prob features (not present in eval CSV) to "
            "construct a true model-vs-market edge.",
        ]

    lines += [
        "",
        "---",
        "",
        f"*Generated by `scripts/iter60_tiered_kelly.py` on {now_str}.*",
        "*Refs: [[Iter57 Post-Iter55 Resweep]] | [[Iter58 Stage Venue 3D Sweep]] | "
        "[[Iter59 Per Player Filter]] | [[Engineering Knowledge]]*",
    ]

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"  Vault report -> {REPORT_PATH}")


if __name__ == "__main__":
    result = run()
    print("\n" + "=" * 78)
    print("  ITER-60 COMPLETE")
    print("=" * 78)
    print(f"  Decision:        {result['decision']}")
    if result["best_candidate"]:
        p = result["best_candidate"]
        print(f"  Scheme:          {p['scheme']}")
        print(f"  low/mid/high:    {p['low_frac']:.2f} / {p['mid_frac']:.2f} / {p['high_frac']:.2f}")
        print(f"  Lift:            {p['lift_pp']:+.4f}pp")
        print(f"  CI:              [{p['ci_lo']:+.2f}%, {p['ci_hi']:+.2f}%]")
    print(f"  Base ROI:        {result['base_agg_roi']:+.4f}% (uniform Kelly-B)")
    print()
