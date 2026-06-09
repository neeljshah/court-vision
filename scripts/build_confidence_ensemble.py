"""build_confidence_ensemble.py — INT-77: Multi-Source Confidence-Weighted Kelly Ensemble.

Combines 5 individual confidence signals into a single Kelly multiplier via two formulas:
  Formula A: multiplicative product of all surviving signal multipliers
  Formula B: z-mean -> single multiplier via 1 + 0.3 * clip(z_bar, -1, 1)

Orthogonality pre-flight drops any signal pair with |Pearson r| > 0.7 (smaller coverage dropped).
If fewer than 3 signals survive: write stub with mult=1.0.

Output schema:
  player_id, asof_date, stat,
  mult_int16, mult_int55, mult_int69, mult_int54, mult_int67,
  n_signals, mult_A, mult_B,
  coverage_class ('full'|'partial'|'thin')
"""
from __future__ import annotations

import logging
import sys
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
INT16_PATH = ROOT / "data" / "intelligence" / "per_player_confidence.parquet"
INT55_PATH = ROOT / "data" / "intelligence" / "cv_consistency_kelly.parquet"
INT69_PATH = ROOT / "data" / "intelligence" / "per_player_calibration.parquet"
INT54_PATH = ROOT / "data" / "intelligence" / "archetype_outlier_signals.parquet"
INT67_PATH = ROOT / "data" / "intelligence" / "player_development_v2.parquet"
OUT_PATH = ROOT / "data" / "intelligence" / "confidence_ensemble.parquet"

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
MULT_CLIP_LO = 0.3
MULT_CLIP_HI = 2.0
ORTHO_R_THRESH = 0.7  # drop signal if |r| > this with another signal


# ---------------------------------------------------------------------------
# Step 1: Load and normalise each signal to (player_id, asof_date, stat, mult_raw, z_raw)
# ---------------------------------------------------------------------------

def _mult_from_z(z: pd.Series) -> pd.Series:
    """Convert raw z-score to multiplier: 1 + 0.3 * clip(z, -1, 1)."""
    return 1.0 + 0.3 * z.clip(-1.0, 1.0)


def load_int16() -> pd.DataFrame:
    """INT-16: per_player_confidence.parquet.
    Wide format with {stat}_confidence_mult columns; no asof_date.
    Broadcast to all stats; asof_date = None (player-level constant).
    """
    df = pd.read_parquet(INT16_PATH)
    rows = []
    for stat in STATS:
        col = f"{stat}_confidence_mult"
        if col not in df.columns:
            log.warning("INT-16 missing column %s; filling 1.0", col)
        sub = df[["player_id"]].copy()
        sub["stat"] = stat
        sub["mult_int16"] = df[col].fillna(1.0) if col in df.columns else 1.0
        # Derive z from mult: mult = 1 + 0.3*cv_norm => reverse not available,
        # so use overall_confidence_mult as proxy z denominator
        # z = (mult - 1) / 0.3  capped to [-1, 1]
        sub["z_int16"] = ((sub["mult_int16"] - 1.0) / 0.3).clip(-1.0, 1.0)
        rows.append(sub)
    result = pd.concat(rows, ignore_index=True)
    result["asof_date"] = None  # will be broadcast by date from other signals
    log.info("INT-16: %d rows (wide->long, %d players)", len(result), result.player_id.nunique())
    return result


def load_int55() -> pd.DataFrame:
    """INT-55: cv_consistency_kelly.parquet.
    Has player_id, asof_date, cv_consistency_mult, cv_consistency_z.
    No stat column — broadcast to all stats.
    """
    df = pd.read_parquet(INT55_PATH)
    # Convert asof_date to string
    df["asof_date"] = df["asof_date"].astype(str)
    rows = []
    for stat in STATS:
        sub = df[["player_id", "asof_date"]].copy()
        sub["stat"] = stat
        sub["mult_int55"] = df["cv_consistency_mult"].fillna(1.0)
        # cv_consistency_z: raw z, may be NaN -> fill 0 -> z=0 -> mult=1
        z = df["cv_consistency_z"].fillna(0.0)
        sub["z_int55"] = z.clip(-1.0, 1.0)
        rows.append(sub)
    result = pd.concat(rows, ignore_index=True)
    log.info("INT-55: %d rows (%d player-date combos)", len(result), len(df))
    return result


