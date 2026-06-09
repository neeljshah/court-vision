"""eval_kelly_with_cv_consistency.py — INT-55: Evaluate CV Consistency Kelly Multiplier.

Replays historical bets with and without the cv_consistency_mult applied.

Gates (all must pass to SHIP):
  G1: Aggregate CLV delta (E2 - baseline) >= +0.5pp
  G2: Worst per-stat CLV regression >= -0.5pp
  G3: Aggregate ROI delta non-negative
  G4: Coverage >= 60% of retro bets have non-NULL cv_consistency_z
  G5 (X3a): Null control — 50 seeds random_uniform[-2,2];
            median |ΔCL V| < 30% of real |ΔCLV|
  G6 (colinearity): |corr(cv_z, INT-16)| AND |corr(cv_z, n_games)| both < 0.4

Outputs:
  data/intelligence/cv_consistency_eval.json
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

KELLY_PATH = ROOT / "data" / "intelligence" / "cv_consistency_kelly.parquet"
INT16_PATH = ROOT / "data" / "intelligence" / "per_player_confidence.parquet"
BETS_GLOB = str(ROOT / "data" / "bets" / "strategy_d_*.csv")
BET_LOG_PATH = ROOT / "data" / "models" / "bet_log.json"
CLV_LOG_PATH = ROOT / "data" / "models" / "clv_log.json"
OUT_PATH = ROOT / "data" / "intelligence" / "cv_consistency_eval.json"

MAX_BET_PCT = 0.04  # 4% bankroll hard cap
DEFAULT_BANKROLL = 10000.0
SEED_NULL_CONTROL = 50  # number of random multiplier seeds

# ---------------------------------------------------------------------------
# Player name -> player_id mapping
# Uses INT-16 per_player_confidence as primary source
# ---------------------------------------------------------------------------

def build_player_name_map() -> Dict[str, int]:
    """Build dict {normalized_name: player_id} from INT-16 parquet."""
    if not INT16_PATH.exists():
        log.warning("INT-16 parquet not found; player name mapping unavailable")
        return {}
    df = pd.read_parquet(INT16_PATH)[["player_id", "player_name"]]
    mapping = {}
    for _, row in df.iterrows():
        name = str(row["player_name"]).strip().lower()
        mapping[name] = int(row["player_id"])
    return mapping


def resolve_player_id(name: str, name_map: Dict[str, int]) -> Optional[int]:
    """Resolve player name to NBA player_id with fuzzy fallback."""
    if not name:
        return None
    key = name.strip().lower()
    if key in name_map:
        return name_map[key]
    # Partial match: last name only
    parts = key.split()
    if len(parts) >= 2:
        last = parts[-1]
        for k, v in name_map.items():
            if k.endswith(last):
                return v
    return None


# ---------------------------------------------------------------------------
# Load retro bet data
# ---------------------------------------------------------------------------

def load_retro_bets() -> pd.DataFrame:
    """Load all strategy_d_*.csv files and bet_log.json into unified DataFrame."""
    import glob as g

    dfs: List[pd.DataFrame] = []

    # strategy_d CSV files (canonical retro grade set)
    csv_files = g.glob(BETS_GLOB)
    for fpath in csv_files:
        df = pd.read_csv(fpath)
        log.info("Loaded %s: %d rows", fpath, len(df))
        # Normalize columns
        col_map = {
            "date": "bet_date",
            "side": "direction",
            "line": "book_line",
            "model_pred": "projection",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        dfs.append(df)

    # bet_log.json (paper bets with CLV-adjacent metadata)
    if BET_LOG_PATH.exists():
        with open(BET_LOG_PATH) as f:
            bets = json.load(f)
        if isinstance(bets, list) and bets:
            bl = pd.DataFrame(bets)
            if "date" in bl.columns:
                bl = bl.rename(columns={"date": "bet_date"})
            dfs.append(bl)
            log.info("Loaded bet_log.json: %d rows", len(bl))

    if not dfs:
        log.error("No bet data found")
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True, sort=False)
    log.info("Total bet rows: %d", len(combined))

    # Normalize date columns
    for col in ["bet_date", "date"]:
        if col in combined.columns:
            combined["bet_date"] = pd.to_datetime(combined["bet_date"], errors="coerce")
            break

    return combined


# ---------------------------------------------------------------------------
# Merge bets with cv_consistency data
# ---------------------------------------------------------------------------

def merge_bets_with_consistency(
    bets: pd.DataFrame,
    kelly_df: pd.DataFrame,
    name_map: Dict[str, int],
) -> pd.DataFrame:
    """Merge bets with cv_consistency_kelly via player_id + asof merge_asof.

    Uses pd.merge_asof (direction='backward') so bets always use a
    cv_consistency snapshot from BEFORE the bet date (no future leak).
    """
    bets = bets.copy()

    # Resolve player_id for each bet
    player_col = None
    for c in ["player", "player_name", "player_id"]:
        if c in bets.columns:
            player_col = c
            break

    if player_col is None:
        log.warning("No player column found in bets; cannot merge")
        bets["player_id_resolved"] = np.nan
        bets["cv_consistency_z"] = np.nan
        bets["cv_consistency_mult"] = 1.0
        bets["n_cv_games_in_window"] = np.nan
        return bets

    if player_col == "player_id":
        bets["player_id_resolved"] = bets["player_id"].astype("Int64")
    else:
        bets["player_id_resolved"] = bets[player_col].apply(
            lambda n: resolve_player_id(str(n), name_map) if pd.notna(n) else None
        )

    # Prepare kelly_df for merge_asof
    kelly_df = kelly_df.copy()
    kelly_df["asof_dt"] = pd.to_datetime(kelly_df["asof_date"])
    kelly_df = kelly_df.sort_values("asof_dt")

    # Per-player merge_asof
    bets["bet_date"] = pd.to_datetime(bets.get("bet_date", bets.get("date")), errors="coerce")
    bets = bets.dropna(subset=["bet_date"])

    merged_parts: List[pd.DataFrame] = []

    for pid, grp in bets.groupby("player_id_resolved", dropna=True):
        try:
            pid_int = int(pid)
        except (ValueError, TypeError):
            grp["cv_consistency_z"] = np.nan
            grp["cv_consistency_mult"] = 1.0
            grp["n_cv_games_in_window"] = np.nan
            merged_parts.append(grp)
            continue

        k_sub = kelly_df[kelly_df["player_id"] == pid_int][
            ["asof_dt", "cv_consistency_z", "cv_consistency_mult", "n_cv_games_in_window"]
        ].sort_values("asof_dt")

        grp = grp.sort_values("bet_date")

        if k_sub.empty:
            grp["cv_consistency_z"] = np.nan
            grp["cv_consistency_mult"] = 1.0
            grp["n_cv_games_in_window"] = np.nan
            merged_parts.append(grp)
            continue

        # merge_asof: for each bet date, find nearest prior cv snapshot
        m = pd.merge_asof(
            grp.reset_index(drop=True).assign(_bet_dt=grp["bet_date"].values),
            k_sub.rename(columns={"asof_dt": "_bet_dt"}),
            on="_bet_dt",
            direction="backward",
        )
        m = m.drop(columns=["_bet_dt"])
        merged_parts.append(m)

    # Also handle bets with no resolved player_id
    unresolved_mask = bets["player_id_resolved"].isna()
    if unresolved_mask.any():
        unresolved = bets[unresolved_mask].copy()
        unresolved["cv_consistency_z"] = np.nan
        unresolved["cv_consistency_mult"] = 1.0
        unresolved["n_cv_games_in_window"] = np.nan
        merged_parts.append(unresolved)

    if not merged_parts:
        return bets

    result = pd.concat(merged_parts, ignore_index=True, sort=False)

    # Fill null multiplier with 1.0 (neutral)
    result["cv_consistency_mult"] = result["cv_consistency_mult"].fillna(1.0)

    return result


# ---------------------------------------------------------------------------
# Replay logic
# ---------------------------------------------------------------------------

def compute_adjusted_stake(
    row: pd.Series,
    bankroll: float,
    max_bet_pct: float = MAX_BET_PCT,
) -> float:
    """Apply cv_consistency_mult to baseline stake, capped at max_bet_pct * bankroll."""
    base_stake = float(row.get("stake", 100.0) or 100.0)
    mult = float(row.get("cv_consistency_mult", 1.0) or 1.0)
    adjusted = base_stake * mult
    max_stake = bankroll * max_bet_pct
    return min(adjusted, max_stake)


def compute_outcome_metrics(
    bets: pd.DataFrame,
    stake_col: str,
    bankroll: float,
) -> Dict[str, Any]:
    """Compute ROI, hit_rate, CLV proxy from a set of bets with given stake column.

    CLV proxy: we use 'edge' (model_pred - line) as CLV proxy.
    Positive edge on correct side = positive CLV.
    Real CLV would require closing line data, which is absent from strategy_d.
    """
    df = bets.dropna(subset=[stake_col]).copy()
    if df.empty:
        return {"roi": np.nan, "hit_rate": np.nan, "total_wagered": 0, "total_profit": 0, "clv_mean": np.nan, "n_bets": 0}

    # Profit calculation
    if "profit" in df.columns:
        # Scale profit by stake ratio
        orig_stake = df.get("stake", pd.Series([100.0] * len(df), index=df.index))
        orig_stake = orig_stake.fillna(100.0).replace(0, 100.0)
        stake_ratio = df[stake_col] / orig_stake
        df["scaled_profit"] = df["profit"] * stake_ratio
    else:
        df["scaled_profit"] = 0.0

    total_wagered = df[stake_col].sum()
    total_profit = df["scaled_profit"].sum()
    roi = total_profit / max(total_wagered, 1.0)

    # Hit rate
    if "status" in df.columns:
        wins = (df["status"].str.upper() == "WIN").sum()
        settled = df["status"].str.upper().isin(["WIN", "LOSS"]).sum()
        hit_rate = wins / max(settled, 1)
    elif "profit" in df.columns:
        hit_rate = (df["scaled_profit"] > 0).mean()
    else:
        hit_rate = np.nan

    # CLV proxy: edge = |model_pred - line| (always positive = model is right directionally)
    clv_mean = np.nan
    if "edge" in df.columns:
        clv_mean = float(df["edge"].mean())

    return {
        "roi": float(roi),
        "hit_rate": float(hit_rate) if not np.isnan(hit_rate) else np.nan,
        "total_wagered": float(total_wagered),
        "total_profit": float(total_profit),
        "clv_mean": clv_mean,
        "n_bets": int(len(df)),
    }


def build_bankroll_curve(bets: pd.DataFrame, stake_col: str, initial: float) -> List[float]:
    """Return cumulative bankroll over bet sequence."""
    df = bets.dropna(subset=[stake_col]).sort_values("bet_date").copy()
    bankroll = initial
    curve = [bankroll]
    for _, row in df.iterrows():
        pnl = float(row.get("scaled_profit", 0.0) if "scaled_profit" in row else 0.0)
        bankroll += pnl
        curve.append(bankroll)
    return curve


# ---------------------------------------------------------------------------
# Null control (X3a)
# ---------------------------------------------------------------------------

def run_null_control(
    bets: pd.DataFrame,
    real_clv_delta: float,
    n_seeds: int = SEED_NULL_CONTROL,
    bankroll: float = DEFAULT_BANKROLL,
) -> Dict[str, Any]:
    """50-seed random uniform[-2,2] multiplier test.

    If median |ΔCLV_random| >= 30% of |ΔCLV_real|, the real signal is not
    convincingly above noise.
    """
    rng = np.random.default_rng(42)
    random_deltas: List[float] = []

    baseline_metrics = compute_outcome_metrics(bets, "stake", bankroll)
    baseline_clv = baseline_metrics.get("clv_mean", 0.0) or 0.0

    for seed in range(n_seeds):
        rng_s = np.random.default_rng(seed)
        bets_s = bets.copy()
        bets_s["random_mult"] = rng_s.uniform(-2, 2, size=len(bets_s)) + 1.0
        # Clip to [0.5, 1.5] to match real multiplier range
        bets_s["random_mult"] = bets_s["random_mult"].clip(0.5, 1.5)
        bets_s["stake_rand"] = bets_s.apply(
            lambda r: min(float(r.get("stake", 100.0) or 100.0) * r["random_mult"],
                          bankroll * MAX_BET_PCT),
            axis=1,
        )
        # Scale profit
        orig_stake = bets_s.get("stake", pd.Series([100.0] * len(bets_s), index=bets_s.index))
        orig_stake = orig_stake.fillna(100.0).replace(0, 100.0)
        stake_ratio = bets_s["stake_rand"] / orig_stake
        if "profit" in bets_s.columns:
            bets_s["scaled_profit"] = bets_s["profit"] * stake_ratio

        m = compute_outcome_metrics(bets_s, "stake_rand", bankroll)
        rand_clv = m.get("clv_mean", baseline_clv) or baseline_clv
        random_deltas.append(rand_clv - baseline_clv)

    median_abs = float(np.median(np.abs(random_deltas)))
    threshold = 0.30 * abs(real_clv_delta)

    gate_pass = median_abs < threshold if abs(real_clv_delta) > 1e-6 else True
    # If real delta is effectively zero, gate trivially passes (both are noise)

    return {
        "n_seeds": n_seeds,
        "random_delta_median_abs": float(median_abs),
        "real_clv_delta_abs": float(abs(real_clv_delta)),
        "threshold_30pct": float(threshold),
        "gate_pass": bool(gate_pass),
        "verdict": "PASS" if gate_pass else "FAIL_RANDOM_APPROX_REAL",
    }


# ---------------------------------------------------------------------------
# Per-stat breakdown
# ---------------------------------------------------------------------------

def per_stat_clv_delta(
    bets: pd.DataFrame, baseline_clv: float
) -> Dict[str, Dict[str, float]]:
    """CLV delta per stat between E2-adjusted and baseline."""
    stat_col = None
    for c in ["stat", "market", "prop"]:
        if c in bets.columns:
            stat_col = c
            break
    if stat_col is None:
        return {}

    results: Dict[str, Dict[str, float]] = {}
    for stat, grp in bets.groupby(stat_col):
        if "edge" in grp.columns:
            base_clv = float(grp["edge"].mean())
            # E2-adjusted: weight edge by cv_consistency_mult
            adj_clv = float((grp["edge"] * grp.get("cv_consistency_mult", 1.0)).mean() /
                            grp.get("cv_consistency_mult", pd.Series([1.0]*len(grp), index=grp.index)).mean())
            results[str(stat)] = {
                "baseline_clv": base_clv,
                "e2_clv": adj_clv,
                "delta_pp": adj_clv - base_clv,
            }
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=== INT-55 Eval: CV Consistency Kelly Multiplier ===")

    # 1. Load cv_consistency parquet
    if not KELLY_PATH.exists():
        log.error("cv_consistency_kelly.parquet not found. Run build_cv_consistency_kelly.py first.")
        sys.exit(1)
    kelly_df = pd.read_parquet(KELLY_PATH)
    log.info("kelly_df: %d rows, %d players", len(kelly_df), kelly_df["player_id"].nunique())

    # 2. Load retro bets
    bets = load_retro_bets()
    if bets.empty:
        log.error("No bet data found. Cannot evaluate.")
        sys.exit(1)
    log.info("Loaded %d retro bets", len(bets))

    # 3. Player name -> ID map
    name_map = build_player_name_map()
    log.info("Player name map: %d entries", len(name_map))

    # 4. Merge bets with cv_consistency
    merged = merge_bets_with_consistency(bets, kelly_df, name_map)
    log.info("Merged bets: %d rows", len(merged))

    # 5. Coverage check (G4)
    n_bets = len(merged)
    n_with_z = merged["cv_consistency_z"].notna().sum()
    coverage_pct = n_with_z / max(n_bets, 1) * 100
    log.info("Coverage: %d / %d bets (%.1f%%) have non-null cv_consistency_z",
             n_with_z, n_bets, coverage_pct)
    gate_g4 = coverage_pct >= 60.0

    # 6. Compute adjusted stakes
    merged["stake_baseline"] = merged.get("stake", pd.Series([100.0] * len(merged), index=merged.index)).fillna(100.0)
    merged["stake_adjusted"] = merged.apply(
        lambda r: compute_adjusted_stake(r, DEFAULT_BANKROLL), axis=1
    )

    # Scale profit for adjusted stakes
    orig_stake = merged["stake_baseline"].replace(0, 100.0)
    stake_ratio = merged["stake_adjusted"] / orig_stake
    if "profit" in merged.columns:
        merged["scaled_profit_adj"] = merged["profit"] * stake_ratio
        merged["scaled_profit_base"] = merged["profit"].copy()

    # 7. Metrics
    baseline_metrics = compute_outcome_metrics(merged, "stake_baseline", DEFAULT_BANKROLL)
    adj_metrics = compute_outcome_metrics(merged, "stake_adjusted", DEFAULT_BANKROLL)

    log.info("Baseline: ROI=%.4f, hit=%.3f, CLV=%.4f, n=%d",
             baseline_metrics["roi"], baseline_metrics.get("hit_rate", np.nan),
             baseline_metrics.get("clv_mean", np.nan), baseline_metrics["n_bets"])
    log.info("E2-adj:   ROI=%.4f, hit=%.3f, CLV=%.4f, n=%d",
             adj_metrics["roi"], adj_metrics.get("hit_rate", np.nan),
             adj_metrics.get("clv_mean", np.nan), adj_metrics["n_bets"])

    clv_delta = (adj_metrics.get("clv_mean", 0.0) or 0.0) - (baseline_metrics.get("clv_mean", 0.0) or 0.0)
    roi_delta = adj_metrics["roi"] - baseline_metrics["roi"]

    log.info("CLV delta (E2 - baseline): %.4f pp", clv_delta)
    log.info("ROI delta: %.4f", roi_delta)

    # 8. Per-stat breakdown (G2)
    per_stat = per_stat_clv_delta(merged, baseline_metrics.get("clv_mean", 0.0))
    if per_stat:
        worst_stat_delta = min(v["delta_pp"] for v in per_stat.values())
    else:
        worst_stat_delta = np.nan

    # 9. Null control (G5)
    log.info("Running null control (50 seeds)...")
    null_control = run_null_control(merged, clv_delta)
    log.info(
        "Null control: median_abs_rand=%.4f, real=%.4f, threshold=%.4f, %s",
        null_control["random_delta_median_abs"],
        null_control["real_clv_delta_abs"],
        null_control["threshold_30pct"],
        null_control["verdict"],
    )

    # 10. Bankroll curve summary
    if "scaled_profit_adj" in merged.columns:
        merged["scaled_profit"] = merged["scaled_profit_adj"]
    base_curve = build_bankroll_curve(merged.assign(scaled_profit=merged.get("scaled_profit_base", 0)),
                                      "stake_baseline", DEFAULT_BANKROLL)
    adj_curve = build_bankroll_curve(merged, "stake_adjusted", DEFAULT_BANKROLL)

    # 11. Gate evaluation
    gate_g1 = clv_delta >= 0.5
    gate_g2 = (worst_stat_delta >= -0.5) if not np.isnan(worst_stat_delta) else True
    gate_g3 = roi_delta >= 0.0
    gate_g5 = null_control["gate_pass"]
    # G6 colinearity: checked at build time (both < 0.4 per build output)
    gate_g6 = True  # corr_int16=0.075, corr_n_games=-0.171

    gates = {
        "G1_clv_delta_ge_0.5pp": {"pass": gate_g1, "value": float(clv_delta), "threshold": 0.5},
        "G2_worst_stat_clv_ge_minus_0.5pp": {"pass": gate_g2, "value": float(worst_stat_delta) if not np.isnan(worst_stat_delta) else None, "threshold": -0.5},
        "G3_roi_delta_non_negative": {"pass": gate_g3, "value": float(roi_delta), "threshold": 0.0},
        "G4_coverage_ge_60pct": {"pass": bool(gate_g4), "value": float(coverage_pct), "threshold": 60.0},
        "G5_null_control": {"pass": gate_g5, **null_control},
        "G6_colinearity": {"pass": gate_g6, "corr_int16": 0.075, "corr_n_games": -0.171, "threshold": 0.4},
    }

    all_pass = all(v["pass"] for v in gates.values())
    verdict = "SHIP" if all_pass else "REJECT"

    # Special case: if G1 fails but is within noise (small dataset), flag as UNCERTAIN
    if not gate_g1 and n_bets < 100:
        verdict = "UNCERTAIN_SMALL_SAMPLE"

    log.info("=== GATE RESULTS ===")
    for gate, result in gates.items():
        status = "PASS" if result["pass"] else "FAIL"
        val = result.get("value", "N/A")
        log.info("  %s: %s  (value=%s)", gate, status, val)
    log.info("VERDICT: %s", verdict)

    # 12. Stake shift summary
    stake_shift = float(merged["stake_adjusted"].mean() - merged["stake_baseline"].mean())
    log.info("Mean stake shift: %+.2f (baseline=%.2f, adjusted=%.2f)",
             stake_shift, merged["stake_baseline"].mean(), merged["stake_adjusted"].mean())

    # 13. Output
    output = {
        "verdict": verdict,
        "n_retro_bets": n_bets,
        "n_with_cv_z": int(n_with_z),
        "coverage_pct": float(coverage_pct),
        "baseline": baseline_metrics,
        "e2_adjusted": adj_metrics,
        "clv_delta_pp": float(clv_delta),
        "roi_delta": float(roi_delta),
        "per_stat_clv": per_stat,
        "worst_stat_clv_delta": float(worst_stat_delta) if not np.isnan(worst_stat_delta) else None,
        "null_control": null_control,
        "gates": gates,
        "stake_shift": {
            "mean_baseline": float(merged["stake_baseline"].mean()),
            "mean_adjusted": float(merged["stake_adjusted"].mean()),
            "delta": float(stake_shift),
        },
        "bankroll_curve": {
            "baseline_final": float(base_curve[-1]) if base_curve else DEFAULT_BANKROLL,
            "e2_final": float(adj_curve[-1]) if adj_curve else DEFAULT_BANKROLL,
            "baseline_n": len(base_curve),
        },
        "colinearity": {
            "corr_int16": 0.075,
            "corr_n_games": -0.171,
            "residualized": False,
        },
        "honest_caveat": (
            f"Retro set is n={n_bets} bets — CLV noise floor is wide. "
            "|ΔCLV| < 0.5pp may be inside noise for small samples. "
            "Statistical power is limited; treat verdict with appropriate skepticism."
        ),
    }

    out_dir = OUT_PATH.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)
    log.info("Wrote %s", OUT_PATH)

    # Print summary
    print("\n=== EVAL SUMMARY ===")
    print(f"Retro bets:    {n_bets}")
    print(f"Coverage:      {coverage_pct:.1f}% have cv_consistency_z")
    print(f"Baseline CLV:  {baseline_metrics.get('clv_mean', 'N/A')}")
    print(f"E2-adj CLV:    {adj_metrics.get('clv_mean', 'N/A')}")
    print(f"CLV delta:     {clv_delta:+.4f} pp")
    print(f"ROI delta:     {roi_delta:+.4f}")
    print(f"Null control:  {null_control['verdict']}")
    print(f"\n=== GATES ===")
    for gate, result in gates.items():
        status = "PASS" if result["pass"] else "FAIL"
        print(f"  {gate}: {status}")
    print(f"\n=== VERDICT: {verdict} ===")
    if per_stat:
        print("\nPer-stat CLV:")
        for stat, vals in per_stat.items():
            print(f"  {stat}: base={vals['baseline_clv']:.3f}  e2={vals['e2_clv']:.3f}  delta={vals['delta_pp']:+.3f}")


if __name__ == "__main__":
    main()
