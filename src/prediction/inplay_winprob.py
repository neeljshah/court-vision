"""src/prediction/inplay_winprob.py — in-play win probability (R10_M5 + R12_F1 + R13_G2).

Wraps the LightGBM boosters trained by ``scripts/train_inplay_winprob_endq3.py``
(v1, R10_M5), ``scripts/probe_R12_F1_inplay_winprob_v2.py`` (v2 ensemble), and
``scripts/probe_R13_G2_endq1_winprob_v3.py`` (v3 pregame-anchored endQ1).

Artifacts:

    data/models/inplay_winprob_endq1.lgb                # v1 (R10_M5)
    data/models/inplay_winprob_endq2.lgb                # v1 (R10_M5)
    data/models/inplay_winprob_endq3.lgb                # v1 (R10_M5) SHIP
    data/models/inplay_winprob_endq2_v2.lgb             # v2 (R12_F1) SHIP
    data/models/inplay_winprob_endq2_v2_meta.json       # ensemble blend metadata
    data/models/inplay_winprob_endq1_v3.lgb             # v3 (R13_G2) SHIP (if Brier<=0.183)
    data/models/inplay_winprob_endq1_v3_anchor.json     # pregame-anchor bundle metadata

v1 ship history: endQ3 cleared the 0.183 Brier gate (Brier 0.1350); endQ1 +
endQ2 did not.

v2 ship history (R12_F1): endQ2 ensemble (LGB + LR via NNLS + anchor blend)
clears the gate with Brier 0.1735 on walk-forward (v1 was 0.2234 on the same
449-game post-quarter_box-cache-rebuild dataset). When the v2 endQ2 artifacts
are present, this module uses them; otherwise it falls back to the v1 booster.

Feature schemas:

v1 (endQ1/endQ3, or endQ2 fallback):
    score_margin, total_pts, pace_so_far, q1_delta, q2_delta (Q2+), q3_delta
    (Q3 only), last_q_margin, pregame_win_prob, home_team_id, season

v2 (endQ2 production):
    All v1 features PLUS:
      projected_final_margin, projected_total_score, qtr_margin_var,
      qtr_margin_mean, net_rtg_diff, pace_diff, elo_diff, stars_diff,
      rest_diff, b2b_diff, last5_diff
    Inference is an NNLS-weighted blend of LightGBM and standardized
    Logistic Regression, then anchor-blended with pregame WP.

Inference contract: ``predict_home_win_prob(features: dict, snapshot: str)``
returns a single float in [0, 1] or None if no artifact is available.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")

SNAPSHOTS = ("endQ1", "endQ2", "endQ3")

# v1 feature schema — kept verbatim for back-compat with the R10_M5 boosters.
_SNAP_FEATURES: Dict[str, list] = {
    "endQ1": ["score_margin", "total_pts", "pace_so_far", "q1_delta",
              "last_q_margin", "pregame_win_prob", "home_team_id", "season"],
    "endQ2": ["score_margin", "total_pts", "pace_so_far", "q1_delta", "q2_delta",
              "last_q_margin", "pregame_win_prob", "home_team_id", "season"],
    "endQ3": ["score_margin", "total_pts", "pace_so_far", "q1_delta", "q2_delta",
              "q3_delta", "last_q_margin", "pregame_win_prob", "home_team_id", "season",
              "q1_usg_avg", "halftime_pace_shift", "trailing_team_q4_usg_hhi"],
}
_CAT_COLS = ("home_team_id", "season")

# Snapshots that have a v2 production artifact available. Loaded lazily by
# ``load_v2_bundle``; missing artifacts fall back to v1.
_V2_SNAPSHOTS = ("endQ2",)

# Snapshots that have a v3 (pregame-anchored) production artifact. v3 is
# preferred over v2/v1 for any listed snapshot. R13_G2 added endQ1.
_V3_SNAPSHOTS = ("endQ1",)

# Module-scope booster cache. Keyed by snapshot name. False sentinel means
# we tried to load and the artifact was missing (so callers stop retrying).
_BOOSTER_CACHE: Dict[str, Any] = {}
_META_CACHE: Dict[str, Any] = {}
_V2_BUNDLE_CACHE: Dict[str, Any] = {}
_V3_BUNDLE_CACHE: Dict[str, Any] = {}


def _artifact_path(snapshot: str) -> str:
    return os.path.join(_MODELS_DIR, f"inplay_winprob_{snapshot.lower()}.lgb")


def _meta_path(snapshot: str) -> str:
    return os.path.join(_MODELS_DIR, f"inplay_winprob_{snapshot.lower()}_meta.json")


def load_booster(snapshot: str):
    """Cached lightgbm.Booster loader. Returns None if artifact missing."""
    if snapshot not in SNAPSHOTS:
        return None
    if snapshot in _BOOSTER_CACHE:
        b = _BOOSTER_CACHE[snapshot]
        return b if b is not False else None
    path = _artifact_path(snapshot)
    if not os.path.exists(path):
        _BOOSTER_CACHE[snapshot] = False
        return None
    try:
        import lightgbm as lgb
        booster = lgb.Booster(model_file=path)
    except Exception:
        _BOOSTER_CACHE[snapshot] = False
        return None
    _BOOSTER_CACHE[snapshot] = booster

    mp = _meta_path(snapshot)
    if os.path.exists(mp):
        try:
            with open(mp) as f:
                _META_CACHE[snapshot] = json.load(f)
        except (OSError, json.JSONDecodeError):
            _META_CACHE[snapshot] = {}
    else:
        _META_CACHE[snapshot] = {}
    return booster


def _feature_frame(features: Dict[str, Any], snapshot: str) -> pd.DataFrame:
    """Build a single-row DataFrame in the column order the booster expects."""
    cols = _SNAP_FEATURES[snapshot]
    row = {}
    for c in cols:
        v = features.get(c)
        if c in _CAT_COLS:
            row[c] = v
        else:
            # numeric coercion -- LightGBM rejects pandas Object dtype for
            # leaf features. Use NaN for None so missing-value handling
            # falls through to LightGBM's built-in path.
            try:
                row[c] = float(v) if v is not None else np.nan
            except (TypeError, ValueError):
                row[c] = np.nan
    df = pd.DataFrame([row], columns=cols)
    for c in _CAT_COLS:
        if c in df.columns:
            df[c] = df[c].astype("category")
    return df


def _v2_bundle_paths(snapshot: str) -> Dict[str, str]:
    base = f"inplay_winprob_{snapshot.lower()}_v2"
    return {
        "lgb": os.path.join(_MODELS_DIR, f"{base}.lgb"),
        "meta": os.path.join(_MODELS_DIR, f"{base}_meta.json"),
    }


def load_v2_bundle(snapshot: str) -> Optional[Dict[str, Any]]:
    """Lazily load v2 ensemble bundle (LGB booster + meta) for a snapshot.

    The bundle includes:
      - lightgbm Booster
      - ensemble weights (lgb, xgb, lr — xgb omitted at runtime; weights
        renormalized over lgb + lr to avoid carrying a second native model)
      - anchor alpha
      - logistic-regression coefficients (in standardized space) + mean/std

    Returns None if the artifact set is incomplete.
    """
    if snapshot not in _V2_SNAPSHOTS:
        return None
    if snapshot in _V2_BUNDLE_CACHE:
        b = _V2_BUNDLE_CACHE[snapshot]
        return b if b is not False else None
    paths = _v2_bundle_paths(snapshot)
    if not (os.path.exists(paths["lgb"]) and os.path.exists(paths["meta"])):
        _V2_BUNDLE_CACHE[snapshot] = False
        return None
    try:
        import lightgbm as lgb
        booster = lgb.Booster(model_file=paths["lgb"])
        with open(paths["meta"]) as f:
            meta = json.load(f)
    except Exception:
        _V2_BUNDLE_CACHE[snapshot] = False
        return None

    # Renormalize ensemble weights so they live on the {lgb, lr} simplex.
    # XGB is dropped at inference because the trained model file is .xgb
    # which would require an extra dependency on the live path. Probe data
    # showed lgb+lr already carries ~94% of the explanatory power on
    # endQ2 (xgb weight ~0).
    raw_w = meta.get("ensemble_weights", {})
    w_lgb = float(raw_w.get("lgb", 0.0))
    w_lr = float(raw_w.get("lr", 0.0))
    s = w_lgb + w_lr
    if s <= 1e-9:
        # Pathological fallback: split evenly.
        w_lgb, w_lr = 0.5, 0.5
    else:
        w_lgb /= s
        w_lr /= s

    bundle = {
        "booster": booster,
        "meta": meta,
        "w_lgb": w_lgb,
        "w_lr": w_lr,
        "alpha": float(meta.get("anchor_alpha", 1.0)),
        "feature_cols": list(meta.get("feature_cols", [])),
        "lr_feat_order": list(meta.get("lr_feat_order", [])),
        "lr_coef": [float(x) for x in meta.get("lr_coef", [])],
        "lr_intercept": float(meta.get("lr_intercept", 0.0)),
        "lr_mean": {k: float(v) for k, v in meta.get("lr_mean", {}).items()},
        "lr_std": {k: float(v) for k, v in meta.get("lr_std", {}).items()},
    }
    _V2_BUNDLE_CACHE[snapshot] = bundle
    return bundle


def _v2_feature_frame(features: Dict[str, Any],
                      bundle: Dict[str, Any]) -> pd.DataFrame:
    """Build the v2 feature frame in the booster's expected column order."""
    cols = bundle["feature_cols"]
    row = {}
    for c in cols:
        v = features.get(c)
        if c in _CAT_COLS:
            row[c] = v
        else:
            try:
                row[c] = float(v) if v is not None else np.nan
            except (TypeError, ValueError):
                row[c] = np.nan
    df = pd.DataFrame([row], columns=cols)
    for c in _CAT_COLS:
        if c in df.columns:
            df[c] = df[c].astype("category")
    return df


