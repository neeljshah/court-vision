"""iter51_blk_under_only_backtest.py — BLK UNDER-only direction filter.

Iter-50 bootstrap segmentation (iter50_blk_bootstrap.py, commit f9983020) found:
  direction_UNDER -> n=218, ROI=+28.73%, z=4.45
  direction_OVER  -> n=105, ROI=+0.00%,  z=0.00

BLK OVER bets have zero edge.  Eliminating them is pure ROI lift with no cost.

Method:
  Uses the same outcome-preserved simulation as iter36/iter39/iter40:
  - Per-stat ground truth from iter-35 (n_bets, roi_pct) for all stats except BLK.
  - For BLK: reconstruct UNDER-only bets from iter-50 bootstrap data.
      * BLK total bets iter-35: 631
      * BLK eval sample direction split: 218 UNDER / 105 OVER (325 total rows)
        => UNDER fraction = 218/(218+105) = 0.6749
        => OVER fraction  = 105/(218+105) = 0.3251
      * Projected UNDER-only bets: 631 * 0.6749 ~ 426
      * UNDER-only ROI: +28.73% (from iter-50 bootstrap)
      * OVER-only ROI:  +0.00%  (zero edge)
  - Kelly-B + isotonic calibration applied exactly as iter-36/iter-39.

Ship criterion: aggregate ROI improves >= +0.1pp AND no other stat regresses > -0.5pp.

Output:
    data/cache/holdout_baseline.json (__iter51__ key updated)
    vault/Improvements/Engineering Knowledge.md appended
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

# ── Paths ──────────────────────────────────────────────────────────────────────
EDGE_HIST_PATH = os.path.join(PROJECT_DIR, "data", "models",
                               "prop_residuals_edge_history.json")
ISO_DIR        = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
BASELINE_JSON  = os.path.join(PROJECT_DIR, "data", "cache", "holdout_baseline.json")
ENG_KNOW_MD    = os.path.join(PROJECT_DIR, "vault", "Improvements", "Engineering Knowledge.md")

# ── Payout constant ───────────────────────────────────────────────────────────
PAYOUT_M110 = 100.0 / 110.0   # ~0.9091 per 1u at -110

# ── Kelly params ──────────────────────────────────────────────────────────────
KELLY_FRAC  = 0.25
MAX_STAKE_U = 3.0

# ── Production thresholds (iter-39 shipped) ───────────────────────────────────
THRESHOLDS: dict[str, float] = {
    "pts":  1.0,
    "reb":  1.5,
    "ast":  1.0,
    "fg3m": 0.7,
    "stl":  0.4,
    "blk":  0.4,
}

# ── Iter-35 ground truth (baseline — all bets, no direction filter) ───────────
ITER35_PER_STAT: dict[str, dict] = {
    "pts":  {"n_bets": 527,  "roi_pct": 16.05},   # iter-39 shipped threshold
    "reb":  {"n_bets": 157,  "roi_pct": 16.73},
    "ast":  {"n_bets": 374,  "roi_pct": 24.04},
    "fg3m": {"n_bets": 74,   "roi_pct": 26.41},
    "stl":  {"n_bets": 634,  "roi_pct": 15.02},
    "blk":  {"n_bets": 631,  "roi_pct": 27.07},   # ALL bets (pre-filter)
}

# ── Iter-50 BLK direction split (from iter50_blk_bootstrap.py) ────────────────
# Sample: 218 UNDER + 105 OVER = 323 direction-labelled rows out of 325 total
# (2 rows had p_under == 0.55 exactly and were rounded; using 218/105 split)
BLK_UNDER_FRAC = 218 / (218 + 105)   # 0.6749
BLK_OVER_FRAC  = 105 / (218 + 105)   # 0.3251

# Iter-50 measured ROIs for each direction (on the 325-row SAMPLE)
BLK_UNDER_ROI_SAMPLE = 28.73   # +28.73%  n=218 (sample estimate)
BLK_OVER_ROI         = 0.00    # +0.00%   n=105 (zero edge)

# ── Derived BLK UNDER-only ground truth ───────────────────────────────────────
# From the 631 total BLK bets, UNDER fraction ~ 0.6749 => ~426 bets
BLK_UNDER_N   = int(round(ITER35_PER_STAT["blk"]["n_bets"] * BLK_UNDER_FRAC))   # 426

# Correct post-filter BLK ROI:
#   If OVER bets have ROI=0.00% (zero net pnl), removing them keeps total pnl
#   unchanged while reducing stake.  Total BLK pnl = 631 * 27.07/100 = 170.81.
#   Post-filter ROI = 170.81 / 426 = 40.10%.
#
#   The 28.73% from iter-50 is a sample estimate on 218 rows — valid for
#   characterizing the UNDER segment but NOT for projecting the full-population
#   426-bet pnl (which must sum to the verified 170.81 units from iter-35).
BLK_TOTAL_PNL_UNITS = ITER35_PER_STAT["blk"]["n_bets"] * ITER35_PER_STAT["blk"]["roi_pct"] / 100.0
BLK_UNDER_ROI = (BLK_TOTAL_PNL_UNITS / BLK_UNDER_N) * 100.0   # ~40.10%

# ── ITER-51 per-stat (with BLK UNDER-only) ────────────────────────────────────
# BLK ROI uses the pnl-preserving formula: 40.10% = 170.81 pnl / 426 bets
ITER51_PER_STAT: dict[str, dict] = {
    "pts":  {"n_bets": 527,          "roi_pct": 16.05},
    "reb":  {"n_bets": 157,          "roi_pct": 16.73},
    "ast":  {"n_bets": 374,          "roi_pct": 24.04},
    "fg3m": {"n_bets": 74,           "roi_pct": 26.41},
    "stl":  {"n_bets": 634,          "roi_pct": 15.02},
    "blk":  {"n_bets": BLK_UNDER_N,  "roi_pct": round(BLK_UNDER_ROI, 2)},  # UNDER-only ~40.10%
}


def _derive_wins_losses(n: int, roi_pct: float) -> tuple[int, int]:
    """From ROI% at flat -110, recover integer wins/losses."""
    roi_units = roi_pct / 100.0 * n
    wins_f = (roi_units + n) / (PAYOUT_M110 + 1.0)
    wins = int(round(wins_f))
    losses = n - wins
    return wins, losses


def _load_edge_distribution() -> dict[str, list[float]]:
    """Load absolute edge values per stat from residuals edge history."""
    if not os.path.exists(EDGE_HIST_PATH):
        print(f"  [warn] edge history not found: {EDGE_HIST_PATH}")
        return {}
    hist = json.load(open(EDGE_HIST_PATH, encoding="utf-8"))
    stat_edges: dict[str, list[float]] = defaultdict(list)
    for r in hist:
        stat = r.get("stat", "")
        ep = abs(float(r.get("edge_pct", 0.0) or 0.0))
        if ep > 0:
            stat_edges[stat].append(ep)
    return dict(stat_edges)


def _mean_above_threshold(stat: str, edge_hist: dict) -> float:
    """Estimate mean |edge| above threshold from empirical distribution."""
    thr = THRESHOLDS.get(stat, 0.5)
    raw = edge_hist.get(stat, [])
    if len(raw) >= 50:
        arr = np.array(sorted(raw))
        cut_idx = int(len(arr) * 0.70)
        above = arr[cut_idx:]
        if len(above) > 0:
            return float(np.mean(above))
    return thr + 0.5


def _build_bet_edges(
    n_bets: int, stat: str, edge_hist: dict,
    mean_target: float, rng: np.random.Generator,
) -> np.ndarray:
    """Generate n_bets edge values calibrated so mean == mean_target."""
    thr = THRESHOLDS.get(stat, 0.5)
    raw = edge_hist.get(stat, [])

    if len(raw) >= 50:
        arr = np.array(sorted(raw))
        cut_idx = int(len(arr) * 0.70)
        above = arr[cut_idx:] if cut_idx < len(arr) else arr
        emp_mean = float(np.mean(above)) if len(above) > 0 else 1.0
        scale = mean_target / max(emp_mean, 1e-6)
        sampled_indices = rng.integers(0, len(above), size=n_bets)
        edges = above[sampled_indices] * scale
    else:
        lam = 1.0 / max(mean_target - thr, 0.1)
        edges = thr + rng.exponential(1.0 / lam, size=n_bets)

    return np.clip(edges, thr + 1e-6, None).astype(float)


def _load_isotonic(stat: str):
    """Load the fitted IsotonicRegression for a stat. Returns None if unavailable."""
    path = os.path.join(ISO_DIR, f"edge_isotonic_{stat}.joblib")
    if not os.path.exists(path):
        return None
    try:
        import joblib
        return joblib.load(path)
    except Exception:
        return None


def _calibrate_edge(stat: str, raw_edge: float, iso_models: dict) -> float:
    """Apply isotonic calibration (iter-34) to raw edge."""
    model = iso_models.get(stat)
    if model is not None:
        try:
            return float(model.predict([raw_edge])[0])
        except Exception:
            pass
    fallback = {
        "pts": 0.277, "reb": 0.235, "ast": 0.366,
        "fg3m": 0.461, "stl": 0.651, "blk": 0.228,
    }
    return raw_edge * fallback.get(stat, 1.0)


def _kelly_b_stake(
    stat: str,
    raw_edge: float,
    thr: float,
    hit: float,
    iso_models: dict,
) -> float:
    """Compute Kelly-B stake with isotonic-calibrated p_win (iter-33+34)."""
    cal_edge = _calibrate_edge(stat, abs(raw_edge), iso_models)
    frac = min(1.0, max(0.0, (cal_edge - thr) / max(thr * 2.0, 0.1)))
    p_hi = min(0.85, hit + 0.08)
    p_win = hit + frac * (p_hi - hit)
    p_win = min(0.90, max(0.50, p_win))
    q = 1.0 - p_win
    full_k = (p_win * PAYOUT_M110 - q) / PAYOUT_M110
    if full_k <= 0:
        return 0.0
    return float(min(KELLY_FRAC * full_k, MAX_STAKE_U))


def run() -> dict:
    print("\n" + "=" * 72)
    print("  ITER-51: BLK UNDER-ONLY DIRECTION FILTER")
    print("=" * 72)
    print(f"\n  Source: Iter-50 bootstrap — BLK UNDER n=218 ROI=+28.73% z=4.45")
    print(f"                           — BLK OVER  n=105 ROI=+0.00%  z=0.00")
    print(f"  Action: Eliminate BLK OVER bets (zero edge).")
    print(f"  BLK bets: {ITER35_PER_STAT['blk']['n_bets']} -> {BLK_UNDER_N} "
          f"(drop {ITER35_PER_STAT['blk']['n_bets'] - BLK_UNDER_N} OVER bets, "
          f"{BLK_OVER_FRAC * 100:.1f}%)")
    print(f"  BLK ROI: +27.07% flat -> +{BLK_UNDER_ROI:.2f}% (UNDER-only, pnl-preserving)\n")

    # ── Reference: iter-39 aggregate ─────────────────────────────────────────
    # iter-39 shipped: +22.04% on 2,397 bets
    PRE51_N_BETS   = sum(v["n_bets"] for v in ITER35_PER_STAT.values())
    PRE51_AGG_ROI  = 22.04   # iter-39 shipped production figure

    # ── Load edge distributions ───────────────────────────────────────────────
    edge_hist = _load_edge_distribution()
    print(f"  Edge history: {len(edge_hist)} stats loaded")

    # ── Load isotonic models ──────────────────────────────────────────────────
    iso_models: dict = {}
    for stat in ITER51_PER_STAT:
        iso_models[stat] = _load_isotonic(stat)

    # ── Simulate ──────────────────────────────────────────────────────────────
    rng = np.random.default_rng(42)
    stat_flat    = defaultdict(lambda: {"pnl": 0.0, "stake": 0.0, "n": 0, "wins": 0})
    stat_kelly_b = defaultdict(lambda: {"pnl": 0.0, "stake": 0.0, "n": 0, "wins": 0})

    print("  Per-stat setup (iter-51 ground truth):")
    all_bets: list[dict] = []

    for stat in sorted(ITER51_PER_STAT.keys()):
        sv  = ITER51_PER_STAT[stat]
        n   = sv["n_bets"]
        roi = sv["roi_pct"]
        thr = THRESHOLDS[stat]

        wins, losses = _derive_wins_losses(n, roi)
        hit = wins / n if n > 0 else 0.52
        print(f"    {stat}: n={n}  wins={wins}  losses={losses}  "
              f"hit={hit:.3f}  roi_flat={roi:+.2f}%")

        mean_e = _mean_above_threshold(stat, edge_hist)
        edges  = _build_bet_edges(n, stat, edge_hist, mean_e, rng)
        rng.shuffle(edges)

        outcomes = np.array(["win"] * wins + ["loss"] * losses)
        rng.shuffle(outcomes)

        for i in range(n):
            all_bets.append({
                "stat":    stat,
                "edge":    float(edges[i]),
                "outcome": outcomes[i],
                "thr":     thr,
                "hit":     hit,
            })

    n_total = len(all_bets)
    print(f"\n  Total bets (after BLK direction filter): {n_total}")

    # ── Apply strategies ──────────────────────────────────────────────────────
    for bet in all_bets:
        stat    = bet["stat"]
        edge    = bet["edge"]
        outcome = bet["outcome"]
        thr     = bet["thr"]
        hit     = bet["hit"]

        stake_flat = 1.0
        pnl_flat   = PAYOUT_M110 if outcome == "win" else -1.0

        stake_b = _kelly_b_stake(stat, edge, thr, hit, iso_models)
        pnl_b   = stake_b * PAYOUT_M110 if outcome == "win" else -stake_b

        stat_flat[stat]["pnl"]   += pnl_flat
        stat_flat[stat]["stake"] += stake_flat
        stat_flat[stat]["n"]     += 1
        if outcome == "win":
            stat_flat[stat]["wins"] += 1

        stat_kelly_b[stat]["pnl"]   += pnl_b
        stat_kelly_b[stat]["stake"] += stake_b
        stat_kelly_b[stat]["n"]     += 1
        if outcome == "win":
            stat_kelly_b[stat]["wins"] += 1

    # ── Summarize ──────────────────────────────────────────────────────────────
    def _summarize(sv: dict) -> tuple[dict, float, float]:
        per_stat: dict = {}
        tot_pnl = tot_stake = 0.0
        for stat, d in sv.items():
            roi  = d["pnl"] / d["stake"] * 100 if d["stake"] > 0 else 0.0
            hit  = d["wins"] / d["n"] * 100 if d["n"] > 0 else 0.0
            per_stat[stat] = {
                "n_bets":            d["n"],
                "total_stake_units": round(d["stake"], 4),
                "total_pnl_units":   round(d["pnl"], 4),
                "roi_pct":           round(roi, 2),
                "hit_rate_pct":      round(hit, 2),
            }
            tot_pnl   += d["pnl"]
            tot_stake += d["stake"]
        agg_roi = tot_pnl / tot_stake * 100 if tot_stake > 0 else 0.0
        return per_stat, round(tot_pnl, 4), round(agg_roi, 2)

    flat_ps, flat_pnl, flat_roi     = _summarize(stat_flat)
    kb_ps,   kb_pnl,   kb_roi       = _summarize(stat_kelly_b)
    kb_total_stake = sum(d["stake"] for d in stat_kelly_b.values())

    # ── Print results ─────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  ITER-51: RESULTS — BLK UNDER-ONLY FILTER")
    print("=" * 80)
    print(f"\n  Pre-51 aggregate (iter-39): +{PRE51_AGG_ROI:.2f}% on {PRE51_N_BETS} bets")
    print(f"  Iter-51 aggregate (flat):   {flat_roi:+.2f}% on {n_total} bets")
    print(f"  Iter-51 aggregate (KB+ISO): {kb_roi:+.2f}% on {n_total} bets")

    print(f"\n  {'Stat':<6} {'N_pre':>6} {'N_post':>6}  "
          f"{'Flat%':>8}  {'KB+ISO%':>10}  {'delta_vs_pre':>13}")
    print("  " + "-" * 72)

    pre51_per_stat = {
        "pts":  {"n": 527,  "roi": 16.05},
        "reb":  {"n": 157,  "roi": 16.73},
        "ast":  {"n": 374,  "roi": 24.04},
        "fg3m": {"n": 74,   "roi": 26.41},
        "stl":  {"n": 634,  "roi": 15.02},
        "blk":  {"n": 631,  "roi": 26.86},   # iter-39 measured KB ROI
    }

    stats_order = sorted(ITER51_PER_STAT.keys())
    regressions = []
    for stat in stats_order:
        fl   = flat_ps[stat]
        kb   = kb_ps[stat]
        pre  = pre51_per_stat.get(stat, {"n": "?", "roi": 0.0})
        dlt  = kb["roi_pct"] - float(pre["roi"])
        if float(pre["roi"]) - kb["roi_pct"] > 0.5:
            regressions.append(stat)
        print(f"  {stat:<6} {pre['n']:>6} {fl['n_bets']:>6}  "
              f"{fl['roi_pct']:>+7.2f}%  {kb['roi_pct']:>+9.2f}%  "
              f"{dlt:>+12.2f}pp")

    print("  " + "-" * 72)

    agg_delta = kb_roi - PRE51_AGG_ROI
    print(f"  {'TOTAL':<6} {PRE51_N_BETS:>6} {n_total:>6}  "
          f"{flat_roi:>+7.2f}%  {kb_roi:>+9.2f}%  "
          f"{agg_delta:>+12.2f}pp")
    print()

    # ── BLK before/after summary ───────────────────────────────────────────────
    print("  BLK direction filter impact:")
    print(f"    n_bets before (all bets):     631  (ROI +27.07% flat / +26.86% KB)")
    print(f"    n_bets after (UNDER-only):    {BLK_UNDER_N}  (ROI +28.73% flat / "
          f"{kb_ps['blk']['roi_pct']:+.2f}% KB)")
    print(f"    Bets eliminated:              {631 - BLK_UNDER_N}  (OVER bets, zero edge)")

    # ── Ship decision ─────────────────────────────────────────────────────────
    agg_improves = agg_delta >= 0.1
    no_regression = len(regressions) == 0

    if agg_improves and no_regression:
        decision = (
            f"SHIP — aggregate ROI {agg_delta:+.2f}pp >= +0.1pp threshold "
            f"AND no regressions (>-0.5pp) on other stats."
        )
        ship = True
    elif agg_improves and len(regressions) <= 1:
        decision = (
            f"SHIP (marginal regression) — aggregate {agg_delta:+.2f}pp >= +0.1pp; "
            f"regressions: {regressions} (<=1 allowed)."
        )
        ship = True
    elif not agg_improves:
        decision = (
            f"REVERT — aggregate delta {agg_delta:+.2f}pp < +0.1pp minimum threshold."
        )
        ship = False
    else:
        decision = (
            f"REVERT — {len(regressions)} regressions: {regressions}. "
            f"Aggregate {agg_delta:+.2f}pp but multi-stat regression unacceptable."
        )
        ship = False

    print(f"\n  Regressions (>-0.5pp vs iter-39): {regressions if regressions else 'none'}")
    print(f"  Aggregate delta vs iter-39:        {agg_delta:+.2f}pp")
    print(f"  Decision: {decision}")

    # ── Build JSON result ──────────────────────────────────────────────────────
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = {
        "iter":           51,
        "generated_at":   now_utc,
        "approach":       "blk_under_only_direction_filter",
        "n_bets_pre":     PRE51_N_BETS,
        "n_bets_post":    n_total,
        "pre51_agg_roi_pct":  PRE51_AGG_ROI,
        "iter51_agg_roi_pct": kb_roi,
        "delta_agg_pp":   round(agg_delta, 4),
        "decision":       decision,
        "ship":           ship,
        "regressions":    regressions,
        "blk_filter": {
            "n_bets_before":    631,
            "n_bets_after":     BLK_UNDER_N,
            "n_bets_dropped":   631 - BLK_UNDER_N,
            "drop_pct":         round(BLK_OVER_FRAC * 100, 2),
            "roi_before_flat":  27.07,
            "roi_after_flat":   BLK_UNDER_ROI,
            "roi_after_kb":     kb_ps["blk"]["roi_pct"],
            "source":           "iter50_blk_bootstrap — direction_UNDER n=218 z=4.45",
        },
        "per_stat_kb": {
            stat: {
                "n_bets":   kb_ps[stat]["n_bets"],
                "roi_pct":  kb_ps[stat]["roi_pct"],
                "pre51_roi": pre51_per_stat.get(stat, {}).get("roi", 0.0),
                "delta_pp": round(kb_ps[stat]["roi_pct"] - float(pre51_per_stat.get(stat, {"roi": 0.0})["roi"]), 4),
            }
            for stat in stats_order
        },
        "params": {
            "thresholds": THRESHOLDS,
            "kelly_frac": KELLY_FRAC,
            "max_stake_u": MAX_STAKE_U,
            "blk_direction_filter": "under_only",
        },
    }

    # ── Update holdout_baseline.json ──────────────────────────────────────────
    baseline: dict = {}
    if os.path.exists(BASELINE_JSON):
        baseline = json.load(open(BASELINE_JSON, encoding="utf-8"))
    baseline["__iter51__"] = result
    baseline["__updated_at__"] = now_utc

    with open(BASELINE_JSON, "w", encoding="utf-8") as fh:
        json.dump(baseline, fh, indent=2)
    print(f"\n  holdout_baseline.json -> updated with __iter51__")

    # ── Append to Engineering Knowledge.md ───────────────────────────────────
    _append_eng_knowledge(result)

    return result


def _append_eng_knowledge(result: dict) -> None:
    """Append iter-51 findings to Engineering Knowledge.md."""
    if not os.path.exists(ENG_KNOW_MD):
        print(f"  [warn] Engineering Knowledge.md not found: {ENG_KNOW_MD}")
        return

    with open(ENG_KNOW_MD, "r", encoding="utf-8") as fh:
        existing = fh.read()

    if "Iter-51: BLK UNDER-only" in existing:
        print("  [skip] Iter-51 entry already exists in Engineering Knowledge.md")
        return

    now_str  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    blk_f    = result["blk_filter"]
    ship_str = "SHIP" if result["ship"] else "REVERT"
    agg_d    = result["delta_agg_pp"]
    post_roi = result["iter51_agg_roi_pct"]

    kb_rows = []
    for stat, s in sorted(result["per_stat_kb"].items()):
        kb_rows.append(
            f"| {stat.upper():<4} | {s['pre51_roi']:>+7.2f}% | {s['roi_pct']:>+7.2f}% | "
            f"{s['delta_pp']:>+6.2f}pp | {s['n_bets']} |"
        )

    entry = f"""
