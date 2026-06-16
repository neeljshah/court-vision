"""domains.tennis.predictor_helpers — recalibration / serve-prob math for TennisPredictor.

Behavior-preserving extraction of the in-game / recalibration helper logic out of
domains.tennis.predictor (the file was over the 300-LOC cap). These are pure functions
(plus the two corpus-fit recalibrators) that the TennisPredictor class delegates to; the
public methods (predict, predict_live, to_jd) keep identical signatures and numeric output.

LEAK / CALIBRATION HONESTY notes live with the callers in predictor.py: the pregame Platt is
fit on year<=_TRAIN_YEAR_MAX; the W156 in-game Platt is refit on the WHOLE corpus (leak-free
ONLY for a genuinely FUTURE live match, NOT a held-out evaluation -- the ECE 0.043->0.006
figure comes from the separate chronological split in proof_tennis.ingame_calib).

INVARIANTS: never edit src/ or kernel/; reuse the domain builders; <=300 LOC.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from domains.tennis.elo_core import SURFACE_BLEND
from domains.tennis.elo_tune import _walk_forward_blend

_TRAIN_YEAR_MAX = 2022          # Platt/temperature fit window (matches the proof modules)
_BASE_HOLD = 0.62               # match_engine's typical ATP hold; we shape around it
_WTA_T = 1.36                   # proof_tennis.wta_temp_live fitted temperature (T>1 = overconfident)
_EPS = 1e-6
# W156 reference in-game recalibrator (leak-free Platt-on-logit from proof_tennis.ingame_accuracy,
# ECE 0.043->0.006). We REFIT on ALL-PRIOR history at build time; this is the data-limited fallback.
_W156_INGAME_PLATT = (0.7324, 0.5517)


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, _EPS, 1.0 - _EPS)
    return np.log(p / (1.0 - p))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def fit_platt(matches: pd.DataFrame) -> Optional[tuple]:
    """Leak-free pregame Platt (a,b) on the Elo logit, fit on year<=TRAIN_YEAR_MAX rows.
    p_cal=sigmoid(a+b*logit(p_raw)); None if data-limited. Uses id-order win_prob_p1 +
    winner==1 as a TARGET only (NO winner-order feature)."""
    try:
        from sklearn.linear_model import LogisticRegression
    except ImportError:
        return None
    wf = _walk_forward_blend(matches, SURFACE_BLEND)
    yr = pd.to_datetime(wf["date"]).dt.year
    tr = wf[yr <= _TRAIN_YEAR_MAX]
    if len(tr) < 200:
        return None
    x = _logit(tr["win_prob_p1"].to_numpy(float)).reshape(-1, 1)
    y = (tr["winner"] == 1).to_numpy(float)
    if y.sum() == 0 or y.sum() == len(y):
        return None
    clf = LogisticRegression(C=1e6, solver="lbfgs", max_iter=500).fit(x, y)
    return float(clf.intercept_[0]), float(clf.coef_[0, 0])


def fit_ingame_recal(matches: pd.DataFrame) -> tuple:
    """Refit the W156 in-game recalibrator (Platt-on-logit) on the WHOLE corpus.
    Reconstructs the SAME COMBINED after-set-1 forecaster proof_tennis.ingame_accuracy
    validated (walk-forward Elo prior -> race-to-N repricer + realized 1-0 set lead) paired
    with the match outcome; fits Platt (a,b) so p_cal=sigmoid(a*logit(p)+b).
    FIT SCOPE: this walks EVERY row of the corpus (not an as-of / held-out tail), so the
    Platt params see all historical matches. That is leak-free ONLY for a genuinely FUTURE
    live match (the predictor's intended use -- none of the fitted matches is the one being
    priced); it is NOT a held-out evaluation, and the ECE 0.043->0.006 claim is NOT measured
    here -- that comes from the separate chronological train/eval split in
    proof_tennis.ingame_calib. Reference fallback (_W156_INGAME_PLATT) if data-limited
    (<200 rows) or helpers are unavailable."""
    try:
        from scripts.platformkit.proof_tennis.ingame_accuracy import (  # noqa: PLC0415
            _parse_sets, _p_set_from_match, _reprice_leader)
        from scripts.platformkit.proof_tennis.ingame_calib import _fit_platt  # noqa: PLC0415
        wf = _walk_forward_blend(matches, SURFACE_BLEND).reset_index(drop=True)
    except Exception:  # noqa: BLE001 - missing helper / data-limited -> reference params
        return _W156_INGAME_PLATT
    preds: List[float] = []; labels: List[float] = []; cache: Dict[tuple, float] = {}
    for i in range(len(wf)):
        r = wf.iloc[i]
        sets = None if bool(r.get("retirement", False)) else _parse_sets(r["score"])
        if not sets:
            continue
        bo = int(r["best_of"]) if r["best_of"] in (3, 5) else 3
        won = int(r["winner"]) == 1                 # p1 (lower id) won the MATCH
        wg, lg = sets[0]
        p1_g, p2_g = (wg, lg) if won else (lg, wg)
        if p1_g == p2_g:
            continue
        lead_p1 = p1_g > p2_g                        # set-1 leader role (set result, not match)
        p_pre = float(r["win_prob_p1"]) if lead_p1 else (1.0 - float(r["win_prob_p1"]))
        key = (int(round(p_pre * 1000)), bo)
        if key not in cache:
            cache[key] = _p_set_from_match(p_pre, bo)
        preds.append(_reprice_leader(bo, 1, 0, cache[key]))
        labels.append(1.0 if (lead_p1 == won) else 0.0)
    if len(preds) < 200:
        return _W156_INGAME_PLATT
    a, b = _fit_platt(np.array(preds), np.array(labels))
    return (float(a), float(b)) if (np.isfinite(a) and np.isfinite(b)) else _W156_INGAME_PLATT


def recal_ingame(p_leader: float, ingame_platt: tuple) -> float:
    """Apply the build-time W156 Platt-on-logit in-game recalibrator to a leader prob."""
    a, b = ingame_platt
    return float(_sigmoid(a * _logit(np.array([p_leader])) + b)[0])


def recal(p_raw: float, *, tour: str, platt: Optional[tuple], use_wta_temp: bool) -> float:
    """Apply the tour's leak-free recalibration to a raw Elo match-win prob."""
    z = _logit(np.array([p_raw]))
    if use_wta_temp or tour == "WTA":
        return float(_sigmoid(z / _WTA_T)[0])
    if platt is not None:
        a, b = platt
        return float(_sigmoid(a + b * z)[0])
    return float(p_raw)
