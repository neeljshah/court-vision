"""
INT-84: Build Cross-Stat Residual Correlation Matrix (Gaussian Copula foundation).

Loads pregame_oof.parquet (long format: player_id, game_date, stat, oof_pred, actual),
pivots to wide, computes per-player 7x7 Pearson residual correlations, Fisher-z pools
to league + per-archetype scopes, PSD-projects, and saves long-format parquet.

Usage:
    python scripts/build_stat_correlations.py
    python scripts/build_stat_correlations.py --validate
"""

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr

ROOT = Path(__file__).resolve().parent.parent

OOF_PATH = ROOT / "data" / "cache" / "pregame_oof.parquet"
FP_PATH = ROOT / "data" / "intelligence" / "player_fingerprints.parquet"
OUT_PATH = ROOT / "data" / "intelligence" / "stat_correlation_matrix.parquet"

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
MIN_PLAYER_GAMES = 20
MIN_ARCHETYPE_PLAYERS = 10


# ---------------------------------------------------------------------------
# PSD projection
# ---------------------------------------------------------------------------

def psd_project(C: np.ndarray, floor: float = 1e-6) -> np.ndarray:
    """Eigen-clip negative eigenvalues to `floor`, renormalize diagonal to 1."""
    eigvals, eigvecs = np.linalg.eigh(C)
    eigvals_clipped = np.maximum(eigvals, floor)
    C_psd = eigvecs @ np.diag(eigvals_clipped) @ eigvecs.T
    # Renormalize diagonal to 1
    d = np.sqrt(np.diag(C_psd))
    C_psd = C_psd / np.outer(d, d)
    return C_psd


def frobenius_dist(A: np.ndarray, B: np.ndarray) -> float:
    return float(np.linalg.norm(A - B, "fro"))


# ---------------------------------------------------------------------------
# Fisher-z pooling
# ---------------------------------------------------------------------------

def fisher_z(r: float) -> float:
    r = np.clip(r, -0.9999, 0.9999)
    return float(np.arctanh(r))


def fisher_z_inv(z: float) -> float:
    return float(np.tanh(z))


def fisher_pool(corrs: list[float], weights: list[float]) -> float:
    """Weighted Fisher-z average."""
    zs = np.array([fisher_z(r) for r in corrs])
    ws = np.array(weights, dtype=float)
    ws /= ws.sum()
    return fisher_z_inv(float((zs * ws).sum()))


# ---------------------------------------------------------------------------
# Build per-player residual correlations
# ---------------------------------------------------------------------------

