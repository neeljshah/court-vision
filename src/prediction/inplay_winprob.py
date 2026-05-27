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


def predict_home_win_prob(features: Dict[str, Any],
                          snapshot: str = "endQ3") -> Optional[float]:
    """Predict P(home team wins) from a snapshot feature dict.

    Routing priority: v3 (pregame-anchored, endQ1) > v2 ensemble (endQ2) > v1
    booster (endQ1/Q2/Q3). Returns None when no artifact is available so
    callers can fall back to raw pregame WP.
    """
    # Try v3 first (pregame-anchored — R13_G2).
    v3 = _predict_v3(features, snapshot)
    if v3 is not None:
        return v3

    # Then v2 (ensemble + learned anchor — R12_F1).
    v2 = _predict_v2(features, snapshot)
    if v2 is not None:
        return v2

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

    return feats


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


__all__ = [
    "SNAPSHOTS",
    "load_booster",
    "load_v2_bundle",
    "load_v3_bundle",
    "predict_home_win_prob",
    "features_from_snapshot",
    "reset_cache",
]