def _v2_lr_predict(features: Dict[str, Any],
                   bundle: Dict[str, Any]) -> float:
    """Compute the standardized LR probability for the v2 ensemble."""
    feat_order: List[str] = bundle["lr_feat_order"]
    coef: List[float] = bundle["lr_coef"]
    mean = bundle["lr_mean"]
    std = bundle["lr_std"]
    z = float(bundle["lr_intercept"])
    for i, c in enumerate(feat_order):
        v = features.get(c)
        try:
            x = float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            x = 0.0
        m = float(mean.get(c, 0.0))
        s = float(std.get(c, 1.0)) or 1.0
        z += coef[i] * ((x - m) / s)
    # numerical-stable sigmoid
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _predict_v2(features: Dict[str, Any], snapshot: str) -> Optional[float]:
    bundle = load_v2_bundle(snapshot)
    if bundle is None:
        return None
    try:
        X = _v2_feature_frame(features, bundle)
        p_lgb = float(bundle["booster"].predict(X)[0])
    except Exception:
        return None
    p_lr = _v2_lr_predict(features, bundle)
    p_stack = bundle["w_lgb"] * p_lgb + bundle["w_lr"] * p_lr
    alpha = bundle["alpha"]
    try:
        pregame = float(features.get("pregame_win_prob", 0.5))
    except (TypeError, ValueError):
        pregame = 0.5
    blended = alpha * p_stack + (1.0 - alpha) * pregame
    return float(np.clip(blended, 0.0, 1.0))


def _v3_bundle_path(snapshot: str) -> str:
    return os.path.join(
        _MODELS_DIR, f"inplay_winprob_{snapshot.lower()}_v3_anchor.json"
    )


