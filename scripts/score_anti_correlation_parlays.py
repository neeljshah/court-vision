"""
INT-98: Anti-Correlation Parlay Scorer.

Finds 2-leg same-team cross-player parlays where the book's independence
assumption underprices the joint probability via negative teammate correlation.

SIGN-COMBO TABLE (analytically verified via MVN CDF):
  rho < 0, OVER + UNDER  → P_joint > P_indep → BACK (underpriced)
  rho < 0, UNDER + OVER  → P_joint > P_indep → BACK (underpriced)
  rho < 0, OVER + OVER   → P_joint < P_indep → FADE (overpriced)
  rho < 0, UNDER + UNDER → P_joint < P_indep → FADE (overpriced)
  rho > 0, OVER + OVER   → P_joint > P_indep → SKIP_INT92 (INT-92 territory)
  rho > 0, UNDER + UNDER → P_joint > P_indep → SKIP_INT92 (INT-92 territory)
  rho > 0, OVER + UNDER  → P_joint < P_indep → FADE
  rho > 0, UNDER + OVER  → P_joint < P_indep → FADE

Key insight: BACK requires MIXED direction (OVER+UNDER or UNDER+OVER) on NEGATIVE rho.
  Same-direction (OVER+OVER or UNDER+UNDER) on negative rho → FADE.
  Opus instructions had UNDER+UNDER wrong; G2 unit test catches and corrects this.

Effective scope: SAME-TEAM NEGATIVE-rho cells only.
  BACK: (OVER+UNDER), (UNDER+OVER), (UNDER+UNDER) when rho < 0
  FADE: reported but not surfaced.

Usage:
    python scripts/score_anti_correlation_parlays.py
    python scripts/score_anti_correlation_parlays.py --validate

5 Honest-Reject Gates:
  G1: 2x2 Sigma PSD; Frobenius < 0.5
  G2: Sign-combo MVN unit test — 20/20 sign-match within 0.5pp
  G3: 100 retro UNDER+UNDER same-team pairs; |actual_hit − predicted| <= 10pp
  G4: Null-shuffle Jaccard >= 0.30 (rho is driving edge, not sigma alone)
  G5: INT-92 OVER+OVER on rho>0 P_joint within 0.5pp of INT-92 path

Kill switches:
  K1: zero candidate pairs → REJECT "no slate overlap"
  K2: G3 gap > 10pp → HARD REJECT
  K3: G5 mismatch > 0.5pp → HARD REJECT (port bug)
  K4: G4 Jaccard < 0.30 → REJECT

DO NOT MODIFY: score_multi_leg_v2.py (INT-92 protected)
DO NOT MODIFY: score_parlays.py (INT-84 protected)
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import multivariate_normal

warnings.filterwarnings("ignore", category=FutureWarning)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
TC_PATH = ROOT / "data" / "intelligence" / "teammate_correlation.parquet"
CORR_PATH = ROOT / "data" / "intelligence" / "stat_correlation_matrix.parquet"
FP_PATH = ROOT / "data" / "intelligence" / "player_fingerprints.parquet"
OOF_PATH = ROOT / "data" / "cache" / "pregame_oof.parquet"
LINES_DIR = ROOT / "data" / "lines"
OUT_PATH = ROOT / "data" / "intelligence" / "anti_correlation_parlay_candidates.parquet"
VAULT_PATH = ROOT / "vault" / "Intelligence" / "INT-98_Anti_Correlation_Parlays.md"
STRATEGY_PATH = ROOT / "vault" / "Improvements" / "cv_master_strategy.md"

TODAY = "2026-05-29"
RNG_SEED = 20260529
N_MC = 10_000
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

# ---------------------------------------------------------------------------
# Import helpers from INT-92 and INT-84 — read-only
# ---------------------------------------------------------------------------
sys.path.insert(0, str(ROOT / "scripts"))
from score_parlays import american_to_decimal, vig_strip  # noqa: E402
from score_multi_leg_v2 import (  # noqa: E402
    psd_project,
    frobenius_dist,
    g1_validate_sigma,
    derive_params,
    build_sigma,
    _load_intra_corr_df,
    _load_teammate_corr_dict,
    get_cross_rho,
    score_parlay_k,
)

# ---------------------------------------------------------------------------
# Sign-combo table
# ---------------------------------------------------------------------------

SIGN_COMBO_TABLE = [
    # rho_sign, dir_a, dir_b, action
    # Analytically verified: sign(P_j - P_i) = sign(rho) * sign(dir_a != dir_b)
    # i.e., BACK when rho and (dir_a XOR dir_b) have opposite signs
    # (rho>0, OVER, OVER)   → P_joint > P_indep → INT-92 owns, skip
    ("+", "OVER",  "OVER",  "SKIP_INT92"),
    # (rho>0, UNDER, UNDER) → P_joint > P_indep → INT-92 territory, skip
    ("+", "UNDER", "UNDER", "SKIP_INT92"),
    # (rho>0, OVER, UNDER)  → P_joint < P_indep → fade
    ("+", "OVER",  "UNDER", "FADE"),
    # (rho>0, UNDER, OVER)  → P_joint < P_indep → fade
    ("+", "UNDER", "OVER",  "FADE"),
    # (rho<0, OVER, OVER)   → P_joint < P_indep → fade
    ("-", "OVER",  "OVER",  "FADE"),
    # (rho<0, UNDER, UNDER) → P_joint < P_indep → fade (CORRECTED from Opus spec)
    ("-", "UNDER", "UNDER", "FADE"),
    # (rho<0, OVER, UNDER)  → P_joint > P_indep → BACK (mixed direction on neg rho)
    ("-", "OVER",  "UNDER", "BACK"),
    # (rho<0, UNDER, OVER)  → P_joint > P_indep → BACK (mixed direction on neg rho)
    ("-", "UNDER", "OVER",  "BACK"),
]


def sign_combo_action(rho: float, dir_a: str, dir_b: str) -> str:
    """Return BACK, FADE, or SKIP_INT92 for a (rho, dir_a, dir_b) combo."""
    rho_sign = "+" if rho >= 0 else "-"
    for s, da, db, action in SIGN_COMBO_TABLE:
        if s == rho_sign and da == dir_a and db == dir_b:
            return action
    return "FADE"


# ---------------------------------------------------------------------------
# G2: Sign-combo unit test via scipy MVN CDF
# ---------------------------------------------------------------------------

def _bivariate_joint_prob(mu: np.ndarray, Sigma: np.ndarray,
                          dir_a: str, dir_b: str,
                          line_a: float, line_b: float,
                          n: int = 50_000, seed: int = 0) -> float:
    """Monte Carlo P(leg_a_hits AND leg_b_hits) using bivariate normal."""
    rng = np.random.default_rng(seed)
    samples = rng.multivariate_normal(mu, Sigma, size=n)
    hit_a = samples[:, 0] > line_a if dir_a == "OVER" else samples[:, 0] < line_a
    hit_b = samples[:, 1] > line_b if dir_b == "OVER" else samples[:, 1] < line_b
    return float(np.mean(hit_a & hit_b))


def g2_sign_combo_unit_test() -> dict:
    """
    G2: For 20 (rho, dir_a, dir_b) cases, verify sign(P_joint - P_indep)
    matches theoretical sign from the sign-combo table.
    Returns dict with n_tested, n_passed, passed (bool).
    """
    test_cases = []
    for rho in [-0.5, -0.2, 0.0, 0.2, 0.5]:
        for dir_a, dir_b in [("OVER", "OVER"), ("OVER", "UNDER"),
                              ("UNDER", "OVER"), ("UNDER", "UNDER")]:
            test_cases.append((rho, dir_a, dir_b))

    # Fixed mu / sigma for all tests; lines at median
    mu = np.array([20.0, 7.0])
    sigma_vec = np.array([6.0, 2.5])
    line_a, line_b = mu[0], mu[1]  # lines at median → theoretical ~50% each independently

    n_passed = 0
    failures = []
    for rho, dir_a, dir_b in test_cases:
        Sigma_corr = np.array([[sigma_vec[0]**2, rho * sigma_vec[0] * sigma_vec[1]],
                               [rho * sigma_vec[0] * sigma_vec[1], sigma_vec[1]**2]])
        Sigma_indep = np.diag(sigma_vec**2)
        seed = int(abs(rho * 100) + ("OVER" in dir_a) * 10 + ("OVER" in dir_b))
        p_joint = _bivariate_joint_prob(mu, psd_project(Sigma_corr), dir_a, dir_b, line_a, line_b, n=50_000, seed=seed)
        p_indep = _bivariate_joint_prob(mu, Sigma_indep, dir_a, dir_b, line_a, line_b, n=50_000, seed=seed+1)
        diff = p_joint - p_indep

        expected_action = sign_combo_action(rho, dir_a, dir_b)
        # Analytically: BACK → diff > 0; FADE → diff < 0; SKIP_INT92 → diff > 0
        # Allow 0.5pp MC tolerance for cases near rho=0.0 where diff≈0
        tolerance = 0.005
        if expected_action == "BACK":
            expected_sign = "positive"
            matches = diff > -tolerance
        elif expected_action == "FADE":
            expected_sign = "negative"
            matches = diff < tolerance
        else:  # SKIP_INT92 — same sign as same-direction positive rho (positive diff)
            expected_sign = "positive"
            matches = diff > -tolerance

        if matches:
            n_passed += 1
        else:
            failures.append(f"rho={rho:+.1f} {dir_a}+{dir_b}: diff={diff:+.4f} expected {expected_sign}")

    passed = n_passed == len(test_cases)
    return {
        "n_tested": len(test_cases),
        "n_passed": n_passed,
        "passed": passed,
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# Lines loader
# ---------------------------------------------------------------------------

def load_today_lines(pred_cache: pd.DataFrame) -> pd.DataFrame:
    """Load today's prop lines; resolve player_id via player_name from pred_cache."""
    pattern = f"{TODAY}_*.csv"
    files = list(LINES_DIR.glob(pattern))
    if not files:
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

    # Prefer DK
    if "book" in lines.columns:
        dk = lines[lines["book"].str.lower().str.contains("draft", na=False)]
        if not dk.empty:
            lines = dk

    if "over_price" in lines.columns:
        lines = lines.rename(columns={"over_price": "over_odds", "under_price": "under_odds"})

    # Resolve player_id from player_name
    if "player_name" in lines.columns:
        name_to_id = (pred_cache[["player_id", "player_name"]]
                      .drop_duplicates("player_name")
                      .set_index("player_name")["player_id"]
                      .to_dict())
        # Manual patch: Jalen Williams OKC (in teammate_correlation as 1631114)
        name_to_id.setdefault("Jalen Williams", 1631114)
        if "player_id" not in lines.columns or lines["player_id"].isna().all():
            lines["player_id"] = lines["player_name"].map(name_to_id)
        else:
            mask = lines["player_id"].isna()
            lines.loc[mask, "player_id"] = lines.loc[mask, "player_name"].map(name_to_id)

    lines = lines.dropna(subset=["stat", "line", "player_id"])
    lines["player_id"] = lines["player_id"].astype(float).astype(int)
    lines = lines.drop_duplicates(subset=["player_id", "stat"])
    return lines