def load_int69() -> pd.DataFrame:
    """INT-69: per_player_calibration.parquet.
    Has player_id, asof_date, stat, bias_z_l20. Needs mult from z.
    """
    df = pd.read_parquet(INT69_PATH)
    df["asof_date"] = df["asof_date"].astype(str)
    df["stat"] = df["stat"].str.lower().str.strip()
    df = df[df["stat"].isin(STATS)].copy()
    df["z_int69"] = df["bias_z_l20"].fillna(0.0).clip(-1.0, 1.0)
    df["mult_int69"] = _mult_from_z(df["z_int69"])
    result = df[["player_id", "asof_date", "stat", "mult_int69", "z_int69"]].copy()
    log.info("INT-69: %d rows (%d players, %d dates)", len(result),
             result.player_id.nunique(), result.asof_date.nunique())
    return result


def load_int54() -> pd.DataFrame:
    """INT-54: archetype_outlier_signals.parquet.
    Has player_id, game_date (rename to asof_date), outlier_z.
    No stat column — broadcast to all stats.
    Recipe says regime_flag; actual column is outlier_z + flag_strong_outlier.
    Use outlier_z as z-score signal (NaN -> 0).
    """
    df = pd.read_parquet(INT54_PATH)
    df = df.rename(columns={"game_date": "asof_date"})
    df["asof_date"] = df["asof_date"].astype(str)
    rows = []
    for stat in STATS:
        sub = df[["player_id", "asof_date"]].copy()
        sub["stat"] = stat
        z = df["outlier_z"].fillna(0.0)
        sub["z_int54"] = z.clip(-1.0, 1.0)
        sub["mult_int54"] = _mult_from_z(sub["z_int54"])
        rows.append(sub)
    result = pd.concat(rows, ignore_index=True)
    log.info("INT-54: %d rows (%d player-date combos)", len(result), len(df))
    return result


def load_int67() -> pd.DataFrame:
    """INT-67: player_development_v2.parquet.
    Has player_id, game_date (rename to asof_date), dev_score.
    No stat column — broadcast to all stats.
    dev_score is a raw composite score (not z). Normalise via /std; fill 0 for NaN.
    """
    df = pd.read_parquet(INT67_PATH)
    df = df.rename(columns={"game_date": "asof_date"})
    df["asof_date"] = df["asof_date"].dt.strftime("%Y-%m-%d") if hasattr(
        df["asof_date"].dtype, "tz") or str(df["asof_date"].dtype) == "datetime64[ns]" else df["asof_date"].astype(str)
    score = df["dev_score"].fillna(0.0)
    std = score.std()
    if std > 0:
        z_raw = (score - score.mean()) / std
    else:
        z_raw = pd.Series(0.0, index=df.index)
    rows = []
    for stat in STATS:
        sub = df[["player_id", "asof_date"]].copy()
        sub["stat"] = stat
        sub["z_int67"] = z_raw.clip(-1.0, 1.0)
        sub["mult_int67"] = _mult_from_z(sub["z_int67"])
        rows.append(sub)
    result = pd.concat(rows, ignore_index=True)
    log.info("INT-67: %d rows (%d player-date combos)", len(result), len(df))
    return result


# ---------------------------------------------------------------------------
# Step 2: Orthogonality pre-flight
# ---------------------------------------------------------------------------

SIGNAL_NAMES = ["int16", "int55", "int69", "int54", "int67"]
SIGNAL_Z_COLS = ["z_int16", "z_int55", "z_int69", "z_int54", "z_int67"]
SIGNAL_MULT_COLS = ["mult_int16", "mult_int55", "mult_int69", "mult_int54", "mult_int67"]


def _row_counts(merged: pd.DataFrame) -> Dict[str, int]:
    """Count non-NaN rows per signal z column."""
    counts = {}
    for sig, zcol in zip(SIGNAL_NAMES, SIGNAL_Z_COLS):
        if zcol in merged.columns:
            counts[sig] = int(merged[zcol].notna().sum())
        else:
            counts[sig] = 0
    return counts


