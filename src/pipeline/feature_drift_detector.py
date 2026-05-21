"""
feature_drift_detector.py — M100: Feature importance drift detector.

Inputs: feature importance from each model over time, player data freshness.
Output: stale_features flag, players needing data refresh, degraded_models list.

Method: Track XGBoost feature importance across retrains.
If importance of key features drops >30% → flag for investigation.
Check data freshness — traded players, role changes, injury returns.

Public API
----------
    FeatureDriftDetector()
    detector.log_importance(model_id, importances)     -> None
    detector.check_drift(model_id)                     -> dict
    detector.get_stale_players()                       -> list[str]
    detector.get_degraded_models()                     -> list[str]
"""

from __future__ import annotations

import glob
import json
import logging
import os
import pickle
import sys
import time
from typing import Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_DRIFT_LOG  = os.path.join(_MODEL_DIR, "feature_drift_log.json")
_MODEL_PATH = os.path.join(_MODEL_DIR, "feature_drift_detector.pkl")

# Thresholds
_DRIFT_ALERT_THRESHOLD   = 0.30   # 30% importance drop → alert
_DRIFT_CRITICAL_THRESHOLD = 0.50  # 50% drop → degrade model flag
_DATA_STALE_HOURS         = 48    # data older than 48h is stale for active players

log = logging.getLogger(__name__)