def build_player_residuals(oof: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot long OOF to wide, compute residual = actual - oof_pred,
    drop DNP rows (all-zero stats in pts+reb+ast), return wide residual df.
    """
    # Pivot: one row per (player_id, game_id), one col per stat
    pivot = oof.pivot_table(
        index=["player_id", "game_id", "game_date"],
        columns="stat",
        values="actual",
        aggfunc="first",
    )
    pivot_pred = oof.pivot_table(
        index=["player_id", "game_id", "game_date"],
        columns="stat",
        values="oof_pred",
        aggfunc="first",
    )

    # Align to STATS columns only
    stats_present = [s for s in STATS if s in pivot.columns]
    missing = [s for s in STATS if s not in pivot.columns]
    if missing:
        print(f"  WARNING: stats missing from OOF: {missing}")

    act = pivot[stats_present].copy()
    pred = pivot_pred[stats_present].copy()

    # Drop rows where ANY actual is NaN
    mask_nan = act.isnull().any(axis=1)
    act = act[~mask_nan]
    pred = pred[~mask_nan]

    # Drop DNP rows: pts+reb+ast all zero
    dnp_cols = [s for s in ["pts", "reb", "ast"] if s in act.columns]
    dnp_mask = (act[dnp_cols] == 0).all(axis=1)
    act = act[~dnp_mask]
    pred = pred[~dnp_mask]

    residuals = act - pred
    residuals.columns.name = None
    return residuals.reset_index()


def per_player_corr(resid_wide: pd.DataFrame, stats: list[str]) -> list[dict]:
    """Compute 7x7 Pearson correlation matrix per player; keep >=MIN_PLAYER_GAMES."""
    records = []
    stat_pairs = [(a, b) for i, a in enumerate(stats) for b in stats[i + 1:]]

    for player_id, grp in resid_wide.groupby("player_id"):
        n = len(grp)
        if n < MIN_PLAYER_GAMES:
            continue
        sub = grp[stats].dropna()
        if len(sub) < MIN_PLAYER_GAMES:
            continue

        row: dict = {"player_id": int(player_id), "n_games": len(sub)}
        for a, b in stat_pairs:
            try:
                r, _ = pearsonr(sub[a], sub[b])
            except Exception:
                r = 0.0
            if np.isnan(r):
                r = 0.0
            row[f"{a}__{b}"] = float(r)
        records.append(row)

    return records


# ---------------------------------------------------------------------------
# Aggregate (Fisher-z pool) to a 7x7 matrix
# ---------------------------------------------------------------------------

def pool_to_matrix(
    player_corrs: pd.DataFrame,
    stats: list[str],
    weight_col: str = "n_games",
) -> tuple[np.ndarray, np.ndarray]:
    """Returns (raw_matrix, psd_matrix) as n_stats x n_stats arrays."""
    stat_pairs = [(a, b) for i, a in enumerate(stats) for b in stats[i + 1:]]
    n = len(stats)
    raw = np.eye(n)
    idx = {s: i for i, s in enumerate(stats)}

    for a, b in stat_pairs:
        col = f"{a}__{b}"
        if col not in player_corrs.columns:
            continue
        valid = player_corrs[[col, weight_col]].dropna()
        if len(valid) == 0:
            continue
        r_pooled = fisher_pool(
            valid[col].tolist(),
            np.sqrt(valid[weight_col].values).tolist(),
        )
        raw[idx[a], idx[b]] = r_pooled
        raw[idx[b], idx[a]] = r_pooled

    psd = psd_project(raw)
    return raw, psd


# ---------------------------------------------------------------------------
# Build long-format output rows from a matrix
# ---------------------------------------------------------------------------

def matrix_to_rows(
    raw: np.ndarray,
    psd: np.ndarray,
    stats: list[str],
    scope: str,
    n_players: int,
    n_games_total: int,
) -> list[dict]:
    rows = []
    for i, a in enumerate(stats):
        for j, b in enumerate(stats):
            rows.append(
                {
                    "scope": scope,
                    "n_players": n_players,
                    "n_games_total": n_games_total,
                    "stat_a": a,
                    "stat_b": b,
                    "corr": float(psd[i, j]),
                    "corr_raw": float(raw[i, j]),
                }
            )
    return rows


# ---------------------------------------------------------------------------
# Sanity gates
# ---------------------------------------------------------------------------

def sanity_gates(psd: np.ndarray, stats: list[str], scope: str) -> None:
    idx = {s: i for i, s in enumerate(stats)}

    def get(a: str, b: str) -> float:
        return float(psd[idx[a], idx[b]])

    checks = [
        ("corr(PTS,FG3M) > 0", get("pts", "fg3m") > 0, f"got {get('pts','fg3m'):.3f}, expect +0.25–0.45"),
        ("corr(PTS,REB) > 0", get("pts", "reb") > 0, f"got {get('pts','reb'):.3f}"),
        ("corr(AST,TOV) > 0", get("ast", "tov") > 0, f"got {get('ast','tov'):.3f}, expect +0.15–0.30"),
        ("|corr(STL,BLK)| < 0.10", abs(get("stl", "blk")) < 0.10, f"got {get('stl','blk'):.3f}"),
    ]
    for name, passed, detail in checks:
        tag = "OK  " if passed else "WARN"
        print(f"  [{scope}] {tag} {name} — {detail}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(validate: bool = False) -> None:
    print("=== INT-84: build_stat_correlations ===")

    # --- Load OOF ---
    if not OOF_PATH.exists():
        print(f"HALT: pregame_oof.parquet not found at {OOF_PATH}")
        sys.exit(1)

    oof = pd.read_parquet(OOF_PATH)
    expected_cols = {"player_id", "game_id", "stat", "oof_pred", "actual"}
    missing = expected_cols - set(oof.columns)
    if missing:
        print(f"HALT: pregame_oof.parquet missing columns: {missing}")
        print(f"  Actual columns: {list(oof.columns)}")
        sys.exit(1)
    print(f"  OOF loaded: {oof.shape[0]:,} rows, {oof.player_id.nunique()} players, "
          f"stats={sorted(oof.stat.unique())}")

    # --- Build residuals ---
    resid = build_player_residuals(oof)
    stats_avail = [s for s in STATS if s in resid.columns]
    print(f"  Residuals: {len(resid):,} rows after DNP filter, stats={stats_avail}")

    # --- Per-player correlations ---
    player_records = per_player_corr(resid, stats_avail)
    player_corrs = pd.DataFrame(player_records)
    n_qualifying = len(player_corrs)
    print(f"  Players qualifying (>={MIN_PLAYER_GAMES} games): {n_qualifying}")

    # --- Load fingerprints for archetypes ---
    archetype_map: dict[int, str] = {}
    if FP_PATH.exists():
        fp = pd.read_parquet(FP_PATH)
        for pid, row in fp.iterrows():
            archetype_map[int(pid)] = str(row.get("archetype_name", "unknown"))
        print(f"  Fingerprints loaded: {len(archetype_map)} players with archetypes")
    else:
        print(f"  WARNING: player_fingerprints.parquet not found; skipping per-archetype scope")

    player_corrs["archetype"] = player_corrs["player_id"].map(archetype_map).fillna("unknown")

    # --- League aggregate ---
    print("\n--- League aggregate ---")
    n_games_league = int(player_corrs["n_games"].sum())
    raw_league, psd_league = pool_to_matrix(player_corrs, stats_avail)
    fro = frobenius_dist(raw_league, psd_league)
    print(f"  Frobenius distance raw vs PSD: {fro:.5f}", end="")
    if fro > 0.05:
        print("  ** FLAG: distortion >0.05 — matrix was noisy **")
    else:
        print("  (OK)")

    all_rows = matrix_to_rows(
        raw_league, psd_league, stats_avail,
        scope="league", n_players=n_qualifying, n_games_total=n_games_league,
    )

    if validate:
        print("  Sanity gates (league):")
        sanity_gates(psd_league, stats_avail, "league")

    # --- Top/bottom pairs ---
    idx_map = {s: i for i, s in enumerate(stats_avail)}
    pairs = [(a, b, float(psd_league[idx_map[a], idx_map[b]]))
             for i, a in enumerate(stats_avail)
             for b in stats_avail[i + 1:]]
    pairs_sorted = sorted(pairs, key=lambda x: -abs(x[2]))
    print("\n  Top-5 strongest pairs (PSD):")
    for a, b, r in pairs_sorted[:5]:
        print(f"    {a:6s} x {b:6s}  r={r:+.4f}")
    print("  Bottom-5 weakest pairs (PSD):")
    for a, b, r in pairs_sorted[-5:]:
        print(f"    {a:6s} x {b:6s}  r={r:+.4f}")

    # --- Per-archetype ---
    archetype_counts: dict[str, int] = {}
    for arch_name, grp in player_corrs.groupby("archetype"):
        if arch_name == "unknown":
            continue
        n_p = len(grp)
        archetype_counts[arch_name] = n_p
        if n_p < MIN_ARCHETYPE_PLAYERS:
            print(f"  SKIP archetype '{arch_name}' — only {n_p} players (need {MIN_ARCHETYPE_PLAYERS})")
            continue
        n_g = int(grp["n_games"].sum())
        raw_a, psd_a = pool_to_matrix(grp, stats_avail)
        scope_tag = f"archetype:{arch_name}"
        all_rows.extend(
            matrix_to_rows(raw_a, psd_a, stats_avail, scope=scope_tag, n_players=n_p, n_games_total=n_g)
        )
        fro_a = frobenius_dist(raw_a, psd_a)
        flag = "  ** FLAG distortion>0.05 **" if fro_a > 0.05 else ""
        print(f"  Archetype '{arch_name}': {n_p} players, {n_g} games, Frobenius={fro_a:.5f}{flag}")
        if validate:
            sanity_gates(psd_a, stats_avail, arch_name)

    # --- Save ---
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_df = pd.DataFrame(all_rows)
    out_df.to_parquet(OUT_PATH, index=False)
    print(f"\n  Saved: {OUT_PATH} — {len(out_df):,} rows, scopes={out_df.scope.nunique()}")
    print(f"  Archetype player counts: {archetype_counts}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true", help="Run sanity gates")
    args = parser.parse_args()
    main(validate=args.validate)
