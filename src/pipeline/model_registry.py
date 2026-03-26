"""
model_registry.py — Central model registry mapping model IDs (M01-M100) to pkl/json files.

Auto-registers all existing pkl files in data/models/ on init.
Supports versioned model retrieval via model_version_manager.

Public API
----------
    ModelRegistry()                                    -> registry instance
    registry.register(model_id, path, model_class)    -> None
    registry.get(model_id)                            -> loaded model or None
    registry.get_active_version(model_id)             -> loaded model (best version)
    registry.list_available()                         -> list[str]
    registry.status()                                 -> dict {model_id: status}
"""

from __future__ import annotations

import glob
import importlib
import json
import logging
import os
import pickle
import sys
from typing import Any, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")

log = logging.getLogger(__name__)

# ── Model ID → metadata table ─────────────────────────────────────────────────
# Maps short IDs to (filename_stem, description)
_MODEL_TABLE: dict[str, tuple[str, str]] = {
    "M01":  ("dnp_model",                  "DNP Predictor"),
    "M02":  ("load_management",            "Load Management"),
    "M03":  ("injury_return",              "Injury Return Curve"),
    "M04":  ("injury_risk",                "Injury Risk"),
    "M05":  ("foul_trouble",               "Foul Trouble Predictor"),
    "M06":  ("garbage_time",               "Garbage Time Detector"),
    "M07":  ("minutes_floor",              "Minutes Floor Model"),
    "M08":  ("beneficiary_cascade",        "Beneficiary Cascade"),
    "M09":  ("win_probability",            "Win Probability"),
    "M10":  ("game_pace",                  "Game Pace"),
    "M11":  ("game_game_total",            "Game Total"),
    "M12":  ("game_spread",                "Game Spread"),
    "M13":  ("game_first_half",            "First Half Model"),
    "M14":  ("game_blowout",               "Blowout Detector"),
    "M15":  ("overtime_probability",       "Overtime Probability"),
    "M16":  ("referee_model",              "Referee Tendency"),
    "M17":  ("back_to_back_model",         "Back-to-Back Discount"),
    "M18":  ("travel_impact_model",        "Travel Impact"),
    "M19":  ("altitude_model",             "Altitude Model"),
    "M20":  ("props_pts",                  "Props — Points"),
    "M21":  ("props_reb",                  "Props — Rebounds"),
    "M22":  ("props_ast",                  "Props — Assists"),
    "M23":  ("props_fg3m",                 "Props — 3PM"),
    "M24":  ("props_stl",                  "Props — Steals"),
    "M25":  ("props_blk",                  "Props — Blocks"),
    "M26":  ("props_tov",                  "Props — Turnovers"),
    "M27":  ("usage_rate_model",           "Usage Rate Model"),
    "M28":  ("true_shooting_model",        "True Shooting %"),
    "M29":  ("plus_minus_predictor",       "Plus/Minus Predictor"),
    "M30":  ("age_curve_model",            "Age Curve"),
    "M31":  ("breakout_predictor",         "Breakout Predictor"),
    "M32":  ("home_away_model",            "Home/Away Split"),
    "M33":  ("rest_day_model",             "Rest Day Performance"),
    "M34":  ("clutch_efficiency",          "Clutch Performance"),
    "M35":  ("matchup_model",              "Matchup Model"),
    "M36":  ("shot_zone_tendency",         "Defender Zone xFG"),
    "M37":  ("xfg_v1",                     "xFG v1"),
    "M38":  ("contested_shot_predictor",   "Contested Shot Predictor"),
    "M39":  ("defensive_scheme",           "Defensive Scheme Detector"),
    "M40":  ("shot_clock_pressure_model",  "Shot Clock Pressure"),
    "M41":  ("shot_type_model",            "Shot Type Model"),
    "M42":  ("contested_rate_model",       "Contested Rate Model"),
    "M68":  ("rotation_predictor",         "Rotation Predictor"),
    "M69":  ("substitution_timing_model",  "Substitution Timing"),
    "M70":  ("team_total_normalizer",      "Team Total Normalizer"),
    "M72":  ("clutch_lineup_model",        "Clutch Lineup Model"),
    "M80":  ("sharp_detector",             "Sharp Money Detector"),
    "M81":  ("clv_tracker",               "CLV Tracker"),
    "M82":  ("public_fade",               "Public Fade"),
    "M83":  ("soft_book_lag",             "Soft Book Lag"),
    "M84":  ("line_movement_predictor",   "Line Movement Predictor"),
    "M85":  ("injury_news_lag",           "Injury News Lag"),
    "M86":  ("prop_correlations",         "Prop Correlation Matrix"),
    "M87":  ("parlay_optimizer",          "SGP Optimizer"),
    "M88":  ("parlay_optimizer",          "Parlay Optimizer"),
    "M91":  ("injury_severity",           "Injury Severity NLP"),
    "M99":  ("prediction_calibrator",     "Prediction Calibrator"),
    "M100": ("feature_drift_detector",    "Feature Drift Detector"),
}


