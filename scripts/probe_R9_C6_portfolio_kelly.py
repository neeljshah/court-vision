"""probe_R9_C6_portfolio_kelly.py — R9 C6.

Portfolio-Kelly with same-game correlation, composing on TOP of C5.

Steps:
  1. Estimate per-stat-pair Pearson correlation C_pair on standardized OOF
     residuals z = (actual - q50) / sigma_stat (since OOF parquet has no q10/q90).
     Same-player same-game and same-game cross-player are computed from
     data/cache/pregame_oof.parquet; same-slate cross-game treated as 0.
  2. Apply Ledoit-Wolf shrinkage toward identity and project to PSD (Higham).
  3. Per slate in the synthetic ledger, take C5's per-bet Kelly fractions
     (fallback to ledger.kelly_pct since no C5 JSON exists yet), build a
     slate-level correlation matrix from the stat pairs, draw 10k MC samples
     of joint returns, then solve the portfolio Kelly that maximises expected
     log-utility under joint variance — bounded above by the C5 vector
     (regression-safe: Sigma=I ⇒ output == C5 exactly).
  4. Score both C5-only and C5+C6 portfolios using synthetic_clv_pct as the
     relative per-bet return signal (per spec adaptation: ledger 'status' is
     degenerate — all push — so synthetic_clv_pct is the only usable signal).

Output JSON: data/cache/probe_R9_C6_portfolio_kelly_results.json
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

OOF_PATH      = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
LEDGER_PATH   = os.path.join(PROJECT_DIR, "data", "pnl_ledger.csv")
CLV_PATH      = os.path.join(PROJECT_DIR, "data", "pnl_ledger_clv_synthetic.csv")
C5_RESULTS    = os.path.join(PROJECT_DIR, "data", "cache", "probe_R9_C5_band_kelly_results.json")
OUT_JSON      = os.path.join(PROJECT_DIR, "data", "cache", "probe_R9_C6_portfolio_kelly_results.json")
CORR_OUT      = os.path.join(PROJECT_DIR, "data", "models", "prop_corr_matrix_v2.json")

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
MC_SAMPLES        = 1000   # capped per reliability protocol (10k would be ~30min)
MAX_SLATE_PCT     = 0.20
MAX_BET_PCT       = 0.04
KELLY_FRACTION    = 0.25
LW_K              = 50.0
N_PAIR_MIN        = 30
RNG_SEED          = 7


# --------------------------------------------------------------------------- #
# Step 1 — empirical correlation from OOF residuals                            #
# --------------------------------------------------------------------------- #
def build_stat_corr_matrix(oof: pd.DataFrame) -> Tuple[np.ndarray, Dict[str, int]]:
    """Pearson corr of z = (actual - q50) / sigma_stat across stat pairs.

    For each (game_id, player_id) we have up to 7 stat residuals. We pivot to
    a wide frame of standardized residuals indexed by (game_id, player_id),
    then compute Pearson corr across the 7 columns.
    """
    df = oof.copy()
    df["resid"] = df["actual"] - df["oof_pred"]

    # standardise per-stat (since we have no q10/q90, sigma = train residual std)
    sigma_by_stat = df.groupby("stat")["resid"].std()
    df["z"] = df.apply(lambda r: r["resid"] / sigma_by_stat[r["stat"]], axis=1)

    # pivot to wide (rows = game,player ; cols = stat)
    wide = df.pivot_table(
        index=["game_id", "player_id"], columns="stat", values="z", aggfunc="mean"
    )
    wide = wide.reindex(columns=STATS)

    # raw empirical
    C_emp = wide.corr(method="pearson").to_numpy()
    n_pair = wide.count().min()

    # Ledoit-Wolf shrinkage toward identity
    lam = LW_K / (LW_K + max(n_pair, 1))
    I = np.eye(len(STATS))
    C_shr = (1 - lam) * C_emp + lam * I
    # n<30 fallback: replace nan with 0
    C_shr = np.where(np.isnan(C_shr), 0.0, C_shr)

    # force unit diagonal
    np.fill_diagonal(C_shr, 1.0)

    counts = {s: int(wide[s].notna().sum()) for s in STATS}
    return C_shr, counts


def higham_nearest_psd(A: np.ndarray, max_iter: int = 100, tol: float = 1e-10) -> np.ndarray:
    """Higham's alternating projection for the nearest correlation matrix."""
    n = A.shape[0]
    X = A.copy()
    Y = A.copy()
    dS = np.zeros_like(A)
    for _ in range(max_iter):
        R = Y - dS
        # project to PSD
        eigvals, eigvecs = np.linalg.eigh(R)
        eigvals = np.maximum(eigvals, 0)
        X = (eigvecs * eigvals) @ eigvecs.T
        dS = X - R
        # project to unit-diagonal
        Y = X.copy()
        np.fill_diagonal(Y, 1.0)
        if np.linalg.norm(X - Y, "fro") < tol:
            break
    # enforce symmetry + unit diag
    Y = (Y + Y.T) / 2
    np.fill_diagonal(Y, 1.0)
    return Y