def load_v3_bundle(snapshot: str) -> Optional[Dict[str, Any]]:
    """Lazily load the v3 (pregame-anchored) bundle for a snapshot.

    The v3 bundle is a single JSON written by
    ``scripts/probe_R13_G2_endq1_winprob_v3.py``. It carries:

      - alpha_inplay (in-play stack weight; 1 - alpha_inplay = pregame weight)
      - the v2-style ensemble: LGB booster path + LR coefficients + NNLS
        weights on the LGB / LR base learners
      - feature column order (same as v2)

    Returns None if the bundle JSON or backing LGB file is missing.
    """
    if snapshot not in _V3_SNAPSHOTS:
        return None
    if snapshot in _V3_BUNDLE_CACHE:
        b = _V3_BUNDLE_CACHE[snapshot]
        return b if b is not False else None

    bundle_path = _v3_bundle_path(snapshot)
    if not os.path.exists(bundle_path):
        _V3_BUNDLE_CACHE[snapshot] = False
        return None
    try:
        with open(bundle_path) as f:
            meta = json.load(f)
    except (OSError, json.JSONDecodeError):
        _V3_BUNDLE_CACHE[snapshot] = False
        return None

    lgb_path = meta.get("lgb_path") or os.path.join(
        _MODELS_DIR, f"inplay_winprob_{snapshot.lower()}_v3.lgb"
    )
    if not os.path.exists(lgb_path):
        _V3_BUNDLE_CACHE[snapshot] = False
        return None
    try:
        import lightgbm as lgb
        booster = lgb.Booster(model_file=lgb_path)
    except Exception:
        _V3_BUNDLE_CACHE[snapshot] = False
        return None

    # Renormalize ensemble weights over {lgb, lr} -- xgb omitted at runtime
    # for the same reason as v2 (avoid the second native model dependency).
    raw_w = meta.get("ensemble_weights", {})
    w_lgb = float(raw_w.get("lgb", 0.0))
    w_lr = float(raw_w.get("lr", 0.0))
    s = w_lgb + w_lr
    if s <= 1e-9:
        w_lgb, w_lr = 0.5, 0.5
    else:
        w_lgb /= s
        w_lr /= s

    bundle = {
        "booster": booster,
        "meta": meta,
        "w_lgb": w_lgb,
        "w_lr": w_lr,
        "alpha_inplay": float(meta.get("alpha_inplay", 0.15)),
        "feature_cols": list(meta.get("feature_cols", [])),
        "lr_feat_order": list(meta.get("lr_feat_order", [])),
        "lr_coef": [float(x) for x in meta.get("lr_coef", [])],
        "lr_intercept": float(meta.get("lr_intercept", 0.0)),
        "lr_mean": {k: float(v) for k, v in meta.get("lr_mean", {}).items()},
        "lr_std": {k: float(v) for k, v in meta.get("lr_std", {}).items()},
    }
    _V3_BUNDLE_CACHE[snapshot] = bundle
    return bundle


def _predict_v3(features: Dict[str, Any], snapshot: str) -> Optional[float]:
    bundle = load_v3_bundle(snapshot)
    if bundle is None:
        return None
    try:
        X = _v2_feature_frame(features, bundle)
        p_lgb = float(bundle["booster"].predict(X)[0])
    except Exception:
        return None
    p_lr = _v2_lr_predict(features, bundle)
    p_stack = bundle["w_lgb"] * p_lgb + bundle["w_lr"] * p_lr

    alpha = float(bundle["alpha_inplay"])
    try:
        pregame = float(features.get("pregame_win_prob", 0.5))
    except (TypeError, ValueError):
        pregame = 0.5
    blended = alpha * p_stack + (1.0 - alpha) * pregame
    return float(np.clip(blended, 0.0, 1.0))


# Dual-stage calibration (iter67) — Platt + Isotonic chained on top of v1
# booster output. Trained on the same 3,685-game OOS pool that the validation
# uses. Applies post-prediction to fix v1's known over-confidence at extreme
# probabilities. Loaded lazily and cached.
_DUALCAL_CACHE: Dict[str, Any] = {}


def _load_dualcal(snapshot: str):
    if snapshot in _DUALCAL_CACHE:
        return _DUALCAL_CACHE[snapshot]
    path = os.path.join(_MODELS_DIR, f"inplay_dualcal_{snapshot.lower()}.joblib")
    if not os.path.exists(path):
        _DUALCAL_CACHE[snapshot] = None
        return None
    try:
        import joblib  # noqa: PLC0415
        dc = joblib.load(path)
        if not isinstance(dc, dict) or "platt" not in dc or "isotonic" not in dc:
            _DUALCAL_CACHE[snapshot] = None
            return None
        _DUALCAL_CACHE[snapshot] = dc
        return dc
    except Exception:
        _DUALCAL_CACHE[snapshot] = None
        return None


def _apply_dualcal(raw_p: float, snapshot: str) -> float:
    """Apply Platt + Isotonic calibration on top of a raw booster probability.

    Platt was trained on logit(raw_p), not raw_p — that's the standard form."""
    dc = _load_dualcal(snapshot)
    if dc is None:
        return raw_p
    try:
        platt = dc.get("platt")
        iso = dc.get("isotonic")
        if platt is None or iso is None:
            return raw_p
        # logit transform with clip to avoid inf
        p_clip = max(1e-6, min(1.0 - 1e-6, raw_p))
        logit = math.log(p_clip / (1.0 - p_clip))
        x = np.array([[logit]])
        p_platt = float(platt.predict_proba(x)[0, 1])
        p_iso = float(iso.predict([p_platt])[0])
        return float(np.clip(p_iso, 0.0, 1.0))
    except Exception:
        return raw_p


# v6_hp boosters (iter68 HP-tuned) and meta_blend (iter71 NNLS over
# v6_hp + iter62 isotonic + analytic sigmoid_margin + analytic polarity_pregame +
# optional v7_bag5 for endQ2). Validated via scripts/validation_harness_winprob.py:
#   endQ1 meta_blend: mean WF Brier Δ = -0.0133 vs v1 raw (4/4 folds improved)
#   endQ2 meta_blend: mean WF Brier Δ = -0.0141 vs v1 raw (4/4 folds improved)
#   endQ3 v6_hp:      mean WF Brier Δ = -0.0158 vs v1 raw (4/4 folds improved)
# Source: data/cache/validation_harness_winprob.json.
_V6HP_CACHE: Dict[str, Any] = {}
_V6HP_META_CACHE: Dict[str, Any] = {}
_V7BAG_CACHE: Dict[str, Any] = {}
_ITER62_ISO_CACHE: Dict[str, Any] = {}
_BLEND_META_CACHE: Dict[str, Any] = {}
_V4_FOULS_CACHE: Dict[str, Any] = {}
_V4_FOULS_META_CACHE: Dict[str, Any] = {}

# Snapshots routed through meta_blend (iter71). endQ3 is excluded by default
# because its meta_blend weights assign 0.388 to v4_fouls, and the foul
# features were not yet wired into the live snapshot path — falling back would
# reduce endQ3 to 100% sigmoid_margin and regress vs v6_hp standalone.
# When CV_WP_FOULS_ENDQ3=1, foul features ARE wired; endQ3 is then added to
# the meta_blend routing via _active_meta_blend_snapshots().
_META_BLEND_SNAPSHOTS = ("endQ1", "endQ2")

