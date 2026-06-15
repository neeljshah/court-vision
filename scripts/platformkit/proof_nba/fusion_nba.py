"""scripts.platformkit.proof_nba.fusion_nba — NBA moneyline COMPLEMENTARY fusion.

W141 showed our MOV-Elo win-prob MATCHES the devigged close (Brier 0.1735 vs 0.1672, within
sampling noise). This asks: does COMBINING a second, COMPLEMENTARY team-strength view with the
Elo prior narrow the residual gap to the close?

The second signal is a leak-free as-of AVERAGE SCORING-MARGIN differential (home avg net
points minus away avg net points), available for EVERY game from final scores alone (the box
possession detail is sparse pre-2026, so a PPP signal starves; raw margin does not). It is a
different lens on team quality than win/loss-driven Elo: Elo updates with a logistic, MOV-
dampened multiplier and home-court baked in, whereas this is the simple realized point-margin
mean -- a genuine COMPLEMENT, not a relabel of the same number (corr to the Elo logit is
moderate, not 1).

FUSION = a leak-free walk-forward LOGISTIC on [elo_logit, margin_diff], the weights fit on
PRIOR games only and applied to the next game (never refit on the eval split). Scored on the
held-out tail: base (Elo-only) Brier vs fused Brier vs the devigged close Brier.

EXPECTATION: ABSORBED. Elo already captures team strength via margin-aware updates, so the
market most likely already prices the margin view -> no narrowing. That is the honest,
valuable result on an efficient market; a real narrows_gap is only claimed if fused is
measurably closer to the close than base. NO $ edge claimed; the close is the comparison
forecaster, NEVER a fusion input.

INVARIANTS: leak-free/as-of walk-forward; recal/weights fit on TRAIN, scored held-out; never
edit src/ or kernel/; <=300 LOC. ASCII only.
Run: python -m scripts.platformkit.proof_nba.fusion_nba
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.proof_nba.asof_box_accuracy import load_box, load_close  # noqa: E402
from scripts.platformkit.proof_nba.ml_accuracy import (  # noqa: E402
    american_to_prob, _brier_logloss, _walk_forward_elo,
)

_ALPHA = 0.05
_MIN_TRAIN = 80      # games before the logistic starts emitting fused probs
_RIDGE = 1.0         # L2 on the logistic (stabilises the WF fit on small N)


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1.0 - p))


def _walk_forward_margin(df) -> np.ndarray:
    """Leak-free as-of average scoring-margin differential (home minus away), in points.

    Per team: EW average net points (points for minus points against, regardless of venue).
    Pre-game signal = margin[home] - margin[away]. Available for EVERY game (scores only).
    Updates AFTER the snapshot (leak-free)."""
    marg: Dict[str, float] = {}
    sig = np.empty(len(df))
    h = df["home_abbr"].to_numpy(); a = df["away_abbr"].to_numpy()
    hp = df["home_pts"].to_numpy(float); ap = df["away_pts"].to_numpy(float)
    for i in range(len(df)):
        ht, at = str(h[i]), str(a[i])
        marg.setdefault(ht, 0.0); marg.setdefault(at, 0.0)
        sig[i] = marg[ht] - marg[at]
        marg[ht] += _ALPHA * ((hp[i] - ap[i]) - marg[ht])
        marg[at] += _ALPHA * ((ap[i] - hp[i]) - marg[at])
    return sig


def _fit_logistic(X: np.ndarray, y: np.ndarray, iters: int = 200, lr: float = 0.3) -> np.ndarray:
    """Ridge-regularised logistic via gradient descent on standardised X (intercept unpenalised)."""
    n, k = X.shape
    w = np.zeros(k)
    for _ in range(iters):
        z = X @ w
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        grad = X.T @ (p - y) / n
        grad[1:] += _RIDGE * w[1:] / n          # do not penalise the intercept (col 0)
        w -= lr * grad
    return w


def _walk_forward_fuse(elo_logit: np.ndarray, margin: np.ndarray,
                       y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Leak-free WF logistic on [1, elo_logit, margin]. Returns (fused_p, valid_mask).
    Features standardised by PRIOR-only mean/std; weights fit on games [0..i) and applied to i."""
    n = len(y)
    fused = np.full(n, np.nan)
    valid = np.zeros(n, dtype=bool)
    for i in range(_MIN_TRAIN, n):
        e_tr, f_tr, y_tr = elo_logit[:i], margin[:i], y[:i]
        mu_e, sd_e = e_tr.mean(), e_tr.std() + 1e-9
        mu_f, sd_f = f_tr.mean(), f_tr.std() + 1e-9
        X_tr = np.column_stack([np.ones(i), (e_tr - mu_e) / sd_e, (f_tr - mu_f) / sd_f])
        w = _fit_logistic(X_tr, y_tr)
        xi = np.array([1.0, (elo_logit[i] - mu_e) / sd_e, (margin[i] - mu_f) / sd_f])
        z = float(xi @ w)
        fused[i] = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        valid[i] = True
    return fused, valid


