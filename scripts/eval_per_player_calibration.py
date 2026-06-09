"""eval_per_player_calibration.py — INT-69 Validation for Per-Player Calibration Shift.

Validation suite:
  1. MAE retro: mae_raw vs mae_corrected (per stat + aggregate)
  2. CLV retro: real CLV vs null-control CLV (50 seeds permutation test)
     real_z = (real_clv - null_mean) / null_std
     SHIP GATE: real_z > 2.0 AND real_clv - null_mean >= +0.5pp
  3. Orthogonality vs INT-16: |Pearson(bias_z_l20, stat_cv)| < 0.5 per stat
  4. Side-flip safety rail: fraction of bets flipping side after correction
     If >15% flip -> recommend reducing multiplier from 0.5 to 0.25

Retro ledger used:
  data/external/historical_lines/extended_oos_canonical.csv   (10,927 rows — main)
  data/external/historical_lines/benashkar_2026_canonical.csv (5,418 rows)
  data/external/historical_lines/playoffs_2024_canonical.csv  (5,108 rows)

These ledgers use CLOSING line as the sportsbook line. No open line available.
We treat closing_line as the line for retro evaluation.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_CALIB = ROOT / "data" / "intelligence" / "per_player_calibration.parquet"
_INT16 = ROOT / "data" / "intelligence" / "per_player_confidence.parquet"
_OOF = ROOT / "data" / "cache" / "pregame_oof.parquet"

_LEDGER_FILES = [
    ROOT / "data" / "external" / "historical_lines" / "extended_oos_canonical.csv",
    ROOT / "data" / "external" / "historical_lines" / "benashkar_2026_canonical.csv",
    ROOT / "data" / "external" / "historical_lines" / "playoffs_2024_canonical.csv",
]

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
NULL_SEEDS = 50
MIN_COVERAGE_PCT = 0.30  # 30% of retro bets must be covered
SHIP_CLV_DELTA = 0.5  # pp
SHIP_Z_MIN = 2.0
SIDE_FLIP_WARN = 0.15  # 15% flip -> recommend reducing multiplier

# ---------------------------------------------------------------------------
# Player name -> player_id from OOF
# ---------------------------------------------------------------------------
def _build_name_to_pid(oof: pd.DataFrame) -> Dict[str, int]:
    """Build lowercase-name -> player_id from OOF + player_avgs."""
    mapping: Dict[str, int] = {}
    # From player_avgs JSON files (lowercase name)
    nba_dir = ROOT / "data" / "nba"
    for season in ("2023-24", "2024-25", "2025-26"):
        path = nba_dir / f"player_avgs_{season}.json"
        if not path.exists():
            continue
        try:
            for name_lc, info in json.load(open(path, encoding="utf-8")).items():
                pid = info.get("player_id")
                if pid is not None:
                    mapping[name_lc.strip().lower()] = int(pid)
        except Exception:
            continue
    log.info("Name->PID map: %d entries", len(mapping))
    return mapping


# ---------------------------------------------------------------------------
# Load and merge ledgers
# ---------------------------------------------------------------------------
def _load_ledgers() -> pd.DataFrame:
    dfs = []
    for p in _LEDGER_FILES:
        if not p.exists():
            log.warning("Ledger not found: %s", p)
            continue
        df = pd.read_csv(p)
        df["_source"] = p.name
        dfs.append(df)
    if not dfs:
        log.error("No ledger files found.")
        sys.exit(1)
    combined = pd.concat(dfs, ignore_index=True)
    # Normalize
    combined["date"] = pd.to_datetime(combined["date"]).dt.date.astype(str)
    combined["stat"] = combined["stat"].str.lower().str.strip()
    combined["player"] = combined["player"].str.strip()
    combined = combined[combined["stat"].isin(STATS)].copy()
    log.info("Ledger rows after stat filter: %d (from %d files)", len(combined), len(dfs))
    return combined


# ---------------------------------------------------------------------------
# Join ledger to OOF predictions and calibration shifts
# ---------------------------------------------------------------------------
def _build_retro_table(
    ledger: pd.DataFrame,
    oof: pd.DataFrame,
    calib: pd.DataFrame,
    name_to_pid: Dict[str, int],
) -> pd.DataFrame:
    """Join ledger bets to OOF pred and calibration shift.

    Returns a DataFrame with one row per (bet), containing:
      player_id, stat, date, closing_line, actual_value,
      oof_pred (model raw), bias_shift_applied, pred_corrected,
      edge_raw, edge_corrected, side_raw, side_corrected
    """
    # Add player_id to ledger via name lookup
    ledger = ledger.copy()
    ledger["player_id"] = ledger["player"].str.lower().map(name_to_pid)
    unmatched = ledger["player_id"].isna().sum()
    log.info("Ledger name->pid: %d/%d matched", len(ledger) - unmatched, len(ledger))
    ledger = ledger.dropna(subset=["player_id"]).copy()
    ledger["player_id"] = ledger["player_id"].astype(int)

    # Get the latest OOF pred per (player_id, stat, date)
    # Use the LAST fold OOF pred available for each game
    oof_agg = (
        oof.sort_values("fold")
        .groupby(["player_id", "stat", "game_date"])
        .last()
        .reset_index()[["player_id", "stat", "game_date", "oof_pred", "actual"]]
    )
    oof_agg = oof_agg.rename(columns={"game_date": "date", "actual": "oof_actual"})

    # Merge ledger + OOF
    merged = ledger.merge(oof_agg, on=["player_id", "stat", "date"], how="inner")
    log.info("After ledger x OOF join: %d rows", len(merged))

    # Get calibration shift for (player_id, stat, asof_date == date)
    # Use the shift that would have been available on that date
    # calib has time-series — pick the row with asof_date == bet date
    calib_lookup = calib[["player_id", "stat", "asof_date", "bias_shift_applied", "bias_z_l20"]].copy()
    calib_lookup = calib_lookup.rename(columns={"asof_date": "date"})

    merged = merged.merge(calib_lookup, on=["player_id", "stat", "date"], how="left")
    covered = merged["bias_shift_applied"].notna().sum()
    log.info(
        "Calibration coverage: %d/%d bets (%.1f%%)",
        covered, len(merged), 100 * covered / max(1, len(merged)),
    )

    # Fill uncovered bets with shift=0 (no correction)
    merged["bias_shift_applied"] = merged["bias_shift_applied"].fillna(0.0)
    merged["bias_z_l20"] = merged["bias_z_l20"].fillna(0.0)
    merged["covered"] = merged["bias_shift_applied"] != 0.0

    # Prediction columns
    merged["pred_raw"] = merged["oof_pred"]
    merged["pred_corrected"] = merged["pred_raw"] + merged["bias_shift_applied"]

    # Edge vs closing line
    merged["edge_raw"] = merged["pred_raw"] - merged["closing_line"]
    merged["edge_corrected"] = merged["pred_corrected"] - merged["closing_line"]

    # Side: +1 = OVER, -1 = UNDER
    merged["side_raw"] = np.sign(merged["edge_raw"])
    merged["side_corrected"] = np.sign(merged["edge_corrected"])

    # Actual outcome vs line
    merged["actual"] = merged["actual_value"]

    return merged


# ---------------------------------------------------------------------------
# CLV calculation
# ---------------------------------------------------------------------------
def _compute_clv(df: pd.DataFrame, use_corrected: bool = True) -> float:
    """Aggregate CLV in pp.

    CLV here = stake-weighted fraction of bets where side aligned with
    (close - open) direction. Since we only have closing_line (no open),
    we use a proxy: CLV ~ mean(correct_side * |edge| / closing_line).

    More precisely: for each bet, after-correction side = sign(pred - close).
    CLV_bet = side * (actual - close) / close  [normalized outcome vs close].
    This measures whether the corrected prediction better anticipates
    where the actual landed relative to closing line.
    """
    side_col = "side_corrected" if use_corrected else "side_raw"
    side = df[side_col].values
    actual = df["actual"].values
    line = df["closing_line"].values

    # Normalized outcome vs closing line: positive when actual > line (over hit)
    outcome_vs_close = actual - line  # raw units above/below close
    # Scale by 1/abs(line) to normalize; guard /0
    scale = np.abs(line)
    scale = np.where(scale < 0.5, 0.5, scale)

    clv_per_bet = side * (outcome_vs_close / scale)  # +: bet with the market
    return float(np.mean(clv_per_bet) * 100)  # in pp


# ---------------------------------------------------------------------------
# MAE evaluation
# ---------------------------------------------------------------------------
def _mae_retro(df: pd.DataFrame) -> Tuple[Dict[str, float], Dict[str, float]]:
    mae_raw: Dict[str, float] = {}
    mae_corr: Dict[str, float] = {}
    for stat, grp in df.groupby("stat"):
        mae_raw[stat] = float(np.mean(np.abs(grp["actual"] - grp["pred_raw"])))
        mae_corr[stat] = float(np.mean(np.abs(grp["actual"] - grp["pred_corrected"])))
    return mae_raw, mae_corr


# ---------------------------------------------------------------------------
# Null control: shuffle bias_shift_applied assignments
# ---------------------------------------------------------------------------
def _null_clv(df: pd.DataFrame, n_seeds: int = NULL_SEEDS) -> np.ndarray:
    """50-seed permutation: shuffle (player_id, stat) -> bias_shift_applied mapping."""
    rng = np.random.default_rng(42)
    null_clvs = np.zeros(n_seeds)

    # Build array of shift values per covered row
    covered = df["covered"].values
    shifts = df["bias_shift_applied"].values.copy()

    for seed in range(n_seeds):
        rng_s = np.random.default_rng(seed)
        shuffled_shifts = shifts.copy()
        # Shuffle only the non-zero shift values across covered rows
        covered_idx = np.where(covered)[0]
        perm = rng_s.permutation(len(covered_idx))
        shuffled_shifts[covered_idx] = shifts[covered_idx][perm]

        df_null = df.copy()
        df_null["bias_shift_applied"] = shuffled_shifts
        df_null["pred_corrected"] = df_null["pred_raw"] + shuffled_shifts
        df_null["edge_corrected"] = df_null["pred_corrected"] - df_null["closing_line"]
        df_null["side_corrected"] = np.sign(df_null["edge_corrected"])

        null_clvs[seed] = _compute_clv(df_null, use_corrected=True)

    return null_clvs


# ---------------------------------------------------------------------------
# Orthogonality vs INT-16
# ---------------------------------------------------------------------------
def _orthogonality(calib: pd.DataFrame, int16: pd.DataFrame) -> Dict[str, float]:
    """Pearson(bias_z_l20, stat_cv) per stat."""
    # INT-16 is wide format: player_id, pts_cv, reb_cv, ...
    # Calibration is long format: player_id, stat, bias_z_l20
    # Take the LATEST calibration per (player_id, stat)
    latest_calib = (
        calib.sort_values("asof_date")
        .groupby(["player_id", "stat"])
        .last()
        .reset_index()[["player_id", "stat", "bias_z_l20"]]
    )

    results: Dict[str, float] = {}
    for stat in STATS:
        cv_col = f"{stat}_cv"
        if cv_col not in int16.columns:
            continue
        merged = latest_calib[latest_calib["stat"] == stat].merge(
            int16[["player_id", cv_col]], on="player_id", how="inner"
        )
        if len(merged) < 10:
            results[stat] = float("nan")
            continue
        corr = merged["bias_z_l20"].corr(merged[cv_col])
        results[stat] = round(float(corr), 4)
    return results


# ---------------------------------------------------------------------------
# Side-flip rate
# ---------------------------------------------------------------------------
def _side_flip_rate(df: pd.DataFrame) -> float:
    flipped = (df["side_raw"] != df["side_corrected"]) & (df["covered"])
    total_covered = df["covered"].sum()
    if total_covered == 0:
        return 0.0
    return float(flipped.sum() / total_covered)


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------
def evaluate() -> dict:
    # Load artifacts
    if not _CALIB.exists():
        log.error("Calibration parquet not found — run build_per_player_calibration.py first")
        sys.exit(1)

    calib = pd.read_parquet(_CALIB)
    oof = pd.read_parquet(_OOF)
    int16 = pd.read_parquet(_INT16) if _INT16.exists() else pd.DataFrame()

    log.info("Calibration: %d rows, %d players", len(calib), calib["player_id"].nunique())

    # Load ledger
    ledger = _load_ledgers()
    if len(ledger) < 100:
        log.error("INSUFFICIENT_RETRO_POOL: only %d ledger rows", len(ledger))
        sys.exit(1)

    # Name -> PID
    name_to_pid = _build_name_to_pid(oof)

    # Build retro table
    retro = _build_retro_table(ledger, oof, calib, name_to_pid)

    if len(retro) < 50:
        log.warning("Very few retro rows matched (%d) — results unreliable", len(retro))

    # Coverage check
    n_total_ledger_bets = len(ledger[ledger["stat"].isin(STATS)])
    coverage_pct = len(retro) / max(1, n_total_ledger_bets)
    log.info("Retro coverage: %d/%d = %.1f%%", len(retro), n_total_ledger_bets, 100 * coverage_pct)

    # -----------------------------------------------------------------------
    # 1. MAE
    # -----------------------------------------------------------------------
    mae_raw, mae_corr = _mae_retro(retro)
    log.info("MAE raw vs corrected:")
    for stat in STATS:
        r = mae_raw.get(stat, float("nan"))
        c = mae_corr.get(stat, float("nan"))
        delta = c - r
        sign = "+" if delta >= 0 else ""
        log.info("  %-4s  raw=%.4f  corr=%.4f  delta=%s%.4f", stat, r, c, sign, delta)

    # -----------------------------------------------------------------------
    # 2. CLV retro
    # -----------------------------------------------------------------------
    real_clv = _compute_clv(retro, use_corrected=True)
    raw_clv = _compute_clv(retro, use_corrected=False)
    log.info("CLV (real, corrected): %.4f pp", real_clv)
    log.info("CLV (raw, uncorrected): %.4f pp", raw_clv)

    log.info("Running null control (%d seeds)...", NULL_SEEDS)
    null_clvs = _null_clv(retro)
    null_mean = float(np.mean(null_clvs))
    null_std = float(np.std(null_clvs, ddof=1))
    real_z = (real_clv - null_mean) / (null_std + 1e-9)
    clv_delta = real_clv - null_mean

    log.info("Null CLV: mean=%.4f  std=%.4f", null_mean, null_std)
    log.info("real_z=%.3f  delta_pp=%.4f", real_z, clv_delta)

    # Per-stat CLV
    per_stat_clv: Dict[str, float] = {}
    for stat, grp in retro.groupby("stat"):
        per_stat_clv[stat] = _compute_clv(grp, use_corrected=True)
    log.info("Per-stat CLV (corrected): %s", {k: round(v, 4) for k, v in per_stat_clv.items()})

    # -----------------------------------------------------------------------
    # 3. Orthogonality vs INT-16
    # -----------------------------------------------------------------------
    if not int16.empty:
        ortho = _orthogonality(calib, int16)
        log.info("Orthogonality |r| vs INT-16 cv:")
        for stat, r in ortho.items():
            ok = abs(r) < 0.5 if not np.isnan(r) else True
            log.info("  %-4s  r=%.4f  %s", stat, r, "OK" if ok else "FAIL")
    else:
        ortho = {}
        log.warning("INT-16 not found — skipping orthogonality check")

    # -----------------------------------------------------------------------
    # 4. Side-flip rate
    # -----------------------------------------------------------------------
    flip_rate = _side_flip_rate(retro)
    log.info("Side-flip rate: %.1f%%  (%s)", 100 * flip_rate,
             "WARN: recommend multiplier 0.25" if flip_rate > SIDE_FLIP_WARN else "OK")

    # -----------------------------------------------------------------------
    # 5. Ship gate
    # -----------------------------------------------------------------------
    gate_clv = clv_delta >= SHIP_CLV_DELTA
    gate_z = real_z >= SHIP_Z_MIN
    gate_coverage = coverage_pct >= MIN_COVERAGE_PCT
    gate_per_stat = all(v >= -0.5 for v in per_stat_clv.values())
    gate_ortho = all(abs(v) < 0.5 for v in ortho.values() if not np.isnan(v))

    ship = gate_clv and gate_z and gate_coverage

    log.info("\n=== SHIP GATE ===")
    log.info("CLV delta >= +0.5pp:   %s  (%.4f pp)", "PASS" if gate_clv else "FAIL", clv_delta)
    log.info("null-z >= 2.0:         %s  (z=%.3f)", "PASS" if gate_z else "FAIL", real_z)
    log.info("coverage >= 30%%:      %s  (%.1f%%)", "PASS" if gate_coverage else "FAIL", 100 * coverage_pct)
    log.info("per-stat CLV >= -0.5pp:%s", "PASS" if gate_per_stat else "FAIL")
    log.info("ortho |r| < 0.5:       %s", "PASS" if gate_ortho else "FAIL (or not checked)")
    log.info("OVERALL VERDICT:       %s", "SHIP" if ship else "REJECT")

    results = {
        "build_ts": datetime.now(timezone.utc).isoformat(),
        "n_retro_bets": len(retro),
        "coverage_pct": round(coverage_pct, 4),
        "residual_source": calib["residual_source"].iloc[0],
        "n_calib_rows": len(calib),
        "n_calib_players": calib["player_id"].nunique(),
        "mae_raw": {k: round(v, 4) for k, v in mae_raw.items()},
        "mae_corr": {k: round(v, 4) for k, v in mae_corr.items()},
        "mae_delta": {k: round(mae_corr.get(k, 0) - mae_raw.get(k, 0), 4) for k in STATS},
        "clv_raw_pp": round(raw_clv, 4),
        "clv_real_pp": round(real_clv, 4),
        "null_clv_mean": round(null_mean, 4),
        "null_clv_std": round(null_std, 4),
        "real_z": round(real_z, 4),
        "clv_delta_pp": round(clv_delta, 4),
        "per_stat_clv": {k: round(v, 4) for k, v in per_stat_clv.items()},
        "ortho_vs_int16": ortho,
        "side_flip_rate": round(flip_rate, 4),
        "gate_clv": gate_clv,
        "gate_z": gate_z,
        "gate_coverage": gate_coverage,
        "gate_per_stat": gate_per_stat,
        "gate_ortho": gate_ortho,
        "ship": ship,
        "verdict": "SHIP" if ship else "REJECT",
    }

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    results = evaluate()

    print("\n" + "=" * 60)
    print("INT-69 EVAL RESULTS")
    print("=" * 60)
    print(f"Retro bets matched   : {results['n_retro_bets']:,}")
    print(f"Coverage             : {100*results['coverage_pct']:.1f}%")
    print(f"Residual source      : {results['residual_source']}")
    print()
    print("MAE raw -> corrected (delta):")
    for stat in STATS:
        r = results["mae_raw"].get(stat, float("nan"))
        c = results["mae_corr"].get(stat, float("nan"))
        d = results["mae_delta"].get(stat, float("nan"))
        sign = "+" if d >= 0 else ""
        print(f"  {stat:<4}  {r:.4f} -> {c:.4f}  ({sign}{d:.4f})")
    print()
    print(f"CLV raw (uncorrected): {results['clv_raw_pp']:+.4f} pp")
    print(f"CLV real (corrected) : {results['clv_real_pp']:+.4f} pp")
    print(f"Null CLV mean        : {results['null_clv_mean']:+.4f} pp")
    print(f"Null CLV std         : {results['null_clv_std']:.4f} pp")
    print(f"real_z               : {results['real_z']:.3f}")
    print(f"CLV delta            : {results['clv_delta_pp']:+.4f} pp")
    print()
    print("Per-stat CLV (corrected):")
    for stat, v in results["per_stat_clv"].items():
        print(f"  {stat:<4}  {v:+.4f} pp")
    print()
    if results["ortho_vs_int16"]:
        print("Orthogonality vs INT-16 |r|:")
        for stat, r in results["ortho_vs_int16"].items():
            ok = abs(r) < 0.5 if not (r != r) else True  # nan check
            print(f"  {stat:<4}  r={r:.4f}  {'OK' if ok else 'FAIL'}")
        print()
    print(f"Side-flip rate       : {100*results['side_flip_rate']:.1f}%")
    print()
    print("SHIP GATE:")
    print(f"  CLV delta >= +0.5pp: {'PASS' if results['gate_clv'] else 'FAIL'}  ({results['clv_delta_pp']:+.4f}pp)")
    print(f"  null-z >= 2.0:       {'PASS' if results['gate_z'] else 'FAIL'}  (z={results['real_z']:.3f})")
    print(f"  coverage >= 30%:     {'PASS' if results['gate_coverage'] else 'FAIL'}  ({100*results['coverage_pct']:.1f}%)")
    print(f"  per-stat CLV ok:     {'PASS' if results['gate_per_stat'] else 'FAIL'}")
    print(f"  ortho ok:            {'PASS' if results['gate_ortho'] else 'FAIL'}")
    print()
    print(f"VERDICT: {results['verdict']}")

    # Save results
    out_path = ROOT / "data" / "cache" / "int69_eval_results.json"
    import json as _json
    with open(out_path, "w") as f:
        _json.dump(results, f, indent=2)
    print(f"\nResults saved: {out_path}")
