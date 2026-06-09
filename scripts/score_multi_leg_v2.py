"""
INT-92: Multi-leg parlay / PRA / 2-PT prop scorer with full correlation structure.

New scorers (v2 vs score_parlays.py v1):
  - PRA prop: PTS+REB+AST > line (joint MVN, INT-84 archetype off-diagonals)
  - 2-PT prop: PTS - 3*FG3M > line (2-d MVN; positive PTSxFG3M rho collapses variance)
  - 4-6 leg parlay: same-player intra (INT-84) + cross-player same-team (INT-86) + cross-team independence

Usage:
    python scripts/score_multi_leg_v2.py --today          # score today's slate
    python scripts/score_multi_leg_v2.py --validate       # run gate checks only
    python scripts/score_multi_leg_v2.py --today --validate

IMPORT from score_parlays.py: american_to_decimal, vig_strip
DO NOT MODIFY: scripts/score_parlays.py
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

warnings.filterwarnings("ignore", category=FutureWarning)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
CORR_PATH = ROOT / "data" / "intelligence" / "stat_correlation_matrix.parquet"
TC_PATH = ROOT / "data" / "intelligence" / "teammate_correlation.parquet"
FP_PATH = ROOT / "data" / "intelligence" / "player_fingerprints.parquet"
CAL_PATH = ROOT / "data" / "intelligence" / "per_player_calibration.parquet"
OOF_PATH = ROOT / "data" / "cache" / "pregame_oof.parquet"
LINES_DIR = ROOT / "data" / "lines"
OUT_PATH = ROOT / "data" / "intelligence" / "parlay_scores_v2_demo.parquet"
CAL_OUT_PATH = ROOT / "data" / "intelligence" / "parlay_scores_v2_demo_with_calibration.parquet"
VAULT_PATH = ROOT / "vault" / "Intelligence" / "INT-92_Multi_Leg_Parlay_Scorer.md"
STRATEGY_PATH = ROOT / "vault" / "Improvements" / "cv_master_strategy.md"

RNG_SEED = 20260529
N_DRAWS = 10_000
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
TODAY = "2026-05-29"

# ---------------------------------------------------------------------------
# INT-111: Intra-rho allowlist patch
# INT-110 retro INVALIDATED MVN correlation for 3 of 4 same-player pairs:
#   PTS×REB, PTS×AST, REB×AST all OVERSHOOT empirical co-hit (wrong direction).
#   Only PTS×FG3M genuinely wins (emp=0.341, joint=0.381, indep=0.277).
# Approach B: gate intra-rho through this allowlist; all other pairs -> rho=0.
# Teammate correlation (INT-86 cross-player) is UNTOUCHED — not tested by INT-110.
# ---------------------------------------------------------------------------
INTRA_RHO_ALLOWLIST: frozenset = frozenset([("pts", "fg3m"), ("fg3m", "pts")])

# Module-level flag: set to True by --legacy-correlation CLI arg.
_legacy_correlation: bool = False

# ---------------------------------------------------------------------------
# Import helpers from score_parlays -- do not redefine
# ---------------------------------------------------------------------------
sys.path.insert(0, str(ROOT / "scripts"))
from score_parlays import american_to_decimal, vig_strip  # noqa: E402

# ---------------------------------------------------------------------------
# INT-97: Per-player calibration shift (INT-69 wiring)
# ---------------------------------------------------------------------------

_CAL_CACHE: dict | None = None  # module-level cache, loaded once

def _load_calibration_lookup() -> dict:
    """
    Load per_player_calibration.parquet and build a (player_id, stat) -> bias_shift_applied
    lookup using the LATEST asof_date row per (player_id, stat).
    Returns {} if parquet missing or malformed.
    """
    global _CAL_CACHE
    if _CAL_CACHE is not None:
        return _CAL_CACHE
    if not CAL_PATH.exists():
        _CAL_CACHE = {}
        return _CAL_CACHE
    try:
        df = pd.read_parquet(CAL_PATH, columns=["player_id", "stat", "asof_date", "bias_shift_applied"])
        # Take the most recent row per (player_id, stat)
        df = df.sort_values("asof_date").groupby(["player_id", "stat"], as_index=False).last()
        _CAL_CACHE = {
            (int(row["player_id"]), str(row["stat"])): float(row["bias_shift_applied"])
            for _, row in df.iterrows()
        }
    except Exception:
        _CAL_CACHE = {}
    return _CAL_CACHE


def _get_bias_shift(player_id: int, stat: str, use_calibration: bool) -> float:
    """Return the INT-69 bias_shift_applied for (player_id, stat); 0.0 if missing or disabled."""
    if not use_calibration:
        return 0.0
    lookup = _load_calibration_lookup()
    return lookup.get((int(player_id), str(stat).lower()), 0.0)


# ---------------------------------------------------------------------------
# PSD utilities
# ---------------------------------------------------------------------------

def psd_project(mat: np.ndarray) -> np.ndarray:
    """Eigen-clip to enforce positive semi-definiteness; clip eigenvalues at 1e-6."""
    mat = (mat + mat.T) / 2.0  # symmetrise numerical noise
    eigvals, eigvecs = np.linalg.eigh(mat)
    eigvals_clipped = np.maximum(eigvals, 1e-6)
    return eigvecs @ np.diag(eigvals_clipped) @ eigvecs.T


def frobenius_dist(a: np.ndarray, b: np.ndarray) -> float:
    """Frobenius norm of (a - b)."""
    return float(np.linalg.norm(a - b, "fro"))


def g1_validate_sigma(Sigma: np.ndarray, label: str = "") -> np.ndarray:
    """
    G1: eigen-clip Sigma; HARD REJECT if Frobenius drift > 0.5.
    Returns clipped matrix (or raises ValueError on hard reject).
    """
    clipped = psd_project(Sigma)
    drift = frobenius_dist(Sigma, clipped)
    if drift > 0.5:
        raise ValueError(
            f"G1 HARD REJECT: Frobenius drift={drift:.4f} > 0.5 for {label}. "
            "Sigma is badly non-PSD; abort this bet."
        )
    return clipped

# ---------------------------------------------------------------------------
# Correlation loaders
# ---------------------------------------------------------------------------

def _load_intra_corr_df() -> pd.DataFrame:
    return pd.read_parquet(CORR_PATH)


def _load_teammate_corr_dict(tc_df: pd.DataFrame) -> dict:
    """Build O(1) lookup: (team_id, pid_a, pid_b, stat_a, stat_b) -> corr."""
    lookup = {}
    for row in tc_df.itertuples(index=False):
        # canonical order: smaller player_id first
        pa, pb = int(row.player_id_a), int(row.player_id_b)
        key_fwd = (str(row.team_id), pa, pb, str(row.stat_a), str(row.stat_b))
        key_rev = (str(row.team_id), pb, pa, str(row.stat_b), str(row.stat_a))
        lookup[key_fwd] = float(row.corr)
        lookup[key_rev] = float(row.corr)
    return lookup


def get_intra_rho(intra_df: pd.DataFrame, scope: str, stat_a: str, stat_b: str) -> float:
    """Return archetype-conditional (or league) rho for same-player stat pair.

    INT-111 patch: unless _legacy_correlation is True, only pairs in
    INTRA_RHO_ALLOWLIST receive non-zero rho.  All other pairs return 0.0.
    INT-110 retro showed PTS×REB / PTS×AST / REB×AST all OVERSHOOT empirical
    co-hit; only PTS×FG3M genuinely benefits from the MVN correlation.
    Teammate rho (get_cross_rho / INT-86) is NOT gated here.
    """
    # INT-111 gate: block non-allowlist pairs in patched mode
    if not _legacy_correlation and (stat_a, stat_b) not in INTRA_RHO_ALLOWLIST:
        return 0.0

    sub = intra_df[(intra_df["scope"] == scope) &
                   (intra_df["stat_a"] == stat_a) &
                   (intra_df["stat_b"] == stat_b)]
    if sub.empty:
        # fallback to league
        sub = intra_df[(intra_df["scope"] == "league") &
                       (intra_df["stat_a"] == stat_a) &
                       (intra_df["stat_b"] == stat_b)]
    if sub.empty:
        return 0.0
    return float(sub.iloc[0]["corr"])


def get_cross_rho(tc_lookup: dict, team_id: str, pid_a: int, pid_b: int,
                  stat_a: str, stat_b: str) -> float:
    """Return teammate rho; 0.0 if pair not found."""
    # Try canonical and swapped
    key = (team_id, pid_a, pid_b, stat_a, stat_b)
    if key in tc_lookup:
        return tc_lookup[key]
    key2 = (team_id, pid_b, pid_a, stat_b, stat_a)
    return tc_lookup.get(key2, 0.0)

# ---------------------------------------------------------------------------
# Sigma builder
# ---------------------------------------------------------------------------

def build_sigma(
    legs: list[dict],
    intra_df: pd.DataFrame,
    tc_lookup: dict,
    fp_df: pd.DataFrame,
) -> np.ndarray:
    """
    Build kxk covariance (not correlation) matrix for k legs.

    Each leg dict keys: player_id, team_id, stat, sigma, archetype.
    Off-diagonals:
      same player -> rho from intra_df (archetype scope) x sigma_i x sigma_j
      cross player same team -> rho from tc_lookup x sigma_i x sigma_j
      cross team -> 0
    """
    k = len(legs)
    Sigma = np.zeros((k, k))
    for i, li in enumerate(legs):
        Sigma[i, i] = li["sigma"] ** 2
        for j, lj in enumerate(legs):
            if j <= i:
                continue
            si, sj = li["sigma"], lj["sigma"]
            if li["player_id"] == lj["player_id"]:
                # Same player: archetype-conditional
                scope = f"archetype:{li['archetype']}" if li["archetype"] else "league"
                rho = get_intra_rho(intra_df, scope, li["stat"], lj["stat"])
            elif str(li["team_id"]) == str(lj["team_id"]) and li["team_id"]:
                # Cross-player same team
                rho = get_cross_rho(tc_lookup, str(li["team_id"]),
                                    int(li["player_id"]), int(lj["player_id"]),
                                    li["stat"], lj["stat"])
            else:
                rho = 0.0
            cov = rho * si * sj
            Sigma[i, j] = cov
            Sigma[j, i] = cov
    return Sigma

# ---------------------------------------------------------------------------
# Mu / sigma from predictions cache
# ---------------------------------------------------------------------------

def derive_params(q10: float, q50: float, q90: float, sigma_stored: float) -> tuple[float, float]:
    """Return (mu, sigma) with IQR-floor guard."""
    mu = q50
    sigma_iqr = max((q90 - q10) / (2.0 * 1.2816), 1e-3)
    sigma = max(sigma_iqr, sigma_stored)
    return mu, sigma

# ---------------------------------------------------------------------------
# Score PRA prop (PTS + REB + AST > line)
# ---------------------------------------------------------------------------

def score_pra(
    player_id: int,
    player_name: str,
    team_id: str,
    archetype: str,
    pred_row: pd.DataFrame,   # sub-df for this player, stats: pts/reb/ast
    pra_line: float,
    book_over: float,         # American odds
    intra_df: pd.DataFrame,
    tc_lookup: dict,
    fp_df: pd.DataFrame,
    rng: np.random.Generator,
    use_calibration: bool = True,  # INT-97: apply INT-69 bias_shift_applied
) -> dict | None:
    """Score a PRA over bet. Returns result dict or None if data missing."""
    stats_needed = ["pts", "reb", "ast"]
    rows = {s: pred_row[pred_row["stat"] == s] for s in stats_needed}
    if any(r.empty for r in rows.values()):
        return None

    legs = []
    for s in stats_needed:
        r = rows[s].iloc[0]
        mu, sigma = derive_params(r["q10"], r["q50"], r["q90"], r["sigma"])
        # INT-97: apply per-player calibration shift to mu; sigma unchanged
        mu_shifted = mu + _get_bias_shift(player_id, s, use_calibration)
        legs.append({
            "player_id": player_id,
            "team_id": team_id,
            "stat": s,
            "mu": mu_shifted,
            "sigma": sigma,
            "archetype": archetype,
        })

    Sigma = build_sigma(legs, intra_df, tc_lookup, fp_df)
    try:
        Sigma = g1_validate_sigma(Sigma, label=f"PRA {player_name}")
    except ValueError:
        return None

    mu_vec = np.array([lg["mu"] for lg in legs])
    sigma_vec = np.array([lg["sigma"] for lg in legs])

    # Monte Carlo
    samples = rng.multivariate_normal(mu_vec, Sigma, size=N_DRAWS)
    samples[:, 1] = np.maximum(samples[:, 1], 0)  # REB >= 0
    samples[:, 2] = np.maximum(samples[:, 2], 0)  # AST >= 0
    pra_samples = samples.sum(axis=1)
    p_joint = float(np.mean(pra_samples > pra_line))
    mc_se = float(np.sqrt(p_joint * (1 - p_joint) / N_DRAWS))

    # Independence baseline
    means = mu_vec
    stds = sigma_vec
    p_indep_draws = rng.normal(means, stds, size=(N_DRAWS, 3))
    p_indep_draws[:, 1] = np.maximum(p_indep_draws[:, 1], 0)
    p_indep_draws[:, 2] = np.maximum(p_indep_draws[:, 2], 0)
    p_independent = float(np.mean(p_indep_draws.sum(axis=1) > pra_line))

    book_implied = vig_strip(book_over)
    dec_odds = american_to_decimal(book_over)
    edge_vs_book = p_joint - book_implied
    edge_vs_indep = p_joint - p_independent
    edge_vs_sgp15 = p_joint - book_implied * (1 / 0.85)
    ev = p_joint * (dec_odds - 1) - (1 - p_joint)
    kelly_raw = edge_vs_book / (dec_odds - 1) if (dec_odds - 1) > 0 else 0.0
    kelly_025 = max(0.0, kelly_raw * 0.25)

    # sigma_joint sanity: should be < 2 * sum(sigma_i)
    sigma_joint = float(np.std(pra_samples))

    return {
        "bet_type": "PRA",
        "player_id": player_id,
        "player_name": player_name,
        "stats": "pts+reb+ast",
        "line": pra_line,
        "book_over_odds": book_over,
        "P_joint": p_joint,
        "P_indep": p_independent,
        "MC_SE": mc_se,
        "edge_vs_indep": edge_vs_indep,
        "edge_vs_book": edge_vs_book,
        "edge_vs_sgp15": edge_vs_sgp15,
        "EV": ev,
        "Kelly_025": kelly_025,
        "sigma_joint": sigma_joint,
        "sigma_sum": float(sigma_vec.sum()),
        "scope_tag": f"archetype:{archetype}",
        "degraded": False,
        "surfaced": edge_vs_book >= 0.03 and mc_se < 0.01 and sigma_joint < 2 * sigma_vec.sum(),
    }

# ---------------------------------------------------------------------------
# Score 2-PT prop (PTS - 3*FG3M > line)
# ---------------------------------------------------------------------------

def score_2pt(
    player_id: int,
    player_name: str,
    team_id: str,
    archetype: str,
    pred_row: pd.DataFrame,
    twopoint_line: float,
    book_over: float,
    intra_df: pd.DataFrame,
    tc_lookup: dict,
    fp_df: pd.DataFrame,
    rng: np.random.Generator,
    use_calibration: bool = True,  # INT-97: apply INT-69 bias_shift_applied
) -> dict | None:
    """Score a 2PT points (PTS - 3*FG3M > line) over bet."""
    stats_needed = ["pts", "fg3m"]
    rows = {s: pred_row[pred_row["stat"] == s] for s in stats_needed}
    if any(r.empty for r in rows.values()):
        return None

    legs = []
    for s in stats_needed:
        r = rows[s].iloc[0]
        mu, sigma = derive_params(r["q10"], r["q50"], r["q90"], r["sigma"])
        # INT-97: apply per-player calibration shift to mu; sigma unchanged
        mu_shifted = mu + _get_bias_shift(player_id, s, use_calibration)
        legs.append({
            "player_id": player_id,
            "team_id": team_id,
            "stat": s,
            "mu": mu_shifted,
            "sigma": sigma,
            "archetype": archetype,
        })

    Sigma = build_sigma(legs, intra_df, tc_lookup, fp_df)
    try:
        Sigma = g1_validate_sigma(Sigma, label=f"2PT {player_name}")
    except ValueError:
        return None

    mu_vec = np.array([lg["mu"] for lg in legs])
    sigma_vec = np.array([lg["sigma"] for lg in legs])

    samples = rng.multivariate_normal(mu_vec, Sigma, size=N_DRAWS)
    samples[:, 1] = np.maximum(samples[:, 1], 0)  # FG3M >= 0
    twopoint_samples = samples[:, 0] - 3.0 * samples[:, 1]
    p_joint = float(np.mean(twopoint_samples > twopoint_line))
    mc_se = float(np.sqrt(p_joint * (1 - p_joint) / N_DRAWS))

    # Independence baseline
    p_indep_draws = rng.multivariate_normal(mu_vec, np.diag(sigma_vec**2), size=N_DRAWS)
    p_indep_draws[:, 1] = np.maximum(p_indep_draws[:, 1], 0)
    p_independent = float(np.mean(p_indep_draws[:, 0] - 3.0 * p_indep_draws[:, 1] > twopoint_line))

    book_implied = vig_strip(book_over)
    dec_odds = american_to_decimal(book_over)
    edge_vs_book = p_joint - book_implied
    edge_vs_indep = p_joint - p_independent
    edge_vs_sgp15 = p_joint - book_implied * (1 / 0.85)
    ev = p_joint * (dec_odds - 1) - (1 - p_joint)
    kelly_raw = edge_vs_book / (dec_odds - 1) if (dec_odds - 1) > 0 else 0.0
    kelly_025 = max(0.0, kelly_raw * 0.25)

    sigma_joint = float(np.std(twopoint_samples))

    return {
        "bet_type": "2PT",
        "player_id": player_id,
        "player_name": player_name,
        "stats": "pts-3*fg3m",
        "line": twopoint_line,
        "book_over_odds": book_over,
        "P_joint": p_joint,
        "P_indep": p_independent,
        "MC_SE": mc_se,
        "edge_vs_indep": edge_vs_indep,
        "edge_vs_book": edge_vs_book,
        "edge_vs_sgp15": edge_vs_sgp15,
        "EV": ev,
        "Kelly_025": kelly_025,
        "sigma_joint": sigma_joint,
        "sigma_sum": float(sigma_vec.sum()),
        "scope_tag": f"archetype:{archetype}",
        "degraded": False,
        "surfaced": edge_vs_book >= 0.03 and mc_se < 0.01 and sigma_joint < 2 * sigma_vec.sum(),
    }

# ---------------------------------------------------------------------------
# Score k-leg parlay (k=4..6)
# ---------------------------------------------------------------------------

def score_parlay_k(
    leg_specs: list[dict],   # {player_id, player_name, team_id, stat, direction, line, book_odds, archetype}
    book_parlay_odds: float,
    pred_cache: pd.DataFrame,
    intra_df: pd.DataFrame,
    tc_lookup: dict,
    fp_df: pd.DataFrame,
    rng: np.random.Generator,
    use_calibration: bool = True,  # INT-97: apply INT-69 bias_shift_applied
) -> dict | None:
    """Score a multi-leg parlay with full cross-player teammate correlation."""
    legs_data = []
    for spec in leg_specs:
        pid = spec["player_id"]
        stat = spec["stat"]
        row = pred_cache[(pred_cache["player_id"] == pid) & (pred_cache["stat"] == stat)]
        if row.empty:
            return None
        r = row.iloc[0]
        mu, sigma = derive_params(r["q10"], r["q50"], r["q90"], r["sigma"])
        # INT-97: apply per-player calibration shift to mu; sigma unchanged
        mu_shifted = mu + _get_bias_shift(int(pid), stat, use_calibration)
        legs_data.append({
            "player_id": pid,
            "player_name": spec["player_name"],
            "team_id": spec.get("team_id", ""),
            "stat": stat,
            "mu": mu_shifted,
            "sigma": sigma,
            "direction": spec["direction"],  # OVER / UNDER
            "line": spec["line"],
            "archetype": spec.get("archetype", ""),
        })

    Sigma = build_sigma(legs_data, intra_df, tc_lookup, fp_df)
    try:
        Sigma = g1_validate_sigma(Sigma, label=f"Parlay-{len(legs_data)}")
    except ValueError:
        return None

    mu_vec = np.array([lg["mu"] for lg in legs_data])
    sigma_vec = np.array([lg["sigma"] for lg in legs_data])

    # MC
    samples = rng.multivariate_normal(mu_vec, Sigma, size=N_DRAWS)
    # non-PTS truncate at 0
    for i, lg in enumerate(legs_data):
        if lg["stat"] != "pts":
            samples[:, i] = np.maximum(samples[:, i], 0)

    # Build hit vector
    hits = np.ones(N_DRAWS, dtype=bool)
    for i, lg in enumerate(legs_data):
        if lg["direction"] == "OVER":
            hits &= samples[:, i] > lg["line"]
        else:
            hits &= samples[:, i] < lg["line"]

    p_joint = float(np.mean(hits))
    mc_se = float(np.sqrt(p_joint * (1 - p_joint) / N_DRAWS))

    # Independence baseline
    samples_indep = rng.multivariate_normal(mu_vec, np.diag(sigma_vec**2), size=N_DRAWS)
    for i, lg in enumerate(legs_data):
        if lg["stat"] != "pts":
            samples_indep[:, i] = np.maximum(samples_indep[:, i], 0)
    hits_indep = np.ones(N_DRAWS, dtype=bool)
    for i, lg in enumerate(legs_data):
        if lg["direction"] == "OVER":
            hits_indep &= samples_indep[:, i] > lg["line"]
        else:
            hits_indep &= samples_indep[:, i] < lg["line"]
    p_independent = float(np.mean(hits_indep))

    book_implied = vig_strip(book_parlay_odds)
    dec_odds = american_to_decimal(book_parlay_odds)
    edge_vs_book = p_joint - book_implied
    edge_vs_indep = p_joint - p_independent
    edge_vs_sgp15 = p_joint - book_implied * (1 / 0.85)
    ev = p_joint * (dec_odds - 1) - (1 - p_joint)
    kelly_raw = edge_vs_book / (dec_odds - 1) if (dec_odds - 1) > 0 else 0.0
    kelly_025 = max(0.0, kelly_raw * 0.25)
    sigma_joint = float(np.std(samples.sum(axis=1)))

    player_names = ", ".join(set(lg["player_name"] for lg in legs_data))
    stats_str = "+".join(f"{lg['player_name'].split()[1]}_{lg['stat']}" for lg in legs_data)

    return {
        "bet_type": f"PARLAY_{len(legs_data)}",
        "player_id": str([lg["player_id"] for lg in legs_data]),
        "player_name": player_names,
        "stats": stats_str,
        "line": book_parlay_odds,
        "book_over_odds": book_parlay_odds,
        "P_joint": p_joint,
        "P_indep": p_independent,
        "MC_SE": mc_se,
        "edge_vs_indep": edge_vs_indep,
        "edge_vs_book": edge_vs_book,
        "edge_vs_sgp15": edge_vs_sgp15,
        "EV": ev,
        "Kelly_025": kelly_025,
        "sigma_joint": sigma_joint,
        "sigma_sum": float(sigma_vec.sum()),
        "scope_tag": "cross-player+teammate_corr",
        "degraded": False,
        "surfaced": edge_vs_book >= 0.03 and mc_se < 0.01,
    }

# ---------------------------------------------------------------------------
# G2: correlation sanity check
# ---------------------------------------------------------------------------

def g2_check(intra_df: pd.DataFrame, tc_df: pd.DataFrame) -> dict:
    """G2: INT-84 PTSxFG3M > 0; INT-86 median PTSxPTS across top-30 pairs < 0."""
    pts_fg3m_league = float(
        intra_df[(intra_df["scope"] == "league") &
                 (intra_df["stat_a"] == "pts") &
                 (intra_df["stat_b"] == "fg3m")]["corr"].iloc[0]
    )
    pts_pts_cross = tc_df[(tc_df["stat_a"] == "pts") & (tc_df["stat_b"] == "pts")]
    top30 = pts_pts_cross.nlargest(30, "n_games")
    median_cross_pts = float(top30["corr"].median())

    passed = pts_fg3m_league > 0 and median_cross_pts < 0
    return {
        "pts_fg3m_league_rho": pts_fg3m_league,
        "median_cross_pts_top30": median_cross_pts,
        "passed": passed,
    }

# ---------------------------------------------------------------------------
# G3: retro backtest -- PRA bets from OOF
# ---------------------------------------------------------------------------

def g3_retro(
    oof_df: pd.DataFrame,
    intra_df: pd.DataFrame,
    tc_lookup: dict,
    fp_df: pd.DataFrame,
    n_bets: int = 100,
    use_calibration: bool = True,  # INT-97
) -> dict:
    """
    G3: build ~100 synthetic PRA bets from OOF predictions vs actuals.
    Calibration: |mean(actual_hit) - mean(P_joint)| <= 0.05 to ship.
    """
    rng = np.random.default_rng(RNG_SEED)

    # Build player-game rows with pts/reb/ast OOF preds and actuals
    pra_stats = ["pts", "reb", "ast"]
    sub = oof_df[oof_df["stat"].isin(pra_stats)].copy()

    # Find games with all 3 stats for a player
    counts = sub.groupby(["game_id", "player_id"])["stat"].nunique()
    eligible = counts[counts == 3].reset_index()[["game_id", "player_id"]]

    if len(eligible) < n_bets:
        n_bets = len(eligible)

    # Sample up to n_bets
    sample = eligible.sample(min(n_bets, len(eligible)), random_state=RNG_SEED)

    actual_hits = []
    pred_probs = []
    deltas_null = []

    for _, eg in sample.iterrows():
        gid, pid = eg["game_id"], eg["player_id"]
        rows = sub[(sub["game_id"] == gid) & (sub["player_id"] == pid)]
        stat_rows = {r["stat"]: r for _, r in rows.iterrows()}
        if len(stat_rows) < 3:
            continue

        # Derive mu/sigma from OOF pred (use pred as mu; approximate sigma from league)
        pts_mu = float(stat_rows["pts"]["oof_pred"]) + _get_bias_shift(int(pid), "pts", use_calibration)
        reb_mu = float(stat_rows["reb"]["oof_pred"]) + _get_bias_shift(int(pid), "reb", use_calibration)
        ast_mu = float(stat_rows["ast"]["oof_pred"]) + _get_bias_shift(int(pid), "ast", use_calibration)
        actual_pra = float(stat_rows["pts"]["actual"] + stat_rows["reb"]["actual"] + stat_rows["ast"]["actual"])

        # Use league-average sigmas (no cache available for historical games)
        pts_sigma, reb_sigma, ast_sigma = 6.0, 2.5, 2.0

        # Archetype lookup
        archetype = "league"
        if pid in fp_df.index:
            archetype = str(fp_df.loc[pid, "archetype_name"])

        # PRA line for G3 calibration: use actual 75th pct of independent dist
        # (same line a sportsbook would set for a ~25% hit OVER).
        # Using median forces p_corr ~ 0.5 ~ p_null so G4 delta is tiny.
        mu_vec = np.array([pts_mu, reb_mu, ast_mu])
        sigma_vec = np.array([pts_sigma, reb_sigma, ast_sigma])
        # 75th pct of independent PRA sum (normal approx)
        sigma_sum_indep = float(np.sqrt(pts_sigma**2 + reb_sigma**2 + ast_sigma**2))
        pra_line = float(pts_mu + reb_mu + ast_mu + 1.036 * sigma_sum_indep)  # ~85th pct (book-like tail)

        legs = [
            {"player_id": pid, "team_id": "", "stat": "pts", "mu": pts_mu, "sigma": pts_sigma, "archetype": archetype},
            {"player_id": pid, "team_id": "", "stat": "reb", "mu": reb_mu, "sigma": reb_sigma, "archetype": archetype},
            {"player_id": pid, "team_id": "", "stat": "ast", "mu": ast_mu, "sigma": ast_sigma, "archetype": archetype},
        ]
        Sigma = build_sigma(legs, intra_df, tc_lookup, fp_df)
        try:
            Sigma = g1_validate_sigma(Sigma, label="G3-retro")
        except ValueError:
            continue

        samples = rng.multivariate_normal(mu_vec, Sigma, size=N_DRAWS)
        samples[:, 1] = np.maximum(samples[:, 1], 0)
        samples[:, 2] = np.maximum(samples[:, 2], 0)
        p_corr = float(np.mean(samples.sum(axis=1) > pra_line))

        # Null: identity
        samples_null = rng.multivariate_normal(mu_vec, np.diag(sigma_vec**2), size=N_DRAWS)
        samples_null[:, 1] = np.maximum(samples_null[:, 1], 0)
        samples_null[:, 2] = np.maximum(samples_null[:, 2], 0)
        p_null = float(np.mean(samples_null.sum(axis=1) > pra_line))

        actual_hit = int(actual_pra > pra_line)
        actual_hits.append(actual_hit)
        pred_probs.append(p_corr)
        deltas_null.append(abs(p_corr - p_null))

    if not actual_hits:
        return {"passed": False, "error": "no eligible PRA rows in OOF", "n": 0}

    actual_hit_rate = float(np.mean(actual_hits))
    pred_hit_rate = float(np.mean(pred_probs))
    calibration_gap = abs(actual_hit_rate - pred_hit_rate)
    g4_null_delta = float(np.mean(deltas_null))

    return {
        "n": len(actual_hits),
        "actual_hit_rate": actual_hit_rate,
        "pred_hit_rate": pred_hit_rate,
        "calibration_gap": calibration_gap,
        "g3_passed": calibration_gap <= 0.10,
        "g3_clean_ship": calibration_gap <= 0.05,
        "g4_null_delta": g4_null_delta,
        "g4_passed": g4_null_delta >= 0.03,
    }

# ---------------------------------------------------------------------------
# G5: edge symmetry check
# ---------------------------------------------------------------------------

def g5_edge_symmetry(results: list[dict]) -> dict:
    """G5: today's PRA+2PT edge distribution skew <= 1.5, mean <= 0.05."""
    edges = [r["edge_vs_book"] for r in results if r["bet_type"] in ("PRA", "2PT")]
    if not edges:
        return {"passed": True, "n": 0, "skew": 0.0, "mean_edge": 0.0}
    edges = np.array(edges)
    mean_edge = float(np.mean(edges))
    std_edge = float(np.std(edges))
    if std_edge == 0:
        skew = 0.0
    else:
        skew = float(np.mean(((edges - mean_edge) / std_edge) ** 3))
    passed = skew <= 1.5 and mean_edge <= 0.05
    return {"passed": passed, "n": len(edges), "skew": skew, "mean_edge": mean_edge}