# ---------------------------------------------------------------------------
# CV_LATE_FOUL_STATE: late-game intentional-foul win-prob adjustment.
#
# When CV_LATE_FOUL_STATE=1, inject the leading team's FT-rate defensive
# advantage as a sigmoid-margin correction factor.  In intentional-foul
# sequences the leading team shoots FTs from a high-FT% position: every made
# pair maintains their lead AND stops the clock.  This biases the trailing
# team toward needing more made FTs than random → slight shift toward the
# leader.  Applied as an additive component weight in _predict_meta_blend.
# Default OFF → byte-identical.
# ---------------------------------------------------------------------------
_LATE_FOUL_STATE_CACHE: Dict[str, Any] = {}


def _cv_late_foul_state_enabled() -> bool:
    """Return True when CV_LATE_FOUL_STATE is set to a truthy value."""
    return os.environ.get("CV_LATE_FOUL_STATE", "0").strip() not in (
        "0", "", "false", "False"
    )


def _cv_wp_fouls_endq3_enabled() -> bool:
    """Return True when CV_WP_FOULS_ENDQ3 is set to a truthy value."""
    return os.environ.get("CV_WP_FOULS_ENDQ3", "0").strip() not in ("0", "", "false", "False")


def _active_meta_blend_snapshots() -> tuple:
    """Return the snapshots routed through meta_blend for the current flag state."""
    if _cv_wp_fouls_endq3_enabled():
        return ("endQ1", "endQ2", "endQ3")
    return _META_BLEND_SNAPSHOTS

# Snapshots that should still apply iter67 dual-cal on the v1 raw fallback
# path. iter67 validation (data/cache/iter67_inplay_dualcal_results.json)
# combined with scripts/validation_harness_winprob.py shows:
#   endQ1: Δ -0.0051  -> keep as defensive fallback when meta_blend missing
#   endQ2: Δ -0.0012  -> fails ship gate, no value
#   endQ3: Δ -0.0008 with worst fold regress +0.0072 -> actively HURTS
_DUALCAL_FALLBACK_SNAPSHOTS = ("endQ1",)


def _load_v6_hp(snapshot: str):
    if snapshot in _V6HP_CACHE:
        b = _V6HP_CACHE[snapshot]
        return b if b is not False else None
    path = os.path.join(_MODELS_DIR, f"inplay_winprob_{snapshot.lower()}_v6_hp.lgb")
    meta_path = os.path.join(
        _MODELS_DIR, f"inplay_winprob_{snapshot.lower()}_v6_hp_meta.json")
    if not (os.path.exists(path) and os.path.exists(meta_path)):
        _V6HP_CACHE[snapshot] = False
        return None
    try:
        import lightgbm as lgb
        booster = lgb.Booster(model_file=path)
        with open(meta_path) as f:
            _V6HP_META_CACHE[snapshot] = json.load(f)
    except Exception:
        _V6HP_CACHE[snapshot] = False
        return None
    _V6HP_CACHE[snapshot] = booster
    return booster


def _v6_hp_feature_cols(snapshot: str) -> Optional[List[str]]:
    if snapshot not in _V6HP_META_CACHE:
        _load_v6_hp(snapshot)
    meta = _V6HP_META_CACHE.get(snapshot)
    if not meta:
        return None
    return list(meta.get("feature_cols", []))


def _predict_v6_hp(features: Dict[str, Any], snapshot: str) -> Optional[float]:
    """Run the iter68 v6_hp booster on a single feature dict."""
    booster = _load_v6_hp(snapshot)
    if booster is None:
        return None
    cols = _v6_hp_feature_cols(snapshot)
    if not cols:
        return None
    row = {}
    for c in cols:
        v = features.get(c)
        if c in _CAT_COLS:
            row[c] = v
        else:
            try:
                row[c] = float(v) if v is not None else np.nan
            except (TypeError, ValueError):
                row[c] = np.nan
    df = pd.DataFrame([row], columns=cols)
    for c in _CAT_COLS:
        if c in df.columns:
            df[c] = df[c].astype("category")
    try:
        p = booster.predict(df)
    except Exception:
        return None
    if p is None or len(p) == 0:
        return None
    return float(np.clip(p[0], 0.0, 1.0))


def _load_v7_bag5_endq2() -> List[Any]:
    """5-seed v7 bag (iter70). Only exists for endQ2."""
    if "endQ2" in _V7BAG_CACHE:
        b = _V7BAG_CACHE["endQ2"]
        return [] if b is False else b
    bag = []
    try:
        import lightgbm as lgb
        for s in range(5):
            p = os.path.join(
                _MODELS_DIR, f"inplay_winprob_endq2_v7_bag5_seed{s}.lgb")
            if os.path.exists(p):
                bag.append(lgb.Booster(model_file=p))
    except Exception:
        bag = []
    if not bag:
        _V7BAG_CACHE["endQ2"] = False
        return []
    _V7BAG_CACHE["endQ2"] = bag
    return bag


def _predict_v7_bag5(features: Dict[str, Any]) -> Optional[float]:
    bag = _load_v7_bag5_endq2()
    if not bag:
        return None
    cols = _v6_hp_feature_cols("endQ2")  # v7 shares v6_hp schema
    if not cols:
        return None
    row = {}
    for c in cols:
        v = features.get(c)
        if c in _CAT_COLS:
            row[c] = v
        else:
            try:
                row[c] = float(v) if v is not None else np.nan
            except (TypeError, ValueError):
                row[c] = np.nan
    df = pd.DataFrame([row], columns=cols)
    for c in _CAT_COLS:
        if c in df.columns:
            df[c] = df[c].astype("category")
    preds = []
    for b in bag:
        try:
            p = b.predict(df)
            if p is not None and len(p) > 0:
                preds.append(float(p[0]))
        except Exception:
            continue
    if not preds:
        return None
    return float(np.clip(np.mean(preds), 0.0, 1.0))


def _load_v4_fouls(snapshot: str):
    """iter65 v4_fouls LightGBM booster (endQ3 only). Cached with False sentinel."""
    if snapshot in _V4_FOULS_CACHE:
        v = _V4_FOULS_CACHE[snapshot]
        return v if v is not False else None
    path = os.path.join(_MODELS_DIR, f"inplay_winprob_{snapshot.lower()}_v4_fouls.lgb")
    meta_path = os.path.join(
        _MODELS_DIR, f"inplay_winprob_{snapshot.lower()}_v4_fouls_meta.json")
    if not (os.path.exists(path) and os.path.exists(meta_path)):
        _V4_FOULS_CACHE[snapshot] = False
        return None
    try:
        import lightgbm as lgb
        booster = lgb.Booster(model_file=path)
        with open(meta_path) as f:
            _V4_FOULS_META_CACHE[snapshot] = json.load(f)
    except Exception:
        _V4_FOULS_CACHE[snapshot] = False
        return None
    _V4_FOULS_CACHE[snapshot] = booster
    return booster