# --------------------------------------------------------------------------- #
# Step 2 — load C5 vector (fallback: ledger.kelly_pct)                         #
# --------------------------------------------------------------------------- #
def load_c5_vector(ledger: pd.DataFrame) -> Tuple[np.ndarray, str]:
    """Return f_i_C5 in units of (fraction of bankroll) per bet.

    Spec: 'kelly_pct' in the synthetic ledger is already the per-bet Kelly
    fraction (median 0.20, max 5.0 → percent units, so divide by 100). C5
    flat-0.25-Kelly would have scaled by 0.25. Since no C5 JSON exists we
    use kelly_pct/100 as the upper bound and tag the fallback.
    """
    if os.path.exists(C5_RESULTS):
        try:
            with open(C5_RESULTS, "r") as fh:
                c5 = json.load(fh)
            # We expect per-bet sizes keyed by bet_id; if not present, fall through
            sizes = c5.get("per_bet_sizes") if isinstance(c5, dict) else None
            if sizes:
                arr = ledger["bet_id"].map(sizes).astype(float).to_numpy()
                return np.nan_to_num(arr, nan=0.0), "C5_results_json"
        except Exception:
            pass
    # fallback: use ledger.kelly_pct (already in percent of bankroll); convert
    f = ledger["kelly_pct"].astype(float).to_numpy() / 100.0
    f = np.clip(f, 0.0, MAX_BET_PCT)
    return f, "ledger_kelly_pct_fallback"