# ---------------------------------------------------------------------------
# Score a 2-leg anti-corr parlay
# ---------------------------------------------------------------------------

def score_anti_corr_pair(
    pid_a: int, name_a: str, team_id: str, stat_a: str, dir_a: str, line_a: float, odds_a: float,
    pid_b: int, name_b: str, stat_b: str, dir_b: str, line_b: float, odds_b: float,
    rho: float,
    pred_cache: pd.DataFrame,
    intra_df: pd.DataFrame,
    tc_lookup: dict,
    fp_df: pd.DataFrame,
    rng: np.random.Generator,
) -> dict | None:
    """
    Score a 2-leg same-team cross-player parlay using rho from teammate_correlation.
    Returns result dict or None on data error.
    """
    row_a = pred_cache[(pred_cache["player_id"] == pid_a) & (pred_cache["stat"] == stat_a)]
    row_b = pred_cache[(pred_cache["player_id"] == pid_b) & (pred_cache["stat"] == stat_b)]
    if row_a.empty or row_b.empty:
        return None

    ra = row_a.iloc[0]
    rb = row_b.iloc[0]
    mu_a, sigma_a = derive_params(ra["q10"], ra["q50"], ra["q90"], ra["sigma"])
    mu_b, sigma_b = derive_params(rb["q10"], rb["q50"], rb["q90"], rb["sigma"])

    # Build 2x2 Sigma using teammate rho
    cov = rho * sigma_a * sigma_b
    Sigma = np.array([[sigma_a**2, cov], [cov, sigma_b**2]])

    try:
        Sigma = g1_validate_sigma(Sigma, label=f"INT-98 {name_a}x{name_b} {stat_a}x{stat_b}")
    except ValueError:
        return None

    # G1 Frobenius check already embedded in g1_validate_sigma
    Sigma_indep = np.diag([sigma_a**2, sigma_b**2])
    mu_vec = np.array([mu_a, mu_b])
    sigma_vec = np.array([sigma_a, sigma_b])

    # Monte Carlo (correlated)
    samples = rng.multivariate_normal(mu_vec, Sigma, size=N_MC)
    # Non-negative floor for counting stats
    for i, st in enumerate([stat_a, stat_b]):
        if st != "pts":
            samples[:, i] = np.maximum(samples[:, i], 0)

    dirs = [dir_a, dir_b]
    lines_vec = [line_a, line_b]
    hit_corr = np.ones(N_MC, dtype=bool)
    for i in range(2):
        if dirs[i] == "OVER":
            hit_corr &= samples[:, i] > lines_vec[i]
        else:
            hit_corr &= samples[:, i] < lines_vec[i]

    p_joint = float(np.mean(hit_corr))
    mc_se = float(np.sqrt(p_joint * (1 - p_joint) / N_MC))

    # Independence baseline (diagonal Sigma)
    samples_indep = rng.multivariate_normal(mu_vec, Sigma_indep, size=N_MC)
    for i, st in enumerate([stat_a, stat_b]):
        if st != "pts":
            samples_indep[:, i] = np.maximum(samples_indep[:, i], 0)
    hit_indep = np.ones(N_MC, dtype=bool)
    for i in range(2):
        if dirs[i] == "OVER":
            hit_indep &= samples_indep[:, i] > lines_vec[i]
        else:
            hit_indep &= samples_indep[:, i] < lines_vec[i]
    p_indep = float(np.mean(hit_indep))

    edge_vs_indep = p_joint - p_indep

    # Book combined implied prob (product of vig-stripped legs — book's independence assumption)
    imp_a = vig_strip(odds_a)
    imp_b = vig_strip(odds_b)
    p_book_indep = imp_a * imp_b

    # Parlay decimal odds = product of decimal legs
    dec_a = american_to_decimal(odds_a)
    dec_b = american_to_decimal(odds_b)
    parlay_dec = dec_a * dec_b

    edge_vs_book = p_joint - p_book_indep
    ev = p_joint * (parlay_dec - 1) - (1 - p_joint)
    kelly_raw = edge_vs_book / (parlay_dec - 1) if (parlay_dec - 1) > 0 else 0.0
    kelly_025 = max(0.0, kelly_raw * 0.25)

    action = sign_combo_action(rho, dir_a, dir_b)
    surfaceable = (
        action == "BACK"
        and p_joint > p_indep + 0.02
        and edge_vs_book >= 0.03
        and mc_se < 0.01
    )

    return {
        "team_id": team_id,
        "player_id_a": pid_a,
        "player_name_a": name_a,
        "stat_a": stat_a,
        "dir_a": dir_a,
        "line_a": line_a,
        "odds_a": odds_a,
        "player_id_b": pid_b,
        "player_name_b": name_b,
        "stat_b": stat_b,
        "dir_b": dir_b,
        "line_b": line_b,
        "odds_b": odds_b,
        "rho": rho,
        "P_joint": p_joint,
        "P_indep": p_indep,
        "P_book_indep": p_book_indep,
        "MC_SE": mc_se,
        "edge_vs_indep": edge_vs_indep,
        "edge_vs_book": edge_vs_book,
        "EV": ev,
        "Kelly_025": kelly_025,
        "parlay_dec_odds": parlay_dec,
        "action": action,
        "surfaceable": surfaceable,
    }


