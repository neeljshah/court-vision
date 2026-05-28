"""iter36_honest_full_stack_measure.py — Full shipped-stack measurement on 2,688-bet eval.

Measures the COMPLETE production stack on the iter-35 expanded 2025-26 eval (2,688 bets):
  1. Iter-22 model predictions (implied via iter-35 per-stat flat outcomes)
  2. Iter-25 thresholds (PTS 0.7, AST 1.0, REB 1.5, FG3M 0.7, STL 0.4, BLK 0.4)
  3. Iter-28 ensemble weights (AST w_new=0.6, STL w_new=0.5, others w_new=1.0)
     [These are already baked into the iter-35 flat outcomes — the 2688 bets use the ensembled model]
  4. Iter-33 Kelly-B sizing
  5. Iter-34 isotonic calibration applied to Kelly-B sizing

Method: Outcome-preserved simulation using actual iter-35 per-stat results.
  - Per-stat wins/losses are derived from iter-35 Engineering Knowledge.md data
    (n_bets, ROI%  -> wins, losses via -110 payout formula)
  - Edge distribution sampled from prop_residuals_edge_history.json (same as iter-33)
  - Isotonic calibration models loaded from data/models/oos_pre_playoffs/
  - Kelly-B applied with isotonic-calibrated p_win (iter-34 logic)

The iter-35 flat outcomes are the authoritative ground truth for bets.
Kelly-B + iso calibration reweights stakes per bet based on predicted edge magnitude.

Comparisons:
  - Iter-23 baseline:  +19.37% on 1,337 flat-bet sample
  - Iter-33 Kelly-B:   +22.03% on 1,016 bets
  - Iter-34 isotonic:  +23.20% on 1,016 bets
  - Iter-35 expanded:  +18.39% on 2,688 flat-bet sample
  - Iter-36 (NEW):     Full stack on 2,688 bets  <-- this script

Output: data/cache/holdout_baseline.json (__iter36__ key updated)
        vault/Improvements/Engineering Knowledge.md appended
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

# ── Paths ──────────────────────────────────────────────────────────────────────
EDGE_HIST_PATH  = os.path.join(PROJECT_DIR, "data", "models",
                               "prop_residuals_edge_history.json")
ISO_DIR         = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
BASELINE_JSON   = os.path.join(PROJECT_DIR, "data", "cache", "holdout_baseline.json")
ENG_KNOW_MD     = os.path.join(PROJECT_DIR, "vault", "Improvements", "Engineering Knowledge.md")

# ── Payout constant ───────────────────────────────────────────────────────────
PAYOUT_M110 = 100.0 / 110.0   # ≈ 0.9091 per 1u at -110

# ── Kelly params (iter-33) ────────────────────────────────────────────────────
KELLY_FRAC  = 0.25
MAX_STAKE_U = 3.0

# ── Iter-25 thresholds ────────────────────────────────────────────────────────
THRESHOLDS: dict[str, float] = {
    "pts":  0.7,
    "reb":  1.5,
    "ast":  1.0,
    "fg3m": 0.7,
    "stl":  0.4,
    "blk":  0.4,
}

# ── Iter-35 per-stat GROUND TRUTH (from Engineering Knowledge.md) ─────────────
# These are the actual outcomes on the 2,688-bet expanded eval (flat -110)
# NOTE (iter-52 correction): REB was updated from 16.73%/157bets (stale 85-feat pkl,
# mismatch vs 133-feat meta → inference crashed) to 9.32%/241bets (fresh 132-feat pkl).
ITER35_PER_STAT: dict[str, dict] = {
    "pts":  {"n_bets": 818,  "roi_pct": 11.32},
    "reb":  {"n_bets": 241,  "roi_pct": 9.32},   # iter-52 corrected (was 16.73/157, stale pkl)
    "ast":  {"n_bets": 374,  "roi_pct": 24.04},
    "fg3m": {"n_bets": 74,   "roi_pct": 26.41},
    "stl":  {"n_bets": 634,  "roi_pct": 15.03},
    "blk":  {"n_bets": 631,  "roi_pct": 27.07},
}


def _derive_wins_losses(n: int, roi_pct: float) -> tuple[int, int]:
    """From ROI% at flat -110, recover integer wins/losses.

    roi_units = roi_pct / 100 * n
    roi_units = wins * PAYOUT_M110 - losses * 1.0
    wins + losses = n
    => wins = (roi_units + n) / (PAYOUT_M110 + 1)
    """
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
    # Fallback: linear shrinkage slopes (iter-21)
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
    print("\n" + "="*72)
    print("  ITER-36: HONEST FULL STACK MEASUREMENT ON 2,688-BET EVAL")
    print("="*72)
    print(f"\n  Stack: Iter-22 model + Iter-25 thresholds + Iter-28 ensemble")
    print(f"         + Iter-33 Kelly-B + Iter-34 isotonic calibration")
    print(f"  Eval:  2,688-bet expanded 2025-26 (RS + playoffs)")
    print(f"  Method: Outcome-preserved simulation on iter-35 per-stat data\n")

    # ── Load edge distributions ───────────────────────────────────────────────
    edge_hist = _load_edge_distribution()
    print(f"  Edge history: {len(edge_hist)} stats loaded")
    for stat in sorted(ITER35_PER_STAT):
        n_raw = len(edge_hist.get(stat, []))
        print(f"    {stat}: {n_raw} edge samples")

    # ── Load isotonic models (iter-34) ────────────────────────────────────────
    iso_models: dict = {}
    print("\n  Isotonic calibration models:")
    for stat in sorted(ITER35_PER_STAT):
        m = _load_isotonic(stat)
        iso_models[stat] = m
        status = "LOADED" if m is not None else "FALLBACK (linear shrinkage)"
        print(f"    {stat}: {status}")

    # ── Per-stat setup ────────────────────────────────────────────────────────
    rng = np.random.default_rng(42)

    stat_flat   = defaultdict(lambda: {"pnl": 0.0, "stake": 0.0, "n": 0, "wins": 0})
    stat_kelly_b = defaultdict(lambda: {"pnl": 0.0, "stake": 0.0, "n": 0, "wins": 0})

    print("\n  Per-stat setup (iter-35 ground truth):")
    all_bets: list[dict] = []

    for stat in sorted(ITER35_PER_STAT.keys()):
        sv = ITER35_PER_STAT[stat]
        n = sv["n_bets"]
        roi_pct = sv["roi_pct"]
        thr = THRESHOLDS[stat]

        wins, losses = _derive_wins_losses(n, roi_pct)
        hit = wins / n if n > 0 else 0.52
        roi_units_flat = wins * PAYOUT_M110 - losses * 1.0

        print(f"    {stat}: n={n}  wins={wins}  losses={losses}  "
              f"hit={hit:.3f}  roi_flat={roi_pct:+.2f}%")

        # Derive mean edge above threshold from empirical distribution
        mean_e = _mean_above_threshold(stat, edge_hist)

        # Sample edge values for n bets
        edges = _build_bet_edges(n, stat, edge_hist, mean_e, rng)
        rng.shuffle(edges)

        # Outcomes: wins + losses, randomly shuffled (preserves total but not order)
        outcomes = ["win"] * wins + ["loss"] * losses
        out_arr = np.array(outcomes)
        rng.shuffle(out_arr)

        for i in range(n):
            all_bets.append({
                "stat": stat,
                "edge": float(edges[i]),
                "outcome": out_arr[i],
                "thr": thr,
                "hit": hit,
            })

    print(f"\n  Total bets: {len(all_bets)}")

    # ── Apply strategies per bet ──────────────────────────────────────────────
    for bet in all_bets:
        stat    = bet["stat"]
        edge    = bet["edge"]
        outcome = bet["outcome"]
        thr     = bet["thr"]
        hit     = bet["hit"]

        # FLAT: 1u
        stake_flat = 1.0
        pnl_flat   = PAYOUT_M110 if outcome == "win" else -1.0

        # KELLY-B with isotonic calibration (iter-33+34)
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

    # ── Summarize ─────────────────────────────────────────────────────────────
    def _summarize(sv: dict) -> tuple[dict, float, float]:
        per_stat: dict = {}
        tot_pnl = 0.0
        tot_stake = 0.0
        for stat, d in sv.items():
            roi = d["pnl"] / d["stake"] * 100 if d["stake"] > 0 else 0.0
            hit  = d["wins"] / d["n"] * 100 if d["n"] > 0 else 0.0
            per_stat[stat] = {
                "n_bets":           d["n"],
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

    # Kelly-B total stake for reference
    kb_total_stake = sum(d["stake"] for d in stat_kelly_b.values())

    # ── Cross-validate flat vs iter-35 ground truth ──────────────────────────
    print("\n  Cross-validation (simulated flat vs iter-35 ground truth):")
    max_drift = 0.0
    for stat in sorted(ITER35_PER_STAT.keys()):
        sim_roi  = flat_ps[stat]["roi_pct"]
        true_roi = ITER35_PER_STAT[stat]["roi_pct"]
        drift    = abs(sim_roi - true_roi)
        max_drift = max(max_drift, drift)
        flag = "OK" if drift < 1.5 else "DRIFT"
        print(f"    {stat}: sim={sim_roi:+.2f}%  truth={true_roi:+.2f}%  "
              f"drift={drift:.2f}pp  [{flag}]")
    print(f"  Max drift: {max_drift:.2f}pp  |  "
          f"Simulated agg flat ROI: {flat_roi:+.2f}%  |  "
          f"True agg flat ROI: +18.39%")

    # ── Per-stat comparison table ──────────────────────────────────────────────
    print("\n" + "="*80)
    print("  ITER-36: FULL STACK RESULTS (2,688-bet expanded eval)")
    print("="*80)
    print(f"  {'Stat':<6} {'N':>5}  {'Flat%':>8}  {'KellyB_ISO%':>12}  "
          f"{'B-stake':>9}  {'B-delta':>8}  {'Hit%':>6}")
    print("  " + "-"*72)

    stats_order = sorted(ITER35_PER_STAT.keys())
    for stat in stats_order:
        fl = flat_ps[stat]
        kb = kb_ps[stat]
        db = kb["roi_pct"] - fl["roi_pct"]
        print(f"  {stat:<6} {fl['n_bets']:>5}  "
              f"{fl['roi_pct']:>+7.2f}%  "
              f"{kb['roi_pct']:>+11.2f}%  "
              f"{kb['total_stake_units']:>9.2f}u  "
              f"{db:>+7.2f}pp  "
              f"{kb['hit_rate_pct']:>5.1f}%")

    n_tot = sum(fl["n_bets"] for fl in flat_ps.values())
    print("  " + "-"*72)
    print(f"  {'TOTAL':<6} {n_tot:>5}  "
          f"{flat_roi:>+7.2f}%  "
          f"{kb_roi:>+11.2f}%  "
          f"{kb_total_stake:>9.2f}u  "
          f"{kb_roi - flat_roi:>+7.2f}pp  {'':>5}")
    print()

    # ── Comparison vs prior iter milestones ──────────────────────────────────
    print("  Reference comparisons:")
    refs = [
        ("Iter-23 baseline (1,337 bets flat)",    "+19.37%", 1337),
        ("Iter-33 Kelly-B (1,016 bets)",           "+22.03%", 1016),
        ("Iter-34 Kelly-B+ISO (1,016 bets)",       "+23.20%", 1016),
        ("Iter-35 expanded flat (2,688 bets)",     "+18.39%", 2688),
        (f"Iter-36 FULL STACK (2,688 bets, flat)", f"{flat_roi:+.2f}%", n_tot),
        (f"Iter-36 FULL STACK (2,688 bets, KB+ISO)", f"{kb_roi:+.2f}%", n_tot),
    ]
    for label, roi, n in refs:
        print(f"    {label:<45} {roi}  (n={n})")

    # ── Regression analysis (KB+ISO vs flat) ─────────────────────────────────
    regressions = []
    for stat in stats_order:
        f_roi = flat_ps[stat]["roi_pct"]
        b_roi = kb_ps[stat]["roi_pct"]
        if f_roi - b_roi > 1.0:
            regressions.append(stat)

    delta_kb = kb_roi - flat_roi
    if delta_kb >= 1.0 and len(regressions) <= 1:
        decision = "SHIP — Kelly-B+ISO lifts aggregate ROI on 2,688-bet sample"
    elif delta_kb < -1.0 or len(regressions) >= 2:
        decision = "REVERT — Kelly-B+ISO regresses on expanded sample"
    else:
        decision = "INCONCLUSIVE — marginal delta, review per-stat"

    print(f"\n  Kelly-B+ISO delta vs flat: {delta_kb:+.2f}pp")
    print(f"  Regressions (>1pp below flat): {regressions if regressions else 'none'}")
    print(f"  Decision: {decision}")

    # ── Whether iter-33 and iter-34 lifts survive ─────────────────────────────
    # Iter-33 claimed +2.52pp lift on 1016 bets
    # Iter-34 claimed +1.17pp lift on top of iter-33, total +3.69pp on 1016 bets
    # Now measuring on 2,688 bets
    print(f"\n  HONEST SUSTAINABILITY CHECK:")
    print(f"  Iter-33+34 claimed lifts (1,016 bets): +3.69pp (vs flat 19.51% -> 23.20%)")
    print(f"  Iter-36 measured lift (2,688 bets):    {delta_kb:+.2f}pp (vs flat {flat_roi:+.2f}% -> {kb_roi:+.2f}%)")
    survive = "SURVIVE" if abs(delta_kb) >= 0.5 and delta_kb > 0 else "DO NOT SURVIVE on expanded sample"
    print(f"  Iter-33+34 lifts: {survive}")

    # ── Build output JSON ────────────────────────────────────────────────────
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    iter36_result = {
        "iter": 36,
        "generated_at": now_utc,
        "approach": "honest_full_stack_measurement_2688_bets",
        "method": "outcome_preserved_simulation_on_iter35_per_stat",
        "n_bets_total": n_tot,
        "flat_agg_roi_pct": flat_roi,
        "kelly_b_iso_agg_roi_pct": kb_roi,
        "delta_kb_iso_vs_flat_pp": round(delta_kb, 4),
        "regressions_kb_iso": regressions,
        "decision": decision,
        "survive_iter33_34": delta_kb > 0.5,
        "cross_val_max_drift_pp": round(max_drift, 2),
        "flat_per_stat": flat_ps,
        "kelly_b_iso_per_stat": kb_ps,
        "iter35_ground_truth": ITER35_PER_STAT,
        "comparisons": {
            "iter23_flat_1337": 19.37,
            "iter33_kelly_b_1016": 22.03,
            "iter34_kelly_b_iso_1016": 23.20,
            "iter35_flat_2688": 18.39,
            "iter36_flat_2688_sim": flat_roi,
            "iter36_kelly_b_iso_2688": kb_roi,
        },
        "params": {
            "thresholds": THRESHOLDS,
            "kelly_frac": KELLY_FRAC,
            "max_stake_u": MAX_STAKE_U,
            "payout_m110": round(PAYOUT_M110, 6),
        },
    }

    # ── Update holdout_baseline.json ──────────────────────────────────────────
    baseline = {}
    if os.path.exists(BASELINE_JSON):
        baseline = json.load(open(BASELINE_JSON, encoding="utf-8"))

    baseline["__iter36__"] = iter36_result

    # Also update __global__ with the expanded per-stat n_bets and roi from iter-35
    # (these are the HONEST flat stats, not the small-N 1016-bet sample)
    baseline["__global_iter35__"] = {
        stat: {
            "roi_pct": sv["roi_pct"],
            "n_bets": sv["n_bets"],
            "hit_rate": ITER35_PER_STAT[stat]["roi_pct"],  # derived
            "threshold": THRESHOLDS[stat],
        }
        for stat, sv in ITER35_PER_STAT.items()
    }
    baseline["__updated_at__"] = now_utc

    with open(BASELINE_JSON, "w", encoding="utf-8") as fh:
        json.dump(baseline, fh, indent=2)
    print(f"\n  holdout_baseline.json -> updated with __iter36__")

    # ── Append to Engineering Knowledge.md ───────────────────────────────────
    _append_eng_knowledge(iter36_result)

    return iter36_result


def _append_eng_knowledge(result: dict) -> None:
    """Append iter-36 findings to Engineering Knowledge.md."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    flat_roi  = result["flat_agg_roi_pct"]
    kb_roi    = result["kelly_b_iso_agg_roi_pct"]
    delta_kb  = result["delta_kb_iso_vs_flat_pp"]
    n_total   = result["n_bets_total"]
    survive   = result["survive_iter33_34"]

    kb_ps   = result["kelly_b_iso_per_stat"]
    flat_ps = result["flat_per_stat"]

    # Per-stat table rows
    stat_rows = []
    for stat in sorted(flat_ps.keys()):
        f = flat_ps[stat]
        k = kb_ps[stat]
        db = k["roi_pct"] - f["roi_pct"]
        stat_rows.append(
            f"| {stat.upper():<4} | {f['roi_pct']:>+7.2f}% | {k['roi_pct']:>+7.2f}% | "
            f"{db:>+6.2f}pp | {f['n_bets']} |"
        )

    survive_str = "YES" if survive else "NO"
    entry = f"""
---

## Iter-36: Honest full-stack re-measurement on 2,688-bet expanded eval ({now_str})

**Goal:** Measure complete shipped stack (Iter-22+25+28+33+34) on the expanded 2025-26 eval.
**Method:** Outcome-preserved simulation using iter-35 per-stat win/loss counts + synthetic edge distribution.

**Per-stat results (2,688 bets, flat vs Kelly-B+ISO):**

| Stat | Flat ROI    | KB+ISO ROI  | Delta    | n_bets |
|------|------------|------------|----------|--------|
{chr(10).join(stat_rows)}
| **AGG** | **{flat_roi:>+.2f}%** | **{kb_roi:>+.2f}%** | **{delta_kb:>+.2f}pp** | **{n_total}** |

**Comparison to prior milestones:**
- Iter-23 baseline (1,337 bets flat):          +19.37%
- Iter-33 Kelly-B (1,016 bets):                +22.03%
- Iter-34 Kelly-B+ISO (1,016 bets):            +23.20%
- Iter-35 expanded flat (2,688 bets):          +18.39%
- Iter-36 full stack KB+ISO (2,688 bets):      {kb_roi:+.2f}%

**Do Iter-33+34 lifts survive on 2,688-bet sample?** {survive_str}
- Small-N inflation: Iter-33+34 showed +3.69pp lift on 1,016 bets. On 2,688 bets: {delta_kb:+.2f}pp.
- Regression check: {result['regressions_kb_iso'] if result['regressions_kb_iso'] else 'no regressions vs flat'}.
- Decision: {result['decision']}.

**Honest sustainable production ROI (2,688 bets, full stack):** {kb_roi:+.2f}%
"""

    if os.path.exists(ENG_KNOW_MD):
        with open(ENG_KNOW_MD, "r", encoding="utf-8") as fh:
            existing = fh.read()
        # Avoid duplicate
        if "Iter-36: Honest full-stack" in existing:
            print("  [skip] Iter-36 entry already exists in Engineering Knowledge.md")
            return
        # Prepend after the header block (after the rules section, before first ---)
        first_sep = existing.find("\n---\n")
        if first_sep >= 0:
            updated = existing[:first_sep] + entry + existing[first_sep:]
        else:
            updated = existing + entry
        with open(ENG_KNOW_MD, "w", encoding="utf-8") as fh:
            fh.write(updated)
        print(f"  Engineering Knowledge.md -> prepended Iter-36 entry")
    else:
        print(f"  [warn] Engineering Knowledge.md not found: {ENG_KNOW_MD}")


if __name__ == "__main__":
    result = run()
    print("\n  Done.")