class FeatureDriftDetector:
    """Monitors feature importance drift and data freshness across models."""

    def __init__(self) -> None:
        self._history: dict = {}       # model_id → list of {timestamp, importances}
        self._stale_players: list = []
        self._degraded: list = []
        self._load()

    def _load(self) -> None:
        if os.path.exists(_DRIFT_LOG):
            try:
                with open(_DRIFT_LOG) as f:
                    self._history = json.load(f)
            except Exception:
                pass

    def _save(self) -> None:
        os.makedirs(_MODEL_DIR, exist_ok=True)
        with open(_DRIFT_LOG, "w") as f:
            json.dump(self._history, f, indent=2)

    def log_importance(self, model_id: str, importances: dict) -> None:
        """
        Log current feature importances for a model.

        Args:
            model_id:     Model identifier.
            importances:  {feature_name: importance_score} dict.
        """
        if model_id not in self._history:
            self._history[model_id] = []

        entry = {
            "timestamp":   time.time(),
            "importances": importances,
        }
        self._history[model_id].append(entry)

        # Keep last 20 snapshots per model
        if len(self._history[model_id]) > 20:
            self._history[model_id] = self._history[model_id][-20:]

        self._save()

    def check_drift(self, model_id: str) -> dict:
        """
        Check if any features have drifted significantly for model_id.

        Uses 2-sigma statistical threshold when >= 3 snapshots exist (so at least
        2 historical points are available before the latest). Falls back to the
        fixed _DRIFT_ALERT_THRESHOLD (30%) when only 1 historical point exists.

        Returns:
            drifted:          bool — any feature exceeded threshold
            drifted_features: list of feature names that drifted
            drift_score:      0-1, normalised overall drift magnitude
            is_degraded:      bool — any feature critically degraded (legacy compat)
            snapshots:        int  — number of history entries
        """
        history = self._history.get(model_id, [])
        if len(history) < 2:
            return {
                "drifted": False,
                "drifted_features": [],
                "is_degraded": False,
                "drift_score": 0.0,
                "snapshots": len(history),
            }

        snapshots = [h["importances"] for h in history]
        all_features = set().union(*[s.keys() for s in snapshots])
        drifted_features: list[str] = []
        drifted_details: list[dict] = []
        max_score: float = 0.0

        for feat in all_features:
            values = [s.get(feat, 0.0) for s in snapshots[:-1]]  # historical
            current = float(snapshots[-1].get(feat, 0.0))

            if len(values) >= 2:
                mean_v = float(np.mean(values))
                std_v = float(np.std(values))
                if std_v > 0:
                    z = abs(current - mean_v) / std_v
                    score = z / 2.0  # normalize: z=2 → score=1.0
                    if z > 2.0:
                        drifted_features.append(feat)
                        drifted_details.append({
                            "feature":   feat,
                            "old":       round(mean_v, 4),
                            "new":       round(current, 4),
                            "drift_pct": round(abs(current - mean_v) / max(mean_v, 0.001) * 100, 1),
                            "critical":  z > 4.0,
                        })
                        max_score = max(max_score, score)
                    continue

            # Fallback: only 1 historical point — use fixed 30% threshold
            baseline = float(values[0]) if values else 0.0
            if baseline > 0.001:
                drop = (baseline - current) / baseline
                if drop > _DRIFT_ALERT_THRESHOLD:
                    drifted_features.append(feat)
                    drifted_details.append({
                        "feature":   feat,
                        "old":       round(baseline, 4),
                        "new":       round(current, 4),
                        "drift_pct": round(drop * 100, 1),
                        "critical":  drop > _DRIFT_CRITICAL_THRESHOLD,
                    })
                    max_score = max(max_score, drop)

        is_degraded = any(d["critical"] for d in drifted_details)
        if is_degraded and model_id not in self._degraded:
            self._degraded.append(model_id)
            log.warning("Model %s flagged as degraded (drift_score=%.3f)", model_id, max_score)

        return {
            "drifted":          len(drifted_features) > 0,
            "drifted_features": drifted_features,
            "is_degraded":      is_degraded,
            "drift_score":      round(max_score, 4),
            "snapshots":        len(history),
        }

    def get_stale_players(self, season: str = "2024-25") -> list[str]:
        """
        Return list of player names whose gamelog data is older than 48h.
        Likely candidates: recently traded, returning from injury, role change.
        """
        stale: list[str] = []
        now = time.time()
        threshold = _DATA_STALE_HOURS * 3600

        gamelog_files = glob.glob(os.path.join(_NBA_CACHE, f"gamelog_full_*_{season}.json"))
        for fpath in gamelog_files:
            age = now - os.path.getmtime(fpath)
            if age > threshold:
                # Extract player name from file if possible
                try:
                    data = json.load(open(fpath))
                    if isinstance(data, list) and data:
                        name = data[0].get("player_name", os.path.basename(fpath))
                        stale.append(name)
                except Exception:
                    stale.append(os.path.basename(fpath))

        self._stale_players = stale
        return stale

    def get_degraded_models(self) -> list[str]:
        """Return list of model IDs flagged as degraded."""
        return list(self._degraded)

    def run_full_check(self, season: str = "2024-25") -> dict:
        """
        Run all drift checks and return a comprehensive health report.
        """
        report = {
            "stale_players":    self.get_stale_players(season),
            "degraded_models":  self.get_degraded_models(),
            "model_drift":      {},
        }

        for model_id in list(self._history.keys()):
            drift = self.check_drift(model_id)
            if drift["drift_score"] > 0.1:
                report["model_drift"][model_id] = drift

        log.info("Drift check: %d stale players, %d degraded models",
                 len(report["stale_players"]), len(report["degraded_models"]))
        return report

    def log_model_retrain(self, model_id: str, model) -> None:
        """
        Extract and log feature importances after a model retrain.
        Supports XGBoost and sklearn models.
        """
        importances: dict = {}
        try:
            if hasattr(model, "feature_importances_"):
                imp_arr = model.feature_importances_
                # Use generic names if no feature names available
                try:
                    names = model.feature_names_in_
                except AttributeError:
                    names = [f"f{i}" for i in range(len(imp_arr))]
                importances = {str(n): float(v) for n, v in zip(names, imp_arr)}
            elif hasattr(model, "get_booster"):
                raw = model.get_booster().get_fscore()
                total = sum(raw.values()) or 1
                importances = {k: v / total for k, v in raw.items()}
        except Exception as e:
            log.debug("Could not extract importances from %s: %s", model_id, e)

        if importances:
            self.log_importance(model_id, importances)