class ModelRegistry:
    """Central registry for all ML models M01–M100."""

    def __init__(self) -> None:
        self._registry: dict[str, dict] = {}  # model_id → {path, loaded, obj}
        self._auto_register()

    def _auto_register(self) -> None:
        """Scan data/models/ and register any pkl/json files found."""
        if not os.path.isdir(_MODEL_DIR):
            return

        # Register from known table first
        for model_id, (stem, desc) in _MODEL_TABLE.items():
            for ext in (".pkl", ".json"):
                path = os.path.join(_MODEL_DIR, f"{stem}{ext}")
                if os.path.exists(path):
                    self._registry[model_id] = {
                        "path": path,
                        "stem": stem,
                        "desc": desc,
                        "loaded": False,
                        "obj": None,
                    }
                    break  # prefer pkl over json if both exist

        # Also scan for any pkl files not in table (future models)
        for fpath in glob.glob(os.path.join(_MODEL_DIR, "*.pkl")):
            stem = os.path.splitext(os.path.basename(fpath))[0]
            # Check if already registered
            already = any(v.get("stem") == stem for v in self._registry.values())
            if not already:
                synthetic_id = f"AUTO_{stem}"
                self._registry[synthetic_id] = {
                    "path": fpath,
                    "stem": stem,
                    "desc": stem,
                    "loaded": False,
                    "obj": None,
                }

        log.debug("ModelRegistry: registered %d models", len(self._registry))

    def register(self, model_id: str, path: str, model_class: Any = None) -> None:
        """Manually register a model by path."""
        self._registry[model_id] = {
            "path": path,
            "stem": os.path.splitext(os.path.basename(path))[0],
            "desc": model_id,
            "loaded": False,
            "obj": None,
            "model_class": model_class,
        }

    def _load_model(self, entry: dict) -> Any:
        """Load model from pkl or json file. Returns None on failure."""
        path = entry["path"]
        try:
            if path.endswith(".pkl"):
                with open(path, "rb") as f:
                    return pickle.load(f)
            elif path.endswith(".json"):
                with open(path) as f:
                    return json.load(f)
        except Exception as e:
            log.warning("Failed to load model %s: %s", path, e)
        return None

    def get(self, model_id: str) -> Any:
        """
        Return loaded model for model_id. Returns None if not registered/trained.
        Lazy-loads on first call and caches in memory.
        """
        entry = self._registry.get(model_id)
        if entry is None:
            log.debug("Model %s not registered", model_id)
            return None
        if not entry["loaded"]:
            entry["obj"] = self._load_model(entry)
            entry["loaded"] = True
        return entry["obj"]

    def get_active_version(self, model_id: str) -> Any:
        """Return best version of model using model_version_manager."""
        try:
            from src.pipeline.model_version_manager import get_version
            version_info = get_version(entry["stem"] if (entry := self._registry.get(model_id)) else model_id)
            if version_info and version_info.get("path"):
                # Load the specific version if different from current
                versioned_path = version_info["path"]
                if os.path.exists(versioned_path):
                    entry = {"path": versioned_path, "loaded": False}
                    return self._load_model(entry)
        except Exception as e:
            log.debug("model_version_manager unavailable: %s", e)
        return self.get(model_id)

    def list_available(self) -> list[str]:
        """Return list of model IDs that have trained files on disk."""
        return [mid for mid, entry in self._registry.items()
                if not mid.startswith("AUTO_")]

    def list_trained(self) -> list[str]:
        """Return list of model IDs whose files actually exist on disk."""
        return [mid for mid, entry in self._registry.items()
                if os.path.exists(entry.get("path", ""))]

    def status(self) -> dict:
        """Return {model_id: {'trained': bool, 'desc': str, 'path': str}}."""
        result = {}
        for mid, entry in sorted(self._registry.items()):
            if mid.startswith("AUTO_"):
                continue
            result[mid] = {
                "trained": os.path.exists(entry.get("path", "")),
                "desc":    entry.get("desc", ""),
                "path":    entry.get("path", ""),
            }
        return result

    def __repr__(self) -> str:
        trained = len(self.list_trained())
        total   = len([k for k in self._registry if not k.startswith("AUTO_")])
        return f"ModelRegistry({trained}/{total} trained)"


# Module-level singleton
_registry: Optional[ModelRegistry] = None

def get_registry() -> ModelRegistry:
    """Return (or create) the global ModelRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
