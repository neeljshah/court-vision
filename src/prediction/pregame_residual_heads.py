"""
src/prediction/pregame_residual_heads.py — R3-F pregame residual head loader.

Cycle R3-F shipped LightGBM heads that predict the residual between the base
prop_pergame stack and the realised actual for 6 stats (reb, ast, fg3m, stl,
blk, tov). PTS gate-failed (mean +0.008 MAE) and is intentionally excluded.

Validated MAE gains (WF 4-fold, >= 3/4 folds positive):
  REB  -0.002    AST  -0.008    FG3M -0.021 (-5.7%)
  STL  -0.039 (-5.5%)    BLK  -0.072 (-14%)    TOV  -0.017

Public API
----------
    load_heads(model_dir=None) -> Dict[str, lgb.Booster | None]
    apply_residual_correction(base_preds, feature_row, stat, model_dir=None) -> float

Usage (single-stat):
    from src.prediction.pregame_residual_heads import apply_residual_correction
    corrected = apply_residual_correction(base_pred, feature_row, stat)

Usage (bulk):
    from src.prediction.pregame_residual_heads import load_heads, apply_residual_correction
    heads = load_heads()
    corrected = apply_residual_correction(base_pred, feature_row, stat, heads=heads)
"""
from __future__ import annotations

import logging
import os
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_HEAD_DIR = os.path.join(_PROJECT_DIR, "data", "models", "pregame_residual_heads")

# Stats with trained + gated heads. PTS is excluded (gate-failed: mean +0.008 MAE).
_HEAD_STATS: frozenset = frozenset({"reb", "ast", "fg3m", "stl", "blk", "tov"})

# Flag: set to False for emergency rollback without touching call sites.
_USE_PREGAME_RESIDUAL_HEADS: bool = True

# Process-level cache so load_heads() is cheap after the first call.
_HEADS_CACHE: Optional[Dict[str, object]] = None


def load_heads(head_dir: Optional[str] = None) -> Dict[str, object]:
    """Load all gated residual .lgb heads from disk into a {stat: booster} dict.

    Returns an empty dict for each stat whose file is absent or unloadable so
    apply_residual_correction degrades gracefully on a fresh checkout. Results
    are process-cached; pass head_dir only when you need a non-default path.

    Returns
    -------
    dict : {stat: lgb.Booster or None}
        stat keys are exactly _HEAD_STATS. None value means the head is absent.
    """
    global _HEADS_CACHE
    if _HEADS_CACHE is not None and head_dir is None:
        return _HEADS_CACHE

    hdir = head_dir or _DEFAULT_HEAD_DIR
    heads: Dict[str, object] = {}
    for stat in _HEAD_STATS:
        path = os.path.join(hdir, f"{stat}.lgb")
        if not os.path.exists(path):
            logger.debug("pregame_residual_heads: %s.lgb not found at %s", stat, path)
            heads[stat] = None
            continue
        try:
            import lightgbm as lgb  # noqa: PLC0415
            booster = lgb.Booster(model_file=path)
            heads[stat] = booster
        except Exception as exc:
            logger.warning("pregame_residual_heads: failed to load %s (%s)", path, exc)
            heads[stat] = None

    if head_dir is None:
        _HEADS_CACHE = heads
    return heads


def apply_residual_correction(
    base_pred: float,
    feature_row: Dict[str, float],
    stat: str,
    *,
    model_dir: Optional[str] = None,
    heads: Optional[Dict[str, object]] = None,
) -> float:
    """Apply the pregame residual head correction to a base prediction.

    For stats in _HEAD_STATS: corrected = base_pred + head.predict(features).
    For pts (or any stat without a gated head): passthrough, base_pred unchanged.

    The module-level flag _USE_PREGAME_RESIDUAL_HEADS must be True (default)
    for the correction to be applied. Set it to False to roll back instantly.

    Parameters
    ----------
    base_pred : float
        Raw-count prediction from the prop_pergame stack (post-transform,
        post-q50, post-calibration).
    feature_row : dict
        Full feature dict as produced by build_prediction_row() — the same
        feature space used in train_pregame_residual_heads.py (feature_columns()
        output keyed by column name).
    stat : str
        One of STATS ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov").
    model_dir : str, optional
        Override the default head directory (for testing).
    heads : dict, optional
        Pre-loaded heads dict from load_heads(). Pass this for bulk prediction
        to avoid repeated disk I/O. When None, load_heads() is called (cached).

    Returns
    -------
    float
        Corrected prediction (floored at 0.0), or base_pred unchanged when the
        head is disabled / absent / stat not in _HEAD_STATS.
    """
    if not _USE_PREGAME_RESIDUAL_HEADS:
        return base_pred
    if stat not in _HEAD_STATS:
        # pts and any future ungated stat: passthrough
        return base_pred

    if heads is None:
        heads = load_heads(head_dir=model_dir)

    booster = heads.get(stat)
    if booster is None:
        return base_pred

    # Build feature vector in the order feature_columns(stat=stat) expects.
    # Import lazily to avoid circular import — prop_pergame imports nothing from here.
    try:
        from src.prediction.prop_pergame import feature_columns  # noqa: PLC0415
        cols = feature_columns(stat=stat)
    except Exception:
        return base_pred

    X = np.array(
        [[float(feature_row.get(c) if feature_row.get(c) is not None else 0.0) for c in cols]],
        dtype=np.float32,
    )
    try:
        residual = float(booster.predict(X)[0])
    except Exception as exc:
        logger.warning("pregame_residual_heads.apply: predict failed for %s (%s)", stat, exc)
        return base_pred

    corrected = base_pred + residual
    return max(0.0, round(corrected, 2))