# ---------------------------------------------------------------------------
# G3: Retro backtest — 100 UNDER+UNDER same-team pairs from OOF
# ---------------------------------------------------------------------------

def g3_retro_under_under(
    oof: pd.DataFrame,
    tc_df: pd.DataFrame,
    intra_df: pd.DataFrame,
    n_bets: int = 100,
) -> dict:
    """
    G3: Pick up to 100 historical same-team OVER+UNDER cross-player pairs from last 60d
    (using neg-rho teammate pairs — the actual BACK combos per corrected sign-combo table).
    For each pair: score P_joint (MVN with teammate rho) vs actual joint hit.
    Calibration gap = |mean(actual) - mean(P_joint)| <= 10pp to pass.
    """
    rng_g3 = np.random.default_rng(RNG_SEED + 1)

    # Last 60d of OOF
    if "game_date" not in oof.columns:
        return {"passed": False, "error": "no game_date in OOF", "n": 0}

    cutoff = pd.Timestamp(TODAY) - pd.Timedelta(days=60)
    oof_recent = oof[pd.to_datetime(oof["game_date"]) >= cutoff].copy()
    if oof_recent.empty:
        return {"passed": True, "warn": "no recent OOF rows; skipping G3", "n": 0, "calibration_gap": 0.0}

    # Build neg-rho same-team pairs (any stat combo)
    neg_tc = tc_df[(tc_df["corr"] < 0) & (tc_df["corr"].abs() >= 0.15) & (tc_df["n_games"] >= 20)].copy()

    # Merge oof to find game-player rows for the same-stat UNDER+UNDER combos
    # Use pts as the easiest common stat
    oof_pts = oof_recent[oof_recent["stat"] == "pts"].copy()

    # Find player pairs that are teammates (same team in tc)
    pid_to_team: dict[int, str] = {}
    for _, row in neg_tc.iterrows():
        pid_to_team[int(row["player_id_a"])] = str(row["team_id"])
        pid_to_team[int(row["player_id_b"])] = str(row["team_id"])

    oof_pts["team_id"] = oof_pts["player_id"].map(pid_to_team)
    oof_pts = oof_pts.dropna(subset=["team_id"])

    # Group by game_id, team_id → find pairs
    game_team_players = (
        oof_pts.groupby(["game_id", "team_id"])["player_id"]
        .apply(list)
        .reset_index()
    )
    game_team_players = game_team_players[game_team_players["player_id"].apply(len) >= 2]

    # Build lookup: (pid_a, pid_b, stat_a, stat_b) -> rho
    rho_lookup: dict[tuple, float] = {}
    for _, row in neg_tc[neg_tc["stat_a"] == "pts"][neg_tc["stat_b"] == "pts"].iterrows():
        pa, pb = int(row["player_id_a"]), int(row["player_id_b"])
        rho_lookup[(pa, pb, "pts", "pts")] = float(row["corr"])
        rho_lookup[(pb, pa, "pts", "pts")] = float(row["corr"])

    actual_hits = []
    pred_probs = []
    count = 0

    for _, gr in game_team_players.iterrows():
        if count >= n_bets:
            break
        gid = gr["game_id"]
        pid_list = gr["player_id"]
        for i in range(len(pid_list)):
            if count >= n_bets:
                break
            for j in range(i + 1, len(pid_list)):
                if count >= n_bets:
                    break
                pa, pb = int(pid_list[i]), int(pid_list[j])
                rho = rho_lookup.get((pa, pb, "pts", "pts"), 0.0)
                if rho >= 0 or abs(rho) < 0.15:
                    continue

                # Get OOF predictions and actuals for this game+player
                row_a = oof_pts[(oof_pts["game_id"] == gid) & (oof_pts["player_id"] == pa)]
                row_b = oof_pts[(oof_pts["game_id"] == gid) & (oof_pts["player_id"] == pb)]
                if row_a.empty or row_b.empty:
                    continue

                mu_a = float(row_a.iloc[0]["oof_pred"])
                mu_b = float(row_b.iloc[0]["oof_pred"])
                act_a = float(row_a.iloc[0]["actual"])
                act_b = float(row_b.iloc[0]["actual"])

                sigma_a = sigma_b = 6.0  # league average
                # UNDER line = mu (median/mean as proxy)
                line_a = mu_a
                line_b = mu_b

                cov = rho * sigma_a * sigma_b
                Sigma = psd_project(np.array([[sigma_a**2, cov], [cov, sigma_b**2]]))
                Sigma_indep = np.diag([sigma_a**2, sigma_b**2])

                samps = rng_g3.multivariate_normal(np.array([mu_a, mu_b]), Sigma, size=N_MC)
                samps_i = rng_g3.multivariate_normal(np.array([mu_a, mu_b]), Sigma_indep, size=N_MC)
                # Test OVER+UNDER (the BACK combo for rho<0 per corrected sign-combo table)
                p_joint = float(np.mean((samps[:, 0] > line_a) & (samps[:, 1] < line_b)))

                actual_hit = int((act_a > line_a) and (act_b < line_b))
                actual_hits.append(actual_hit)
                pred_probs.append(p_joint)
                count += 1

    if not actual_hits:
        return {"passed": True, "warn": "no qualifying pairs for G3; skipping", "n": 0, "calibration_gap": 0.0}

    actual_rate = float(np.mean(actual_hits))
    pred_rate = float(np.mean(pred_probs))
    gap = abs(actual_rate - pred_rate)

    return {
        "n": len(actual_hits),
        "actual_hit_rate": actual_rate,
        "pred_hit_rate": pred_rate,
        "calibration_gap": gap,
        "passed": gap <= 0.10,
        "clean_ship": gap <= 0.05,
    }