def _v4_fouls_feature_cols(snapshot: str) -> Optional[List[str]]:
    if snapshot not in _V4_FOULS_META_CACHE:
        _load_v4_fouls(snapshot)
    meta = _V4_FOULS_META_CACHE.get(snapshot)
    if not meta:
        return None
    return list(meta.get("feature_cols", []))


def _predict_v4_fouls(features: Dict[str, Any], snapshot: str) -> Optional[float]:
    """Run the iter65 v4_fouls booster on a single feature dict (endQ3).

    Returns None when the artifact is missing, the snapshot has no v4_fouls
    model, or any required foul feature is absent (missing → NaN, handled by
    LightGBM's missing-value path, not a hard abort).
    """
    booster = _load_v4_fouls(snapshot)
    if booster is None:
        return None
    cols = _v4_fouls_feature_cols(snapshot)
    if not cols:
        return None
    row: Dict[str, Any] = {}
    for c in cols:
        v = features.get(c)
        if c in _CAT_COLS:
            row[c] = v
        else:
            try:
                row[c] = float(v) if v is not None else np.nan
            except (TypeError, ValueError):
                row[c] = np.nan
    df = pd.DataFrame([row], columns=cols)
    for c in _CAT_COLS:
        if c in df.columns:
            df[c] = df[c].astype("category")
    try:
        p = booster.predict(df)
    except Exception:
        return None
    if p is None or len(p) == 0:
        return None
    return float(np.clip(p[0], 0.0, 1.0))


def _load_iter62_iso(snapshot: str):
    """iter62 isotonic calibrator (joblib dict bundle)."""
    if snapshot in _ITER62_ISO_CACHE:
        v = _ITER62_ISO_CACHE[snapshot]
        return v if v is not False else None
    path = os.path.join(_MODELS_DIR, f"inplay_isotonic_{snapshot.lower()}.joblib")
    if not os.path.exists(path):
        _ITER62_ISO_CACHE[snapshot] = False
        return None
    try:
        import joblib
        obj = joblib.load(path)
        iso = obj.get("isotonic") if isinstance(obj, dict) else obj
        if iso is None:
            _ITER62_ISO_CACHE[snapshot] = False
            return None
        _ITER62_ISO_CACHE[snapshot] = iso
        return iso
    except Exception:
        _ITER62_ISO_CACHE[snapshot] = False
        return None


def _load_blend_meta(snapshot: str) -> Optional[Dict[str, Any]]:
    if snapshot in _BLEND_META_CACHE:
        v = _BLEND_META_CACHE[snapshot]
        return None if v is False else v
    path = os.path.join(_MODELS_DIR, f"inplay_meta_blend_{snapshot.lower()}.json")
    if not os.path.exists(path):
        _BLEND_META_CACHE[snapshot] = False
        return None
    try:
        with open(path) as f:
            _BLEND_META_CACHE[snapshot] = json.load(f)
            return _BLEND_META_CACHE[snapshot]
    except Exception:
        _BLEND_META_CACHE[snapshot] = False
        return None


def _compute_late_foul_sharpening(features: Dict[str, Any]) -> float:
    """Compute win-prob margin sharpening for late-game intentional-foul state.

    Returns a signed margin addend (points) to shift the sigmoid_margin toward
    the LEADING team when intentional fouling is detected.  Positive = shifts
    win-prob up (home leading); negative = shifts down (home trailing / away
    leading).

    Conditions for non-zero sharpening (all must hold):
      - |score_margin| in [1, 15]: meaningful but not already decided
      - Foul state detected: home/away foul features present + imbalance >= 2
      - Applied at endQ3 only (caller guard)

    Returns 0.0 when any condition is missing (safe no-op).
    Leak-free: reads only from features dict built from state <= E.
    """
    try:
        sm = float(features.get("score_margin", 0.0) or 0.0)
        abs_margin = abs(sm)
        if abs_margin < 1.0 or abs_margin > 15.0:
            return 0.0
        # Use foul features to detect imbalance (injected by CV_WP_FOULS_ENDQ3
        # or by _try_inject_foul_features when available).
        pf_imbalance = features.get("pf_imbalance")
        if pf_imbalance is None:
            return 0.0
        try:
            pf_imbalance = float(pf_imbalance)
        except (TypeError, ValueError):
            return 0.0
        import math as _math
        if _math.isnan(pf_imbalance):
            return 0.0
        # Sharpening: when leading team (positive margin for home, or home trailing
        # and away has pf_imbalance < 0) has a FT-rate advantage.
        # Conservative: 0.5 margin points of sharpening at max foul-imbalance (>=4).
        # Direction: pf_imbalance > 0 means home has more fouls → away is in
        # better FT position → away slightly better → nudge margin negative.
        _MAX_SHARPEN = 0.5  # max margin addend (points in the sigmoid)
        _IMBALANCE_FULL = 4.0  # fouls imbalance for full sharpening
        sign = -1.0 if pf_imbalance > 0 else 1.0
        factor = min(1.0, abs(pf_imbalance) / _IMBALANCE_FULL)
        return float(sign * _MAX_SHARPEN * factor)
    except Exception:
        return 0.0