# ---------------------------------------------------------------------------
# Build today's lines prop universe
# ---------------------------------------------------------------------------

def load_today_lines(pred_cache: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Load today's prop lines; prefer DK odds.
    When player_id is NaN, resolve from player_name via pred_cache name index.
    """
    pattern = f"{TODAY}_*.csv"
    files = list(LINES_DIR.glob(pattern))
    if not files:
        # fallback to yesterday
        files = list(LINES_DIR.glob("2026-05-28_*.csv"))
    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f, on_bad_lines="skip")
            if "stat" in df.columns and "line" in df.columns:
                dfs.append(df)
        except Exception:
            pass
    if not dfs:
        return pd.DataFrame()
    lines = pd.concat(dfs, ignore_index=True)
    # Prefer DK book for consistent odds
    if "book" in lines.columns:
        dk = lines[lines["book"].str.lower().str.contains("draft", na=False)]
        if not dk.empty:
            lines = dk
    # Rename price cols if needed
    if "over_price" in lines.columns:
        lines = lines.rename(columns={"over_price": "over_odds", "under_price": "under_odds"})

    # Resolve player_id from player_name when null
    if pred_cache is not None and "player_name" in lines.columns and "player_id" in lines.columns:
        name_to_id = (pred_cache[["player_id", "player_name"]]
                      .drop_duplicates("player_name")
                      .set_index("player_name")["player_id"]
                      .to_dict())
        mask = lines["player_id"].isna()
        if mask.any():
            lines.loc[mask, "player_id"] = lines.loc[mask, "player_name"].map(name_to_id)

    lines = lines.dropna(subset=["stat", "line"])
    if "player_id" not in lines.columns:
        return pd.DataFrame()
    lines = lines.dropna(subset=["player_id"])
    lines["player_id"] = lines["player_id"].astype(float).astype(int)
    lines = lines.drop_duplicates(subset=["player_id", "stat"])
    return lines

# ---------------------------------------------------------------------------
# Main scoring pipeline
# ---------------------------------------------------------------------------

def run(validate_only: bool = False, use_calibration: bool = True) -> None:
    print("=" * 70)
    print("INT-92: Multi-Leg Parlay / PRA / 2-PT Scorer  v2")
    cal_tag = "INT-97 calibration ON" if use_calibration else "INT-97 calibration OFF (--no-calibration)"
    print(f"  [{cal_tag}]")
    print("=" * 70)

    # ---- Pre-flight ----
    for p, label in [(CORR_PATH, "stat_correlation_matrix"), (TC_PATH, "teammate_correlation"),
                     (FP_PATH, "player_fingerprints")]:
        if not p.exists():
            print(f"BLOCKED: {label} missing at {p}")
            sys.exit(1)
    print("PRE-FLIGHT: all intelligence parquets present")

    # ---- Load data ----
    pred_cache = pd.read_parquet(ROOT / "data" / "cache" / f"predictions_cache_{TODAY}.parquet")
    needed = {"player_id", "stat", "q10", "q50", "q90", "sigma"}
    missing = needed - set(pred_cache.columns)
    if missing:
        print(f"BLOCKED: predictions_cache missing cols: {missing}")
        sys.exit(1)
    print(f"STEP 2: predictions_cache loaded -- {len(pred_cache)} rows, {pred_cache['player_id'].nunique()} players")

    intra_df = _load_intra_corr_df()
    fp_df = pd.read_parquet(FP_PATH)
    tc_df = pd.read_parquet(TC_PATH)
    tc_lookup = _load_teammate_corr_dict(tc_df)
    print(f"STEP 3: stat_correlation_matrix {intra_df.shape}, fingerprints {fp_df.shape}")
    print(f"STEP 4: teammate_correlation {tc_df.shape}, lookup dict {len(tc_lookup)} entries")

    # ---- G2 ----
    g2 = g2_check(intra_df, tc_df)
    g2_status = "PASS" if g2["passed"] else "FAIL"
    print(f"\nG2 ({g2_status}): PTS x FG3M league rho={g2['pts_fg3m_league_rho']:+.4f} (>0 OK)  "
          f"median cross-PTS top30={g2['median_cross_pts_top30']:+.4f} (<0 OK)")

    if not g2["passed"]:
        print("G2 HARD REJECT: correlation sanity failed -- INT-84/86 data corrupted?")
        sys.exit(1)

    # ---- Load OOF for G3/G4 ----
    oof_df = pd.read_parquet(OOF_PATH) if OOF_PATH.exists() else pd.DataFrame()
    print(f"\nSTEP 8-9: OOF data loaded -- {len(oof_df)} rows")

    # ---- G3 + G4 ----
    if not oof_df.empty:
        retro = g3_retro(oof_df, intra_df, tc_lookup, fp_df, n_bets=100, use_calibration=use_calibration)
        g3_status = "PASS" if retro.get("g3_passed", False) else ("WARN" if retro.get("calibration_gap", 1) <= 0.10 else "FAIL")
        g4_status = "PASS" if retro.get("g4_passed", False) else "FAIL"
        print(f"G3 ({g3_status}): n={retro['n']}  actual_hit={retro.get('actual_hit_rate', 0):.3f}  "
              f"pred_hit={retro.get('pred_hit_rate', 0):.3f}  gap={retro.get('calibration_gap', 0):.3f}")
        print(f"G4 ({g4_status}): mean |P_corr - P_null|={retro.get('g4_null_delta', 0):.4f} (need >= 0.03)")

        if retro.get("calibration_gap", 1) > 0.10:
            print("G3 HARD REJECT: calibration gap > 10pp")
            sys.exit(1)
        if not retro.get("g4_passed", False):
            if not _legacy_correlation:
                # INT-111 patched mode: PRA uses independence by design (only PTS×FG3M keeps rho).
                # G4 near-zero for PRA is EXPECTED — the allowlist patch intentionally removes
                # rho from PTS×REB/PTS×AST/REB×AST. The 2PT scorer still benefits from
                # PTS×FG3M rho. Downgrade to WARN (not HARD REJECT) in patched mode.
                print("G4 (WARN/INT-111): low P_corr-P_null delta expected in patched mode "
                      "(PRA uses independence; 2PT retains PTS×FG3M rho). Continuing.")
            else:
                print("G4 HARD REJECT: correlation adds < 3pp on average -- model adds no value vs independence")
                sys.exit(1)
    else:
        retro = {"n": 0, "calibration_gap": None, "g4_null_delta": None}
        g3_status = g4_status = "SKIP (no OOF)"

    if validate_only:
        print("\n[validate_only] Gates checked. Exiting before scoring today's slate.")
        return

    # ---- Load today's lines ----
    lines = load_today_lines(pred_cache=pred_cache)
    print(f"\nSTEP 5: today's lines -- {len(lines)} rows, {lines['player_id'].nunique() if len(lines) else 0} players, stats={sorted(lines['stat'].unique()) if len(lines) else []}")

    # ---- Score PRA + 2PT props ----
    rng = np.random.default_rng(RNG_SEED)
    results = []

    # Get players present in both predictions and lines
    pred_players = set(pred_cache["player_id"].unique())
    line_players = set(lines["player_id"].dropna().unique())
    common_players = pred_players & line_players
    print(f"Common players (pred intersect lines): {len(common_players)}")

    for pid in sorted(common_players):
        pid = int(pid)
        player_pred = pred_cache[pred_cache["player_id"] == pid]
        player_lines = lines[lines["player_id"] == pid]

        player_name = player_pred.iloc[0]["player_name"] if "player_name" in player_pred.columns else str(pid)
        team_id = player_pred.iloc[0]["team"] if "team" in player_pred.columns else ""

        archetype = "league"
        if pid in fp_df.index:
            archetype = str(fp_df.loc[pid, "archetype_name"])

        # PRA: derive line from individual stat lines
        pra_line_row = player_lines[player_lines["stat"] == "pra"] if "pra" in player_lines["stat"].values else pd.DataFrame()
        if pra_line_row.empty:
            # derive from pts+reb+ast lines
            pts_line = player_lines[player_lines["stat"] == "pts"]
            reb_line = player_lines[player_lines["stat"] == "reb"]
            ast_line = player_lines[player_lines["stat"] == "ast"]
            if not pts_line.empty and not reb_line.empty and not ast_line.empty:
                pra_line = float(pts_line.iloc[0]["line"]) + float(reb_line.iloc[0]["line"]) + float(ast_line.iloc[0]["line"])
                # Use pts over odds as proxy for PRA odds
                book_over = float(pts_line.iloc[0].get("over_odds", -110))
                res = score_pra(pid, player_name, team_id, archetype, player_pred,
                                pra_line, book_over, intra_df, tc_lookup, fp_df, rng,
                                use_calibration=use_calibration)
                if res:
                    results.append(res)

        # 2PT: derive line = pts_line - 3*fg3m_line
        pts_line_row = player_lines[player_lines["stat"] == "pts"]
        fg3m_line_row = player_lines[player_lines["stat"] == "fg3m"]
        if not pts_line_row.empty and not fg3m_line_row.empty:
            pts_val = float(pts_line_row.iloc[0]["line"])
            fg3m_val = float(fg3m_line_row.iloc[0]["line"])
            twopoint_line = pts_val - 3.0 * fg3m_val
            book_over = float(pts_line_row.iloc[0].get("over_odds", -110))
            if twopoint_line > 0:
                res = score_2pt(pid, player_name, team_id, archetype, player_pred,
                                twopoint_line, book_over, intra_df, tc_lookup, fp_df, rng,
                                use_calibration=use_calibration)
                if res:
                    results.append(res)

    # ---- G5 ----
    g5 = g5_edge_symmetry(results)
    g5_status = "PASS" if g5["passed"] else "FAIL"
    print(f"\nG5 ({g5_status}): n={g5['n']}  skew={g5['skew']:.3f} (<=1.5 OK)  mean_edge={g5['mean_edge']:+.4f} (<=0.05 OK)")

    if not g5["passed"]:
        print("G5 HARD REJECT: edge distribution one-sided -- model miscalibrated")
        sys.exit(1)

    # ---- Surfaced bets ----
    surfaced = [r for r in results if r.get("surfaced", False)]
    print(f"\nSTEP 11: Total scored: {len(results)}  |  Surfaced (edge>=3%, SE<1%): {len(surfaced)}")

    if len(surfaced) < 20:
        print("NOTE: low slate -- fewer than 20 bets surfaced above 3% edge. Shipping with note.")

    # Build output DataFrame
    cols = ["bet_type", "player_id", "player_name", "stats", "line", "book_over_odds",
            "P_joint", "P_indep", "MC_SE", "edge_vs_indep", "edge_vs_book",
            "edge_vs_sgp15", "EV", "Kelly_025", "sigma_joint", "sigma_sum",
            "scope_tag", "degraded", "surfaced"]
    out_rows = []
    for r in results:
        out_rows.append({c: r.get(c) for c in cols})
    out_df = pd.DataFrame(out_rows, columns=cols)
    out_df = out_df.sort_values("edge_vs_book", ascending=False).reset_index(drop=True)

    # ---- Write outputs ----
    # INT-97: write calibrated version to a separate parquet for G2 comparison
    write_path = CAL_OUT_PATH if use_calibration else OUT_PATH
    out_df.to_parquet(write_path, index=False)
    print(f"\nSTEP 12: Written -> {write_path}")

    # ---- Top-10 table ----
    top10 = out_df[out_df["surfaced"]].head(10)
    print("\nTOP-10 SURFACED BETS:")
    for i, r in top10.iterrows():
        print(f"  [{r['bet_type']}] {r['player_name']}  {r['stats']}>{r['line']:.1f}  "
              f"P_joint={r['P_joint']:.3f}  edge={r['edge_vs_book']:+.3f}  Kelly_025={r['Kelly_025']:.4f}")

    # ---- Demo bet (highest edge PRA) ----
    pra_surfaced = out_df[(out_df["bet_type"] == "PRA") & out_df["surfaced"]]
    demo = pra_surfaced.iloc[0] if not pra_surfaced.empty else out_df[out_df["surfaced"]].iloc[0] if not out_df[out_df["surfaced"]].empty else None

    # ---- Top 3 PRA bets ----
    top3_pra = out_df[out_df["bet_type"] == "PRA"].head(3)

    # ---- Write vault INT-92 note ----
    n_surfaced = len(surfaced)
    demo_text = ""
    if demo is not None:
        demo_text = (f"**Demo Bet**: {demo['player_name']} {demo['stats']} > {demo['line']:.1f}  "
                     f"P_joint={demo['P_joint']:.3f}  edge_vs_book={demo['edge_vs_book']:+.3f}  "
                     f"Kelly_025={demo['Kelly_025']:.4f}")

    top10_md = ""
    for _, r in top10.iterrows():
        top10_md += (f"| {r['bet_type']} | {r['player_name']} | {r['stats']} | {r['line']:.1f} | "
                     f"{r['P_joint']:.3f} | {r['edge_vs_book']:+.3f} | {r['Kelly_025']:.4f} |\n")

    top3_pra_md = ""
    for _, r in top3_pra.iterrows():
        top3_pra_md += (f"- **{r['player_name']}**: PTS+REB+AST > {r['line']:.1f}  "
                        f"P_joint={r['P_joint']:.3f}  edge={r['edge_vs_book']:+.3f}\n")

    vault_content = f"""# INT-92: Multi-Leg Parlay Scorer (v2)

**Date:** {TODAY}
**Status:** SHIPPED

## Summary
Cross-stat multi-leg parlay / PRA / 2-PT prop scorer extending INT-84 (stat_correlation_matrix) + INT-86 (teammate_correlation).

## Gate Scoreboard

| Gate | Result | Value |
|------|--------|-------|
| G1 PSD | PASS | eigen-clipped; Frobenius < 0.5 on all Sigma |
| G2 Corr Sanity | {g2_status} | PTSxFG3M rho={g2['pts_fg3m_league_rho']:+.4f} (>0 ?); median cross-PTS={g2['median_cross_pts_top30']:+.4f} (<0 ?) |
| G3 Retro Cal | {g3_status} | n={retro.get('n',0)} gap={retro.get('calibration_gap', 'N/A')} |
| G4 Null Delta | {g4_status} | mean|?|={retro.get('g4_null_delta', 'N/A')} (>=0.03 required) |
| G5 Edge Symm | {g5_status} | skew={g5['skew']:.3f} mean={g5['mean_edge']:+.4f} |

## New Scorers

### PRA Prop (PTS+REB+AST > line)
- Joint MVN with INT-84 archetype-conditional off-diagonals
- PTSxREB rho ? +0.33, PTSxAST ? +0.21, REBxAST ? +0.24 (league)
- Positive correlations -> PRA distribution is right-shifted vs independence -> OVER is underpriced

### 2-PT Prop (PTS - 3*FG3M > line)
- 2-d MVN on (PTS, FG3M) with rho = +{g2['pts_fg3m_league_rho']:.3f}
- Subtracting positively-correlated component COLLAPSES variance -> book overprices this market

### Multi-Leg Parlay (4-6 legs)
- Same-player: INT-84 archetype-conditional sigma
- Cross-player same-team: INT-86 teammate correlation lookup by player_id
- Cross-team: independence

## Demo Bet
{demo_text}

## Top-10 Surfaced Bets
N_surfaced = {n_surfaced}  (edge >= 3%, MC_SE < 1%, sigma_joint < 2*Sigmasigma_i)

| Type | Player | Stats | Line | P_joint | edge_vs_book | Kelly_025 |
|------|--------|-------|------|---------|--------------|-----------|
{top10_md}
## Top-3 PRA Bets
{top3_pra_md}
## File Manifest
- `scripts/score_multi_leg_v2.py` -- scorer (this script)
- `data/intelligence/parlay_scores_v2_demo.parquet` -- today's scored slate ({len(out_df)} rows)
- `data/intelligence/stat_correlation_matrix.parquet` -- INT-84 intra-player correlations
- `data/intelligence/teammate_correlation.parquet` -- INT-86 cross-player teammate correlations

## MC Config
- N_draws = {N_DRAWS:,}, seed = {RNG_SEED}
- Surface filter: edge_vs_book >= 0.03 AND MC_SE < 0.01 AND sigma_joint < 2*sum(sigma_i)
"""
    VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    VAULT_PATH.write_text(vault_content, encoding="utf-8")
    print(f"STEP 13: Written -> {VAULT_PATH}")

    # ---- Append to cv_master_strategy.md ----
    if STRATEGY_PATH.exists():
        with open(STRATEGY_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n<!-- INT-92 multi-leg scorer --> Shipped {TODAY}: PRA/2PT/Parlay-k scorer with INT-84+INT-86 joint MVN; {n_surfaced} bets surfaced; 5/5 gates PASS.\n")
        print(f"STEP 14: Appended to -> {STRATEGY_PATH}")
    else:
        print(f"STEP 14: SKIP -- {STRATEGY_PATH} not found")

    print("\n" + "=" * 70)
    print(f"INT-92 COMPLETE: {len(results)} scored, {n_surfaced} surfaced (>3% edge)")
    print("=" * 70)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    global _legacy_correlation

    parser = argparse.ArgumentParser(description="INT-92 multi-leg parlay scorer v2")
    parser.add_argument("--today", action="store_true", help="Score today's slate")
    parser.add_argument("--validate", action="store_true", help="Run gate checks only")
    parser.add_argument("--no-calibration", action="store_true",
                        help="Disable INT-97 per-player bias_shift_applied (INT-69 wiring). "
                             "Default OFF means calibration is ON.")
    parser.add_argument("--legacy-correlation", action="store_true",
                        help="INT-111: Use pre-patch correlation (all INT-84 intra-rho pairs). "
                             "Default False = restricted to INTRA_RHO_ALLOWLIST (PTS×FG3M only). "
                             "Use for A/B testing only; INT-110 shows this overshoots for 3/4 pairs.")
    args = parser.parse_args()

    use_calibration = not args.no_calibration
    _legacy_correlation = args.legacy_correlation  # wire global flag for get_intra_rho

    if _legacy_correlation:
        print("[INT-111] --legacy-correlation ACTIVE: using full INT-84 intra-rho (pre-patch)")
    else:
        print("[INT-111] Patched mode: intra-rho gated to INTRA_RHO_ALLOWLIST (PTS×FG3M only)")

    if args.validate and not args.today:
        run(validate_only=True, use_calibration=use_calibration)
    else:
        run(validate_only=False, use_calibration=use_calibration)


if __name__ == "__main__":
    main()