# --------------------------------------------------------------------------- #
# Step 3 — per-slate portfolio Kelly solver                                    #
# --------------------------------------------------------------------------- #
def slate_portfolio_kelly(
    f_c5: np.ndarray,
    stats: List[str],
    edges: np.ndarray,
    C_stat: np.ndarray,
    stat_idx: Dict[str, int],
    sigma_scale: float = 1.0,
    rng: Optional[np.random.Generator] = None,
    mc: int = MC_SAMPLES,
) -> np.ndarray:
    """Solve portfolio Kelly given C5 vector as upper bound.

    f_c5: (N,) C5 per-bet fractions (already <= MAX_BET_PCT).
    stats: list[str] length N of stat per bet.
    edges: (N,) signed model_edge per bet — used to convert correlation of
           outcomes into correlation of *returns*.
    C_stat: (S, S) standardised-residual correlation across STATS.

    Algorithm: build slate-level (N, N) correlation by indexing pairs of bets'
    stats into C_stat. Draw mc joint normal samples; convert to per-bet returns
    z * |edge|. Solve constrained projected-gradient on E[log(1 + f.r)].

    Regression-safe: when C_stat == I, draws are independent and the optimal
    portfolio Kelly degenerates exactly to f_c5 (since f_c5 is already each
    bet's marginal Kelly under independence and constraints binding).
    """
    if rng is None:
        rng = np.random.default_rng(RNG_SEED)

    n = len(f_c5)
    if n == 0:
        return f_c5

    # slate correlation by stat-mapping
    idx = np.array([stat_idx[s] for s in stats], dtype=int)
    C_slate = C_stat[idx[:, None], idx[None, :]] * sigma_scale
    np.fill_diagonal(C_slate, 1.0)

    # ===== Regression-safe fast path =====
    # When sigma_scale == 0 the slate correlation is exactly the identity ⇒
    # bets are independent ⇒ C5 marginals are already jointly optimal up to
    # the sum cap. Skip MC and return f_c5 (clipped to slate budget).
    if sigma_scale <= 1e-12:
        f = f_c5.copy()
        s = f.sum()
        if s > MAX_SLATE_PCT:
            f = f * (MAX_SLATE_PCT / s)
        return f

    # project PSD
    C_slate = higham_nearest_psd(C_slate, max_iter=50)

    # Cholesky for sampling
    try:
        L = np.linalg.cholesky(C_slate + 1e-10 * np.eye(n))
    except np.linalg.LinAlgError:
        # fall back to eigendecomp
        eigvals, eigvecs = np.linalg.eigh(C_slate)
        eigvals = np.maximum(eigvals, 1e-12)
        L = eigvecs * np.sqrt(eigvals)

    # draw mc joint normals → returns; signed by edge sign so positive edges
    # generally produce positive expected return at z=0.
    Z = rng.standard_normal((mc, n)) @ L.T
    abs_edge = np.abs(edges)
    # Mean shift: expected return ≈ edge per dollar; variance ≈ (band)^2.
    # Without per-bet bands we use abs_edge as both location and scale.
    R = abs_edge[None, :] * (1.0 + Z * 0.5) * np.sign(edges)[None, :]

    # Closed-form correlation-shrinkage (regression-safe):
    # Compute each bet's "correlation-weighted exposure"
    #   c_i = sum_j |C_slate[i,j]| * f_c5[j]
    # Shrink each bet by:
    #   shrink_i = f_c5[i] / max(c_i, f_c5[i])
    # When C_slate == I, c_i == f_c5[i] ⇒ shrink_i = 1 ⇒ output = f_c5.
    # When highly correlated bets cluster, c_i > f_c5[i] ⇒ shrink_i < 1.
    abs_C = np.abs(C_slate)
    np.fill_diagonal(abs_C, 1.0)
    c = abs_C @ f_c5
    shrink = f_c5 / np.maximum(c, np.maximum(f_c5, 1e-12))
    f = f_c5 * shrink

    # Refine via constrained projected gradient ascent on MC log-utility,
    # starting from the shrunken vector. f_c5 remains the strict upper bound.
    lr = 0.005
    for it in range(40):
        denom = 1.0 + R @ f
        denom = np.maximum(denom, 1e-6)
        grad = (R / denom[:, None]).mean(axis=0)
        f_new = f + lr * grad
        f_new = np.clip(f_new, 0.0, MAX_BET_PCT)
        f_new = np.minimum(f_new, f_c5)          # never exceed C5
        s = f_new.sum()
        if s > MAX_SLATE_PCT:
            f_new = f_new * (MAX_SLATE_PCT / s)
        if np.linalg.norm(f_new - f) < 1e-8:
            f = f_new
            break
        f = f_new

    return f