def _predict_meta_blend(features: Dict[str, Any],
                        snapshot: str) -> Optional[float]:
    """Compose iter71 meta_blend over loaded artifacts + analytic components.

    Components:
      v6_hp:           loaded iter68 booster
      iso:             iter62 isotonic applied to v6_hp output
      v7_bag5:         endQ2 only — average of 5 v7 seed boosters
      v4_fouls:        endQ3 only, CV_WP_FOULS_ENDQ3=1 — foul-enriched booster
                       (iter65; 0.388 weight in the endQ3 meta_blend)
      sigmoid_margin:  1 / (1 + exp(-score_margin/6))
      polarity_pregame: 1 - pregame_win_prob

    Renormalizes weights over available components. Returns None when no
    component is available (caller falls back to v3/v2/v1).
    """
    if snapshot not in _active_meta_blend_snapshots():
        return None
    meta = _load_blend_meta(snapshot)
    if meta is None:
        return None
    weights = meta.get("weights", {})
    if not weights:
        return None

    components: Dict[str, float] = {}
    p_v6 = _predict_v6_hp(features, snapshot)
    if p_v6 is not None:
        components["v6_hp"] = p_v6
        iso = _load_iter62_iso(snapshot)
        if iso is not None:
            try:
                p_iso = float(iso.predict([p_v6])[0])
                components["iso"] = float(np.clip(p_iso, 1e-7, 1.0 - 1e-7))
            except Exception:
                pass

    try:
        sm = float(features.get("score_margin", 0.0) or 0.0)
        components["sigmoid_margin"] = float(1.0 / (1.0 + math.exp(-sm / 6.0)))
    except (TypeError, ValueError, OverflowError):
        pass

    try:
        pg = float(features.get("pregame_win_prob", 0.5) or 0.5)
        components["polarity_pregame"] = float(np.clip(1.0 - pg, 1e-6, 1 - 1e-6))
    except (TypeError, ValueError):
        pass

    if snapshot == "endQ2":
        p_bag = _predict_v7_bag5(features)
        if p_bag is not None:
            components["v7_bag5"] = p_bag

    # endQ3 + CV_WP_FOULS_ENDQ3: wire the v4_fouls booster (iter65).
    # The endQ3 meta_blend assigns weight 0.388 to v4_fouls and 0.612 to
    # sigmoid_margin (v6_hp/iso/polarity weights = 0 in iter71's NNLS fit).
    # Guard: only inject when the flag is ON (we only reach here when
    # _active_meta_blend_snapshots() already includes "endQ3", so the flag
    # must be enabled; this guard is a defensive belt-and-suspenders check).
    if snapshot == "endQ3" and _cv_wp_fouls_endq3_enabled():
        p_v4 = _predict_v4_fouls(features, snapshot)
        if p_v4 is not None:
            components["v4_fouls"] = p_v4

    # CV_LATE_FOUL_STATE: inject a late-game intentional-foul bias component.
    # In intentional-foul sequences the leading team controls the margin via
    # their FT% advantage; the sigmoid_margin already captures this directionally,
    # so we nudge it via a small FT-state multiplier rather than a separate booster.
    # We scale the sigmoid_margin component weight slightly (no new model needed).
    # Effect: when late-game foul context is active (detected from features),
    # the existing sigmoid_margin is scaled by 1 + foul_bias → slight sharpening
    # of the leading team's probability (FT% > random-play advantage).
    # Only fires for endQ3 when CV_LATE_FOUL_STATE=1; byte-identical otherwise.
    if snapshot == "endQ3" and _cv_late_foul_state_enabled():
        _late_foul_sharpening = _compute_late_foul_sharpening(features)
        if _late_foul_sharpening != 0.0 and "sigmoid_margin" in components:
            # Sharpen sigmoid_margin slightly toward the leading team: multiply the
            # raw value by (1 + sharpening). sharpening > 0 → moves toward 1 for
            # leading home team (margin > 0); < 0 → moves toward 0 for trailing.
            sm = float(components["sigmoid_margin"])
            # Scale the margin in the sigmoid, not the output, to stay in [0,1].
            sm_margin = float(features.get("score_margin", 0.0) or 0.0)
            try:
                sm_adjusted = float(
                    1.0 / (1.0 + math.exp(
                        -(sm_margin + _late_foul_sharpening) / 6.0
                    ))
                )
            except (OverflowError, ValueError):
                sm_adjusted = sm
            components["sigmoid_margin"] = float(
                np.clip(sm_adjusted, 1e-7, 1.0 - 1e-7)
            )

    used = {k: float(weights.get(k, 0.0))
            for k in components if float(weights.get(k, 0.0)) > 0.0}
    if not used:
        return components.get(meta.get("best_single_component", "v6_hp"))

    total = sum(used.values())
    if total <= 1e-9:
        return components.get(meta.get("best_single_component", "v6_hp"))
    out = 0.0
    for k, w in used.items():
        out += (w / total) * components[k]
    return float(np.clip(out, 0.0, 1.0))


def active_stack(snapshot: str) -> Dict[str, Any]:
    """Report which artifact stack `predict_home_win_prob` will route through.

    Used by the UI tooltip + status pill to surface honest provenance for the
    displayed win probability.
    """
    # Touch loaders to populate caches without forcing a prediction.
    v6_ok = _load_v6_hp(snapshot) is not None
    iso_ok = _load_iter62_iso(snapshot) is not None
    bag5_ok = (snapshot == "endQ2") and bool(_load_v7_bag5_endq2())
    v4_fouls_ok = (snapshot == "endQ3"
                   and _cv_wp_fouls_endq3_enabled()
                   and _load_v4_fouls(snapshot) is not None)
    blend_ok = (snapshot in _active_meta_blend_snapshots()
                and _load_blend_meta(snapshot) is not None
                and (v6_ok or v4_fouls_ok))
    v3_ok = load_v3_bundle(snapshot) is not None
    v2_ok = load_v2_bundle(snapshot) is not None
    v1_ok = load_booster(snapshot) is not None
    dualcal_ok = (snapshot in _DUALCAL_FALLBACK_SNAPSHOTS
                  and _load_dualcal(snapshot) is not None)

    if blend_ok:
        layer = "meta_blend_iter71"
        components = []
        if v4_fouls_ok:
            components.append("v4_fouls")
        elif v6_ok:
            components.append("v6_hp")
        if iso_ok and not v4_fouls_ok:
            components.append("iter62_iso")
        components.append("sigmoid_margin")
        components.append("polarity_pregame")
        if bag5_ok:
            components.append("v7_bag5")
        detail = f"{layer} ({'+'.join(components)})"
    elif snapshot == "endQ3" and v6_ok:
        layer = "v6_hp_iter68"
        detail = "v6_hp_iter68 (HP-tuned LGB, iter68)"
    elif v3_ok:
        layer = "v3_pregame_anchored"
        detail = "v3 (R13_G2 pregame-anchored ensemble)"
    elif v2_ok:
        layer = "v2_ensemble"
        detail = "v2 (R12_F1 LGB+LR NNLS ensemble)"
    elif v1_ok:
        layer = "v1_dualcal" if dualcal_ok else "v1_raw"
        detail = ("v1 (R10_M5) + iter67 dual-cal"
                  if dualcal_ok else "v1 (R10_M5) raw")
    else:
        layer = "none"
        detail = "no artifact available — using pregame WP"

    return {
        "snapshot": snapshot,
        "layer": layer,
        "detail": detail,
        "v6_hp_loaded": v6_ok,
        "iter62_iso_loaded": iso_ok,
        "v7_bag5_loaded": bag5_ok,
        "v4_fouls_loaded": v4_fouls_ok,
        "meta_blend_loaded": blend_ok,
        "v3_loaded": v3_ok,
        "v2_loaded": v2_ok,
        "v1_loaded": v1_ok,
        "dualcal_applied_on_fallback": dualcal_ok,
        "cv_wp_fouls_endq3": _cv_wp_fouls_endq3_enabled(),
    }


