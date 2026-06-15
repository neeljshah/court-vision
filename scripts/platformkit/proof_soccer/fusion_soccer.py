"""scripts.platformkit.proof_soccer.fusion_soccer — COMPLEMENTARY-signal fusion vs the close.

Soccer O/U-2.5 complementary fusion.  The composed walk-forward Poisson+finishing engine
(domains.soccer.finishing_prior.walk_forward_finishing_prior -> p_over25_adj) is BLENDED with a
SECOND, structurally complementary signal: leak-free as-of shots-on-target FORM
(domains.soccer.asof_features diff_sot_for_asof, a free xG-quality proxy) via a leak-free
logistic fusion.  The fused forecaster is compared, on a held-out chronological split, against
(a) the engine baseline (Platt-recalibrated, ~0.2465 Brier) and (b) the devigged Pinnacle
CLOSING O/U-2.5 price (~0.2390 Brier).

WHY this is a real test, not a fishing expedition: the engine prices goal RATES; the as-of SoT
signal prices recent shot-VOLUME/quality form, which the engine's slow EW ratings may lag.  If
that form carries incremental, leak-free O/U information the market has NOT already priced, the
fusion narrows the gap to the close.  The edge map says SoT-form PASSES accuracy WF but is
ABSORBED on CLV -> the honest expectation is calibration_win or absorbed_null: the close (and the
engine's own lambdas) already price SoT form, so the fusion adds little.  An ABSORBED null is a
SUCCESS (markets efficient); we do NOT manufacture a narrows_gap.

LEAK-FREE DISCIPLINE (binding):
  - The engine prob is a STRICTLY pre-match walk-forward snapshot (finishing_prior).
  - The as-of SoT form is prior-only (snapshot-before-update; asof_features).
  - The fusion logistic weights AND the feature standardizer are FIT on the first chronological
    half (TRAIN) and APPLIED to the held-out second half (TEST); never refit on the eval split.
  - The Platt baseline recalibrator is likewise fit on TRAIN, applied to TEST.
  - The closing line is the COMPARISON forecaster only, NEVER an input to any fit.
  - Rows with no as-of history (n_prior==0 -> NaN form) fall back to the engine-only logit
    (the standardized form term contributes 0), so coverage gaps cannot leak or inflate.

INVARIANTS: never edit src/ or kernel/; reuse domains.soccer (read-only); <=300 LOC; ASCII only.
Run: python -m scripts.platformkit.proof_soccer.fusion_soccer
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import pandas as pd  # noqa: E402

from domains.soccer.finishing_prior import walk_forward_finishing_prior  # noqa: E402

_MATCHES = _REPO / "data/domains/soccer/matches.parquet"
_STATS = _REPO / "data/domains/soccer/match_stats.parquet"
_ODDS = _REPO / "data/domains/soccer/odds.parquet"
_ASOF = _REPO / "data/domains/soccer/asof_features.parquet"

_EPS = 1e-6
_FUSE_COL = "diff_sot_for_asof"  # home-away prior SoT-for diff (free xG-quality proxy)
_ECE_BINS = 10


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #

def _brier(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, _EPS, 1 - _EPS)
    return float(np.mean((p - y) ** 2))


def _ece(p: np.ndarray, y: np.ndarray, bins: int = _ECE_BINS) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    e = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            e += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(e)


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, _EPS, 1 - _EPS)
    return np.log(p / (1.0 - p))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


# --------------------------------------------------------------------------- #
# Leak-free logistic fits (numpy GD; no sklearn dependency)
# --------------------------------------------------------------------------- #

def _fit_logistic(X: np.ndarray, y: np.ndarray, iters: int = 600,
                  lr: float = 0.3, l2: float = 1e-4) -> np.ndarray:
    """Fit w (incl. bias col) on X (n,k) -> y via GD on log-loss.  X must include a 1s column."""
    n, k = X.shape
    w = np.zeros(k, dtype=float)
    for _ in range(iters):
        q = _sigmoid(X @ w)
        g = X.T @ (q - y) / n + l2 * w
        w -= lr * g
    return w


def _fit_platt(p: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    """Platt a,b on logit(p): returns (a,b) s.t. cal = sigmoid(a*logit(p)+b)."""
    z = _logit(p).reshape(-1, 1)
    X = np.hstack([z, np.ones_like(z)])
    w = _fit_logistic(X, y)
    return float(w[0]), float(w[1])


def _apply_platt(p: np.ndarray, a: float, b: float) -> np.ndarray:
    return _sigmoid(a * _logit(p) + b)


# --------------------------------------------------------------------------- #
# Forecast assembly
# --------------------------------------------------------------------------- #

def _build_model_forecast() -> pd.DataFrame:
    """Walk-forward composed engine: ratings -> finishing prior -> scoreline engine."""
    matches = pd.read_parquet(_MATCHES)
    stats = pd.read_parquet(_STATS)
    wf = walk_forward_finishing_prior(matches, stats, rho=0.0).copy()
    if "target_over25" not in wf.columns:
        wf["target_over25"] = ((wf["fthg"] + wf["ftag"]) >= 3).astype(float)
    wf = wf[wf["target_over25"].notna()].copy()
    wf["p_model_raw"] = wf["p_over25_adj"].astype(float)
    return wf[["event_id", "date", "p_model_raw", "target_over25"]]


def _devig(odds_a: np.ndarray, odds_b: np.ndarray) -> np.ndarray:
    ia, ib = 1.0 / odds_a, 1.0 / odds_b
    return ia / (ia + ib)


def _assemble() -> pd.DataFrame:
    """Merge engine forecast + devigged close + as-of SoT form, sorted chronologically."""
    model = _build_model_forecast()

    odds = pd.read_parquet(_ODDS)
    odds = odds.dropna(subset=["pc_over", "pc_under"]).copy()
    odds = odds[(odds["pc_over"] > 1.0) & (odds["pc_under"] > 1.0)]
    odds["p_close"] = _devig(odds["pc_over"].to_numpy(float),
                             odds["pc_under"].to_numpy(float))

    asof = pd.read_parquet(_ASOF)
    asof["event_id"] = asof["event_id"].astype(str)
    asof = asof[["event_id", _FUSE_COL, "home_n_prior", "away_n_prior"]].copy()

    model["event_id"] = model["event_id"].astype(str)
    m = model.merge(odds[["event_id", "p_close"]], on="event_id", how="inner")
    m = m.merge(asof, on="event_id", how="left")
    m["date"] = pd.to_datetime(m["date"])
    m = m.sort_values("date", kind="mergesort").reset_index(drop=True)
    m = m.dropna(subset=["p_model_raw", "p_close", "target_over25"]).reset_index(drop=True)
    return m


# --------------------------------------------------------------------------- #
# The fusion test
# --------------------------------------------------------------------------- #

def run() -> Dict:
    if not (_MATCHES.exists() and _ODDS.exists() and _ASOF.exists()):
        return {"status": "data_missing", "n": 0}

    m = _assemble()
    n = len(m)
    if n < 400:
        return {"status": "data_limited", "n": n}

    y = m["target_over25"].to_numpy(float)
    p_raw = m["p_model_raw"].to_numpy(float)
    p_close = m["p_close"].to_numpy(float)
    form = m[_FUSE_COL].to_numpy(float)

    mid = n // 2
    tr, te = slice(0, mid), slice(mid, n)

    # --- Baseline: engine + leak-free Platt (fit TRAIN, apply TEST) ---
    a, b = _fit_platt(p_raw[tr], y[tr])
    p_base = _apply_platt(p_raw, a, b)

    # --- As-of form: standardize on TRAIN-only finite rows; NaN -> 0 (engine-only fallback) ---
    f_tr = form[tr]
    f_tr_fin = f_tr[np.isfinite(f_tr)]
    mu = float(np.mean(f_tr_fin)) if f_tr_fin.size else 0.0
    sd = float(np.std(f_tr_fin)) if f_tr_fin.size else 1.0
    sd = sd if sd > _EPS else 1.0
    form_z = (form - mu) / sd
    form_z = np.where(np.isfinite(form_z), form_z, 0.0)  # no-history -> engine-only
    cov = float(np.mean(np.isfinite(form)))

    # --- Fusion: logistic on [engine logit, standardized form]; fit TRAIN, apply TEST ---
    z_eng = _logit(p_raw)
    X = np.column_stack([z_eng, form_z, np.ones(n)])
    w = _fit_logistic(X[tr], y[tr])
    p_fused = _sigmoid(X @ w)

    # Held-out scoring
    b_base = _brier(p_base[te], y[te])
    b_fused = _brier(p_fused[te], y[te])
    b_close = _brier(p_close[te], y[te])
    e_base = _ece(p_base[te], y[te])
    e_fused = _ece(p_fused[te], y[te])

    gap_base = round(b_base - b_close, 4)    # engine baseline gap to close (>0 = close sharper)
    gap_fused = round(b_fused - b_close, 4)  # fused gap to close
    narrowing = round(gap_base - gap_fused, 4)  # >0 = fusion moved toward the close
    fused_w = round(float(w[1]), 4)  # learned weight on the standardized form term

    # --- Honest verdict classification ---
    if narrowing >= 0.002 and b_fused < b_base - 0.0005:
        kind = "narrows_gap"
        verdict = (f"FUSION NARROWS THE GAP: fused Brier {round(b_fused,4)} < base "
                   f"{round(b_base,4)}; gap to close {gap_base:+} -> {gap_fused:+} "
                   f"(narrowed {narrowing}). As-of SoT form carries incremental, "
                   f"leak-free O/U info beyond the engine.")
    elif (e_fused < e_base - 0.003) and abs(b_fused - b_base) <= 0.0015:
        kind = "calibration_win"
        verdict = (f"CALIBRATION WIN: ECE {round(e_base,4)} -> {round(e_fused,4)} with "
                   f"Brier ~flat ({round(b_base,4)} -> {round(b_fused,4)}). The fusion "
                   f"sharpens reliability but does not move closer to the close.")
    else:
        kind = "absorbed_null"
        verdict = (f"ABSORBED NULL (SUCCESS): fusion does not beat the engine baseline "
                   f"(fused {round(b_fused,4)} vs base {round(b_base,4)}; gap to close "
                   f"{gap_fused:+} vs {gap_base:+}). The market AND the engine's lambdas "
                   f"already price as-of SoT form (learned form weight {fused_w}); the "
                   f"second signal is redundant. Markets efficient.")

    return {
        "status": "ok", "market": "over_2.5", "fuse_col": _FUSE_COL,
        "n": n, "n_holdout": n - mid, "asof_coverage": round(cov, 4),
        "base_brier": round(b_base, 4), "fused_brier": round(b_fused, 4),
        "close_brier": round(b_close, 4),
        "base_brier_raw": round(_brier(p_raw[te], y[te]), 4),
        "base_ece": round(e_base, 4), "fused_ece": round(e_fused, 4),
        "gap_base_to_close": gap_base, "gap_fused_to_close": gap_fused,
        "narrowing": narrowing, "fused_form_weight": fused_w,
        "platt_a": round(a, 4), "platt_b": round(b, 4),
        "base_rate_over25": round(float(np.mean(y[te])), 4),
        "verdict_kind": kind, "verdict": verdict,
        "note": ("Leak-free complementary fusion: composed Poisson+finishing engine logit + "
                 "as-of SoT-form (diff_sot_for_asof), logistic weights+standardizer fit on "
                 "TRAIN, scored on held-out TEST, vs the devigged Pinnacle close. The close is "
                 "the comparison forecaster only, never an input. No $ edge claimed."),
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: n={rep.get('n')}")
        return 0
    print(f"=== Soccer O/U-2.5 COMPLEMENTARY FUSION (engine + as-of SoT form) "
          f"(n={rep['n']}, holdout={rep['n_holdout']}, asof_cov={rep['asof_coverage']}) ===")
    print(f"  {'predictor':>26}  {'Brier':>8}  {'ECE':>7}")
    print(f"  {'devig Pinnacle close':>26}  {rep['close_brier']:>8}  {'-':>7}")
    print(f"  {'engine baseline (Platt)':>26}  {rep['base_brier']:>8}  {rep['base_ece']:>7}")
    print(f"  {'engine + SoT-form FUSION':>26}  {rep['fused_brier']:>8}  {rep['fused_ece']:>7}")
    print(f"\ngap to close: base {rep['gap_base_to_close']:+}  fused "
          f"{rep['gap_fused_to_close']:+}  (narrowing {rep['narrowing']:+})")
    print(f"learned form weight: {rep['fused_form_weight']}  |  "
          f"base-rate(over)={rep['base_rate_over25']}")
    print(f"VERDICT [{rep['verdict_kind']}]: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())


__all__ = ["run", "_assemble", "_build_model_forecast", "_fit_logistic",
           "_fit_platt", "_brier", "_ece"]