def orthogonality_preflight(
    merged: pd.DataFrame,
) -> Tuple[List[str], List[str], np.ndarray, List[str]]:
    """Compute 5x5 Pearson r matrix; drop signals failing the 0.7 threshold.

    Because signals differ in time-resolution (INT-16 = player-constant, others sparse),
    orthogonality is checked on the player_id x stat aggregated mean-z, giving a
    stable representation of each signal's cross-sectional rank ordering.

    Returns: (surviving_signal_names, dropped_signals, r_matrix, log_lines)
    """
    log_lines: List[str] = []
    counts = _row_counts(merged)

    # Build z-matrix for valid signals
    valid_sigs = [s for s in SIGNAL_NAMES if counts.get(s, 0) > 0]
    z_cols = [f"z_{s}" for s in valid_sigs]

    # Aggregate to player_id x stat level (mean z per player-stat) for cross-signal comparison.
    # This avoids the sparse asof_date intersection reducing rows to 0.
    agg = merged.groupby(["player_id", "stat"])[z_cols].mean().reset_index()
    subset = agg[z_cols].dropna()
    n = len(subset)
    log_lines.append(f"Orthogonality common rows (player x stat agg): {n}")
    if n < 10:
        log_lines.append("Too few common rows for orthogonality check; keeping all signals")
        return valid_sigs, [], np.eye(len(valid_sigs)), log_lines

    r_matrix = subset.corr(method="pearson").values
    sig_array = np.array(valid_sigs)

    # Report max |r| per pair
    pairs = []
    for i in range(len(valid_sigs)):
        for j in range(i + 1, len(valid_sigs)):
            r = abs(r_matrix[i, j])
            pairs.append((r, valid_sigs[i], valid_sigs[j]))
            log_lines.append(f"|r|({valid_sigs[i]}, {valid_sigs[j]}) = {r:.3f}")

    # Drop rule: if any pair |r| > threshold, drop the one with fewer rows
    dropped: List[str] = []
    surviving = list(valid_sigs)
    for r, sig_a, sig_b in sorted(pairs, reverse=True):
        if r > ORTHO_R_THRESH:
            if sig_a not in surviving or sig_b not in surviving:
                continue
            # Drop the smaller
            if counts[sig_a] <= counts[sig_b]:
                dropped.append(sig_a)
                surviving.remove(sig_a)
                log_lines.append(f"DROP {sig_a} (|r|={r:.3f} with {sig_b}; {counts[sig_a]} < {counts[sig_b]} rows)")
            else:
                dropped.append(sig_b)
                surviving.remove(sig_b)
                log_lines.append(f"DROP {sig_b} (|r|={r:.3f} with {sig_a}; {counts[sig_b]} < {counts[sig_a]} rows)")

    log_lines.append(f"Surviving signals ({len(surviving)}): {surviving}")
    return surviving, dropped, r_matrix, log_lines


# ---------------------------------------------------------------------------
# Step 3: Build ensemble
# ---------------------------------------------------------------------------