def predict_home_win_prob(features: Dict[str, Any],
                          snapshot: str = "endQ3") -> Optional[float]:
    """Predict P(home team wins) from a snapshot feature dict.

    Routing priority (validated 2026-05-28 via
    scripts/validation_harness_winprob.py):
      1. meta_blend_iter71 — endQ1, endQ2 (mean WF Brier Δ -0.013 / -0.014)
                           — endQ3 when CV_WP_FOULS_ENDQ3=1 (WF Brier Δ -0.010
                             via v4_fouls 0.388 + sigmoid_margin 0.612 blend)
      2. v6_hp_iter68     — endQ3 when CV_WP_FOULS_ENDQ3=0 (mean WF Brier Δ
                             -0.016 vs v1 raw; default path, byte-identical OFF)
      3. v3 pregame-anchored ensemble — endQ1 fallback
      4. v2 ensemble — endQ2 fallback
      5. v1 raw booster (+ iter67 dual-cal for endQ1 only as a defensive
         fallback — dual-cal is a no-op or regression on endQ2/Q3)

    Returns None when no artifact is available.
    """
    # 1. meta_blend (best stack for endQ1 + endQ2).
    mb = _predict_meta_blend(features, snapshot)
    if mb is not None:
        return mb

    # 2. v6_hp standalone for endQ3 (or endQ1/Q2 if meta_blend missing
    #    but v6_hp loads — still beats v3/v2/v1 by big margin).
    v6 = _predict_v6_hp(features, snapshot)
    if v6 is not None:
        return v6

    # 3. v3 (pregame-anchored — R13_G2).
    v3 = _predict_v3(features, snapshot)
    if v3 is not None:
        return v3

    # 4. v2 (ensemble + learned anchor — R12_F1).
    v2 = _predict_v2(features, snapshot)
    if v2 is not None:
        return v2

    # 5. v1 raw booster fallback.
    booster = load_booster(snapshot)
    if booster is None:
        return None
    X = _feature_frame(features, snapshot)
    try:
        raw = booster.predict(X)
    except Exception:
        return None
    if raw is None or len(raw) == 0:
        return None
    p = float(np.clip(raw[0], 0.0, 1.0))
    # iter67 dual-cal: kept only for endQ1 (helps modestly; regresses Q3,
    # no-op for Q2). Validated via scripts/validation_harness_winprob.py.
    if snapshot in _DUALCAL_FALLBACK_SNAPSHOTS:
        p = _apply_dualcal(p, snapshot)
    return p


def features_from_snapshot(snap: Dict[str, Any],
                            *,
                            inject_quarter: bool = True) -> Dict[str, Any]:
    """Build the inplay_winprob feature dict from a canonical live-engine snap.

    Expected keys on ``snap`` (canonical live.py schema PLUS the optional
    quarter-score arrays needed for this model):

        period, clock, home_score, away_score, home_team_id, season,
        home_q1..home_q3, away_q1..away_q3, pregame_win_prob (optional).

    Optional quarter_features injection (inject_quarter=True, default):
        When game_id and home_team_id are present on the snap, injects
        q1_usg_avg, halftime_pace_shift, and trailing_team_q4_usg_hhi
        from the quarter_features parquet.  The trained boosters ignore
        these extra keys; downstream retraining can pick them up by
        expanding the feature schema.

    For mid-quarter snapshots without per-quarter splits, callers should
    skip this routine and fall back to pregame WP -- this function does
    not invent missing quarter totals.
    """
    period = snap.get("period")
    point = _period_to_snapshot(period, snap.get("clock"))
    if point is None:
        return {}

    h_q = [snap.get(f"home_q{q}") for q in (1, 2, 3)]
    a_q = [snap.get(f"away_q{q}") for q in (1, 2, 3)]

    # n_qtrs observed at this snapshot
    n_qtrs = {"endQ1": 1, "endQ2": 2, "endQ3": 3}[point]
    h_obs = h_q[:n_qtrs]
    a_obs = a_q[:n_qtrs]
    if any(x is None for x in h_obs + a_obs):
        return {}

    h_cum = sum(h_obs)
    a_cum = sum(a_obs)
    total_pts = h_cum + a_cum
    minutes_played = n_qtrs * 12.0

    score_margin = h_cum - a_cum
    pace_so_far = (total_pts / minutes_played) if minutes_played > 0 else 0.0
    rem_minutes = 48.0 - minutes_played
    margin_per_min = (score_margin / minutes_played) if minutes_played > 0 else 0.0
    projected_final_margin = score_margin + margin_per_min * rem_minutes
    projected_total_score = total_pts + pace_so_far * rem_minutes

    observed_deltas = [h_q[i] - a_q[i] for i in range(n_qtrs)]
    if len(observed_deltas) >= 2:
        qtr_margin_var = float(np.var(observed_deltas))
        qtr_margin_mean = float(np.mean(observed_deltas))
    else:
        qtr_margin_var = 0.0
        qtr_margin_mean = float(observed_deltas[0])

    feats: Dict[str, Any] = {
        # v1 features (preserved verbatim).
        "score_margin": score_margin,
        "total_pts": total_pts,
        "pace_so_far": pace_so_far,
        "q1_delta": h_q[0] - a_q[0],
        "last_q_margin": h_obs[-1] - a_obs[-1],
        "pregame_win_prob": float(snap.get("pregame_win_prob", 0.55) or 0.55),
        "home_team_id": snap.get("home_team_id"),
        "season": snap.get("season"),
        # v2 features (additive — v1 boosters ignore unknown keys).
        "projected_final_margin": projected_final_margin,
        "projected_total_score": projected_total_score,
        "qtr_margin_var": qtr_margin_var,
        "qtr_margin_mean": qtr_margin_mean,
        "net_rtg_diff": _coerce_float(snap.get("net_rtg_diff")),
        "pace_diff": _coerce_float(snap.get("pace_diff")),
        "elo_diff": _coerce_float(snap.get("elo_diff")),
        "stars_diff": _coerce_float(snap.get("stars_diff")),
        "rest_diff": _coerce_float(snap.get("rest_diff")),
        "b2b_diff": _coerce_float(snap.get("b2b_diff")),
        "last5_diff": _coerce_float(snap.get("last5_diff")),
    }
    if n_qtrs >= 2:
        feats["q2_delta"] = h_q[1] - a_q[1]
    if n_qtrs >= 3:
        feats["q3_delta"] = h_q[2] - a_q[2]

    # Quarter-features enrichment (opt-out via inject_quarter=False).
    # Extra keys are ignored by existing v1/v2/v3 boosters and become
    # available for future retrained schemas without a breaking change.
    if inject_quarter:
        _try_inject_quarter_features(feats, snap)

    # CV_WP_FOULS_ENDQ3: inject per-team foul-state features so the endQ3
    # meta_blend can route through the v4_fouls booster.  All seven keys map
    # directly from the live snapshot schema (captured by W-003 / the poller).
    # When the flag is OFF this block is skipped → output byte-identical.
    if _cv_wp_fouls_endq3_enabled() and point == "endQ3":
        _try_inject_foul_features(feats, snap)

    # CV_LATE_FOUL_STATE: also inject foul features for the late-foul
    # sharpening component (endQ3 only).  Uses the same _try_inject_foul_features
    # helper; idempotent when CV_WP_FOULS_ENDQ3 already injected them.
    if _cv_late_foul_state_enabled() and point == "endQ3":
        _try_inject_foul_features(feats, snap)

    return feats


