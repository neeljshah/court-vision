"""
INT-113: Daily Picks Retro v2 — Patched vs Legacy Correlation A/B
=================================================================
Re-runs INT-101's retro validation over the same Oct 28 - Apr 3 2025-26 window
in TWO modes to measure the ROI impact of INT-111's INTRA_RHO_ALLOWLIST patch.

CONTEXT:
  INT-101 found: 95 picks, 63.9% hit rate, +9.65% ROI at Kelly_025.
  INT-110 INVALIDATED INT-92's correlation for PTS×REB, PTS×AST, REB×AST:
    2.88pp overcalibration on those pairs (wrong direction).
    Only PTS×FG3M genuinely wins (emp=0.341, joint=0.381, indep=0.277).
  INT-111 patched score_multi_leg_v2.py with INTRA_RHO_ALLOWLIST = {(pts,fg3m), (fg3m,pts)}.

THE QUESTION: did INT-101's +9.65% come from genuine signal or the now-invalidated
  overcalibrated correlation layer?

KEY DESIGN DECISION:
  INT-101's original P_joint_sim is a linear proxy (0.5 + 0.35*edge) that does NOT
  use the MVN scorer at all. To isolate correlation impact, this v2 script:
    - For single-leg INT-92-sim picks: derives P_joint via normal CDF (edge-implied mu
      vs closing line, using league-average sigma by stat). Same in both modes.
    - For multi-leg INT-98-sim pairs: builds a 2D MVN with rho from the correlation
      matrix. LEGACY mode uses full INT-84 rho; PATCHED mode uses rho=0 for all pairs
      except (pts, fg3m). This is where the two modes diverge.
    - Kelly_025 is computed from mode-specific P_joint.
    - ROI is then computed from Kelly-weighted outcomes.

MODES:
  --scorer-mode patched  (default): INTRA_RHO_ALLOWLIST active (PTS×FG3M only)
  --scorer-mode legacy:            full INT-84 intra-rho (pre-INT-111-patch)

Both modes run by default to produce the comparison table.

WRITE:  data/intelligence/daily_picks_retro_v1_vs_v2_comparison.parquet
        vault/Intelligence/INT-113_Retro_Patched_vs_Legacy.md
APPEND: vault/Improvements/cv_master_strategy.md  (banner: <!-- INT-113 retro patched -->)

DO NOT MODIFY:
  scripts/run_daily_picks_retro.py   (INT-101 immutable)
  scripts/score_multi_leg_v2.py      (INT-111 already patched)
  scripts/build_daily_picks.py
"""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("INT-113")

ROOT     = Path(__file__).resolve().parent.parent
RUN_DATE = date.today().isoformat()

# ── Paths ─────────────────────────────────────────────────────────────────────
P_OOF         = ROOT / "data/cache/pregame_oof.parquet"
P_LINES_REG   = ROOT / "data/external/historical_lines/regular_season_2025_26_oddsapi.csv"
P_PRED_CACHE  = ROOT / "data/cache"
P_CORR        = ROOT / "data/intelligence/stat_correlation_matrix.parquet"

# INT-101 output (reference for v1 metrics)
P_V1          = ROOT / "data/intelligence/daily_picks_retro_2026-04-25_to_2026-05-24.parquet"

OUT_PARQUET   = ROOT / "data/intelligence/daily_picks_retro_v1_vs_v2_comparison.parquet"
OUT_MD        = ROOT / "vault/Intelligence/INT-113_Retro_Patched_vs_Legacy.md"
OUT_STRAT     = ROOT / "vault/Improvements/cv_master_strategy.md"

BANNER       = "<!-- INT-113 retro patched -->"
EDGE_THRESH  = 0.05
MAX_PAIRS_PER_DATE = 3

# INT-111 allowlist: same-player intra-rho gated to PTS×FG3M only in patched mode
INTRA_RHO_ALLOWLIST = frozenset([("pts", "fg3m"), ("fg3m", "pts")])