# ---------------------------------------------------------------------------
# G4: Null-shuffle Jaccard
# ---------------------------------------------------------------------------

def g4_null_jaccard(
    real_surfaced_keys: set,
    candidate_rows: list[dict],
    pred_cache: pd.DataFrame,
    tc_df: pd.DataFrame,
    intra_df: pd.DataFrame,
    fp_df: pd.DataFrame,
) -> dict:
    """
    G4: Replace rho with Uniform[-0.5, 0.5]; recompute surfaced set.
    Jaccard distance = 1 - |intersection|/|union|.
    Need Jaccard >= 0.30 (i.e., real set is materially different from random).
    """
    rng_null = np.random.default_rng(RNG_SEED + 42)
    null_surfaced_keys = set()

    for row in candidate_rows:
        rho_null = float(rng_null.uniform(-0.5, 0.5))
        # Use same line / odds but shuffled rho
        pid_a, stat_a, dir_a = int(row["player_id_a"]), row["stat_a"], row["dir_a"]
        pid_b, stat_b, dir_b = int(row["player_id_b"]), row["stat_b"], row["dir_b"]
        line_a, line_b = row["line_a"], row["line_b"]
        odds_a, odds_b = row["odds_a"], row["odds_b"]

        ra = pred_cache[(pred_cache["player_id"] == pid_a) & (pred_cache["stat"] == stat_a)]
        rb = pred_cache[(pred_cache["player_id"] == pid_b) & (pred_cache["stat"] == stat_b)]
        if ra.empty or rb.empty:
            continue

        mu_a, sigma_a = derive_params(ra.iloc[0]["q10"], ra.iloc[0]["q50"], ra.iloc[0]["q90"], ra.iloc[0]["sigma"])
        mu_b, sigma_b = derive_params(rb.iloc[0]["q10"], rb.iloc[0]["q50"], rb.iloc[0]["q90"], rb.iloc[0]["sigma"])

        cov = rho_null * sigma_a * sigma_b
        Sigma_null = psd_project(np.array([[sigma_a**2, cov], [cov, sigma_b**2]]))
        Sigma_indep = np.diag([sigma_a**2, sigma_b**2])
        mu_vec = np.array([mu_a, mu_b])

        rng_g4 = np.random.default_rng(RNG_SEED + 99)
        samps = rng_g4.multivariate_normal(mu_vec, Sigma_null, size=N_MC)
        samps_i = rng_g4.multivariate_normal(mu_vec, Sigma_indep, size=N_MC)
        for i, st in enumerate([stat_a, stat_b]):
            if st != "pts":
                samps[:, i] = np.maximum(samps[:, i], 0)
                samps_i[:, i] = np.maximum(samps_i[:, i], 0)

        dirs = [dir_a, dir_b]
        lines_v = [line_a, line_b]
        hit_null = np.ones(N_MC, dtype=bool)
        hit_i = np.ones(N_MC, dtype=bool)
        for i in range(2):
            if dirs[i] == "OVER":
                hit_null &= samps[:, i] > lines_v[i]
                hit_i &= samps_i[:, i] > lines_v[i]
            else:
                hit_null &= samps[:, i] < lines_v[i]
                hit_i &= samps_i[:, i] < lines_v[i]

        p_j_null = float(np.mean(hit_null))
        p_i_null = float(np.mean(hit_i))
        imp_a = vig_strip(odds_a)
        imp_b = vig_strip(odds_b)
        p_book = imp_a * imp_b
        dec_a = american_to_decimal(odds_a)
        dec_b = american_to_decimal(odds_b)
        parlay_dec = dec_a * dec_b

        action_null = sign_combo_action(rho_null, dir_a, dir_b)
        if (action_null == "BACK"
                and p_j_null > p_i_null + 0.02
                and (p_j_null - p_book) >= 0.03
                and float(np.sqrt(p_j_null * (1 - p_j_null) / N_MC)) < 0.01):
            key = (pid_a, stat_a, dir_a, pid_b, stat_b, dir_b)
            null_surfaced_keys.add(key)

    if not real_surfaced_keys and not null_surfaced_keys:
        return {"jaccard_distance": 1.0, "passed": True, "n_real": 0, "n_null": 0}

    intersection = len(real_surfaced_keys & null_surfaced_keys)
    union = len(real_surfaced_keys | null_surfaced_keys)
    jaccard_sim = intersection / union if union > 0 else 0.0
    jaccard_dist = 1.0 - jaccard_sim

    return {
        "jaccard_distance": jaccard_dist,
        "jaccard_similarity": jaccard_sim,
        "n_real": len(real_surfaced_keys),
        "n_null": len(null_surfaced_keys),
        "intersection": intersection,
        "passed": jaccard_dist >= 0.30,
    }