def build_ensemble(
    merged: pd.DataFrame,
    surviving: List[str],
) -> pd.DataFrame:
    """Add mult_A, mult_B, n_signals, coverage_class columns."""
    m_cols = [f"mult_{s}" for s in surviving]
    z_cols = [f"z_{s}" for s in surviving]

    # n_signals = how many surviving signals have non-NaN multipliers pre-fill
    # INT-16 always present (player-level); others depend on date coverage
    # Use the original z-cols to determine actual coverage (NaN = not present)
    n_sig = merged[z_cols].notna().sum(axis=1)
    merged["n_signals"] = n_sig

    # Where n_signals < 3: fallback to 1.0
    thin_mask = n_sig < 3

    # Formula A: multiplicative product of surviving mults (fill NaN with 1.0 = neutral)
    m_filled = merged[m_cols].fillna(1.0)
    mult_A = m_filled.prod(axis=1)
    mult_A = mult_A.clip(MULT_CLIP_LO, MULT_CLIP_HI)
    mult_A[thin_mask] = 1.0

    # Formula B: z-mean -> single mult
    z_filled = merged[z_cols].fillna(0.0)
    z_bar = z_filled.mean(axis=1)
    mult_B = 1.0 + 0.3 * z_bar.clip(-1.0, 1.0)
    mult_B[thin_mask] = 1.0

    merged["mult_A"] = mult_A
    merged["mult_B"] = mult_B

    # Coverage class
    def _cov_class(n: int) -> str:
        if n >= 5:
            return "full"
        elif n >= 3:
            return "partial"
        else:
            return "thin"

    merged["coverage_class"] = n_sig.map(_cov_class)
    return merged


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=== INT-77 Confidence Ensemble Build ===")

    # Load signals
    int16 = load_int16()
    int55 = load_int55()
    int69 = load_int69()
    int54 = load_int54()
    int67 = load_int67()

    # INT-16 has no asof_date; merge strategy:
    # Base = INT-69 (has player_id, asof_date, stat — largest coverage)
    # Left-join INT-55 on (player_id, asof_date, stat) — broadcast by stat already
    # Left-join INT-54 on (player_id, asof_date, stat)
    # Left-join INT-67 on (player_id, asof_date, stat)
    # Left-join INT-16 on (player_id, stat) — no asof_date dimension

    base = int69.rename(columns={"mult_int69": "mult_int69", "z_int69": "z_int69"})

    # Merge INT-55
    m55 = int55.rename(columns={"mult_int55": "mult_int55", "z_int55": "z_int55"})
    merged = base.merge(m55, on=["player_id", "asof_date", "stat"], how="left")

    # Merge INT-54
    m54 = int54.rename(columns={"mult_int54": "mult_int54", "z_int54": "z_int54"})
    merged = merged.merge(m54, on=["player_id", "asof_date", "stat"], how="left")

    # Merge INT-67
    m67 = int67.rename(columns={"mult_int67": "mult_int67", "z_int67": "z_int67"})
    merged = merged.merge(m67, on=["player_id", "asof_date", "stat"], how="left")

    # Merge INT-16 (no asof_date — just player_id x stat)
    m16 = int16[["player_id", "stat", "mult_int16", "z_int16"]].copy()
    merged = merged.merge(m16, on=["player_id", "stat"], how="left")

    log.info("After all merges: %d rows, %d player-date-stat combos",
             len(merged), len(merged[["player_id", "asof_date", "stat"]].drop_duplicates()))

    # Orthogonality pre-flight
    surviving, dropped, r_matrix, ortho_log = orthogonality_preflight(merged)
    for line in ortho_log:
        log.info("ORTHO: %s", line)

    if len(surviving) < 3:
        log.warning("Fewer than 3 signals survive orthogonality check (%d). Writing stub.", len(surviving))
        # Write stub
        stub = merged[["player_id", "asof_date", "stat"]].copy()
        for col in ["mult_int16", "mult_int55", "mult_int69", "mult_int54", "mult_int67"]:
            stub[col] = np.nan
        stub["n_signals"] = 0
        stub["mult_A"] = 1.0
        stub["mult_B"] = 1.0
        stub["coverage_class"] = "thin"
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        stub.to_parquet(OUT_PATH, index=False)
        log.info("STUB written: %s (%d rows)", OUT_PATH, len(stub))
        return

    # Build ensemble
    merged = build_ensemble(merged, surviving)

    # Final output columns
    out_cols = [
        "player_id", "asof_date", "stat",
        "mult_int16", "mult_int55", "mult_int69", "mult_int54", "mult_int67",
        "n_signals", "mult_A", "mult_B", "coverage_class",
    ]
    # Ensure all expected cols exist (fill NaN if a signal was dropped)
    for col in out_cols:
        if col not in merged.columns:
            merged[col] = np.nan

    result = merged[out_cols].copy()

    # Summary stats
    log.info("Output: %d rows", len(result))
    log.info("Coverage breakdown: %s", result.coverage_class.value_counts().to_dict())
    log.info("mult_A range: [%.4f, %.4f] mean=%.4f",
             result.mult_A.min(), result.mult_A.max(), result.mult_A.mean())
    log.info("mult_B range: [%.4f, %.4f] mean=%.4f",
             result.mult_B.min(), result.mult_B.max(), result.mult_B.mean())

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(OUT_PATH, index=False)
    log.info("Written: %s", OUT_PATH)


if __name__ == "__main__":
    main()
