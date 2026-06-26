"""domains.mlb.asof_ra_diff_eval -- gate the on-disk sp_ra_diff_asof CANDIDATE.

Reclaims the already-built, leak-free starting-pitcher trailing runs-allowed
DIFFERENTIAL column (``data/domains/mlb/asof_features.parquet:sp_ra_diff_asof``)
by LEFT-MERGING it onto the gate corpus (mirroring the odds left-merge in
``MLBAdapter.feature_bundle``) and running it through the SAME single-corpus
walk-forward Diebold-Mariano gate the A3 SP-form lever uses.

CANDIDATE-ONLY / DEFAULT-OFF: this is a pure ship-or-reject experiment.  It does
NOT touch ``MLBAdapter.feature_bundle`` (the production/default forecaster); it
reads the parquet additively and gates it.  No flag is flipped.

WHY SINGLE-CORPUS (honest): the on-disk asof parquet + pitchers.parquet cover
ONLY corpus A (games.parquet, 2010-2021).  games_current.parquet (2022-2026) has
ZERO pitcher-identity rows on disk, so a TRUE cross-corpus (A<->B) replication is
IMPOSSIBLE -- exactly the documented A3 SP-form constraint.  We therefore run the
honest single-corpus 70/30 walk-forward DM gate and NEVER claim cross-corpus
replication.  Robustness instead comes from a PLANTED-NULL control (a shuffled
feature must collapse) and a TRUNCATION-INVARIANCE check (drop the last 10% of
train rows -> the verdict must not flip).

Leak-free: every per-game value is snapshot-before-update walk-forward (Elo via
ratings.walk_forward_elo; sp_ra_diff_asof via asof_features strict-prior trailing
mean).  NaN handling is honest: standardize on train stats, NaN -> 0 (neutral),
and the DM is computed on COVERED rows only (both SPs have prior starts) where the
feature is real signal.

NO $ / edge anywhere; verdict is CALIBRATION (held-out Brier).  A REJECT/NULL is a
SUCCESS.  PURE numpy/pandas + the shared clustered DM + local Elo builder.  No
src.*/kernel.* imports.

CLI:  python -m domains.mlb.asof_ra_diff_eval
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from domains.mlb.ratings import walk_forward_elo
from domains.mlb.pregame_gate import _platt_fit, _logit, _sigmoid, _brier, BSS_MIN
from scripts.platformkit.eval_gate.dm_test import diebold_mariano

_REPO = Path(__file__).resolve().parents[2]
_GAMES_A = _REPO / "data/domains/mlb/games.parquet"          # 2010-2021 (corpus A)
_ASOF = _REPO / "data/domains/mlb/asof_features.parquet"     # sp_ra_diff_asof

MIN_PRIOR_STARTS = 3   # both SPs need >= N strictly-prior starts for "covered"
TRAIN_FRAC = 0.70      # leak-free time split (first 70% train, last 30% score)
EPS = 0.05             # DM significance threshold


# --------------------------------------------------------------------------- #
# Build the merged candidate frame (mirrors the adapter odds left-merge)
# --------------------------------------------------------------------------- #

def build_candidate_frame(
    games: Optional[pd.DataFrame] = None,
    asof: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Left-merge sp_ra_diff_asof onto leak-free Elo, keyed on event_id.

    Mirrors ``MLBAdapter.feature_bundle``'s odds merge: select only the needed
    columns, drop_duplicates(event_id, keep='first'), left-merge (NaN where the
    asof row is absent).  Returns a chronologically-sorted frame carrying:
        event_id, date, target_home_win, p_base (Elo P(home)), sp_ra_diff_asof,
        home_sp_starts_prior, away_sp_starts_prior, _cov (bool).
    """
    gdf = games.copy() if isinstance(games, pd.DataFrame) else pd.read_parquet(_GAMES_A)
    gdf = gdf[gdf["target_home_win"].notna()].reset_index(drop=True)

    elo = walk_forward_elo(gdf)[["event_id", "p_home_elo", "date"]].rename(
        columns={"p_home_elo": "p_base"})

    adf = asof.copy() if isinstance(asof, pd.DataFrame) else pd.read_parquet(_ASOF)
    _cols = ["event_id", "sp_ra_diff_asof",
             "home_sp_starts_prior", "away_sp_starts_prior"]
    adf = adf[[c for c in _cols if c in adf.columns]].drop_duplicates(
        "event_id", keep="first")

    out = gdf[["event_id", "target_home_win"]].merge(elo, on="event_id", how="left")
    out = out.merge(adf, on="event_id", how="left")
    out["_cov"] = (
        (out["home_sp_starts_prior"].fillna(0) >= MIN_PRIOR_STARTS)
        & (out["away_sp_starts_prior"].fillna(0) >= MIN_PRIOR_STARTS)
        & out["sp_ra_diff_asof"].notna()
    )
    return out.sort_values("date").reset_index(drop=True)


# --------------------------------------------------------------------------- #
# One single-corpus walk-forward DM gate
# --------------------------------------------------------------------------- #

def _fit_2feature(
    lz_tr: np.ndarray, fz_tr: np.ndarray, y_tr: np.ndarray,
    lz_te: np.ndarray, fz_te: np.ndarray,
) -> np.ndarray:
    """Fit p = sigmoid(w1*elo_logit + w2*feat_z + b) on train; predict on test."""
    from scipy.optimize import minimize

    def _nll(par: np.ndarray) -> float:
        w1, w2, b = par
        p = np.clip(_sigmoid(w1 * lz_tr + w2 * fz_tr + b), 1e-7, 1 - 1e-7)
        return float(-np.mean(y_tr * np.log(p) + (1 - y_tr) * np.log(1 - p)))

    res = minimize(_nll, x0=np.array([1.0, 0.1, 0.0]), method="L-BFGS-B",
                   bounds=[(0.05, 10), (-5, 5), (-3, 3)])
    w1, w2, b = res.x
    return _sigmoid(w1 * lz_te + w2 * fz_te + b), float(w2)


