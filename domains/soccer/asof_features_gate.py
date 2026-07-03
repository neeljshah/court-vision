"""domains.soccer.asof_features_gate -- gate the on-disk soccer asof_features
CANDIDATE columns as direct logit-features atop the Poisson O/U 2.5 baseline.

Reclaims the already-built, leak-free trailing shot/SoT differential columns
(``data/domains/soccer/asof_features.parquet``) by LEFT-MERGING each onto the
leak-free Poisson goals gate corpus (walk_forward_goals) and running it through
the SAME single-corpus walk-forward Diebold-Mariano gate the NBA
ast_rate_diff_asof / MLB sp_ra_diff_asof / WTA hold_pct_diff_asof reclaims use.

WHY THE POISSON BASE (not Elo): soccer's SportContext market is O/U 2.5 goals,
not match-win; the adapter's own baseline_probability() is the Poisson p_over25
from domains.soccer.ratings.walk_forward_goals -- this gate reuses THAT as the
base, exactly mirroring what SoccerAdapter.feature_bundle() already does (base =
[lam_home, lam_away, lam_total, rest_home, rest_away], signal_col = p_over25).
Per the brief: "logit(p) = logit(p_elo) + w*feature" generalizes here to
logit(p) = logit(p_over25) + w*feature -- same 2-parameter walk-forward logistic
lift-on-top-of-baseline shape as the NBA/MLB/tennis reclaim gates.

CANDIDATE-ONLY / DEFAULT-OFF: does NOT touch SoccerAdapter.feature_bundle() or
any predictor; reads the parquet additively and gates it.  No flag is flipped.

WHY SINGLE-CORPUS (honest): asof_features.parquet is built from ONE match_stats
sidecar (25,834 rows, football-data.co.uk).  A true cross-corpus replication
needs a second independent shot-stats corpus on disk -- absent here.  We run the
honest single-corpus 70/30 walk-forward DM gate and NEVER claim cross-corpus
replication.  Robustness comes from a PLANTED-NULL control (a shuffled feature
must collapse to REJECT) and a TRUNCATION-INVARIANCE check (drop the last 10% of
train rows -> the verdict must not flip) -- identical controls to the NBA/MLB/
WTA precedent.

Leak-free: Poisson lambdas via ratings.walk_forward_goals (snapshot-before-
update); the shot/SoT diffs via asof_features strict-prior expanding mean.  NaN
feature -> 0 (neutral) after standardizing on TRAIN stats; DM computed on
COVERED rows only (both teams have >= MIN_PRIOR strictly-prior matches).

NO $ / edge anywhere; verdict is CALIBRATION (held-out Brier).  PURE numpy/pandas
+ the shared clustered DM + local Poisson goals builder.  No src.*/kernel.*
imports; no domains.nba/mlb/tennis imports (F5).

CLI:  python -m domains.soccer.asof_features_gate
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from domains.soccer.ratings import walk_forward_goals
from scripts.platformkit.eval_gate.dm_test import diebold_mariano

_REPO = Path(__file__).resolve().parents[2]
_MATCHES = _REPO / "data/domains/soccer/matches.parquet"
_ASOF = _REPO / "data/domains/soccer/asof_features.parquet"

FEAT_COL = "diff_sot_for_asof"   # default candidate; parameterized for the sweep
MIN_PRIOR = 5          # both teams need >= N strictly-prior matches for "covered"
TRAIN_FRAC = 0.70      # leak-free time split (first 70% train, last 30% score)
EPS = 0.05             # DM significance threshold
BSS_MIN = 0.0          # base must carry non-degenerate skill vs the base rate


# --------------------------------------------------------------------------- #
# Inlined logistic helpers (F5: no cross-domain import; mirrors NBA/MLB/WTA gates)
# --------------------------------------------------------------------------- #

def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-7, 1 - 1e-7)
    return np.log(p / (1.0 - p))


def _brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _platt_fit(z: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    """1-feature Platt scaling: p = sigmoid(w*z + b) via L-BFGS on the NLL."""
    from scipy.optimize import minimize

    def _nll(par: np.ndarray) -> float:
        w, b = par
        p = np.clip(_sigmoid(w * z + b), 1e-7, 1 - 1e-7)
        return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))

    res = minimize(_nll, x0=np.array([1.0, 0.0]), method="L-BFGS-B",
                   bounds=[(0.05, 10.0), (-3.0, 3.0)])
    return float(res.x[0]), float(res.x[1])


# --------------------------------------------------------------------------- #
# Build the merged candidate frame (mirrors the NBA/MLB/WTA reclaim merge)
# --------------------------------------------------------------------------- #

def build_candidate_frame(
    matches: Optional[pd.DataFrame] = None,
    asof: Optional[pd.DataFrame] = None,
    feat_col: str = FEAT_COL,
) -> pd.DataFrame:
    """Left-merge ``feat_col`` onto leak-free Poisson p_over25, keyed on event_id.

    Returns a chronologically-sorted frame carrying: event_id, date,
    target_over25, p_base (Poisson P(over 2.5)), <feat_col>, home_n_prior,
    away_n_prior, _cov (bool).
    """
    mdf = matches.copy() if isinstance(matches, pd.DataFrame) else pd.read_parquet(_MATCHES)
    mdf["event_id"] = mdf["event_id"].astype(str)
    total_goals = pd.to_numeric(mdf["fthg"], errors="coerce") + pd.to_numeric(mdf["ftag"], errors="coerce")
    mdf["target_over25"] = (total_goals >= 3).astype(float)
    mdf = mdf[total_goals.notna()].reset_index(drop=True)

    wf = walk_forward_goals(mdf)[["event_id", "p_over25", "date"]].rename(
        columns={"p_over25": "p_base"})
    wf["event_id"] = wf["event_id"].astype(str)

    adf = asof.copy() if isinstance(asof, pd.DataFrame) else pd.read_parquet(_ASOF)
    _cols = ["event_id", feat_col, "home_n_prior", "away_n_prior"]
    adf = adf[[c for c in _cols if c in adf.columns]].copy()
    adf["event_id"] = adf["event_id"].astype(str)
    adf = adf.drop_duplicates("event_id", keep="first")

    out = mdf[["event_id", "target_over25"]].merge(wf, on="event_id", how="left")
    out = out.merge(adf, on="event_id", how="left")
    out["_cov"] = (
        (out["home_n_prior"].fillna(0) >= MIN_PRIOR)
        & (out["away_n_prior"].fillna(0) >= MIN_PRIOR)
        & out[feat_col].notna()
    )
    return out.sort_values("date").reset_index(drop=True)


# --------------------------------------------------------------------------- #
# One single-corpus walk-forward DM gate
# --------------------------------------------------------------------------- #

def _fit_2feature(
    lz_tr: np.ndarray, fz_tr: np.ndarray, y_tr: np.ndarray,
    lz_te: np.ndarray, fz_te: np.ndarray,
) -> Tuple[np.ndarray, float]:
    """Fit p = sigmoid(w1*base_logit + w2*feat_z + b) on train; predict on test."""
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
    df: pd.DataFrame, feat_col: str = FEAT_COL,
    train_frac: float = TRAIN_FRAC, eps: float = EPS,
) -> Dict:
    """Single-corpus 70/30 walk-forward DM gate: Poisson BASE vs Poisson+feature CAND."""
    n = len(df)
    split = int(n * train_frac)
    tr, te = df.iloc[:split], df.iloc[split:]
    y_tr = tr["target_over25"].values.astype(float)
    y_te = te["target_over25"].values.astype(float)

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

def _planted_null(df: pd.DataFrame, seed: int = 0, feat_col: str = FEAT_COL) -> Dict:
    """Shuffle the feature column (break its match alignment) -> must collapse."""
    rng = np.random.default_rng(seed)
    nd = df.copy()
    nd[feat_col] = rng.permutation(nd[feat_col].values)
    return _gate_once(nd, feat_col=feat_col)


def gate_feature(feat_col: str = FEAT_COL,
                  asof_path: Optional[str] = None, seed: int = 0) -> Dict:
    """Gate ONE leak-free soccer asof feature column (real + planted-null + truncation).

    ``asof_path`` lets a sweep point at a different asof_* parquet (e.g. the xg
    proxy file) for a different feature family; default None -> asof_features.parquet.
    """
    asof = pd.read_parquet(asof_path) if asof_path else None
    df = build_candidate_frame(asof=asof, feat_col=feat_col)
    n = len(df)
    cov_total = int(df["_cov"].sum())
    real = _gate_once(df, feat_col=feat_col)
    null = _planted_null(df, seed=seed, feat_col=feat_col)
    trunc = _gate_once(df, feat_col=feat_col, train_frac=TRAIN_FRAC * 0.90)
    return {
        "feature": feat_col, "n_rows": n, "cov_total": cov_total,
        "cov_pct": round(100.0 * cov_total / max(n, 1), 1),
        "real": real, "planted_null": null, "truncation": trunc,
    }


def run(seed: int = 0) -> Dict:
    """Full gate for the default candidate (diff_sot_for_asof)."""
    return gate_feature(FEAT_COL, seed=seed)


def main() -> int:
    res = run()
    print("=" * 72)
    print(f"soccer {FEAT_COL} CANDIDATE -- single-corpus WF gate")
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