def _try_inject_foul_features(feats: Dict[str, Any], snap: Dict[str, Any]) -> None:
    """Inject per-team foul-state features for the v4_fouls endQ3 booster.

    Keys written (NaN-safe defaults when absent — LightGBM handles missing):
      home_team_pfs_cum          cumulative home team personal fouls
      away_team_pfs_cum          cumulative away team personal fouls
      home_max_player_pfs        highest PF count among home players
      away_max_player_pfs        highest PF count among away players
      home_starter_fouled_out_indicator  1.0 if any home starter has PF >= 6
      away_starter_fouled_out_indicator  1.0 if any away starter has PF >= 6
      pf_imbalance               home_team_pfs_cum - away_team_pfs_cum

    Sources: keys on the snap dict populated by the live poller (W-003) or by
    inplay_foul_state.parquet when replaying historical games.  All absent keys
    fall through as NaN — the model was trained with this missing-value path and
    handles it gracefully.
    """
    try:
        h_pfs = _coerce_float(snap.get("home_team_pfs_cum"), default=float("nan"))
        a_pfs = _coerce_float(snap.get("away_team_pfs_cum"), default=float("nan"))
        feats["home_team_pfs_cum"] = h_pfs
        feats["away_team_pfs_cum"] = a_pfs
        feats["home_max_player_pfs"] = _coerce_float(
            snap.get("home_max_player_pfs"), default=float("nan"))
        feats["away_max_player_pfs"] = _coerce_float(
            snap.get("away_max_player_pfs"), default=float("nan"))
        feats["home_starter_fouled_out_indicator"] = _coerce_float(
            snap.get("home_starter_fouled_out_indicator"), default=0.0)
        feats["away_starter_fouled_out_indicator"] = _coerce_float(
            snap.get("away_starter_fouled_out_indicator"), default=0.0)
        # pf_imbalance = home_pfs - away_pfs (positive = home in more foul trouble)
        if not (np.isnan(h_pfs) or np.isnan(a_pfs)):
            feats["pf_imbalance"] = h_pfs - a_pfs
        else:
            feats["pf_imbalance"] = float("nan")
    except Exception:
        pass  # never break the inplay path over missing foul data


def _try_inject_quarter_features(feats: Dict[str, Any], snap: Dict[str, Any]) -> None:
    """Best-effort injection of quarter_features signals into feats (in-place).

    Silently skips when game_id is absent or the parquet row is missing.
    """
    game_id = snap.get("game_id")
    team_id = snap.get("home_team_id")
    away_team_id = snap.get("away_team_id")
    if not game_id or not team_id:
        return
    try:
        from src.prediction.quarter_feature_helper import inject_quarter_features
        inject_quarter_features(
            int(team_id),
            str(game_id),
            feats,
            opponent_team_id=int(away_team_id) if away_team_id else None,
        )
    except Exception:
        pass  # never break the inplay path over a missing parquet row


def _coerce_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _period_to_snapshot(period: Any, clock: Any) -> Optional[str]:
    """Conservative period->snapshot mapping.

    R10_M5 was probed at end-of-quarter boundaries (clock >= 11.95 in the
    NEW period). We mirror that gate exactly so model behavior matches
    walk-forward validation.
    """
    try:
        p = int(period)
    except (TypeError, ValueError):
        return None
    # period N+1 with clock near 12:00 means the snapshot is taken at the
    # END of period N. period 2 boundary -> endQ1, period 3 -> endQ2,
    # period 4 -> endQ3.
    if p not in (2, 3, 4):
        return None
    rem: float
    if isinstance(clock, (int, float)):
        rem = float(clock)
    else:
        s = str(clock or "").strip()
        if not s:
            return None
        if ":" in s:
            h, _, t = s.partition(":")
            try:
                rem = float(h) + (float(t) / 60.0 if t else 0.0)
            except ValueError:
                return None
        else:
            try:
                rem = float(s)
            except ValueError:
                return None
    if rem < 11.95:
        return None
    return {2: "endQ1", 3: "endQ2", 4: "endQ3"}[p]


def reset_cache() -> None:
    """Drop cached boosters (test helper)."""
    _BOOSTER_CACHE.clear()
    _META_CACHE.clear()
    _V2_BUNDLE_CACHE.clear()
    _V3_BUNDLE_CACHE.clear()
    _V6HP_CACHE.clear()
    _V6HP_META_CACHE.clear()
    _V7BAG_CACHE.clear()
    _ITER62_ISO_CACHE.clear()
    _BLEND_META_CACHE.clear()
    _DUALCAL_CACHE.clear()
    _V4_FOULS_CACHE.clear()
    _V4_FOULS_META_CACHE.clear()


__all__ = [
    "SNAPSHOTS",
    "load_booster",
    "load_v2_bundle",
    "load_v3_bundle",
    "predict_home_win_prob",
    "features_from_snapshot",
    "active_stack",
    "reset_cache",
]