def _gate_once(
    df: pd.DataFrame, feat_col: str = "sp_ra_diff_asof",
    train_frac: float = TRAIN_FRAC, eps: float = EPS,
) -> Dict:
    """Single-corpus 70/30 walk-forward DM gate: Elo BASE vs Elo+feature CAND.

    BASE = Platt(elo).  CAND = 2-feature logistic(elo_logit, feat_z).  Both fit on
    the first ``train_frac`` (leak-free time split), scored on the rest.  DM is
    clustered by event_id on COVERED test rows only (feat is real signal there).
    NaN feature -> 0 after standardizing on train stats (neutral; honest).
    """
    n = len(df)
    split = int(n * train_frac)
    tr, te = df.iloc[:split], df.iloc[split:]
    y_tr = tr["target_home_win"].values.astype(float)
    y_te = te["target_home_win"].values.astype(float)

    lz_tr = _logit(tr["p_base"].values.astype(float))
    lz_te = _logit(te["p_base"].values.astype(float))
    f_tr = tr[feat_col].values.astype(float)
    f_te = te[feat_col].values.astype(float)
    m, s = float(np.nanmean(f_tr)), max(float(np.nanstd(f_tr)), 1e-8)
    fz_tr = np.nan_to_num((f_tr - m) / s)
    fz_te = np.nan_to_num((f_te - m) / s)

    wb, bb_ = _platt_fit(lz_tr, y_tr)
    p_base = _sigmoid(wb * lz_te + bb_)
    p_cand, w2 = _fit_2feature(lz_tr, fz_tr, y_tr, lz_te, fz_te)

    cov = te["_cov"].values.astype(bool)
    yb = y_te[cov]
    br_base = _brier(yb, p_base[cov])
    br_cand = _brier(yb, p_cand[cov])
    d = (p_base[cov] - yb) ** 2 - (p_cand[cov] - yb) ** 2
    dm = diebold_mariano(d, te["event_id"].astype(str).values[cov])

    base_rate = float(np.mean(y_tr))
    br_const = _brier(yb, np.full_like(yb, base_rate))
    bss = (br_const - br_base) / br_const if br_const > 0 else 0.0
    degen = bss < BSS_MIN
    beats = bool((br_cand < br_base) and (dm.p_value < eps) and not degen)
    return {
        "n_cov_test": int(cov.sum()), "brier_base": round(br_base, 6),
        "brier_cand": round(br_cand, 6), "brier_delta": round(br_base - br_cand, 6),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "feat_weight": round(w2, 5), "base_bss": round(bss, 5),
        "base_degenerate": degen, "verdict": "SHIP" if beats else "REJECT",
    }


# --------------------------------------------------------------------------- #
# Planted-null + truncation-invariance controls
# --------------------------------------------------------------------------- #

def _planted_null(df: pd.DataFrame, seed: int = 0) -> Dict:
    """Shuffle the feature column (break its game alignment) -> must collapse."""
    rng = np.random.default_rng(seed)
    nd = df.copy()
    nd["sp_ra_diff_asof"] = rng.permutation(nd["sp_ra_diff_asof"].values)
    return _gate_once(nd)


def run(seed: int = 0) -> Dict:
    """Full gate: real candidate + planted-null + truncation-invariance."""
    df = build_candidate_frame()
    n = len(df)
    cov_total = int(df["_cov"].sum())
    real = _gate_once(df)
    null = _planted_null(df, seed=seed)
    # truncation invariance: drop the LAST 10% of TRAIN rows (shorter history) and
    # re-gate; the verdict must not flip if the signal is real, not edge-of-train.
    trunc = _gate_once(df, train_frac=TRAIN_FRAC * 0.90)
    return {
        "n_rows": n, "cov_total": cov_total,
        "cov_pct": round(100.0 * cov_total / max(n, 1), 1),
        "real": real, "planted_null": null, "truncation": trunc,
    }


def main() -> int:
    res = run()
    print("=" * 72)
    print("MLB sp_ra_diff_asof CANDIDATE -- single-corpus WF gate (2010-2021)")
    print("=" * 72)
    print(f"rows={res['n_rows']}  covered={res['cov_total']} ({res['cov_pct']}%)")
    r = res["real"]
    print(f"\nREAL     verdict={r['verdict']}  n_cov_test={r['n_cov_test']}")
    print(f"   Brier base {r['brier_base']:.6f}  cand {r['brier_cand']:.6f}"
          f"  delta {r['brier_delta']:+.6f}")
    print(f"   DM p={r['dm_p']:.4f}  feat_w={r['feat_weight']:+.4f}"
          f"  base_bss={r['base_bss']:.4f}  degen={r['base_degenerate']}")
    nn = res["planted_null"]
    print(f"\nNULL     verdict={nn['verdict']}  Brier delta {nn['brier_delta']:+.6f}"
          f"  DM p={nn['dm_p']:.4f}  (must be REJECT)")
    tr = res["truncation"]
    print(f"\nTRUNC    verdict={tr['verdict']}  Brier delta {tr['brier_delta']:+.6f}"
          f"  DM p={tr['dm_p']:.4f}  (must match REAL)")
    print("\n(REJECT = honest success; calibration only; no edge ever claimed.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
