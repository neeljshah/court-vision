"""src/prediction/pregame_calibration.py — serve the per-stat pregame calibration.

Applies the covariate calibrator trained by scripts/train_pregame_calibrators.py:
maps (base model prediction + pre-game covariates) -> a recalibrated prediction.

WHY this exists and WHY it is per-stat. Against real DK/FD/MGM closes
(scripts/calibration_gate1_test.py) calibrating PTS cut its ROI from -8.89% to
-5.04% (the base PTS model loses to Vegas, so nudging toward the conditional mean
helps), lifting the whole book from -2.00% to ~-0.76%. But calibrating AST collapsed
its real +7.03% edge to +0.93% — because that edge IS the model's correct divergence
from the line, and shrinking toward accuracy shrinks toward the market. So only stats
where the base model does NOT beat Vegas are enabled (default: PTS). docs/VS_VEGAS_ASSESSMENT.md §5.

Strict no-op unless CV_PREGAME_CAL=1 (or apply(..., force=True)). Degrades to the
base prediction on any missing model / covariate / import error — never raises.
"""
from __future__ import annotations

import json
import os
from datetime import date as _date
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent.parent
_DIR = _ROOT / "data" / "models" / "pregame_cal"

# Defaults for covariates the caller can't supply at serve time (so a partial
# context degrades gracefully instead of feeding the booster zeros).
_DEFAULTS = {
    "l10_min": 24.0, "l5_min": 24.0, "l3_min": 24.0, "std_min": 6.0,
    "prev_min": 24.0, "min_trend": 0.0, "rest_days": 2.0, "is_b2b": 0,
    "is_home": 1, "opp_pace": 99.5, "opp_def": 112.0,
    "vac_min": 0.0, "vac_pts": 0.0, "n_out": 0,
    "l5_pts_pm": 0.5, "l5_reb_pm": 0.2, "month": 0, "days_into_season": 60,
}


@lru_cache(maxsize=1)
def _meta() -> dict:
    try:
        return json.loads((_DIR / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        return {"covariates": [], "enabled": [], "models": {}}


@lru_cache(maxsize=16)
def _model(stat: str):
    try:
        import xgboost as xgb
    except Exception:
        return None
    path = _DIR / f"{stat}.json"
    if not path.exists():
        return None
    try:
        bst = xgb.Booster()
        bst.load_model(str(path))
        return bst
    except Exception:
        return None


def enabled_stats() -> set:
    return set(_meta().get("enabled", []))


def blend_weight(stat: str) -> float:
    """Per-stat blend weight a: served = a*calibrated + (1-a)*base. 0 => raw."""
    return float(_meta().get("blend", {}).get(stat, 0.0))


def is_enabled() -> bool:
    """Master opt-in. OFF unless CV_PREGAME_CAL=1 (mirrors CV_LIVE_ADJUST)."""
    return os.environ.get("CV_PREGAME_CAL", "0") == "1"


def apply(stat: str, base_pred: float,
          covariates: Optional[Dict[str, float]] = None,
          force: bool = False) -> float:
    """Return the calibrated prediction for *stat*, or *base_pred* unchanged.

    No-op (returns base_pred) when: the layer is off and not forced; the stat is
    not in the enabled set; the model/covariates are unavailable. Pure + safe.
    """
    if not (force or is_enabled()):
        return base_pred
    a = blend_weight(stat)
    if a <= 0.0 or stat not in enabled_stats():
        return base_pred  # AST etc. served RAW on purpose
    bst = _model(stat)
    if bst is None:
        return base_pred
    covs = _meta().get("covariates", [])
    if not covs:
        return base_pred
    ctx = dict(_DEFAULTS)
    if covariates:
        ctx.update({k: v for k, v in covariates.items() if v is not None})
    ctx["pred"] = float(base_pred)
    if not ctx.get("month"):
        ctx["month"] = _date.today().month
    try:
        import xgboost as xgb
        row = [[float(ctx.get(c, _DEFAULTS.get(c, 0.0))) for c in covs]]
        # the booster was trained from a named DataFrame, so the DMatrix MUST carry
        # the same feature names or predict() raises (which would silently no-op).
        cal = float(bst.predict(xgb.DMatrix(row, feature_names=list(covs)))[0])
    except Exception:
        return base_pred
    # blend toward the calibrated value by the per-stat weight, then guard the net
    # move (nudge, never wildly swing — cap at +-35% of base).
    out = a * cal + (1.0 - a) * float(base_pred)
    if base_pred > 0 and (out < 0.65 * base_pred or out > 1.35 * base_pred):
        out = max(0.65 * base_pred, min(out, 1.35 * base_pred))
    return round(out, 3)