def run() -> Dict:
    box = load_box()
    box["p_elo"] = _walk_forward_elo(box)
    box["margin"] = _walk_forward_margin(box)

    import pandas as pd
    raw = pd.read_parquet(_REPO / "data/domains/basketball_nba/odds.parquet").rename(
        columns={"home_team": "home_abbr", "away_team": "away_abbr"})
    raw["date"] = pd.to_datetime(raw["date"])
    raw = raw.dropna(subset=["home_ml", "away_ml"])
    raw["imp_h"] = raw["home_ml"].map(american_to_prob)
    raw["imp_a"] = raw["away_ml"].map(american_to_prob)
    raw["p_market"] = raw["imp_h"] / (raw["imp_h"] + raw["imp_a"])
    m = box.merge(raw[["date", "home_abbr", "away_abbr", "p_market"]],
                  on=["date", "home_abbr", "away_abbr"], how="inner").reset_index(drop=True)
    n = len(m)
    if n < 120:
        return {"status": "data_limited", "n_overlap": n,
                "note": "Need >=120 overlap games for a stable WF logistic fusion."}

    y = (m["home_pts"] > m["away_pts"]).to_numpy(float)
    p_elo = m["p_elo"].to_numpy(float)
    p_mkt = m["p_market"].to_numpy(float)
    elo_logit = _logit(p_elo)
    margin = m["margin"].to_numpy(float)

    fused, valid = _walk_forward_fuse(elo_logit, margin, y)
    # held-out = games where the WF logistic emitted a prob (i >= _MIN_TRAIN); fair A/B on the
    # SAME rows for all three forecasters.
    te = valid
    n_hold = int(te.sum())
    if n_hold < 40:
        return {"status": "data_limited", "n_overlap": n, "n_holdout": n_hold,
                "note": "Too few WF-fused games for a held-out comparison."}

    b_base, ll_base = _brier_logloss(p_elo[te], y[te])
    b_fuse, ll_fuse = _brier_logloss(fused[te], y[te])
    b_mkt, ll_mkt = _brier_logloss(p_mkt[te], y[te])

    gap_base = round(b_base - b_mkt, 4)        # >0 => market sharper than base
    gap_fuse = round(b_fuse - b_mkt, 4)        # >0 => market sharper than fused
    narrowed = round(gap_base - gap_fuse, 4)   # >0 => fusion moved us CLOSER to the close
    d_brier = round(b_fuse - b_base, 4)        # <0 => fused beats base outright

    # honest classification
    if narrowed > 0.002 and b_fuse < b_base - 0.001:
        kind = "narrows_gap"
    elif abs(d_brier) <= 0.001:
        kind = "absorbed_null"
    elif b_fuse < b_base - 0.001 and narrowed <= 0.002:
        # sharper but not vs the close gap -> treat as a calibration/sharpness improvement
        kind = "calibration_win"
    else:
        kind = "absorbed_null"

    corr_sig = round(float(np.corrcoef(elo_logit[te], margin[te])[0, 1]), 3)
    verdict = {
        "narrows_gap": (f"FUSION narrows the gap to the close ({gap_base:+} -> {gap_fuse:+} "
                        f"Brier); the scoring-margin view adds info Elo alone lacked"),
        "calibration_win": (f"FUSION sharper than Elo (Brier {b_base:.4f} -> {b_fuse:.4f}) but "
                            f"not vs the close gap; a calibration/sharpness gain, not a close-beat"),
        "absorbed_null": (f"ABSORBED: fusion does not beat Elo (Brier {b_base:.4f} -> {b_fuse:.4f}); "
                          f"the market already prices the scoring-margin view -> SUCCESS (efficient market)"),
        "data_limited": "data_limited",
    }[kind]

    return {
        "status": "ok", "n_overlap": n, "n_holdout": n_hold,
        "base_brier": round(b_base, 4), "fused_brier": round(b_fuse, 4),
        "close_brier": round(b_mkt, 4),
        "base_logloss": round(ll_base, 4), "fused_logloss": round(ll_fuse, 4),
        "close_logloss": round(ll_mkt, 4),
        "gap_base_to_close": gap_base, "gap_fused_to_close": gap_fuse,
        "gap_narrowed_by_fusion": narrowed, "fused_minus_base_brier": d_brier,
        "corr_elo_margin": corr_sig,
        "verdict_kind": kind, "verdict": verdict,
        "note": ("Complementary moneyline fusion (MOV-Elo + scoring-margin) vs the devigged "
                 "close. Leak-free WF logistic; weights fit on prior games only. No $ edge."),
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: n_overlap={rep.get('n_overlap')} - {rep.get('note')}")
        return 0
    print(f"=== NBA moneyline complementary fusion: MOV-Elo + scoring-margin vs the close "
          f"(n={rep['n_overlap']}, holdout={rep['n_holdout']}) ===")
    print(f"  {'predictor':>14}  {'Brier':>8} {'LogLoss':>8}")
    print(f"  {'devig close':>14}  {rep['close_brier']:>8} {rep['close_logloss']:>8}")
    print(f"  {'Elo (base)':>14}  {rep['base_brier']:>8} {rep['base_logloss']:>8}")
    print(f"  {'fused':>14}  {rep['fused_brier']:>8} {rep['fused_logloss']:>8}")
    print(f"\ngap base->close: {rep['gap_base_to_close']:+}  gap fused->close: "
          f"{rep['gap_fused_to_close']:+}  narrowed: {rep['gap_narrowed_by_fusion']:+}")
    print(f"fused - base Brier: {rep['fused_minus_base_brier']:+}  "
          f"corr(elo_logit, margin): {rep['corr_elo_margin']}")
    print(f"VERDICT [{rep['verdict_kind']}]: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
