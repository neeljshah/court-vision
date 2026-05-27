"""iter33_fractional_kelly_backtest.py — Fractional Kelly sizing test on 2025-26 OOS bets.

Tests two Kelly variants against the flat-1u baseline (iter-22+25+28 production).
The flat baseline matches holdout_baseline.json: 1016 bets, +19.5% aggregate ROI.

Variants:
  A. FIXED FRACTIONAL: stake = f * 1u where f = edge / mean_train_edge (per stat).
     Capped at 3u. Normalised so mean stake ≈ 1u (same total exposure as flat).
  B. KELLY-INFORMED: stake = 0.25 * (p_win * b - p_loss) / b.
     p_win from hit-rate + edge-bucket linear scaling. Capped at 3u.

Ship criterion: any variant beats flat by >= +1pp aggregate ROI AND
no more than 1 stat regresses by >1pp.

Method:
  - Uses holdout_baseline per-stat roi_units (actual outcomes) at -110 flat.
  - Reconstructs per-bet edge distribution from prop_residuals_edge_history.json.
  - Reweights each virtual bet by its Kelly stake multiplier.
  - This preserves ACTUAL hit rates / win/loss balance from the production run.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

# ── Paths ─────────────────────────────────────────────────────────────────────
EVAL_CSV      = os.path.join(PROJECT_DIR, "data", "cache", "eval_2025_26_combined.csv")
BASELINE_JSON = os.path.join(PROJECT_DIR, "data", "cache", "holdout_baseline.json")
OUTPUT_JSON   = os.path.join(PROJECT_DIR, "data", "cache", "iter33_kelly_backtest.json")
EDGE_HIST     = os.path.join(PROJECT_DIR, "data", "models",
                              "prop_residuals_edge_history.json")

# ── Thresholds (iter-25) ──────────────────────────────────────────────────────
THRESHOLDS: dict[str, float] = {
    "pts": 0.7, "reb": 1.5, "ast": 1.0,
    "fg3m": 0.7, "stl": 0.4, "blk": 0.4, "tov": 0.5,
}

# ── Kelly caps / fractions ────────────────────────────────────────────────────
MAX_STAKE_U = 3.0    # cap at 3u per bet
KELLY_FRAC  = 0.25   # quarter-Kelly for variant B
PAYOUT_M110 = 100.0 / 110.0  # ≈ 0.9091 per 1u at -110


def _load_baseline() -> dict:
    return json.load(open(BASELINE_JSON, encoding="utf-8"))


def _derive_wins_losses(n: int, roi_units: float) -> tuple[int, int]:
    """From roi_units at flat -110, recover integer wins/losses.
    roi_units = wins * PAYOUT_M110 - losses
    wins + losses = n (ignoring pushes)
    => wins = (roi_units + n) / (PAYOUT_M110 + 1)
    """
    wins_f = (roi_units + n) / (PAYOUT_M110 + 1.0)
    wins = int(round(wins_f))
    losses = n - wins
    return wins, losses


def _load_edge_distribution() -> dict[str, list[float]]:
    """Load absolute edge values per stat from residuals edge history.

    edge_pct = (predicted - line) / line — proportional to absolute edge.
    We use these as relative rankings and rescale later per stat.
    """
    if not os.path.exists(EDGE_HIST):
        print(f"  [warn] {EDGE_HIST} not found — using exponential approximation")
        return {}
    hist = json.load(open(EDGE_HIST, encoding="utf-8"))
    stat_edges: dict[str, list[float]] = defaultdict(list)
    for r in hist:
        stat = r.get("stat", "")
        ep = abs(float(r.get("edge_pct", 0.0) or 0.0))
        if ep > 0:
            stat_edges[stat].append(ep)
    return dict(stat_edges)


def _build_bet_edges(n_bets: int, stat: str,
                     edge_hist: dict[str, list],
                     mean_target: float,
                     rng: np.random.Generator) -> np.ndarray:
    """Generate n_bets edge values for a stat.

    Calibrates edges so their mean equals mean_target.
    If hist data exists, samples from empirical top-30% CDF (above-threshold bets).
    Otherwise falls back to exponential.
    """
    thr = THRESHOLDS.get(stat, 0.5)
    raw = edge_hist.get(stat, [])

    if len(raw) >= 50:
        # Use empirical distribution — top 30% of edges (proxy for above threshold)
        arr = np.array(sorted(raw))
        cut_idx = int(len(arr) * 0.70)
        above = arr[cut_idx:] if cut_idx < len(arr) else arr
        # Scale so mean == mean_target (positive only)
        emp_mean = float(np.mean(above)) if len(above) > 0 else 1.0
        scale = mean_target / max(emp_mean, 1e-6)
        sampled_indices = rng.integers(0, len(above), size=n_bets)
        edges = above[sampled_indices] * scale
    else:
        # Exponential above threshold
        lam = 1.0 / max(mean_target - thr, 0.1)
        edges = thr + rng.exponential(1.0 / lam, size=n_bets)

    return np.clip(edges, thr + 1e-6, None).astype(float)


def _mean_above_threshold(stat: str, edge_hist: dict[str, list]) -> float:
    """Estimate mean |edge| above threshold from the empirical distribution."""
    thr = THRESHOLDS.get(stat, 0.5)
    raw = edge_hist.get(stat, [])
    if len(raw) >= 50:
        arr = np.array(sorted(raw))
        cut_idx = int(len(arr) * 0.70)
        above = arr[cut_idx:]
        if len(above) > 0:
            return float(np.mean(above))
    # Fallback: threshold + 0.5 (typical mean of Exp with rate=2 above threshold)
    return thr + 0.5


def _edge_to_win_prob(edge_abs: float, thr: float, baseline_hit: float) -> float:
    """Linear interpolation from baseline_hit at thr to baseline_hit+0.08 at thr*3."""
    frac = min(1.0, max(0.0, (edge_abs - thr) / max(thr * 2.0, 0.1)))
    p_hi = min(0.85, baseline_hit + 0.08)
    p = baseline_hit + frac * (p_hi - baseline_hit)
    return min(0.90, max(0.50, p))


def run() -> dict:
    print("\n  iter-33 Fractional Kelly Backtest (2025-26 OOS)")
    print(f"  baseline: {BASELINE_JSON}")

    baseline = _load_baseline()
    baseline_g = baseline.get("__global__", {})

    # ── Per-stat production statistics ───────────────────────────────────────
    prod_stats: dict[str, dict] = {}
    for stat, sv in baseline_g.items():
        n = sv["n_bets"]
        roi_units = sv["roi_units"]  # total units PnL at flat -110
        wins, losses = _derive_wins_losses(n, roi_units)
        hit = wins / n if n > 0 else 0.52
        prod_stats[stat] = {
            "n": n,
            "wins": wins,
            "losses": losses,
            "hit": hit,
            "roi_units_flat": roi_units,
            "roi_pct_flat": sv["roi_pct"],
        }
        print(f"  {stat}: n={n} wins={wins} losses={losses} hit={hit:.3f} "
              f"roi_flat={sv['roi_pct']:+.2f}%")

    # ── Load edge distributions ───────────────────────────────────────────────
    edge_hist = _load_edge_distribution()

    # ── Compute mean edges per stat (training proxy) ─────────────────────────
    stat_mean_edge: dict[str, float] = {}
    for stat in THRESHOLDS:
        stat_mean_edge[stat] = _mean_above_threshold(stat, edge_hist)
    print("\n  mean edge above threshold (train proxy):")
    for stat in sorted(THRESHOLDS.keys()):
        print(f"    {stat}: {stat_mean_edge[stat]:.4f}")

    # ── Generate per-bet simulations ──────────────────────────────────────────
    # For each stat, produce n_bets ordered as [wins, losses].
    # Assign edge values from the empirical distribution (IID sample).
    # Outcomes match actual production (wins first, then losses).
    # This preserves the total ROI at flat-1u.

    rng = np.random.default_rng(42)

    all_bets: list[dict] = []

    for stat, ps in sorted(prod_stats.items()):
        n = ps["n"]
        wins = ps["wins"]
        losses = ps["losses"]
        thr = THRESHOLDS.get(stat, 0.5)
        hit = ps["hit"]
        mean_e = stat_mean_edge[stat]

        # Sample edges
        edges = _build_bet_edges(n, stat, edge_hist, mean_e, rng)

        # Shuffle edges to avoid systematic edge–outcome correlation
        rng.shuffle(edges)

        # Outcomes: wins first, then losses (arbitrary ordering)
        outcomes = ["win"] * wins + ["loss"] * losses
        rng.shuffle(np.array(outcomes))  # this is a no-op for shuffling a list
        # Actually shuffle properly:
        outcome_arr = np.array(outcomes)
        rng.shuffle(outcome_arr)
        outcomes = list(outcome_arr)

        for i in range(n):
            edge_val = float(edges[i])
            outcome = outcomes[i]
            all_bets.append({
                "stat": stat,
                "edge": edge_val,
                "outcome": outcome,
                "thr": thr,
                "hit": hit,
                "mean_edge_train": mean_e,
            })

    print(f"\n  total bets generated: {len(all_bets)}")

    # ── Mean edge for normalization (Kelly-A) ─────────────────────────────────
    # Kelly-A: stake = edge / mean_edge_train (per stat), so mean stake = 1u per stat.
    # Aggregate mean across all stats by n-weighted average:
    total_n = sum(ps["n"] for ps in prod_stats.values())
    global_mean_edge = sum(
        prod_stats[s]["n"] * stat_mean_edge.get(s, 1.0)
        for s in prod_stats if s in stat_mean_edge
    ) / max(total_n, 1)
    print(f"  global mean edge (for Kelly-A normalization): {global_mean_edge:.4f}")

    # ── Apply strategies per bet ──────────────────────────────────────────────
    # Payout: flat -110 = 0.9091u per 1u stake (matches production)
    payout_b = PAYOUT_M110

    stat_flat:    dict[str, dict] = defaultdict(lambda: {"pnl": 0.0, "stake": 0.0, "n": 0, "wins": 0})
    stat_kelly_a: dict[str, dict] = defaultdict(lambda: {"pnl": 0.0, "stake": 0.0, "n": 0, "wins": 0})
    stat_kelly_b: dict[str, dict] = defaultdict(lambda: {"pnl": 0.0, "stake": 0.0, "n": 0, "wins": 0})

    top_edge_bets: list[dict] = []

    for bet in all_bets:
        stat    = bet["stat"]
        edge    = bet["edge"]
        outcome = bet["outcome"]
        thr     = bet["thr"]
        hit     = bet["hit"]
        mean_e  = bet["mean_edge_train"]

        # ── FLAT: 1u ────────────────────────────────────────────────────────
        stake_flat = 1.0
        pnl_flat   = payout_b if outcome == "win" else -1.0

        # ── KELLY-A: fixed fractional (edge-proportional, mean=1u per stat) ─
        f_a       = edge / max(mean_e, 1e-6)
        stake_a   = min(f_a, MAX_STAKE_U)
        pnl_a     = stake_a * payout_b if outcome == "win" else -stake_a

        # ── KELLY-B: quarter-Kelly with p_win from edge–hit interpolation ────
        p_win     = _edge_to_win_prob(edge, thr, hit)
        q         = 1.0 - p_win
        full_k    = (p_win * payout_b - q) / payout_b
        if full_k <= 0:
            stake_b = 0.0
        else:
            stake_b = min(KELLY_FRAC * full_k, MAX_STAKE_U)
        pnl_b     = stake_b * payout_b if outcome == "win" else -stake_b

        # Accumulate
        for sv, stake, pnl in [(stat_flat, stake_flat, pnl_flat),
                                (stat_kelly_a, stake_a, pnl_a),
                                (stat_kelly_b, stake_b, pnl_b)]:
            d = sv[stat]
            d["pnl"]   += pnl
            d["stake"] += stake
            d["n"]     += 1
            if outcome == "win":
                d["wins"] += 1

        top_edge_bets.append({
            "stat": stat,
            "edge": round(edge, 4),
            "outcome": outcome,
            "stake_flat": 1.0,
            "stake_a": round(stake_a, 4),
            "stake_b": round(stake_b, 4),
            "pnl_flat": round(pnl_flat, 4),
            "pnl_a": round(pnl_a, 4),
            "pnl_b": round(pnl_b, 4),
        })

    # ── Summaries ─────────────────────────────────────────────────────────────
    def _summarize(sv: dict) -> dict:
        per_stat: dict[str, dict] = {}
        tot_pnl = 0.0
        tot_stake = 0.0
        for stat, d in sv.items():
            roi = d["pnl"] / d["stake"] * 100 if d["stake"] > 0 else 0.0
            per_stat[stat] = {
                "n":       d["n"],
                "pnl":     round(d["pnl"], 4),
                "stake":   round(d["stake"], 4),
                "wins":    d["wins"],
                "roi_pct": round(roi, 2),
            }
            tot_pnl   += d["pnl"]
            tot_stake += d["stake"]
        agg_roi = tot_pnl / tot_stake * 100 if tot_stake > 0 else 0.0
        return {
            "per_stat":    per_stat,
            "total_pnl":   round(tot_pnl, 4),
            "total_stake": round(tot_stake, 4),
            "agg_roi_pct": round(agg_roi, 2),
        }

    flat_s = _summarize(stat_flat)
    ka_s   = _summarize(stat_kelly_a)
    kb_s   = _summarize(stat_kelly_b)

    # ── Cross-validate flat ROI against holdout_baseline ─────────────────────
    print("\n  Cross-validation (flat simulation vs holdout_baseline):")
    max_drift = 0.0
    for stat in sorted(prod_stats.keys()):
        sim_roi   = flat_s["per_stat"].get(stat, {}).get("roi_pct", 0.0)
        prod_roi  = prod_stats[stat]["roi_pct_flat"]
        drift     = abs(sim_roi - prod_roi)
        max_drift = max(max_drift, drift)
        ok = "OK" if drift < 2.0 else "DRIFT"
        print(f"    {stat}: sim={sim_roi:+.2f}%  prod={prod_roi:+.2f}%  drift={drift:.2f}pp  [{ok}]")
    print(f"  sim agg ROI={flat_s['agg_roi_pct']:+.2f}%  "
          f"prod agg ROI={baseline_g.get('pts', {}).get('roi_pct', '?')}% (pts only sample)")
    # Correct agg from baseline
    total_prod_units = sum(sv.get("roi_units", 0) for sv in baseline_g.values())
    total_prod_bets  = sum(sv.get("n_bets", 0) for sv in baseline_g.values())
    prod_agg_roi     = total_prod_units / total_prod_bets * 100 if total_prod_bets else 0
    print(f"  prod agg ROI (exact): {prod_agg_roi:+.2f}%")
    print(f"  sim agg ROI (flat):   {flat_s['agg_roi_pct']:+.2f}%")

    # ── Ship / revert decisions ───────────────────────────────────────────────
    def _decide(variant_s: dict) -> tuple[str, float, int]:
        delta = variant_s["agg_roi_pct"] - flat_s["agg_roi_pct"]
        regressions = 0
        for stat in prod_stats:
            f_roi = flat_s["per_stat"].get(stat, {}).get("roi_pct", 0.0)
            v_roi = variant_s["per_stat"].get(stat, {}).get("roi_pct", 0.0)
            if f_roi - v_roi > 1.0:
                regressions += 1
        if delta >= 1.0 and regressions <= 1:
            dec = "SHIP"
        elif delta < -1.0 or regressions >= 2:
            dec = "REVERT"
        else:
            dec = "INCONCLUSIVE"
        return dec, delta, regressions

    dec_a, delta_a, reg_a = _decide(ka_s)
    dec_b, delta_b, reg_b = _decide(kb_s)

    # ── Print results table ───────────────────────────────────────────────────
    stats_order = sorted(prod_stats.keys())

    print("\n" + "="*76)
    print("  ITER-33 FRACTIONAL KELLY SIZING -- RESULTS (flat @ -110, outcome-preserved)")
    print("="*76)
    print(f"  {'Stat':<6} {'N':>5}  {'Flat%':>8}  {'KellyA%':>9}  {'KellyB%':>9}  "
          f"{'A-stake':>8}  {'B-stake':>8}  {'A-delta':>7}  {'B-delta':>7}")
    print("  " + "-"*76)

    for stat in stats_order:
        fl = flat_s["per_stat"].get(stat, {})
        ka = ka_s["per_stat"].get(stat, {})
        kb = kb_s["per_stat"].get(stat, {})
        da = ka.get("roi_pct", 0) - fl.get("roi_pct", 0)
        db = kb.get("roi_pct", 0) - fl.get("roi_pct", 0)
        print(f"  {stat:<6} {fl.get('n',0):>5}  "
              f"{fl.get('roi_pct',0):>+7.2f}%  "
              f"{ka.get('roi_pct',0):>+8.2f}%  "
              f"{kb.get('roi_pct',0):>+8.2f}%  "
              f"{ka.get('stake',0):>8.2f}u  "
              f"{kb.get('stake',0):>8.2f}u  "
              f"{da:>+6.2f}pp  "
              f"{db:>+6.2f}pp")

    print("  " + "-"*76)
    n_tot = sum(flat_s["per_stat"].get(s, {}).get("n", 0) for s in stats_order)
    print(f"  {'TOTAL':<6} {n_tot:>5}  "
          f"{flat_s['agg_roi_pct']:>+7.2f}%  "
          f"{ka_s['agg_roi_pct']:>+8.2f}%  "
          f"{kb_s['agg_roi_pct']:>+8.2f}%  "
          f"{ka_s['total_stake']:>8.2f}u  "
          f"{kb_s['total_stake']:>8.2f}u  "
          f"{delta_a:>+6.2f}pp  "
          f"{delta_b:>+6.2f}pp")
    print()

    print(f"  Kelly-A: delta={delta_a:+.2f}pp, regressions={reg_a}  =>  {dec_a}")
    print(f"  Kelly-B: delta={delta_b:+.2f}pp, regressions={reg_b}  =>  {dec_b}")

    # ── Top-3 biggest-edge bets ───────────────────────────────────────────────
    top3 = sorted(top_edge_bets, key=lambda x: x["edge"], reverse=True)[:3]
    print("\n  Top-3 biggest-edge bets:")
    for i, b in enumerate(top3, 1):
        print(f"  {i}. stat={b['stat']}, edge={b['edge']:.3f}, outcome={b['outcome']}")
        print(f"     stakes: flat=1u, A={b['stake_a']:.3f}u, B={b['stake_b']:.3f}u")
        print(f"     pnl:    flat={b['pnl_flat']:+.4f}u, A={b['pnl_a']:+.4f}u, B={b['pnl_b']:+.4f}u")

    # ── Save ──────────────────────────────────────────────────────────────────
    output = {
        "iter": 33,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "approach": "fractional_kelly_sizing",
        "method": "edge_dist_sampled_outcome_preserved",
        "flat":    flat_s,
        "kelly_a": ka_s,
        "kelly_b": kb_s,
        "kelly_a_decision": dec_a,
        "kelly_b_decision": dec_b,
        "delta_a_pp": round(delta_a, 4),
        "delta_b_pp": round(delta_b, 4),
        "kelly_a_regressions": reg_a,
        "kelly_b_regressions": reg_b,
        "prod_agg_roi_pct": round(prod_agg_roi, 4),
        "top3_biggest_edge": top3,
        "params": {
            "thresholds": THRESHOLDS,
            "kelly_frac_b": KELLY_FRAC,
            "max_stake_u": MAX_STAKE_U,
            "payout_flat": PAYOUT_M110,
            "prod_hit_rates": {s: round(ps["hit"], 4) for s, ps in prod_stats.items()},
            "mean_train_edges": {s: round(v, 4) for s, v in stat_mean_edge.items()},
        },
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)
    print(f"\n  Output -> {OUTPUT_JSON}")
    return output


if __name__ == "__main__":
    run()