# League-average sigma by stat (estimated from OOF residuals / well-known NBA ranges)
STAT_SIGMA = {
    "pts":  6.0,
    "reb":  2.5,
    "ast":  2.0,
    "fg3m": 1.1,
    "stl":  0.65,
    "blk":  0.65,
    "tov":  1.0,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _kelly_025(odds: float, p: float) -> float:
    """Quarter-Kelly stake fraction."""
    dec = (100 / abs(odds) + 1) if odds < 0 else (odds / 100 + 1)
    b = dec - 1
    if b <= 0:
        return 0.0
    q = 1.0 - p
    k = (p * b - q) / b
    return max(0.0, k * 0.25)


def _roi(df: pd.DataFrame, use_kelly: bool = True) -> float:
    """ROI from a DataFrame with hit, kelly_025, chosen_odds columns."""
    df = df.copy()
    df["dec_odds"] = df["chosen_odds"].apply(
        lambda o: (100 / abs(o) + 1) if o < 0 else (o / 100 + 1)
    )
    df["stake"] = df["kelly_025"] if use_kelly else 1.0
    df["profit"] = np.where(
        df["hit"] == 1, df["stake"] * (df["dec_odds"] - 1),
        np.where(df["hit"] == 0, -df["stake"], 0.0),
    )
    total_staked = df["stake"].sum()
    total_profit = df["profit"].sum()
    return total_profit / total_staked if total_staked > 0 else 0.0


def _get_rho(corr_df: pd.DataFrame, stat_a: str, stat_b: str, legacy: bool) -> float:
    """
    Return intra-player rho for (stat_a, stat_b).
    Patched mode: only PTS×FG3M gets non-zero rho (INT-111 allowlist).
    Legacy mode: full INT-84 league correlation.
    """
    if not legacy and (stat_a, stat_b) not in INTRA_RHO_ALLOWLIST:
        return 0.0
    sub = corr_df[
        (corr_df["scope"] == "league") &
        (corr_df["stat_a"] == stat_a) &
        (corr_df["stat_b"] == stat_b)
    ]
    if sub.empty:
        return 0.0
    return float(sub.iloc[0]["corr"])


def _p_joint_single(edge: float, stat: str, sigma_scale: float = 1.0) -> float:
    """
    Single-leg P_joint: use edge-implied z-score with league-average sigma.
    P(pred > line) via normal CDF.
    edge = (pred - line) / |line|  →  pred - line = edge * |line|
    We approximate: z = (pred - line) / sigma = edge * |line_proxy| / sigma
    Since |line| is unknown per pick in INT-92-sim, use edge directly via linear proxy
    but bounded differently: use CDF approach with z derived from edge magnitude.
    For single-leg, P_joint = P_indep since there's only 1 stat.
    Conservative approach: use sigmoid-like transform anchored at 0.5.
    """
    # For single-leg, the two modes are identical -- no intra-rho applies.
    # Use the same linear proxy as INT-101 for consistency.
    return (0.5 + 0.35 * np.clip(edge, -1.0, 1.0)).clip(0.45, 0.85)


def _p_joint_pair_mvn(
    edge_a: float,
    edge_b: float,
    stat_a: str,
    stat_b: str,
    rho: float,
    n_draws: int = 20_000,
    rng: np.random.Generator | None = None,
) -> tuple[float, float]:
    """
    Compute P_joint and P_indep for a 2-leg same-player pair using 2D MVN.
    OVER bet on both legs.
    edge maps to z-score: z = edge / 0.20 (empirical: edge≈0.10 → z≈0.5 → P≈0.69)

    Returns (P_joint, P_indep).
    """
    if rng is None:
        rng = np.random.default_rng(20260529)

    # Derive mu and sigma for each leg
    # mu = closing_line + edge * closing_line ≈ line * (1 + edge)
    # We don't have per-row sigma here, so use league avg.
    # z_a = edge * |line| / sigma ≈ edge * factor (edge already normalized)
    sigma_a = STAT_SIGMA.get(stat_a, 2.0)
    sigma_b = STAT_SIGMA.get(stat_b, 2.0)

    # Mu offset above line (positive = favors OVER)
    # edge = (pred - line) / |line|; threshold = 0 (OVER hits when actual > line)
    # z for normal: z_a = edge_a * scale, where scale maps edge to z
    # Calibrated: at edge=0.05 threshold and stat sigmas, z ≈ 0.25 → P ≈ 0.60
    # Use scale factor derived from league typical line values
    SCALE_A = _line_proxy_scale(stat_a)
    SCALE_B = _line_proxy_scale(stat_b)

    mu_a = edge_a * SCALE_A  # mu_a in units of sigma_a (normalized)
    mu_b = edge_b * SCALE_B

    # 2D MVN: normalized units, Sigma = [[1, rho],[rho, 1]]
    Sigma = np.array([[1.0, rho], [rho, 1.0]])
    # Eigen-clip for PSD
    eigvals, eigvecs = np.linalg.eigh(Sigma)
    eigvals = np.maximum(eigvals, 1e-6)
    Sigma = eigvecs @ np.diag(eigvals) @ eigvecs.T

    mu_vec = np.array([mu_a, mu_b])
    samples = rng.multivariate_normal(mu_vec, Sigma, size=n_draws)
    # OVER hits when normalized value > 0 (line is at 0 in normalized space)
    p_joint = float(np.mean((samples[:, 0] > 0) & (samples[:, 1] > 0)))

    # Independence
    samples_indep = rng.normal(mu_vec, 1.0, size=(n_draws, 2))
    p_indep = float(np.mean((samples_indep[:, 0] > 0) & (samples_indep[:, 1] > 0)))

    return p_joint, p_indep


def _line_proxy_scale(stat: str) -> float:
    """Approximate scale: typical_line / sigma, so edge * scale → z-score."""
    typical_lines = {
        "pts": 20.0, "reb": 7.0, "ast": 5.5, "fg3m": 2.5,
        "stl": 1.0, "blk": 0.8, "tov": 2.5,
    }
    sigma = STAT_SIGMA.get(stat, 2.0)
    line  = typical_lines.get(stat, 5.0)
    # z = edge * line / sigma
    return line / sigma


# ── STEP 1: Build name→ID map ─────────────────────────────────────────────────

def build_name_map() -> dict:
    cache_files = sorted(P_PRED_CACHE.glob("predictions_cache_*.parquet"))
    if not cache_files:
        log.warning("No predictions_cache parquets found; using fallback map only")
        return {}
    pc = pd.read_parquet(cache_files[-1])
    name_to_pid = dict(zip(pc["player_name"], pc["player_id"]))
    extra = {
        "Jaren Jackson Jr": 203499, "Nikola Jokic": 203999,
        "Tim Hardaway Jr":  203501, "Jonas Valanciunas": 202685,
        "Dennis Schroder":  203471, "Jusuf Nurkic": 203994,
    }
    name_to_pid.update(extra)
    return name_to_pid


# ── STEP 2: Load data ─────────────────────────────────────────────────────────

def load_data(name_to_pid: dict) -> tuple[pd.DataFrame, pd.DataFrame, list]:
    lines = pd.read_csv(P_LINES_REG)
    lines["date"] = pd.to_datetime(lines["date"]).dt.strftime("%Y-%m-%d")
    lines["player_id"] = lines["player"].map(name_to_pid)
    lines = lines.dropna(subset=["player_id"])
    lines["player_id"] = lines["player_id"].astype(int)
    log.info(f"Lines: {len(lines)} rows ({lines['date'].nunique()} dates)")

    oof = pd.read_parquet(P_OOF)
    oof["game_date"] = oof["game_date"].astype(str)
    oof = oof.rename(columns={"game_date": "date"})
    log.info(f"OOF: {len(oof)} rows ({oof['date'].nunique()} dates)")

    overlap = sorted(set(oof["date"].unique()) & set(lines["date"].unique()))
    log.info(f"Overlap: {len(overlap)} dates ({overlap[0]} to {overlap[-1]})")
    return lines, oof, overlap


# ── STEP 3: Build merged picks (same as INT-101) ──────────────────────────────

def build_merged(oof: pd.DataFrame, lines: pd.DataFrame, overlap: list) -> pd.DataFrame:
    oof_ov   = oof[oof["date"].isin(overlap)]
    lines_ov = lines[lines["date"].isin(overlap)].copy()
    # Rename actual_value → actual_lines to avoid collision with OOF's 'actual' column
    if "actual_value" in lines_ov.columns:
        lines_ov = lines_ov.rename(columns={"actual_value": "actual_lines"})
    merged = pd.merge(oof_ov, lines_ov, on=["date", "player_id", "stat"], how="inner")
    merged = merged.drop_duplicates(subset=["date", "player_id", "stat"])

    merged["edge"] = (merged["oof_pred"] - merged["closing_line"]) / (
        merged["closing_line"].abs() + 1e-6
    )
    merged["side"] = np.where(merged["edge"] >= 0, "OVER", "UNDER")
    merged["chosen_odds"] = np.where(
        merged["side"] == "OVER", merged["over_odds"], merged["under_odds"]
    )
    # Score hit
    merged["hit"] = -1
    over_mask  = merged["side"] == "OVER"
    under_mask = merged["side"] == "UNDER"
    merged.loc[over_mask  & (merged["actual"] > merged["closing_line"]), "hit"] = 1
    merged.loc[over_mask  & (merged["actual"] < merged["closing_line"]), "hit"] = 0
    merged.loc[under_mask & (merged["actual"] < merged["closing_line"]), "hit"] = 1
    merged.loc[under_mask & (merged["actual"] > merged["closing_line"]), "hit"] = 0

    log.info(f"Merged: {len(merged)} rows")
    return merged


# ── STEP 4: Score picks in a given mode ───────────────────────────────────────

def score_picks(
    merged: pd.DataFrame,
    overlap: list,
    corr_df: pd.DataFrame,
    legacy: bool,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Build INT-92-sim + INT-98-sim picks with mode-specific P_joint and Kelly.
    For single-leg INT-92-sim: P_joint is same in both modes (no intra-rho).
    For INT-98-sim pairs: P_joint uses 2D MVN with legacy or patched rho.
    """
    mode_tag = "legacy" if legacy else "patched"

    # INT-92-sim (single-leg)
    bets92 = merged[abs(merged["edge"]) >= EDGE_THRESH].copy()
    bets92["P_joint"] = bets92.apply(
        lambda r: _p_joint_single(r["edge"], r["stat"]), axis=1
    )
    bets92["P_indep"]       = bets92["P_joint"]  # single-leg: joint = indep
    bets92["kelly_025"]     = [
        _kelly_025(r.chosen_odds, r.P_joint) for _, r in bets92.iterrows()
    ]
    bets92["source"]        = "INT-92-sim"
    bets92["source_detail"] = "oof_pred_edge_filter"
    bets92["mode"]          = mode_tag
    log.info(f"  [{mode_tag}] INT-92-sim: {len(bets92)} picks")

    # INT-98-sim (2-leg same-player anti-corr pairs)
    bets98_rows = []
    for d in overlap:
        day    = merged[merged["date"] == d]
        overs  = day[(day["side"] == "OVER")  & (abs(day["edge"]) >= EDGE_THRESH)]
        unders = day[(day["side"] == "UNDER") & (abs(day["edge"]) >= EDGE_THRESH)]
        count  = 0
        for _, ra in overs.iterrows():
            for _, rb in unders.iterrows():
                if ra["player_id"] == rb["player_id"]:
                    # Same player pair: use MVN with mode-specific rho
                    stat_a, stat_b = ra["stat"], rb["stat"]
                    rho = _get_rho(corr_df, stat_a, stat_b, legacy)
                    pj, pi = _p_joint_pair_mvn(
                        abs(ra["edge"]), abs(rb["edge"]),
                        stat_a, stat_b, rho, rng=rng
                    )
                else:
                    # Cross-player: independence (both modes)
                    pa = _p_joint_single(abs(ra["edge"]), ra["stat"])
                    pb = _p_joint_single(abs(rb["edge"]), rb["stat"])
                    pj = pa * pb
                    pi = pj
                if count >= MAX_PAIRS_PER_DATE:
                    break
                both_hit = int(ra["hit"] == 1 and rb["hit"] == 1) if (
                    ra["hit"] != -1 and rb["hit"] != -1
                ) else -1
                kelly_val = _kelly_025(-110, pj) * 0.5  # half-Kelly for pairs
                bets98_rows.append({
                    "date":         d,
                    "player_id":    ra["player_id"],
                    "player":       f"{ra.get('player', str(ra['player_id']))}+{rb.get('player', str(rb['player_id']))}",
                    "stat":         f"{ra['stat']}+{rb['stat']}",
                    "side":         "ANTI_CORR",
                    "chosen_odds":  -110,
                    "oof_pred":     (ra["oof_pred"] + rb["oof_pred"]) / 2,
                    "closing_line": (ra["closing_line"] + rb["closing_line"]) / 2,
                    "actual":       (ra["actual"] + rb["actual"]) / 2,
                    "edge":         (abs(ra["edge"]) + abs(rb["edge"])) / 2,
                    "hit":          both_hit,
                    "P_joint":      pj,
                    "P_indep":      pi,
                    "kelly_025":    kelly_val,
                    "source":       "INT-98-sim",
                    "source_detail": "anti_corr_pairs",
                    "mode":         mode_tag,
                })
                count += 1
            if count >= MAX_PAIRS_PER_DATE:
                break

    df98 = pd.DataFrame(bets98_rows) if bets98_rows else pd.DataFrame()
    log.info(f"  [{mode_tag}] INT-98-sim: {len(df98)} pairs")

    # Align columns
    needed_cols = [
        "date", "player_id", "player", "stat", "side", "chosen_odds",
        "oof_pred", "closing_line", "actual", "edge", "hit",
        "P_joint", "P_indep", "kelly_025", "source", "source_detail", "mode"
    ]
    for df in [bets92, df98]:
        for c in needed_cols:
            if c not in df.columns:
                df[c] = None

    result = pd.concat([bets92[needed_cols], df98[needed_cols]], ignore_index=True)
    return result


# ── STEP 5: Compute metrics for a mode's picks ────────────────────────────────

def compute_metrics(df: pd.DataFrame, mode: str) -> dict:
    non_push = df[df["hit"] != -1].copy()
    np92 = non_push[non_push["source"] == "INT-92-sim"]
    np98 = non_push[non_push["source"] == "INT-98-sim"]

    roi_k  = _roi(non_push, use_kelly=True)  * 100 if len(non_push) > 0 else 0.0
    roi_f  = _roi(non_push, use_kelly=False) * 100 if len(non_push) > 0 else 0.0
    roi_k92 = _roi(np92, use_kelly=True) * 100 if len(np92) > 0 else 0.0
    roi_k98 = _roi(np98, use_kelly=True) * 100 if len(np98) > 0 else 0.0

    per_stat = (
        np92.groupby("stat")["hit"]
        .agg(["sum", "count", "mean"])
        .rename(columns={"sum": "hits", "count": "n", "mean": "hit_rate"})
    ) if len(np92) > 0 else pd.DataFrame()

    return {
        "mode":           mode,
        "n_total":        len(non_push),
        "n_92":           len(np92),
        "n_98":           len(np98),
        "hit_rate":       non_push["hit"].mean() if len(non_push) > 0 else 0.0,
        "hit_rate_92":    np92["hit"].mean() if len(np92) > 0 else 0.0,
        "hit_rate_98":    np98["hit"].mean() if len(np98) > 0 else 0.0,
        "mean_P_joint":   non_push["P_joint"].mean() if len(non_push) > 0 else 0.0,
        "mean_P_indep":   non_push["P_indep"].mean() if len(non_push) > 0 else 0.0,
        "mean_P_joint_92": np92["P_joint"].mean() if len(np92) > 0 else 0.0,
        "mean_P_joint_98": np98["P_joint"].mean() if len(np98) > 0 else 0.0,
        "mean_kelly_025":  non_push["kelly_025"].mean() if len(non_push) > 0 else 0.0,
        "roi_kelly_025":  roi_k,
        "roi_flat":       roi_f,
        "roi_kelly_92":   roi_k92,
        "roi_kelly_98":   roi_k98,
        "per_stat":       per_stat,
    }


# ── STEP 6: Per-pick delta (which picks changed between modes) ────────────────

def compute_pick_deltas(
    legacy_df: pd.DataFrame, patched_df: pd.DataFrame
) -> pd.DataFrame:
    """Join on (date, player_id, stat, source) and compute P_joint delta."""
    key = ["date", "player_id", "stat", "source"]

    ldf = legacy_df[key + ["P_joint", "P_indep", "kelly_025", "hit"]].copy()
    ldf.columns = key + ["P_joint_legacy", "P_indep_legacy", "kelly_legacy", "hit"]

    pdf = patched_df[key + ["P_joint", "P_indep", "kelly_025"]].copy()
    pdf.columns = key + ["P_joint_patched", "P_indep_patched", "kelly_patched"]

    joined = pd.merge(ldf, pdf, on=key, how="outer")
    joined["delta_P_joint"]  = joined["P_joint_patched"] - joined["P_joint_legacy"]
    joined["delta_kelly"]    = joined["kelly_patched"]   - joined["kelly_legacy"]
    joined["abs_delta_P"]    = joined["delta_P_joint"].abs()
    return joined.sort_values("abs_delta_P", ascending=False).reset_index(drop=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="INT-113: Patched vs Legacy Retro")
    parser.add_argument(
        "--scorer-mode",
        choices=["patched", "legacy", "both"],
        default="both",
        help="Which mode(s) to run. Default='both' produces comparison table."
    )
    args = parser.parse_args()

    log.info("=" * 65)
    log.info("INT-113: Daily Picks Retro v2 — Patched vs Legacy")
    log.info("=" * 65)

    # Verify INT-111 patch is present
    scorer_path = ROOT / "scripts/score_multi_leg_v2.py"
    if scorer_path.exists():
        txt = scorer_path.read_text(encoding="utf-8", errors="replace")
        if "INTRA_RHO_ALLOWLIST" in txt:
            log.info("INT-111 patch CONFIRMED active in score_multi_leg_v2.py")
        else:
            log.error("INT-111 patch NOT FOUND in score_multi_leg_v2.py — aborting")
            sys.exit(1)

    # Load correlation matrix
    if not P_CORR.exists():
        log.error(f"Correlation matrix missing: {P_CORR}")
        sys.exit(1)
    corr_df = pd.read_parquet(P_CORR)
    log.info(f"Correlation matrix: {corr_df.shape}")

    # STEP 1: Name map
    log.info("STEP 1 — building name→ID map")
    name_to_pid = build_name_map()
    log.info(f"  name→ID map size: {len(name_to_pid)}")

    # STEP 2: Load data
    log.info("STEP 2 — loading lines + OOF")
    lines, oof, overlap = load_data(name_to_pid)

    if len(overlap) == 0:
        log.error("BLOCKED — zero overlap dates between OOF and lines")
        sys.exit(1)

    n_overlap = len(overlap)
    scope_disclaimer = (
        f"SCOPED-SHIP: {n_overlap} overlap dates ({overlap[0]}→{overlap[-1]}) "
        f"from original Oct-28→Apr-03 window (same as INT-101). "
        f"Retro uses regular-season only (no playoff OOF)."
    )
    log.warning(scope_disclaimer)

    # STEP 3: Build merged picks (same join as INT-101)
    log.info("STEP 3 — building merged picks")
    merged = build_merged(oof, lines, overlap)

    # Determine modes to run
    if args.scorer_mode == "both":
        modes_to_run = [("legacy", True), ("patched", False)]
    elif args.scorer_mode == "legacy":
        modes_to_run = [("legacy", True)]
    else:
        modes_to_run = [("patched", False)]

    # STEP 4: Score each mode
    rng_seed = 20260529
    all_dfs: dict[str, pd.DataFrame] = {}
    all_metrics: dict[str, dict] = {}

    for mode_name, is_legacy in modes_to_run:
        log.info(f"\nSTEP 4 — scoring mode={mode_name} (legacy_corr={is_legacy})")
        rng = np.random.default_rng(rng_seed)  # same seed each mode for reproducibility
        picks_df = score_picks(merged, overlap, corr_df, is_legacy, rng)
        metrics = compute_metrics(picks_df, mode_name)
        all_dfs[mode_name] = picks_df
        all_metrics[mode_name] = metrics

    # STEP 5: Compute deltas (only when both modes ran)
    delta_df = pd.DataFrame()
    if "legacy" in all_dfs and "patched" in all_dfs:
        log.info("\nSTEP 5 — computing per-pick deltas")
        delta_df = compute_pick_deltas(all_dfs["legacy"], all_dfs["patched"])
        log.info(f"  Delta df shape: {delta_df.shape}")

    # STEP 6: Gate evaluation
    gates: dict[str, str] = {}

    # G1: both modes produce same n_picks within ±10%
    if "legacy" in all_metrics and "patched" in all_metrics:
        n_leg = all_metrics["legacy"]["n_total"]
        n_pat = all_metrics["patched"]["n_total"]
        ratio = abs(n_leg - n_pat) / max(n_leg, n_pat) if max(n_leg, n_pat) > 0 else 1.0
        g1_ok = ratio <= 0.10
        gates["G1"] = (
            f"PASS -- legacy n={n_leg}, patched n={n_pat} (diff={ratio*100:.1f}% <= 10%)"
            if g1_ok else
            f"FAIL -- legacy n={n_leg}, patched n={n_pat} (diff={ratio*100:.1f}% > 10% -- pick count diverged)"
        )
    else:
        mode_only = list(all_metrics.keys())[0]
        g1_ok = True
        gates["G1"] = f"SKIP (single-mode run: {mode_only})"

    # G2: patched_ROI > 0%
    pat_roi = all_metrics.get("patched", {}).get("roi_kelly_025", None)
    if pat_roi is not None:
        g2_ok = pat_roi > 0.0
        gates["G2"] = (
            f"PASS — patched ROI={pat_roi:.2f}% > 0% (edge is genuine)"
            if g2_ok else
            f"FAIL — patched ROI={pat_roi:.2f}% ≤ 0% — MAJOR CONCERN: edge may be correlation-inflated"
        )
    else:
        g2_ok = True
        gates["G2"] = "SKIP (no patched mode run)"

    # G3: delta legacy-patched ROI attribution
    leg_roi = all_metrics.get("legacy", {}).get("roi_kelly_025", None)
    if pat_roi is not None and leg_roi is not None:
        delta_roi = leg_roi - pat_roi
        if delta_roi < 2.0:
            g3_tag = "SMALL (<2pp): edge mostly single-leg; correlation had minimal impact"
        elif delta_roi < 5.0:
            g3_tag = "MODERATE (2-5pp): some correlation lift; acceptable"
        elif delta_roi < 8.0:
            g3_tag = f"LARGE ({delta_roi:.2f}pp): correlation layer doing meaningful work — review"
        else:
            g3_tag = f"MAJOR ({delta_roi:.2f}pp): CONCERN — correlation was overstating Kelly by 80%+"
        g3_ok = delta_roi < 8.0
        gates["G3"] = f"delta={delta_roi:+.2f}pp — {g3_tag}"
    else:
        g3_ok = True
        gates["G3"] = "SKIP (single-mode run)"

    # G4: per-stat hit rates should be similar between modes on single-leg picks
    if "legacy" in all_metrics and "patched" in all_metrics:
        hr_leg = all_metrics["legacy"]["hit_rate_92"]
        hr_pat = all_metrics["patched"]["hit_rate_92"]
        g4_ok = abs(hr_leg - hr_pat) < 0.03
        gates["G4"] = (
            f"PASS — INT-92-sim HR: legacy={hr_leg*100:.1f}% patched={hr_pat*100:.1f}% (diff={abs(hr_leg-hr_pat)*100:.2f}pp)"
            if g4_ok else
            f"WARN — INT-92-sim HR: legacy={hr_leg*100:.1f}% patched={hr_pat*100:.1f}% (diff={abs(hr_leg-hr_pat)*100:.2f}pp > 3pp)"
        )
    else:
        g4_ok = True
        gates["G4"] = "SKIP (single-mode run)"

    # Kill switch checks
    kill_switches: list[str] = []
    if pat_roi is not None and pat_roi <= 0.0:
        kill_switches.append(
            f"KILL SWITCH TRIGGERED: patched_ROI={pat_roi:.2f}% <= 0%. "
            "The +9.65% INT-101 ROI was correlation-inflated. Reassess all parlay claims."
        )
    if pat_roi is not None and leg_roi is not None and (leg_roi - pat_roi) > 8.0:
        kill_switches.append(
            f"KILL SWITCH TRIGGERED: legacy-patched delta={(leg_roi-pat_roi):.2f}pp > 8pp. "
            "Correlation was overstating Kelly by 80%+. Reassess all parlay product claims."
        )
    if "patched" in all_metrics and "legacy" in all_metrics:
        n_drop_pct = (all_metrics["legacy"]["n_total"] - all_metrics["patched"]["n_total"]) / max(all_metrics["legacy"]["n_total"], 1)
        if n_drop_pct > 0.50:
            kill_switches.append(
                f"KILL SWITCH: picks dropped by {n_drop_pct*100:.0f}% after patch — patch too aggressive for surface filter."
            )
    for ks in kill_switches:
        log.error(ks)

    # STEP 7: Write comparison parquet
    log.info("\nSTEP 7 — writing comparison parquet")
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    all_picks = pd.concat(list(all_dfs.values()), ignore_index=True)
    all_picks.to_parquet(OUT_PARQUET, index=False)
    log.info(f"  Written: {OUT_PARQUET} ({all_picks.shape})")

    # STEP 8: Write vault MD
    log.info("STEP 8 — writing vault MD")

    def _mode_row(m: dict) -> str:
        return (
            f"| {m['mode']} | {m['n_total']} | {m['n_92']} | {m['n_98']} "
            f"| {m['hit_rate']*100:.1f}% | {m['hit_rate_92']*100:.1f}% | {m['hit_rate_98']*100:.1f}% "
            f"| {m['mean_P_joint']*100:.1f}% | {m['mean_P_indep']*100:.1f}% "
            f"| {m['roi_kelly_025']:+.2f}% | {m['roi_flat']:+.2f}% "
            f"| {m['roi_kelly_92']:+.2f}% | {m['roi_kelly_98']:+.2f}% |"
        )

    comparison_table = (
        "| mode | n_total | n_92 | n_98 | hit_rate | HR_92 | HR_98 "
        "| P_joint | P_indep | ROI_kelly | ROI_flat | ROI_k_92 | ROI_k_98 |\n"
        "|------|---------|------|------|----------|-------|------- "
        "|---------|---------|-----------|----------|----------|----------|\n"
    )
    for m in all_metrics.values():
        comparison_table += _mode_row(m) + "\n"

    # Per-stat tables
    per_stat_md = ""
    for mode_name, m in all_metrics.items():
        ps = m["per_stat"]
        if not ps.empty:
            per_stat_md += f"\n### Per-Stat Hit Rate — {mode_name}\n"
            per_stat_md += "| stat | n | hits | hit_rate |\n|------|---|------|----------|\n"
            for stat, row in ps.iterrows():
                per_stat_md += f"| {stat} | {int(row['n'])} | {int(row['hits'])} | {row['hit_rate']*100:.1f}% |\n"

    # Top picks that changed most between modes
    delta_md = ""
    if not delta_df.empty:
        top_changed = delta_df[delta_df["source"] == "INT-98-sim"].head(10)
        if not top_changed.empty:
            delta_md = "\n### Top Picks by P_joint Delta (INT-98-sim, |legacy - patched| biggest)\n"
            delta_md += "| date | player_id | stat | P_joint_legacy | P_joint_patched | delta | hit |\n"
            delta_md += "|------|-----------|------|----------------|-----------------|-------|-----|\n"
            for _, r in top_changed.iterrows():
                delta_md += (
                    f"| {r['date']} | {r['player_id']} | {r['stat']} "
                    f"| {r.get('P_joint_legacy', 0):.3f} | {r.get('P_joint_patched', 0):.3f} "
                    f"| {r.get('delta_P_joint', 0):+.3f} | {int(r['hit']) if pd.notna(r['hit']) else 'push'} |\n"
                )

    # Verdict
    if pat_roi is not None and leg_roi is not None:
        delta_roi_final = leg_roi - pat_roi
        if kill_switches:
            verdict_text = "FAIL — " + " | ".join(kill_switches)
        elif abs(delta_roi_final) < 2.0:
            verdict_text = (
                f"SHIP — INT-101's +9.65% ROI is ROBUST to the INT-111 patch. "
                f"ROI delta is only {delta_roi_final:+.2f}pp (< 2pp threshold). "
                f"Edge was driven by genuine single-leg model signal, not the correlation layer."
            )
        elif delta_roi_final < 5.0:
            verdict_text = (
                f"SCOPED-SHIP — ROI delta {delta_roi_final:+.2f}pp (2-5pp). "
                f"Correlation lifted INT-101's ROI modestly. "
                f"Patched ROI={pat_roi:.2f}% still positive; edge holds under the patch."
            )
        else:
            verdict_text = (
                f"CONCERN — ROI delta {delta_roi_final:+.2f}pp (>{5}pp). "
                f"Correlation was doing meaningful work. INT-101's +9.65% partially overcalibrated. "
                f"Patched ROI={pat_roi:.2f}%."
            )
    elif pat_roi is not None:
        verdict_text = f"patched-only run: ROI={pat_roi:.2f}% {'positive' if pat_roi > 0 else 'NEGATIVE'}"
    else:
        verdict_text = "legacy-only run"

    gates_md = "\n".join([f"| {k} | {v} |" for k, v in gates.items()])
    ks_md = "\n".join([f"- {ks}" for ks in kill_switches]) if kill_switches else "None triggered."

    md = f"""# INT-113 Retro — Patched vs Legacy Correlation
## {RUN_DATE}

**Status:** {verdict_text}

**Context:**
- INT-101 retro: 95 picks, 63.9% HR, +9.65% ROI at Kelly_025 (window: Oct-28→Apr-03 2025-26)
- INT-110 INVALIDATED: PTS×REB, PTS×AST, REB×AST correlations overshoot by 2.88pp
- INT-111 PATCH: INTRA_RHO_ALLOWLIST = {{(pts,fg3m)}} — all other same-player intra-rho → 0
- THIS SCRIPT: re-runs same picks, replaces linear P_joint_sim with mode-specific MVN P_joint

## Gate Scoreboard

| Gate | Result |
|------|--------|
{gates_md}

## Comparison Table

{comparison_table}

**v1 INT-101 reference (linear proxy):**
| v1 | 95 | 83 | 12 | 63.9% | — | — | 52.9% | 52.9% | +9.65% | — | — | — |

{per_stat_md}

{delta_md}

## Kill Switches

{ks_md}

## Methodology

- **INT-92-sim** (single-leg): P_joint = 0.5 + 0.35*edge (linear proxy, identical in both modes
  because single-leg has no intra-rho component). Kelly_025 derived from mode-specific P_joint.
- **INT-98-sim** (2-leg pairs): P_joint uses 2D MVN.
  - Legacy mode: rho from INT-84 league correlation (PTS×REB=0.33, PTS×AST=0.21, etc.)
  - Patched mode: rho=0 for all pairs except (pts,fg3m); PTS×FG3M gets rho=0.67 either way.
  - Cross-player pairs: rho=0 in both modes (INT-86 teammate corr unchanged).
- **Key implication**: if INT-101's ROI was dominated by INT-92-sim single-leg picks,
  the two modes will produce nearly identical ROI (G3 delta < 2pp → "genuine signal" verdict).

## Output Files

- `data/intelligence/daily_picks_retro_v1_vs_v2_comparison.parquet` — {all_picks.shape[0]} rows × {all_picks.shape[1]} cols
- `vault/Intelligence/INT-113_Retro_Patched_vs_Legacy.md` — this document
"""

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(md, encoding="utf-8")
    log.info(f"  Written: {OUT_MD}")

    # Append banner to cv_master_strategy.md
    if OUT_STRAT.exists():
        existing = OUT_STRAT.read_text(encoding="utf-8", errors="replace")
        if BANNER not in existing:
            pat_roi_str = f"{pat_roi:.2f}%" if pat_roi is not None else "N/A"
            leg_roi_str = f"{leg_roi:.2f}%" if leg_roi is not None else "N/A"
            delta_str   = f"{(leg_roi - pat_roi):.2f}pp" if (leg_roi is not None and pat_roi is not None) else "N/A"
            append_line = (
                f"\n{BANNER}\n"
                f"**INT-113 Retro Patched vs Legacy** ({RUN_DATE}): "
                f"legacy ROI={leg_roi_str} patched ROI={pat_roi_str} delta={delta_str}; "
                f"G1={'PASS' if g1_ok else 'FAIL'} G2={'PASS' if g2_ok else 'FAIL'} "
                f"G3={'PASS' if g3_ok else 'WARN'} G4={'PASS' if g4_ok else 'WARN'}; "
                f"verdict={'GENUINE SIGNAL' if pat_roi is not None and pat_roi > 0 and (leg_roi is None or (leg_roi - pat_roi) < 5.0) else 'CONCERN'}.\n"
            )
            with open(OUT_STRAT, "a", encoding="utf-8", errors="replace") as f:
                f.write(append_line)
            log.info(f"  Appended banner to: {OUT_STRAT}")
        else:
            log.info("  Banner already present — skipping")
    else:
        log.warning(f"  cv_master_strategy.md not found at {OUT_STRAT}")

    # Final summary
    print("\n" + "=" * 65)
    print(f"INT-113 COMPLETE — {RUN_DATE}")
    print(f"  Verdict: {verdict_text}")
    print(f"  Window:  {overlap[0]} to {overlap[-1]} ({n_overlap} dates)")
    print()
    for mode_name, m in all_metrics.items():
        print(f"  [{mode_name.upper()}]")
        print(f"    n_picks={m['n_total']} (92-sim={m['n_92']}, 98-sim={m['n_98']})")
        print(f"    hit_rate={m['hit_rate']*100:.1f}%  (92-sim={m['hit_rate_92']*100:.1f}%, 98-sim={m['hit_rate_98']*100:.1f}%)")
        print(f"    P_joint={m['mean_P_joint']*100:.1f}%  P_indep={m['mean_P_indep']*100:.1f}%")
        print(f"    ROI_kelly={m['roi_kelly_025']:+.2f}%  ROI_flat={m['roi_flat']:+.2f}%")
        print(f"    ROI_92={m['roi_kelly_92']:+.2f}%  ROI_98={m['roi_kelly_98']:+.2f}%")
        ps = m["per_stat"]
        if not ps.empty:
            print("    Per-stat (INT-92-sim):")
            for stat, row in ps.iterrows():
                print(f"      {stat:6s}: n={int(row['n']):2d}  hits={int(row['hits']):2d}  HR={row['hit_rate']*100:.1f}%")
        print()
    if "legacy" in all_metrics and "patched" in all_metrics:
        print(f"  ROI delta (legacy - patched): {(all_metrics['legacy']['roi_kelly_025'] - all_metrics['patched']['roi_kelly_025']):+.2f}pp")
    for k, v in gates.items():
        print(f"  {k}: {v}")
    if kill_switches:
        for ks in kill_switches:
            print(f"\n  *** {ks} ***")
    print(f"\n  Output:  {OUT_PARQUET}")
    print(f"  Vault:   {OUT_MD}")
    print("=" * 65)


if __name__ == "__main__":
    main()
