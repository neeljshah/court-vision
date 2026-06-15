"""scripts.platformkit.proof_mlb.fusion_mlb — MLB moneyline COMPLEMENTARY fusion.

Question: does combining two *complementary* pregame signals -- team strength (leak-free
MOV-aware Elo) + starting-pitcher form (domains.mlb.asof_sp_form.sp_first6_diff_ew) --
via a leak-free walk-forward logistic narrow the gap to the devigged closing line?

The close already prices the announced starting pitcher, so the edge map expects this to be
NEUTRAL: SP-form is mostly *absorbed* by the market (and partly by Elo's team ratings). The
honest, valuable outcome here is `absorbed_null` -- we do NOT manufacture a narrows_gap.

Method (leak-free):
  * Elo p_home from the SAME engine the headline proof scores (beat_the_close_ml._replay),
    so the Elo-only baseline here == the published 0.2429 Brier (parity).
  * sp_first6_diff_ew is snapshot-before-update (asof_sp_form leak contract).
  * Fusion = logistic on [elo_logit, z(sp_first6_diff_ew)], fit on the TRAIN split
    (first half) ONLY, scored on the held-out SECOND HALF. The standardizer (mean/std)
    is also fit on TRAIN only. The close is the comparison forecaster, NEVER an input.
  * Eval rows missing SP-form fall back to the Elo-only probability, so base / fused / close
    are scored on the IDENTICAL holdout rows (a fair head-to-head).

Reports base Brier vs fused Brier vs close Brier (+ logloss/ECE) and an honest verdict_kind:
  narrows_gap | calibration_win | absorbed_null | data_limited.

INVARIANTS: never edit src/ or kernel/; <=300 LOC; calibration/accuracy only, no $ edge.
Run: python -m scripts.platformkit.proof_mlb.fusion_mlb
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.proof_mlb.beat_the_close_ml import (  # noqa: E402
    _replay, american_to_prob,
)
from domains.mlb.asof_sp_form import build_sp_form_features  # noqa: E402

_GAMES = _REPO / "data/domains/mlb/games.parquet"
_ODDS = _REPO / "data/domains/mlb/odds.parquet"

_CLIP = 1e-6


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, _CLIP, 1 - _CLIP)
    return np.log(p / (1 - p))


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((np.clip(p, _CLIP, 1 - _CLIP) - y) ** 2))


def _logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, _CLIP, 1 - _CLIP)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _ece(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    tot = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (p >= lo) & (p < hi)
        if m.sum() == 0:
            continue
        tot += m.sum() * abs(y[m].mean() - p[m].mean())
    return float(tot / len(y))


# ---------------------------------------------------------------------------
# 2-feature logistic via Newton-Raphson (no sklearn dependency)
# ---------------------------------------------------------------------------

def _fit_logistic(X: np.ndarray, y: np.ndarray, iters: int = 50) -> np.ndarray:
    """Newton-Raphson logistic regression. X has an intercept column. Returns weights."""
    w = np.zeros(X.shape[1])
    ridge = 1e-4 * np.eye(X.shape[1])
    for _ in range(iters):
        p = _sigmoid(X @ w)
        grad = X.T @ (p - y)
        W = p * (1 - p)
        H = X.T @ (X * W[:, None]) + ridge
        try:
            step = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        w_new = w - step
        if np.max(np.abs(w_new - w)) < 1e-8:
            w = w_new
            break
        w = w_new
    return w


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> Dict:
    import pandas as pd

    games = pd.read_parquet(_GAMES).sort_values(
        ["date", "game_seq", "event_id"]).reset_index(drop=True)
    p_elo, _ = _replay(games)
    games = games.copy()
    games["p_elo"] = p_elo

    # devig close -> market P(home win)
    odds = pd.read_parquet(_ODDS)[
        ["event_id", "ml_close_home_am", "ml_close_away_am"]].dropna(
        subset=["ml_close_home_am", "ml_close_away_am"]).copy()
    odds["imp_h"] = odds["ml_close_home_am"].map(american_to_prob)
    odds["imp_a"] = odds["ml_close_away_am"].map(american_to_prob)
    odds["p_market"] = odds["imp_h"] / (odds["imp_h"] + odds["imp_a"])

    # complementary signal: starting-pitcher form
    spf = build_sp_form_features()[["event_id", "sp_first6_diff_ew"]]

    m = games.merge(odds[["event_id", "p_market"]], on="event_id", how="inner")
    m = m.merge(spf, on="event_id", how="left")
    m = m.sort_values(["date", "game_seq", "event_id"]).reset_index(drop=True)
    n = len(m)
    if n < 200:
        return {"status": "data_limited", "n": n,
                "verdict_kind": "data_limited"}

    y = (m["home_runs"] > m["away_runs"]).to_numpy(float)
    p_elo = m["p_elo"].to_numpy(float)
    p_mkt = m["p_market"].to_numpy(float)
    elo_logit = _logit(p_elo)
    sp = m["sp_first6_diff_ew"].to_numpy(float)
    has_sp = ~np.isnan(sp)

    mid = n // 2
    tr = slice(0, mid)
    te = slice(mid, n)

    # standardizer fit on TRAIN rows that have SP-form ONLY (no eval leakage)
    sp_tr_mask = has_sp[tr]
    sp_tr = sp[tr][sp_tr_mask]
    if sp_tr.size < 50:
        return {"status": "data_limited", "n": n, "n_train_sp": int(sp_tr.size),
                "verdict_kind": "data_limited"}
    sp_mu = float(sp_tr.mean())
    sp_sd = float(sp_tr.std()) or 1.0

    def _z(v: np.ndarray) -> np.ndarray:
        return (v - sp_mu) / sp_sd

    # ----- fit fusion logistic on TRAIN rows that HAVE sp-form -----
    Xtr = np.column_stack([
        np.ones(sp_tr_mask.sum()),
        elo_logit[tr][sp_tr_mask],
        _z(sp[tr][sp_tr_mask]),
    ])
    ytr = y[tr][sp_tr_mask]
    w = _fit_logistic(Xtr, ytr)

    # ----- score on the held-out SECOND HALF -----
    yh = y[te]
    p_base_te = p_elo[te]                       # Elo-only baseline (parity w/ headline)
    p_mkt_te = p_mkt[te]

    # fused: where SP-form present use the 2-feature logistic; else fall back to Elo-only.
    p_fused_te = p_base_te.copy()
    sp_te_mask = has_sp[te]
    if sp_te_mask.sum() > 0:
        Xte = np.column_stack([
            np.ones(sp_te_mask.sum()),
            elo_logit[te][sp_te_mask],
            _z(sp[te][sp_te_mask]),
        ])
        p_fused_te[sp_te_mask] = _sigmoid(Xte @ w)

    b_base = _brier(p_base_te, yh)
    b_fused = _brier(p_fused_te, yh)
    b_mkt = _brier(p_mkt_te, yh)
    ll_base = _logloss(p_base_te, yh)
    ll_fused = _logloss(p_fused_te, yh)
    ll_mkt = _logloss(p_mkt_te, yh)
    ece_base = _ece(p_base_te, yh)
    ece_fused = _ece(p_fused_te, yh)

    gap_base = b_base - b_mkt                   # >0 => market sharper
    gap_fused = b_fused - b_mkt
    narrow = gap_base - gap_fused               # >0 => fusion moved us TOWARD the close

    # Sub-population where the signal actually applies (rows with SP-form on eval)
    sub_base = sub_fused = float("nan")
    if sp_te_mask.sum() >= 100:
        sub_base = _brier(p_base_te[sp_te_mask], yh[sp_te_mask])
        sub_fused = _brier(p_fused_te[sp_te_mask], yh[sp_te_mask])

    # ----- honest verdict -----
    # thresholds: a real combine win must move materially toward the close (>0.0010 Brier)
    if narrow > 0.0010 and b_fused < b_base - 0.0005:
        vk = "narrows_gap"
        verdict = (f"NARROWS GAP: fusion Brier {b_fused:.4f} < Elo {b_base:.4f}; "
                   f"gap to close {gap_base:+.4f} -> {gap_fused:+.4f}")
    elif abs(b_fused - b_base) <= 0.0005 and ece_fused < ece_base - 0.002:
        vk = "calibration_win"
        verdict = (f"CALIBRATION WIN: Brier flat ({b_base:.4f}->{b_fused:.4f}) but "
                   f"ECE {ece_base:.4f}->{ece_fused:.4f}")
    else:
        vk = "absorbed_null"
        verdict = (f"ABSORBED NULL (SUCCESS): SP-form gives no material lift "
                   f"(Brier {b_base:.4f}->{b_fused:.4f}, narrow {narrow:+.4f}); "
                   f"the close already prices the starter.")

    return {
        "status": "ok", "verdict_kind": vk, "verdict": verdict,
        "n": n, "n_holdout": n - mid,
        "n_eval_with_sp": int(sp_te_mask.sum()),
        "coverage_eval": round(float(sp_te_mask.mean()), 3),
        "fusion_weights": {"intercept": round(float(w[0]), 4),
                           "elo_logit": round(float(w[1]), 4),
                           "z_sp_diff": round(float(w[2]), 4)},
        "close_brier": round(b_mkt, 4),
        "base_brier": round(b_base, 4),
        "fused_brier": round(b_fused, 4),
        "close_logloss": round(ll_mkt, 4),
        "base_logloss": round(ll_base, 4),
        "fused_logloss": round(ll_fused, 4),
        "base_ece": round(ece_base, 4),
        "fused_ece": round(ece_fused, 4),
        "gap_base_to_close": round(gap_base, 4),
        "gap_fused_to_close": round(gap_fused, 4),
        "narrow": round(narrow, 4),
        "sub_base_brier": (round(sub_base, 4) if sub_base == sub_base else None),
        "sub_fused_brier": (round(sub_fused, 4) if sub_fused == sub_fused else None),
        "note": ("Complementary fusion (Elo + SP-form) vs the devigged close on real "
                 "outcomes. Leak-free walk-forward; logistic + standardizer fit on TRAIN, "
                 "scored on held-out half; close NEVER an input. No $ edge claimed."),
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: n={rep.get('n')}")
        return 0
    print(f"=== MLB moneyline complementary fusion: Elo + SP-form vs the devigged close "
          f"(n={rep['n']}, holdout={rep['n_holdout']}, "
          f"eval-with-SP={rep['n_eval_with_sp']}/{rep['coverage_eval']}) ===")
    print(f"  {'predictor':>13}  {'Brier':>8} {'LogLoss':>8} {'ECE':>8}")
    print(f"  {'devig close':>13}  {rep['close_brier']:>8} {rep['close_logloss']:>8} "
          f"{'-':>8}")
    print(f"  {'Elo (base)':>13}  {rep['base_brier']:>8} {rep['base_logloss']:>8} "
          f"{rep['base_ece']:>8}")
    print(f"  {'Elo + SP-form':>13}  {rep['fused_brier']:>8} {rep['fused_logloss']:>8} "
          f"{rep['fused_ece']:>8}")
    print(f"\ngap to close: base {rep['gap_base_to_close']:+}  ->  fused "
          f"{rep['gap_fused_to_close']:+}  (narrow {rep['narrow']:+})")
    if rep["sub_base_brier"] is not None:
        print(f"sub-population (eval rows WITH SP-form): Elo {rep['sub_base_brier']} -> "
              f"fused {rep['sub_fused_brier']}")
    print(f"fusion weights: {rep['fusion_weights']}")
    print(f"VERDICT [{rep['verdict_kind']}]: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