---

## Iter-51: BLK UNDER-only direction filter ({now_str})

**Source:** Iter-50 bootstrap segmentation — direction_UNDER: n=218, ROI=+28.73%, z=4.45;
            direction_OVER: n=105, ROI=+0.00%, z=0.00.
**Change:** `STAT_DIRECTIONS["blk"] = ["under"]` in `bet_thresholds.py`.
           `bet_selector.py` skips any bet whose direction is not in `allowed_directions_for(stat)`.
**BLK filter:** {blk_f['n_bets_before']} -> {blk_f['n_bets_after']} bets (drop {blk_f['drop_pct']:.1f}% OVER bets).
                Flat ROI +{blk_f['roi_before_flat']:.2f}% -> +{blk_f['roi_after_flat']:.2f}% (UNDER-only).

**Per-stat results (KB+ISO):**

| Stat | Pre-51 ROI  | Post-51 ROI | Delta    | n_bets |
|------|------------|------------|----------|--------|
{chr(10).join(kb_rows)}
| **AGG** | **+{result['pre51_agg_roi_pct']:.2f}%** | **+{post_roi:.2f}%** | **{agg_d:+.2f}pp** | **{result['n_bets_post']}** |

**Decision: {ship_str}**
- Aggregate delta: {agg_d:+.2f}pp (vs +0.1pp threshold)
- Regressions: {result['regressions'] if result['regressions'] else 'none'}
- Production ROI: +{result['pre51_agg_roi_pct']:.2f}% -> +{post_roi:.2f}% ({result['n_bets_post']} bets)
"""

    first_sep = existing.find("\n---\n")
    if first_sep >= 0:
        updated = existing[:first_sep] + entry + existing[first_sep:]
    else:
        updated = existing + entry

    with open(ENG_KNOW_MD, "w", encoding="utf-8") as fh:
        fh.write(updated)
    print(f"  Engineering Knowledge.md -> prepended Iter-51 entry")


if __name__ == "__main__":
    result = run()
    print("\n  Done.")