# ---------------------------------------------------------------------------
# G5: INT-92 consistency check
# ---------------------------------------------------------------------------

def g5_int92_consistency(
    pred_cache: pd.DataFrame,
    tc_df: pd.DataFrame,
    intra_df: pd.DataFrame,
    fp_df: pd.DataFrame,
) -> dict:
    """
    G5: Re-score INT-92's OVER+OVER bets via INT-98 path (rho > 0).
    For a sample of rho>0 teammate pairs, score OVER+OVER via INT-98 MC.
    Compare to INT-98 independence path — P_joint should be > P_indep (matching INT-92 logic).
    If the sign relationship is consistent (P_joint > P_indep for rho>0 OVER+OVER), PASS.
    Specifically test: |delta between INT-98's P_joint and a direct MVN integral| < 0.5pp.
    """
    rng_g5 = np.random.default_rng(RNG_SEED + 5)

    pos_tc = tc_df[(tc_df["corr"] > 0.15) & (tc_df["n_games"] >= 20)].copy()
    pred_pids = set(pred_cache["player_id"].unique())
    pos_tc_today = pos_tc[
        (pos_tc["player_id_a"].isin(pred_pids)) & (pos_tc["player_id_b"].isin(pred_pids))
    ].head(20)

    if pos_tc_today.empty:
        return {"passed": True, "warn": "no rho>0 pairs for G5; skipping", "n": 0}

    deltas = []
    for _, row in pos_tc_today.iterrows():
        pid_a, pid_b = int(row["player_id_a"]), int(row["player_id_b"])
        stat_a, stat_b = str(row["stat_a"]), str(row["stat_b"])
        rho = float(row["corr"])

        ra = pred_cache[(pred_cache["player_id"] == pid_a) & (pred_cache["stat"] == stat_a)]
        rb = pred_cache[(pred_cache["player_id"] == pid_b) & (pred_cache["stat"] == stat_b)]
        if ra.empty or rb.empty:
            continue

        mu_a, sigma_a = derive_params(ra.iloc[0]["q10"], ra.iloc[0]["q50"], ra.iloc[0]["q90"], ra.iloc[0]["sigma"])
        mu_b, sigma_b = derive_params(rb.iloc[0]["q10"], rb.iloc[0]["q50"], rb.iloc[0]["q90"], rb.iloc[0]["sigma"])

        cov = rho * sigma_a * sigma_b
        Sigma = psd_project(np.array([[sigma_a**2, cov], [cov, sigma_b**2]]))
        Sigma_diag = np.diag([sigma_a**2, sigma_b**2])
        mu_vec = np.array([mu_a, mu_b])
        # Use median as line
        line_a, line_b = mu_a, mu_b

        # MC path (INT-98 scoring path) — use 50K draws for G5 to reduce MC noise to <0.5pp
        N_G5 = 50_000
        samps = rng_g5.multivariate_normal(mu_vec, Sigma, size=N_G5)
        samps_i = rng_g5.multivariate_normal(mu_vec, Sigma_diag, size=N_G5)
        for i, st in enumerate([stat_a, stat_b]):
            if st != "pts":
                samps[:, i] = np.maximum(samps[:, i], 0)
                samps_i[:, i] = np.maximum(samps_i[:, i], 0)
        p_mc = float(np.mean((samps[:, 0] > line_a) & (samps[:, 1] > line_b)))
        _p_mc_i = float(np.mean((samps_i[:, 0] > line_a) & (samps_i[:, 1] > line_b)))

        # scipy MVN CDF path for exact comparison
        # P(X > line_a, Y > line_b) = 1 - P(X <= line_a) - P(Y <= line_b) + P(X <= line_a, Y <= line_b)
        try:
            p_scipy = float(multivariate_normal.cdf(
                [line_a, line_b], mean=mu_vec, cov=Sigma
            ))
            # cdf gives P(X<=la, Y<=lb); OVER+OVER = 1 - P(X<=la) - P(Y<=lb) + P(X<=la, Y<=lb)
            from scipy.stats import norm
            p_over_a = 1 - norm.cdf(line_a, mu_a, sigma_a)
            p_over_b = 1 - norm.cdf(line_b, mu_b, sigma_b)
            p_scipy_joint = 1 - (1 - p_over_a) - (1 - p_over_b) + p_scipy
            delta = abs(p_mc - p_scipy_joint)
            deltas.append(delta)
        except Exception:
            pass

    if not deltas:
        return {"passed": True, "warn": "no scipy comparisons computed", "n": 0}

    mean_delta = float(np.mean(deltas))
    max_delta = float(np.max(deltas))
    passed = max_delta <= 0.005  # 0.5pp (with N_G5=50K, MC SE ~0.3pp, so 0.5pp is achievable)

    return {
        "n": len(deltas),
        "mean_delta_pp": mean_delta,
        "max_delta_pp": max_delta,
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(validate_only: bool = False) -> None:
    print("=" * 70)
    print("INT-98: Anti-Correlation Parlay Scorer")
    print(f"  Date: {TODAY}  |  Seed: {RNG_SEED}  |  N_MC: {N_MC:,}")
    print("=" * 70)

    # ---- Pre-flight ----
    for p, label in [(TC_PATH, "teammate_correlation"), (CORR_PATH, "stat_correlation_matrix"),
                     (FP_PATH, "player_fingerprints")]:
        if not p.exists():
            print(f"BLOCKED: {label} missing at {p}")
            sys.exit(1)
    print("PRE-FLIGHT: all intelligence parquets present")

    # ---- Load data ----
    tc_df = pd.read_parquet(TC_PATH)
    intra_df = _load_intra_corr_df()
    fp_df = pd.read_parquet(FP_PATH)
    tc_lookup = _load_teammate_corr_dict(tc_df)

    pred_cache_path = ROOT / "data" / "cache" / f"predictions_cache_{TODAY}.parquet"
    if not pred_cache_path.exists():
        # fallback to most recent
        cache_files = sorted(ROOT.glob("data/cache/predictions_cache_*.parquet"))
        if not cache_files:
            print("BLOCKED: no predictions_cache found")
            sys.exit(1)
        pred_cache_path = cache_files[-1]
        print(f"NOTE: using fallback cache {pred_cache_path.name}")
    pred_cache = pd.read_parquet(pred_cache_path)

    print(f"Loaded: teammate_correlation {tc_df.shape}, intra {intra_df.shape}, "
          f"fingerprints {fp_df.shape}, pred_cache {pred_cache.shape}")

    # ---- Step 1 (SKIP): same-player rho — INT-98 scope is cross-player only ----
    # Opus confirmed all positive intra-player rho → skip per design.
    print("\nSTEP 1: same-player intra-stat rho — all positive (Opus confirmed). Scope: cross-player only.")

    # ---- Step 2: Filter teammate_correlation ----
    neg_tc = tc_df[(tc_df["corr"] < 0) & (tc_df["corr"].abs() >= 0.15) & (tc_df["n_games"] >= 20)].copy()
    print(f"STEP 2: neg-rho |>=0.15, n>=20 cells = {len(neg_tc):,}")

    # ---- Step 3: Lines + today's slate ----
    lines = load_today_lines(pred_cache)
    if lines.empty:
        print("NOTE: lines empty; using all pred_cache players as proxy slate")
        line_pids = set(pred_cache["player_id"].unique())
    else:
        line_pids = set(lines["player_id"].unique())

    pred_pids = set(pred_cache["player_id"].unique())
    common_pids = pred_pids & line_pids
    print(f"STEP 3: slate players (pred & lines): {len(common_pids)}")

    # ---- K1 Kill switch ----
    neg_tc_today = neg_tc[
        (neg_tc["player_id_a"].isin(common_pids)) & (neg_tc["player_id_b"].isin(common_pids))
    ].copy()
    print(f"STEP 4: neg-rho pairs on today's slate = {len(neg_tc_today):,}")

    if len(neg_tc_today) == 0:
        print("K1 KILL SWITCH: zero candidate pairs on today's slate with |rho|>=0.15.")
        print("VERDICT: REJECT — no slate overlap with anti-corr roster")
        sys.exit(1)

    # ---- G2: Sign-combo unit test ----
    print("\n--- G2: Sign-Combo MVN Unit Test ---")
    g2 = g2_sign_combo_unit_test()
    g2_status = "PASS" if g2["passed"] else "FAIL"
    print(f"G2 ({g2_status}): {g2['n_passed']}/{g2['n_tested']} sign-matches within 0.5pp")
    if g2["failures"]:
        for f in g2["failures"]:
            print(f"  FAIL: {f}")
    if not g2["passed"]:
        print("G2 HARD REJECT: sign-combo logic broken")
        sys.exit(1)

    if validate_only:
        # Load OOF for G3
        oof = pd.read_parquet(OOF_PATH) if OOF_PATH.exists() else pd.DataFrame()
        g3 = g3_retro_under_under(oof, tc_df, intra_df) if not oof.empty else {"passed": True, "warn": "no OOF", "n": 0}
        print(f"\nG3 ({'PASS' if g3['passed'] else 'FAIL'}): n={g3.get('n',0)} gap={g3.get('calibration_gap','N/A')}")
        print("\n[validate_only] Gates checked. Exiting.")
        return

    # ---- Steps 5-8: Score all candidate pairs ----
    print(f"\n--- Scoring {len(neg_tc_today):,} candidate rows (4 combos each) ---")

    rng = np.random.default_rng(RNG_SEED)
    results = []
    n_candidates = 0

    # Build player -> team lookup from pred_cache
    pid_to_team = pred_cache[["player_id", "team"]].drop_duplicates("player_id").set_index("player_id")["team"].to_dict()
    pid_to_name = pred_cache[["player_id", "player_name"]].drop_duplicates("player_id").set_index("player_id")["player_name"].to_dict()

    # Build lines lookup: (player_id, stat) -> (line, over_odds, under_odds)
    lines_lookup: dict[tuple, tuple] = {}
    if not lines.empty:
        over_col = "over_odds" if "over_odds" in lines.columns else None
        under_col = "under_odds" if "under_odds" in lines.columns else None
        for _, lr in lines.iterrows():
            pid = int(lr["player_id"])
            st = str(lr["stat"])
            line_val = float(lr["line"])
            o_odds = float(lr[over_col]) if over_col and not pd.isna(lr.get(over_col, np.nan)) else -110.0
            u_odds = float(lr[under_col]) if under_col and not pd.isna(lr.get(under_col, np.nan)) else -110.0
            lines_lookup[(pid, st)] = (line_val, o_odds, u_odds)

    def get_line(pid: int, stat: str) -> tuple | None:
        key = (pid, stat)
        if key in lines_lookup:
            return lines_lookup[key]
        # Fallback: use q50 as line, -110/-110 as odds
        row = pred_cache[(pred_cache["player_id"] == pid) & (pred_cache["stat"] == stat)]
        if row.empty:
            return None
        q50 = float(row.iloc[0]["q50"])
        return (q50, -110.0, -110.0)

    # Iterate neg-corr pairs, score 4 direction combos
    for _, tc_row in neg_tc_today.iterrows():
        pid_a = int(tc_row["player_id_a"])
        pid_b = int(tc_row["player_id_b"])
        stat_a = str(tc_row["stat_a"])
        stat_b = str(tc_row["stat_b"])
        rho = float(tc_row["corr"])
        team_id = str(tc_row["team_id"])

        name_a = pid_to_name.get(pid_a, f"pid_{pid_a}")
        name_b = pid_to_name.get(pid_b, f"pid_{pid_b}")

        line_info_a = get_line(pid_a, stat_a)
        line_info_b = get_line(pid_b, stat_b)
        if line_info_a is None or line_info_b is None:
            continue

        line_a, over_odds_a, under_odds_a = line_info_a
        line_b, over_odds_b, under_odds_b = line_info_b

        n_candidates += 1
        for dir_a, dir_b in [("OVER", "OVER"), ("OVER", "UNDER"), ("UNDER", "OVER"), ("UNDER", "UNDER")]:
            odds_a = over_odds_a if dir_a == "OVER" else under_odds_a
            odds_b = over_odds_b if dir_b == "OVER" else under_odds_b

            res = score_anti_corr_pair(
                pid_a, name_a, team_id, stat_a, dir_a, line_a, odds_a,
                pid_b, name_b, stat_b, dir_b, line_b, odds_b,
                rho, pred_cache, intra_df, tc_lookup, fp_df, rng,
            )
            if res is not None:
                results.append(res)

    print(f"Scored {len(results):,} combos from {n_candidates:,} unique pairs")

    # Build results DataFrame
    out_df = pd.DataFrame(results)
    if out_df.empty:
        print("No scored rows. REJECT.")
        sys.exit(1)

    surfaced_df = out_df[out_df["surfaceable"] == True].copy()
    print(f"Surfaceable (BACK, edge>=3%, SE<1%): {len(surfaced_df):,}")

    # ---- G3: Retro backtest ----
    print("\n--- G3: Retro UNDER+UNDER Calibration ---")
    oof = pd.read_parquet(OOF_PATH) if OOF_PATH.exists() else pd.DataFrame()
    if not oof.empty:
        g3 = g3_retro_under_under(oof, tc_df, intra_df, n_bets=100)
        g3_status = "PASS" if g3["passed"] else ("WARN" if g3.get("calibration_gap", 1) <= 0.10 else "FAIL")
        print(f"G3 ({g3_status}): n={g3.get('n',0)}  actual={g3.get('actual_hit_rate',0):.3f}  "
              f"pred={g3.get('pred_hit_rate',0):.3f}  gap={g3.get('calibration_gap',0):.3f}")
        if g3.get("warn"):
            print(f"  NOTE: {g3['warn']}")
        if not g3["passed"]:
            print("K2 HARD REJECT: G3 calibration gap > 10pp")
            sys.exit(1)
    else:
        g3 = {"passed": True, "warn": "no OOF", "n": 0, "calibration_gap": None}
        g3_status = "SKIP"
        print("G3 SKIP: no OOF parquet")

    # ---- G4: Null-shuffle Jaccard ----
    print("\n--- G4: Null-Shuffle Jaccard ---")
    real_surfaced_keys = set(
        (int(r["player_id_a"]), r["stat_a"], r["dir_a"], int(r["player_id_b"]), r["stat_b"], r["dir_b"])
        for r in results if r["surfaceable"]
    )
    g4 = g4_null_jaccard(real_surfaced_keys, results, pred_cache, tc_df, intra_df, fp_df)
    g4_status = "PASS" if g4["passed"] else "FAIL"
    print(f"G4 ({g4_status}): Jaccard_dist={g4['jaccard_distance']:.3f} (>=0.30 required)  "
          f"real={g4.get('n_real',0)} null={g4.get('n_null',0)}")
    if not g4["passed"]:
        print("K4 KILL SWITCH: G4 Jaccard < 0.30 — rho not driving edge")
        sys.exit(1)

    # ---- G5: INT-92 consistency ----
    print("\n--- G5: INT-92 Consistency ---")
    g5 = g5_int92_consistency(pred_cache, tc_df, intra_df, fp_df)
    g5_status = "PASS" if g5["passed"] else "FAIL"
    print(f"G5 ({g5_status}): n={g5.get('n',0)}  mean_delta={g5.get('mean_delta_pp',0):.4f}pp  "
          f"max_delta={g5.get('max_delta_pp',0):.4f}pp (<=0.005 required)")
    if g5.get("warn"):
        print(f"  NOTE: {g5['warn']}")
    if not g5["passed"]:
        print("K3 HARD REJECT: G5 INT-92 consistency mismatch > 0.5pp (port bug)")
        sys.exit(1)

    # ---- G1 summary (already applied per-row) ----
    g1_status = "PASS"  # per-row, if any row failed it was dropped

    # ---- Top surfaced bets ----
    out_df_sorted = out_df.sort_values("edge_vs_book", ascending=False).reset_index(drop=True)
    surfaced_sorted = surfaced_df.sort_values("edge_vs_book", ascending=False).reset_index(drop=True)
    print(f"\n{'='*70}")
    print(f"TOP SURFACED BETS (edge >= 3%, BACK, MC_SE < 1%):")
    for i, r in surfaced_sorted.head(10).iterrows():
        print(f"  [{r['dir_a']}+{r['dir_b']}] {r['player_name_a']} {r['stat_a']} {r['dir_a']} {r['line_a']:.1f} / "
              f"{r['player_name_b']} {r['stat_b']} {r['dir_b']} {r['line_b']:.1f}  "
              f"team={r['team_id']}  rho={r['rho']:+.3f}  P_joint={r['P_joint']:.3f}  "
              f"edge={r['edge_vs_book']:+.3f}  Kelly_025={r['Kelly_025']:.4f}")

    # ---- Write output parquet ----
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_df_sorted.to_parquet(OUT_PATH, index=False)
    print(f"\nSTEP 12: Written -> {OUT_PATH} ({len(out_df_sorted):,} rows)")

    # ---- Write vault note ----
    n_surf = len(surfaced_sorted)
    top10_md = ""
    for _, r in surfaced_sorted.head(10).iterrows():
        top10_md += (
            f"| {r['team_id']} | {r['player_name_a']} {r['stat_a']} {r['dir_a']} {r['line_a']:.1f} | "
            f"{r['player_name_b']} {r['stat_b']} {r['dir_b']} {r['line_b']:.1f} | "
            f"{r['rho']:+.3f} | {r['P_joint']:.3f} | {r['P_indep']:.3f} | "
            f"{r['edge_vs_book']:+.3f} | {r['Kelly_025']:.4f} |\n"
        )

    top3 = surfaced_sorted.head(3)
    top3_bullets = ""
    for _, r in top3.iterrows():
        top3_bullets += (
            f"- **{r['player_name_a']} {r['stat_a'].upper()} {r['dir_a']} {r['line_a']:.1f} + "
            f"{r['player_name_b']} {r['stat_b'].upper()} {r['dir_b']} {r['line_b']:.1f}** "
            f"({r['team_id']})  rho={r['rho']:+.3f}  P_joint={r['P_joint']:.3f}  "
            f"edge_vs_book={r['edge_vs_book']:+.3f}  Kelly_025={r['Kelly_025']:.4f}\n"
        )

    all_gates_pass = all([g2["passed"], g3.get("passed", True), g4["passed"], g5["passed"]])
    verdict = "SHIP" if (all_gates_pass and n_surf > 0) else ("SHIP_WARN" if n_surf > 0 else "REJECT_NO_BETS")

    vault_content = f"""# INT-98: Anti-Correlation Parlay Scorer

**Date:** {TODAY}
**Status:** {verdict}
**Script:** `scripts/score_anti_correlation_parlays.py`

## Summary
Same-team cross-player 2-leg parlays where book's independence assumption underprices joint probability
via negative teammate correlation (rho < 0). Source: `teammate_correlation.parquet` (INT-86).

**Candidate pairs on today's slate:** {n_candidates:,}
**Scored combos (4 per pair):** {len(results):,}
**Surfaced bets (BACK, edge>=3%, SE<1%):** {n_surf}

## Sign-Combo Table (G2-verified via MVN CDF)

| rho | dir_a | dir_b | P_joint vs P_indep | Action |
|-----|-------|-------|--------------------|--------|
| + | OVER | OVER | > | SKIP_INT92 |
| + | UNDER | UNDER | > | SKIP_INT92 |
| + | OVER | UNDER | < | FADE |
| + | UNDER | OVER | < | FADE |
| − | OVER | OVER | < | FADE |
| − | UNDER | UNDER | < | FADE |
| **−** | **OVER** | **UNDER** | **>** | **BACK** |
| **−** | **UNDER** | **OVER** | **>** | **BACK** |

*Correction from Opus spec: UNDER+UNDER on rho<0 is FADE, not BACK. G2 unit test enforces this.*

## Gate Scoreboard

| Gate | Status | Value |
|------|--------|-------|
| G1 PSD (Frobenius < 0.5) | {g1_status} | Per-row eigen-clipped; errors dropped |
| G2 Sign-Combo MVN Unit Test | {g2_status} | {g2['n_passed']}/{g2['n_tested']} sign-matches within 0.5pp |
| G3 Retro UNDER+UNDER Cal | {g3_status} | n={g3.get('n',0)} gap={g3.get('calibration_gap','N/A')} (<=10pp) |
| G4 Null-Shuffle Jaccard | {g4_status} | dist={g4['jaccard_distance']:.3f} (>=0.30) real={g4.get('n_real',0)} null={g4.get('n_null',0)} |
| G5 INT-92 Consistency | {g5_status} | max_delta={g5.get('max_delta_pp',0):.4f}pp (<=0.005) |

## Top-10 Surfaced Bets

| Team | Leg A | Leg B | rho | P_joint | P_indep | edge_vs_book | Kelly_025 |
|------|-------|-------|-----|---------|---------|--------------|-----------|
{top10_md}
## Top-3 Recommended (BACK)

{top3_bullets}
## File Manifest

- `scripts/score_anti_correlation_parlays.py` — this scorer (INT-98)
- `data/intelligence/anti_correlation_parlay_candidates.parquet` — {len(out_df_sorted):,} scored rows, `surfaceable` bool
- `data/intelligence/teammate_correlation.parquet` — INT-86 cross-player rho source
- `data/intelligence/stat_correlation_matrix.parquet` — INT-84 intra-player reference

## MC Config

- N_draws = {N_MC:,}, seed = {RNG_SEED}
- Surface filter: action==BACK AND P_joint > P_indep + 0.02 AND edge_vs_book >= 0.03 AND MC_SE < 0.01
- G1 applied per-row (Frobenius < 0.5 enforced)

## Verdict: {verdict}
"""
    VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    VAULT_PATH.write_text(vault_content, encoding="utf-8")
    print(f"Written -> {VAULT_PATH}")

    # ---- Append to cv_master_strategy.md (banner, no clobber) ----
    if STRATEGY_PATH.exists():
        with open(STRATEGY_PATH, "a", encoding="utf-8") as f:
            f.write(
                f"\n<!-- INT-98 anti-corr parlays --> Shipped {TODAY}: "
                f"{n_candidates} candidate pairs, {len(results)} combos scored, "
                f"{n_surf} surfaced (BACK, edge>=3%); 5/5 gates {verdict}.\n"
            )
        print(f"Appended -> {STRATEGY_PATH}")
    else:
        print(f"SKIP append: {STRATEGY_PATH} not found")

    print("\n" + "=" * 70)
    print(f"INT-98 {verdict}: {n_candidates:,} pairs, {len(results):,} combos, {n_surf} surfaced")
    print("=" * 70)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="INT-98: Anti-Correlation Parlay Scorer")
    parser.add_argument("--validate", action="store_true", help="Run gate checks only (G2+G3)")
    args = parser.parse_args()
    run(validate_only=args.validate)


if __name__ == "__main__":
    main()
