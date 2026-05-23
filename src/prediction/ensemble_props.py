"""
ensemble_props.py — Blended prop ensemble: (v3 LGB) + (v2 stacker) + (hierarchical EB).

Public API
----------
    BlendedPropEnsemble.predict(player_id, features) -> dict
    BlendedPropEnsemble.load_weights() -> dict
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Dict, Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_MODELS_DIR   = os.path.join(PROJECT_DIR, "data", "models")
_WEIGHTS_PATH = os.path.join(_MODELS_DIR, "ensemble_weights.json")
_DEFAULT_WEIGHTS = {"v3_lgb": 0.6, "v2_stacker": 0.2, "hierarchical": 0.2}

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
log   = logging.getLogger(__name__)


class BlendedPropEnsemble:
    """
    Blend three prediction sources for player props:
      - v3 LGB (props_lgb_{stat}.pkl)   — primary, highest signal
      - v2 stacker (props_stacker_{stat}.pkl)
      - hierarchical EB (hierarchical_{stat}.pkl)

    Weights loaded from data/models/ensemble_weights.json (per-stat or global).
    Missing components fall back to equal weighting among available ones.

    Final uncertainty = max of available interval widths (conservative).
    """

    def __init__(self, model_dir: str = _MODELS_DIR) -> None:
        self.model_dir = model_dir
        self._weights  = self.load_weights()
        self._hier_models: Dict[str, object] = {}  # stat -> HierarchicalPropModel

    # ── Weights ───────────────────────────────────────────────────────────────

    def load_weights(self) -> Dict[str, Dict[str, float]]:
        """
        Load per-stat weights from ensemble_weights.json.
        Falls back to _DEFAULT_WEIGHTS if file absent.

        Format:
          {"blk": {"v3_lgb": 0.5, "v2_stacker": 0.2, "hierarchical": 0.3}, ...}
          OR flat {"v3_lgb": 0.6, "v2_stacker": 0.2, "hierarchical": 0.2}
        """
        if os.path.exists(_WEIGHTS_PATH):
            try:
                with open(_WEIGHTS_PATH) as f:
                    raw = json.load(f)
                # Detect flat vs per-stat format
                if any(k in raw for k in ("v3_lgb", "v2_stacker", "hierarchical")):
                    return {stat: dict(raw) for stat in STATS}
                return raw
            except Exception as e:
                log.debug("Failed to load ensemble weights: %s", e)
        return {stat: dict(_DEFAULT_WEIGHTS) for stat in STATS}

    def _norm_weights(self, stat: str, available: list) -> Dict[str, float]:
        """Normalize weights for available components; sum to 1.0."""
        w = self._weights.get(stat, dict(_DEFAULT_WEIGHTS))
        filtered = {k: v for k, v in w.items() if k in available}
        total = sum(filtered.values())
        if total <= 0:
            eq = 1.0 / max(len(available), 1)
            return {k: eq for k in available}
        return {k: v / total for k, v in filtered.items()}

    # ── Component loaders ─────────────────────────────────────────────────────

    def _predict_v3_lgb(self, stat: str, features: dict) -> Optional[float]:
        """Predict from v3 LGB if available; features must be the model's feature vector."""
        path = os.path.join(self.model_dir, f"props_lgb_{stat}.pkl")
        if not os.path.exists(path):
            return None
        try:
            import joblib
            model = joblib.load(path)
            # features dict -> np.array in model's feature order
            feat_names = getattr(model, "feature_name_", None)
            if feat_names is None:
                try:
                    feat_names = model.booster_.feature_name()
                except Exception:
                    feat_names = None
            if feat_names is not None:
                X = np.array([[float(features.get(f, 0.0)) for f in feat_names]])
            else:
                X = np.array([[float(v) for v in features.values()]])
            return float(model.predict(X)[0])
        except Exception as e:
            log.debug("v3_lgb predict(%s) failed: %s", stat, e)
            return None

    def _predict_v2_stacker(self, stat: str, features: dict) -> Optional[float]:
        """Predict from v2 stacker if available."""
        path = os.path.join(self.model_dir, f"props_stacker_{stat}.pkl")
        if not os.path.exists(path):
            return None
        try:
            import joblib
            model = joblib.load(path)
            feat_names = getattr(model, "feature_names_in_", None)
            if feat_names is not None:
                X = np.array([[float(features.get(f, 0.0)) for f in feat_names]])
            else:
                X = np.array([[float(v) for v in features.values()]])
            return float(model.predict(X)[0])
        except Exception as e:
            log.debug("v2_stacker predict(%s) failed: %s", stat, e)
            return None

    def _predict_hierarchical(self, stat: str, player_id: int, features: dict) -> Optional[dict]:
        """Predict from hierarchical EB model if fitted."""
        if stat not in self._hier_models:
            from src.prediction.hierarchical_props import HierarchicalPropModel
            m = HierarchicalPropModel(stat, self.model_dir)
            pkl_path = os.path.join(self.model_dir, f"hierarchical_{stat}.pkl")
            if os.path.exists(pkl_path):
                try:
                    m.load(pkl_path)
                    self._hier_models[stat] = m
                except Exception as e:
                    log.debug("hierarchical load(%s) failed: %s", stat, e)
                    self._hier_models[stat] = None
            else:
                self._hier_models[stat] = None
        model = self._hier_models.get(stat)
        if model is None:
            return None
        try:
            return model.predict(player_id, features)
        except Exception as e:
            log.debug("hierarchical predict(%s) failed: %s", stat, e)
            return None

    # ── predict ───────────────────────────────────────────────────────────────

    def predict(self, player_id: int, features: dict) -> dict:
        """
        Blend ensemble predictions for all 7 stats.

        Args:
            player_id: NBA player ID (int).
            features:  Feature dict passed to LGB/stacker models.

        Returns dict with per-stat results:
          {stat: {"mean", "lo_80", "hi_80", "lo_95", "hi_95",
                  "components", "weights_used"}}
        """
        results: Dict[str, dict] = {}

        for stat in STATS:
            components: Dict[str, float] = {}
            intervals:  Dict[str, tuple]  = {}

            # V3 LGB
            v3 = self._predict_v3_lgb(stat, features)
            if v3 is not None:
                v3 = max(0.0, v3)
                components["v3_lgb"] = v3

            # V2 stacker
            v2 = self._predict_v2_stacker(stat, features)
            if v2 is not None:
                v2 = max(0.0, v2)
                components["v2_stacker"] = v2

            # Hierarchical EB
            hier = self._predict_hierarchical(stat, player_id, features)
            if hier is not None:
                components["hierarchical"] = hier["mean"]
                intervals["hierarchical"]  = (
                    hier["lo_80"], hier["hi_80"],
                    hier["lo_95"], hier["hi_95"],
                )

            if not components:
                results[stat] = {
                    "mean": float("nan"), "lo_80": float("nan"), "hi_80": float("nan"),
                    "lo_95": float("nan"), "hi_95": float("nan"),
                    "components": {}, "weights_used": {},
                }
                continue

            avail   = list(components.keys())
            weights = self._norm_weights(stat, avail)
            blend   = sum(weights[k] * components[k] for k in avail)

            # Uncertainty: if hierarchical available use its intervals (scaled by weight);
            # otherwise fall back to ±1 std heuristic.
            if "hierarchical" in intervals:
                lo80_raw, hi80_raw, lo95_raw, hi95_raw = intervals["hierarchical"]
                # Widen proportionally: blend may be tighter, hier may be wider
                half80 = (hi80_raw - lo80_raw) / 2.0
                half95 = (hi95_raw - lo95_raw) / 2.0
                lo80 = max(0.0, blend - half80)
                hi80 = blend + half80
                lo95 = max(0.0, blend - half95)
                hi95 = blend + half95
            else:
                # Rough heuristic: ±30% of blend
                half80 = 0.30 * blend
                half95 = 0.50 * blend
                lo80 = max(0.0, blend - half80)
                hi80 = blend + half80
                lo95 = max(0.0, blend - half95)
                hi95 = blend + half95

            results[stat] = {
                "mean":         round(blend, 4),
                "lo_80":        round(lo80, 4),
                "hi_80":        round(hi80, 4),
                "lo_95":        round(lo95, 4),
                "hi_95":        round(hi95, 4),
                "components":   {k: round(v, 4) for k, v in components.items()},
                "weights_used": {k: round(v, 4) for k, v in weights.items()},
            }

        return results