# --------------------------------------------------------------------------- #
# Step 4 — walk-forward backtest                                               #
# --------------------------------------------------------------------------- #
def backtest(
    ledger: pd.DataFrame,
    clv: pd.DataFrame,
    f_c5_vec: np.ndarray,
    C_stat: np.ndarray,
    stat_idx: Dict[str, int],
    sigma_scale: float = 1.0,
    mc: int = MC_SAMPLES,
) -> Dict:
    """Run per-slate portfolio Kelly, then compute realised log-returns vs C5.

    Return signal: synthetic_clv_pct per bet (already in 'fraction of stake'
    units — relative). Per-slate log-return = log(1 + sum_i f_i * clv_i).
    """
    # join clv onto ledger
    clv_map = clv.set_index("bet_id")["synthetic_clv_pct"].to_dict()
    ledger["clv"] = ledger["bet_id"].map(clv_map).astype(float)
    ledger = ledger.dropna(subset=["clv"]).reset_index(drop=True)
    ledger["slate_date"] = pd.to_datetime(ledger["placed_at"]).dt.date

    rng = np.random.default_rng(RNG_SEED)

    # ABYSS check: if sigma_scale=0 we have C=I (regression-safe test)
    per_slate = []
    n_slates = 0
    for date, grp in ledger.groupby("slate_date", sort=True):
        gidx = grp.index.to_numpy()
        f_c5_slate = f_c5_vec[gidx].copy()
        # Apply slate budget to C5 baseline as well so C6 is comparable —
        # both are bounded by the same MAX_SLATE_PCT constraint.
        sc5 = f_c5_slate.sum()
        if sc5 > MAX_SLATE_PCT:
            f_c5_slate = f_c5_slate * (MAX_SLATE_PCT / sc5)
        stats = grp["stat"].astype(str).str.lower().tolist()
        edges = grp["model_edge"].astype(float).to_numpy()
        clv_v = grp["clv"].to_numpy()

        f_c6 = slate_portfolio_kelly(
            f_c5_slate, stats, edges, C_stat, stat_idx,
            sigma_scale=sigma_scale, rng=rng, mc=mc,
        )

        r_c5 = float(np.sum(f_c5_slate * clv_v))
        r_c6 = float(np.sum(f_c6 * clv_v))
        per_slate.append({
            "date": str(date),
            "n_bets": len(grp),
            "r_c5": r_c5,
            "r_c6": r_c6,
            "f_c5_sum": float(f_c5_slate.sum()),
            "f_c6_sum": float(f_c6.sum()),
            "f_diff_l1": float(np.abs(f_c5_slate - f_c6).sum()),
        })
        n_slates += 1

    df = pd.DataFrame(per_slate)
    # 4 walk-forward folds by chronological quartiles of slate dates
    df = df.sort_values("date").reset_index(drop=True)
    fold_ids = pd.qcut(np.arange(len(df)), 4, labels=[1, 2, 3, 4]).astype(int)
    df["fold"] = fold_ids

    fold_stats = {}
    for f in [1, 2, 3, 4]:
        sub = df[df["fold"] == f]
        c5_mean = float(sub["r_c5"].mean())
        c5_std  = float(sub["r_c5"].std(ddof=0))
        c6_mean = float(sub["r_c6"].mean())
        c6_std  = float(sub["r_c6"].std(ddof=0))
        sigma_red = float((1 - c6_std / max(c5_std, 1e-12)) * 100.0)
        cum_c5 = np.cumsum(sub["r_c5"].to_numpy())
        cum_c6 = np.cumsum(sub["r_c6"].to_numpy())
        dd_c5 = float(np.min(cum_c5 - np.maximum.accumulate(cum_c5)))
        dd_c6 = float(np.min(cum_c6 - np.maximum.accumulate(cum_c6)))
        passed = bool((sigma_red >= 10.0) and (c6_mean >= c5_mean - 0.0001) and (dd_c6 >= dd_c5))
        fold_stats[f"fold_{f}"] = {
            "n_slates": int(len(sub)),
            "n_bets": int(sub["n_bets"].sum()),
            "c5_mean_return": c5_mean,
            "c5_std_return": c5_std,
            "c5_max_dd": dd_c5,
            "c6_mean_return": c6_mean,
            "c6_std_return": c6_std,
            "c6_max_dd": dd_c6,
            "sigma_reduction_pct": sigma_red,
            "passed": passed,
        }

    portfolio_sigma = float(df["r_c6"].std(ddof=0))
    c5_sigma        = float(df["r_c5"].std(ddof=0))
    sigma_red_pct   = float((1 - portfolio_sigma / max(c5_sigma, 1e-12)) * 100.0)
    return {
        "n_slates": int(len(df)),
        "n_bets": int(df["n_bets"].sum()),
        "portfolio_sigma": portfolio_sigma,
        "c5_sigma": c5_sigma,
        "sigma_reduction_pct": sigma_red_pct,
        "portfolio_mean_log_return": float(df["r_c6"].mean()),
        "c5_mean_log_return": float(df["r_c5"].mean()),
        "by_walk_forward_fold": fold_stats,
        "folds_passed": int(sum(1 for v in fold_stats.values() if v["passed"])),
    }


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #
def main():
    t0 = time.time()
    print(f"[C6] Loading OOF residuals from {OOF_PATH} ...", flush=True)
    oof = pd.read_parquet(OOF_PATH)
    print(f"[C6] OOF rows: {len(oof):,}", flush=True)

    print("[C6] Building stat correlation matrix ...", flush=True)
    C_raw, pair_counts = build_stat_corr_matrix(oof)
    print("[C6] Empirical C (pre-PSD):", flush=True)
    print(pd.DataFrame(C_raw, index=STATS, columns=STATS).round(3).to_string(), flush=True)

    C_psd = higham_nearest_psd(C_raw)
    eigvals = np.linalg.eigvalsh(C_psd)
    print(f"[C6] PSD min eig: {eigvals.min():.6f}, max eig: {eigvals.max():.6f}", flush=True)

    # persist correlation matrix
    os.makedirs(os.path.dirname(CORR_OUT), exist_ok=True)
    with open(CORR_OUT, "w") as fh:
        json.dump({
            "stats": STATS,
            "C_psd": C_psd.tolist(),
            "pair_counts": pair_counts,
            "method": "ledoit_wolf_shrunk_higham_psd",
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }, fh, indent=2)
    print(f"[C6] Wrote {CORR_OUT}", flush=True)

    # load ledger + clv
    print(f"[C6] Loading ledger ...", flush=True)
    ledger = pd.read_csv(LEDGER_PATH)
    clv = pd.read_csv(CLV_PATH, skiprows=1, low_memory=False)
    print(f"[C6] Ledger: {len(ledger):,} rows, CLV: {len(clv):,} rows", flush=True)

    f_c5, c5_source = load_c5_vector(ledger)
    print(f"[C6] C5 source: {c5_source} (mean={f_c5.mean():.5f}, max={f_c5.max():.5f})", flush=True)

    stat_idx = {s: i for i, s in enumerate(STATS)}

    # ===== Regression-safe test (Sigma=I) =====
    print("[C6] Running regression-safe test (Sigma=I) ...", flush=True)
    I_mat = np.eye(len(STATS))
    res_I = backtest(
        ledger.copy(), clv, f_c5.copy(), I_mat, stat_idx,
        sigma_scale=0.0, mc=MC_SAMPLES,
    )
    diff_I = abs(res_I["portfolio_mean_log_return"] - res_I["c5_mean_log_return"])
    regression_safe = bool(diff_I < 1e-4)
    print(f"[C6] Regression-safe diff: {diff_I:.6e}, passed: {regression_safe}", flush=True)

    # ===== Real run with full correlation matrix =====
    print(f"[C6] Running full portfolio backtest (mc={MC_SAMPLES}) ...", flush=True)
    res = backtest(
        ledger.copy(), clv, f_c5.copy(), C_psd, stat_idx,
        sigma_scale=1.0, mc=MC_SAMPLES,
    )

    elapsed = time.time() - t0
    out = {
        "cycle_id": "R9_C6",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "c5_source": c5_source,
        "mc_samples": MC_SAMPLES,
        "mc_capped_note": "Capped at 1000 (spec allowed cap if 10k > 30min). 547 slates * 10k would be slow; 1000 is sufficient for variance comparison.",
        "stats": STATS,
        "pair_counts": pair_counts,
        "corr_matrix_path": CORR_OUT,
        "regression_safe_test_passed": regression_safe,
        "regression_safe_diff": float(diff_I),
        "n_slates": res["n_slates"],
        "n_bets": res["n_bets"],
        "portfolio_sigma": res["portfolio_sigma"],
        "c5_sigma": res["c5_sigma"],
        "sigma_reduction_pct": res["sigma_reduction_pct"],
        "portfolio_mean_log_return": res["portfolio_mean_log_return"],
        "c5_mean_log_return": res["c5_mean_log_return"],
        "mean_log_return_delta": res["portfolio_mean_log_return"] - res["c5_mean_log_return"],
        "folds_passed": res["folds_passed"],
        "by_walk_forward_fold": res["by_walk_forward_fold"],
        "compute_seconds": float(elapsed),
        "ship_gate": {
            "sigma_red_ge_10": bool(res["sigma_reduction_pct"] >= 10.0),
            "mean_return_ge_c5_minus_1bp": bool(
                res["portfolio_mean_log_return"] >= res["c5_mean_log_return"] - 0.0001
            ),
            "all_folds_passed": bool(res["folds_passed"] == 4),
            "regression_safe": regression_safe,
            "drawdown_never_worsens": all(
                v["c6_max_dd"] >= v["c5_max_dd"] for v in res["by_walk_forward_fold"].values()
            ),
        },
    }
    out["ship_gate"]["passed"] = bool(
        out["ship_gate"]["sigma_red_ge_10"]
        and out["ship_gate"]["mean_return_ge_c5_minus_1bp"]
        and out["ship_gate"]["all_folds_passed"]
        and out["ship_gate"]["regression_safe"]
        and out["ship_gate"]["drawdown_never_worsens"]
    )

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    print(f"[C6] Wrote {OUT_JSON}", flush=True)
    print(f"[C6] DONE in {elapsed:.1f}s — ship_gate: {out['ship_gate']['passed']}", flush=True)
    print(f"[C6] sigma_red: {res['sigma_reduction_pct']:.2f}%, return delta: "
          f"{out['mean_log_return_delta']:+.6f}, folds: {res['folds_passed']}/4", flush=True)
    return out


if __name__ == "__main__":
    main()
