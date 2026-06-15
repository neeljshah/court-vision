"""scripts.platformkit.proof_tennis.fusion_tennis -- ATP complementary-signal fusion.

Does COMBINING complementary pregame signals (surface-Elo + leak-free as-of serve/return
form) close the gap to the devigged Pinnacle close on ATP match-win, beyond Elo alone?

Setup (all leak-free, walk-forward):
  * BASE      = surface-blended Elo win-prob, leak-free Platt-recalibrated (the W141 baseline,
                ~0.2177 Brier per the edge map / beat_the_close_ml).
  * FUSED     = a walk-forward LOGISTIC over [elo_logit, 5 as-of serve/return diffs]
                (diff_1st_win/ace_rate/1st_in/2nd_win/bp_saved_asof, all strictly prior-only,
                snapshot-before-update from domains.tennis.asof_features). The logistic weights
                are FIT ON THE TRAIN ERA (year <= TRAIN_YEAR_MAX) and applied FORWARD to the
                held-out test split -- never refit on the eval rows.
  * CLOSE     = devigged Pinnacle closing prob (~0.2028 Brier). The close is ONLY the comparison
                forecaster, NEVER a fusion input.

Honest expectation (edge map): the 5 as-of serve diffs all REJECT through the real gate
(player serve/return quality is already priced into Elo + the market) -> the fusion should be
ABSORBED (no narrowing of the gap to the close). That ABSORBED_NULL is the valuable, honest
result for an efficient pregame market, NOT a defect. We do NOT manufacture a narrows_gap.

LEAK GUARD (inherited from beat_the_close_ml): symmetric id-order p1_id<p2_id; label winner==1;
odds in the same id-order; Elo win-prob strictly walk-forward; as-of diffs strictly prior-only;
logistic fit on train-era rows only. No winner-order field is ever read.

INVARIANTS: never edit src/ or kernel/; recalibrator/fusion fit on TRAIN, scored on held-out;
<=300 LOC; ASCII output only.
Run: python -m scripts.platformkit.proof_tennis.fusion_tennis
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.tennis.elo_core import SURFACE_BLEND  # noqa: E402
from domains.tennis.elo_tune import _walk_forward_blend, platt_recalibrate  # noqa: E402

_MATCHES = _REPO / "data/domains/tennis/matches.parquet"
_ODDS = _REPO / "data/domains/tennis/odds.parquet"
_ASOF = _REPO / "data/domains/tennis/asof_features.parquet"
_TRAIN_YEAR_MAX = 2022  # fit Elo warm-up + Platt + fusion logistic <= this; test > this
_MIN_PRIOR = 5          # min prior matches for an as-of diff to be considered informative
_EPS = 1e-6

# The 5 complementary as-of serve/return diff signals (edge map: all REJECT individually).
_ASOF_DIFFS: Tuple[str, ...] = (
    "diff_1st_win_asof",
    "diff_ace_rate_asof",
    "diff_1st_in_asof",
    "diff_2nd_win_asof",
    "diff_bp_saved_asof",
)


def _brier_logloss(p: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    p = np.clip(p, _EPS, 1.0 - _EPS)
    return float(np.mean((p - y) ** 2)), float(
        -np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


def _ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    out = 0.0
    n = len(p)
    for b in range(bins):
        m = idx == b
        if m.any():
            out += (m.sum() / n) * abs(p[m].mean() - y[m].mean())
    return float(out)


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, _EPS, 1.0 - _EPS)
    return np.log(p / (1.0 - p))


def _devig_market(odds: pd.DataFrame) -> pd.DataFrame:
    """Devig Pinnacle close to P(p1 win) in id-order p1/p2 (outcome-independent)."""
    o = odds.dropna(subset=["ps_p1", "ps_p2"]).copy()
    o = o[(o["ps_p1"] > 1.0) & (o["ps_p2"] > 1.0)]
    imp1 = 1.0 / o["ps_p1"].to_numpy(float)
    imp2 = 1.0 / o["ps_p2"].to_numpy(float)
    o["p_market"] = imp1 / (imp1 + imp2)
    return o[["event_id", "p_market"]].drop_duplicates("event_id", keep="first")


def _load_asof() -> pd.DataFrame:
    """Load as-of diffs; zero-out (uninformative) where either player has < _MIN_PRIOR prior."""
    a = pd.read_parquet(_ASOF)
    have = [c for c in _ASOF_DIFFS if c in a.columns]
    a = a[["event_id", "p1_n_prior", "p2_n_prior"] + have].copy()
    thin = (a["p1_n_prior"] < _MIN_PRIOR) | (a["p2_n_prior"] < _MIN_PRIOR)
    for c in have:
        v = pd.to_numeric(a[c], errors="coerce").to_numpy(float)
        v = np.where(np.isnan(v), 0.0, v)       # NaN diff -> 0 (no information)
        v[thin.to_numpy()] = 0.0                # thin prior -> 0 (no information)
        a[c] = v
    a["event_id"] = a["event_id"].astype(str)
    a = a[["event_id"] + have].drop_duplicates("event_id", keep="first")
    return a, have


def _fit_logistic(X: np.ndarray, y: np.ndarray):
    """Standardise X (train stats) and fit logistic; return (model, mu, sd)."""
    from sklearn.linear_model import LogisticRegression
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd = np.where(sd < 1e-9, 1.0, sd)
    Xs = (X - mu) / sd
    clf = LogisticRegression(C=1.0, max_iter=2000)
    clf.fit(Xs, y)
    return clf, mu, sd


def run() -> Dict:
    if not _MATCHES.is_file() or not _ASOF.is_file():
        return {"ok": False, "status": "data_limited", "error": "missing tennis corpus/asof"}

    matches = pd.read_parquet(_MATCHES)
    odds = pd.read_parquet(_ODDS)
    asof, asof_cols = _load_asof()

    # --- leak-free walk-forward surface-blended Elo over the FULL history (train+test) ---
    wf = _walk_forward_blend(matches, blend=SURFACE_BLEND).copy()
    wf["event_id"] = wf["event_id"].astype(str)
    wf["elo_logit"] = _logit(wf["win_prob_p1"].to_numpy(float))

    # --- leak-free Platt base (W141 baseline) returns the held-out test rows only ---
    platt = platt_recalibrate(wf, train_year_max=_TRAIN_YEAR_MAX).copy()
    platt["event_id"] = platt["event_id"].astype(str)
    p_base = platt["win_prob_recal"].to_numpy(float)
    p_base = np.where(np.isnan(p_base), platt["win_prob_p1"].to_numpy(float), p_base)
    platt["p_base"] = np.clip(p_base, _EPS, 1.0 - _EPS)
    platt_base = platt[["event_id", "p_base"]].drop_duplicates("event_id", keep="first")

    # --- attach complementary as-of diffs + base prob (base only present on test rows) ---
    n0 = len(wf)
    df = wf.merge(asof, on="event_id", how="left")
    df = df.merge(platt_base, on="event_id", how="left")
    if len(df) != n0:
        return {"ok": False, "status": "data_limited",
                "error": "merge changed row count %d->%d" % (n0, len(df))}
    for c in asof_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    df["_year"] = pd.to_datetime(df["date"]).dt.year
    y_all = (df["winner"] == 1).to_numpy(float)
    feat_cols = ["elo_logit"] + asof_cols
    X_all = df[feat_cols].to_numpy(float)

    # --- FUSION logistic: fit on TRAIN era only, apply forward (NEVER refit on eval) ---
    train_mask = (df["_year"] <= _TRAIN_YEAR_MAX).to_numpy()
    test_mask = (df["_year"] > _TRAIN_YEAR_MAX).to_numpy()
    if train_mask.sum() < 200 or test_mask.sum() < 60:
        return {"ok": False, "status": "data_limited", "n_train": int(train_mask.sum()),
                "n_test": int(test_mask.sum())}
    clf, mu, sd = _fit_logistic(X_all[train_mask], y_all[train_mask])
    Xs_all = (X_all - mu) / sd
    df["p_fused"] = np.clip(clf.predict_proba(Xs_all)[:, 1], _EPS, 1.0 - _EPS)

    # Elo-only logistic control (recover an Elo-only logistic on the same train fit) to
    # isolate the as-of contribution from any logistic re-fit of the Elo logit itself.
    clf_e, mu_e, sd_e = _fit_logistic(X_all[train_mask][:, :1], y_all[train_mask])
    df["p_elo_only"] = np.clip(
        clf_e.predict_proba(((X_all[:, :1] - mu_e) / sd_e))[:, 1], _EPS, 1.0 - _EPS)

    # --- devigged Pinnacle close (comparison forecaster only) ---
    mkt = _devig_market(odds)
    mkt["event_id"] = mkt["event_id"].astype(str)
    df = df.merge(mkt, on="event_id", how="left")

    # --- held-out evaluation: rows with model+market available ---
    ev = df[df["_year"] > _TRAIN_YEAR_MAX].dropna(
        subset=["p_base", "p_fused", "p_market"]).reset_index(drop=True)
    n = len(ev)
    if n < 60:
        return {"ok": False, "status": "data_limited", "n": n}

    y = (ev["winner"] == 1).to_numpy(float)
    b_base, ll_base = _brier_logloss(ev["p_base"].to_numpy(float), y)
    b_fused, ll_fused = _brier_logloss(ev["p_fused"].to_numpy(float), y)
    b_elo_only, _ = _brier_logloss(ev["p_elo_only"].to_numpy(float), y)
    b_close, ll_close = _brier_logloss(ev["p_market"].to_numpy(float), y)

    e_base = _ece(ev["p_base"].to_numpy(float), y)
    e_fused = _ece(ev["p_fused"].to_numpy(float), y)

    gap_base = round(b_base - b_close, 4)     # >0 => close sharper than base
    gap_fused = round(b_fused - b_close, 4)   # >0 => close sharper than fused
    narrowing = round(gap_base - gap_fused, 4)  # >0 => fusion moved toward the close
    d_fused_base = round(b_fused - b_base, 4)   # <0 => fusion sharper than base

    # --- honest verdict classification ---
    if d_fused_base < -0.002 and gap_fused < gap_base - 0.002:
        kind = "narrows_gap"
        verdict = (f"NARROWS_GAP: fusing as-of serve/return into Elo cuts Brier "
                   f"{b_base:.4f}->{b_fused:.4f} and the gap to the close "
                   f"{gap_base:+}->{gap_fused:+}.")
    elif e_fused < e_base - 0.005 and abs(d_fused_base) <= 0.002:
        kind = "calibration_win"
        verdict = (f"CALIBRATION_WIN: ECE {e_base:.4f}->{e_fused:.4f} improves with Brier "
                   f"~flat ({b_base:.4f}->{b_fused:.4f}).")
    else:
        kind = "absorbed_null"
        verdict = (f"ABSORBED_NULL: fusing the 5 as-of serve/return diffs does NOT beat Elo "
                   f"(Brier {b_base:.4f}->{b_fused:.4f}, delta {d_fused_base:+}) nor narrow "
                   f"the gap to the close ({gap_base:+}->{gap_fused:+}); the market already "
                   f"prices serve/return form. Honest SUCCESS on an efficient pregame market.")

    # Logistic weights (standardised) for transparency on which signals the fit leaned on.
    weights = {feat_cols[i]: round(float(clf.coef_[0][i]), 4) for i in range(len(feat_cols))}

    return {
        "ok": True,
        "status": "ok",
        "n": n,
        "metric_name": "Brier",
        "base_brier": round(b_base, 4),
        "fused_brier": round(b_fused, 4),
        "elo_only_logistic_brier": round(b_elo_only, 4),
        "close_brier": round(b_close, 4),
        "base_logloss": round(ll_base, 4),
        "fused_logloss": round(ll_fused, 4),
        "close_logloss": round(ll_close, 4),
        "base_ece": round(e_base, 4),
        "fused_ece": round(e_fused, 4),
        "gap_base_to_close": gap_base,
        "gap_fused_to_close": gap_fused,
        "narrowing": narrowing,
        "fused_minus_base": d_fused_base,
        "asof_cols": list(asof_cols),
        "logistic_weights_std": weights,
        "verdict_kind": kind,
        "verdict": verdict,
        "note": "Leak-free WF Elo + prior-only as-of serve/return; fusion logistic fit on "
                "train era (<=%d), scored on held-out (>%d). Close is comparison only, never "
                "an input. No $ edge claimed; markets efficient." % (
                    _TRAIN_YEAR_MAX, _TRAIN_YEAR_MAX),
    }


def _main() -> int:
    rep = run()
    if not rep.get("ok"):
        print("status=%s %s" % (rep.get("status"), rep.get("error", "")))
        return 0
    print("=== ATP complementary fusion: Elo+as-of serve/return vs Elo base vs Pinnacle "
          "close (held-out n=%d, year>%d) ===" % (rep["n"], _TRAIN_YEAR_MAX))
    print("  %-26s %8s %8s %8s" % ("predictor", "Brier", "LogLoss", "ECE"))
    print("  %-26s %8.4f %8.4f %8.4f" % (
        "Pinnacle close", rep["close_brier"], rep["close_logloss"], float("nan")))
    print("  %-26s %8.4f %8.4f %8.4f" % (
        "Elo base (Platt)", rep["base_brier"], rep["base_logloss"], rep["base_ece"]))
    print("  %-26s %8.4f %8.4f %8.4f" % (
        "FUSED (Elo + as-of)", rep["fused_brier"], rep["fused_logloss"], rep["fused_ece"]))
    print("  %-26s %8.4f" % ("Elo-only logistic ctrl", rep["elo_only_logistic_brier"]))
    print("\ngap base->close: %+.4f   gap fused->close: %+.4f   narrowing: %+.4f   "
          "fused-base: %+.4f" % (rep["gap_base_to_close"], rep["gap_fused_to_close"],
                                 rep["narrowing"], rep["fused_minus_base"]))
    print("logistic weights (std): %s" % rep["logistic_weights_std"])
    print("VERDICT[%s]: %s" % (rep["verdict_kind"], rep["verdict"]))
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())


__all__ = ["run", "_brier_logloss", "_ece", "_devig_market", "_load_asof", "_fit_logistic"]
