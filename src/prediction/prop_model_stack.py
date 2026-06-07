"""
prop_model_stack.py — Phase 4.7: Confidence-gated meta-model for player prop predictions.

Stacks outputs from individual prop models (pts/reb/ast/3pm/stl/blk/tov) through a
Ridge regression meta-model trained on residuals.  A confidence gate suppresses
low-quality predictions and flags high-edge plays.

Architecture
------------
    Base models:    7 XGBoost models (one per stat) from player_props.py
    Meta features:  base prediction + DNP risk + injury mult + recent form z-score
                    + motivation flags (contract year, load management, breakout)
    Meta model:     Ridge regression per stat — reduces systematic bias
    Confidence gate: suppress when |base_pred - line| < edge_threshold OR
                     dnp_prob > 0.30 OR injury_mult < 0.70

Public API
----------
    stack_predict(player_id, game_context)     -> PropStackResult
    train_meta(seasons, stat)                  -> dict (metrics)
    load_stack_models()                        -> dict
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")
_STACK_CACHE = os.path.join(_MODELS_DIR, "prop_stack_meta.json")
_QUARANTINE_PATH = os.path.join(_MODELS_DIR, "quarantine_state.json")

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

# ── Ensemble base-learner registry ───────────────────────────────────────────
# Maps learner name -> model-file template. The linear stacker (prop_stacker.py,
# a later task) consumes this to combine base-learner predictions.
BASE_LEARNERS: Dict[str, str] = {
    "xgboost":  "props_{stat}.json",
    "lightgbm": "props_lgb_{stat}.pkl",
    "catboost": "props_cb_{stat}.cbm",
}


def base_learner_available(name: str) -> Dict[str, bool]:
    """Return {stat: file-exists-bool} for each stat under the given learner name."""
    template = BASE_LEARNERS.get(name, "")
    return {
        stat: os.path.exists(os.path.join(_MODELS_DIR, template.format(stat=stat)))
        for stat in STATS
    }


def predict_base_learner(name: str, stat: str, X) -> Optional[float]:
    """Load the model for (name, stat) and return scalar prediction on X (shape (1, n_feats)).

    Returns None if the model file is missing or loading fails.
    XGBoost (.json) loads via xgb.XGBRegressor; everything else via joblib.
    """
    template = BASE_LEARNERS.get(name, "")
    if not template:
        return None
    path = os.path.join(_MODELS_DIR, template.format(stat=stat))
    if not os.path.exists(path):
        return None
    try:
        import numpy as _np
        _X = _np.array(X)
        if _X.ndim == 1:
            _X = _X.reshape(1, -1)
        if path.endswith(".json"):
            import xgboost as xgb
            m = xgb.XGBRegressor()
            m.load_model(path)
            return float(m.predict(_X)[0])
        elif path.endswith(".cbm"):
            import catboost as cb
            m = cb.CatBoostRegressor()
            m.load_model(path)
            return float(m.predict(_X)[0])
        else:
            import joblib
            m = joblib.load(path)
            return float(m.predict(_X)[0])
    except Exception:
        return None


# Confidence gate thresholds
_DNP_GATE      = 0.30   # suppress if DNP probability ≥ this
_INJURY_GATE   = 0.70   # suppress if injury_mult ≤ this
_MIN_EDGE_PCT  = 0.04   # minimum |pred - line| / line to flag edge


@dataclass
class PropStackResult:
    """Output from stack_predict()."""
    player_id: str
    player_name: str
    predictions: Dict[str, float]          # stat → adjusted prediction
    base_predictions: Dict[str, float]     # stat → raw base-model prediction
    confidence: Dict[str, float]           # stat → 0-1 confidence score
    edges: Dict[str, float]                # stat → (pred - line) / line, NaN if no line
    suppressed: bool                       # True when DNP risk or injury gate fires
    suppression_reason: str
    motivation_flags: Dict[str, bool]      # contract_year, load_management, breakout
    meta_applied: bool                     # True if Ridge meta was applied
    micro_signals: Dict[str, float] = field(default_factory=dict)  # raw micro-model outputs
    calibrated_win_probs: Dict[str, float] = field(default_factory=dict)  # stat → P(actual>line)


_CALIB_DIR = _MODELS_DIR


class CalibrationLayer:
    """Per-stat isotonic regression calibration for prop probabilities.

    fit():      Train one IsotonicRegression per stat on held-out (predicted_prob,
                actual_outcome) pairs and persist to data/models/calibration_{stat}.joblib.
    transform():Apply fitted isotonic to a raw probability; returns identity if not fitted.
    """

    def __init__(self) -> None:
        self._models: Dict[str, object] = {}
        self._win_models: Dict[str, object] = {}
        self._load()
        self._load_win_models()

    def _path(self, stat: str) -> str:
        return os.path.join(_CALIB_DIR, f"calibration_{stat}.joblib")

    def _load(self) -> None:
        try:
            import joblib
            for stat in STATS:
                p = self._path(stat)
                if os.path.exists(p):
                    self._models[stat] = joblib.load(p)
        except Exception:
            pass  # joblib absent or model corrupt — identity passthrough

    def fit(self, stat: str, probs: "np.ndarray", outcomes: "np.ndarray") -> None:
        """Fit isotonic regression for *stat*. probs in [0,1], outcomes in {0,1}."""
        try:
            import joblib
            from sklearn.isotonic import IsotonicRegression
            ir = IsotonicRegression(out_of_bounds="clip")
            ir.fit(probs, outcomes)
            self._models[stat] = ir
            joblib.dump(ir, self._path(stat))
        except Exception as e:
            import logging
            logging.warning("CalibrationLayer.fit(%s) failed: %s", stat, e)

    def transform(self, stat: str, prob: float) -> float:
        """Return calibrated probability (identity if not fitted)."""
        mdl = self._models.get(stat)
        if mdl is None:
            return prob
        try:
            return float(mdl.predict([prob])[0])
        except Exception:
            return prob

    # ── Win-probability calibration (over/under) ──────────────────────────────

    def _win_path(self, stat: str) -> str:
        return os.path.join(_CALIB_DIR, f"calibration_win_{stat}.joblib")

    def train_win_prob(
        self,
        stat: str,
        predictions: "np.ndarray",
        lines: "np.ndarray",
        actuals: "np.ndarray",
    ) -> None:
        """Fit isotonic regression: (pred/line - 1) → P(actual > line).

        Args:
            predictions: Model point predictions (N,).
            lines:       Sportsbook lines (N,).
            actuals:     Actual stat values (N,).
        """
        try:
            import joblib
            from sklearn.isotonic import IsotonicRegression
            edges = predictions / np.maximum(lines, 0.01) - 1.0  # (N,)
            outcomes = (actuals > lines).astype(float)            # {0, 1}
            ir = IsotonicRegression(out_of_bounds="clip")
            ir.fit(edges, outcomes)
            self._win_models[stat] = ir
            joblib.dump(ir, self._win_path(stat))
        except Exception as e:
            import logging
            logging.warning("CalibrationLayer.train_win_prob(%s) failed: %s", stat, e)

    def win_prob(self, stat: str, pred: float, line: float) -> float:
        """Return calibrated P(actual > line) for an over bet.

        Falls back to sigmoid of edge if no calibration model is fitted.
        Never returns below 0.05 or above 0.95.
        """
        edge = pred / max(line, 0.01) - 1.0
        mdl = self._win_models.get(stat)
        if mdl is not None:
            try:
                p = float(mdl.predict([edge])[0])
                return max(0.05, min(0.95, p))
            except Exception:
                pass
        # Uncalibrated fallback: sigmoid centred at 50%, scaled by typical σ≈0.15
        import math
        p = 1.0 / (1.0 + math.exp(-edge / 0.15))
        return max(0.05, min(0.95, p))

    def _load_win_models(self) -> None:
        try:
            import joblib
            for stat in STATS:
                p = self._win_path(stat)
                if os.path.exists(p):
                    self._win_models[stat] = joblib.load(p)
        except Exception:
            pass


# Module-level singleton loaded once
_calibration = CalibrationLayer()

# ── Cohort calibrator (lazy-loaded singleton) ─────────────────────────────────

_cohort_calibrator: Optional["CohortCalibrator"] = None  # type: ignore[name-defined]


def _get_cohort_calibrator() -> Optional[object]:
    """Return the module-level CohortCalibrator, loading it from disk if available."""
    global _cohort_calibrator
    if _cohort_calibrator is not None:
        return _cohort_calibrator
    try:
        from src.calibration.cohort_calibrator import CohortCalibrator
        pkl_path = os.path.join(_CALIB_DIR, "cohort_calibrator.pkl")
        if os.path.exists(pkl_path):
            _cohort_calibrator = CohortCalibrator.load(pkl_path)
            logger.info("CohortCalibrator loaded from %s", pkl_path)
        else:
            _cohort_calibrator = CohortCalibrator()  # empty — falls back to global
    except Exception as exc:
        logger.warning("CohortCalibrator load failed: %s", exc)
    return _cohort_calibrator


def _load_motivation_flags(player_id: str) -> Dict[str, bool]:
    """Load pre-computed motivation flags from model cache files."""
    flags: Dict[str, bool] = {
        "contract_year": False,
        "load_management": False,
        "breakout": False,
    }
    # Contract year — check contracts cache
    contracts_path = os.path.join(PROJECT_DIR, "data", "external", "contracts_2024-25.json")
    if os.path.exists(contracts_path):
        try:
            contracts = json.load(open(contracts_path, encoding="utf-8"))
            for p in contracts:
                if str(p.get("player_id", "")) == str(player_id):
                    flags["contract_year"] = bool(p.get("contract_year", False))
                    break
        except Exception:
            pass

    # Resolve player name for name-based predictors
    player_name: str = ""
    try:
        from src.pipeline.feature_assembler import _resolve_player_name
        player_name = _resolve_player_name(int(player_id)) or ""
    except Exception:
        pass

    # Load management — flag if load_prob > 0.30
    if player_name:
        try:
            from src.prediction.load_management import predict_load_management
            lm = predict_load_management(player_name)
            flags["load_management"] = float(lm.get("load_prob", 0.0)) > 0.30
        except Exception:
            pass

    # Breakout predictor — flag if breakout_score > 0.60
    if player_name:
        try:
            from src.prediction.breakout_predictor import predict_breakout
            bo = predict_breakout(player_name)
            flags["breakout"] = float(bo.get("breakout_score", 0.0)) > 0.60
        except Exception:
            pass

    return flags


def _get_dnp_prob(player_id: str) -> float:
    """Return DNP probability from cached dnp_model or default 0.05."""
    try:
        import pickle
        model_path = os.path.join(_MODELS_DIR, "dnp_model.pkl")
        if not os.path.exists(model_path):
            return 0.05
        with open(model_path, "rb") as f:
            model = pickle.load(f)
        # Model expects a feature vector; return intercept-based prior if no features
        return float(getattr(model, "class_prior_", [0.95, 0.05])[1])
    except Exception:
        return 0.05


def _get_injury_mult(player_id: str) -> float:
    """Return injury multiplier (0=out, 1=healthy) from injury report."""
    try:
        injury_path = os.path.join(PROJECT_DIR, "data", "nba", "injury_report.json")
        if not os.path.exists(injury_path):
            return 1.0
        report = json.load(open(injury_path, encoding="utf-8"))
        players = report if isinstance(report, list) else report.get("players", [])
        for p in players:
            if str(p.get("player_id", "")) == str(player_id):
                status = str(p.get("status", "Available")).lower()
                if "out" in status:
                    return 0.0
                if "doubtful" in status:
                    return 0.25
                if "questionable" in status:
                    return 0.65
                if "probable" in status:
                    return 0.90
        return 1.0
    except Exception:
        return 1.0


def _collect_micro_signals(player_id: str, game_context: dict) -> dict:
    """
    Load each available micro-model .pkl and return a dict of signal values.
    All failures are silently swallowed — missing models return safe defaults.
    """
    gc = game_context  # shorthand
    pid_int = int(player_id) if str(player_id).isdigit() else 0
    signals: dict = {}

    # ── Multiplier models ────────────────────────────────────────────────────
    try:
        from src.prediction.rest_day_model import predict_rest_mult
        signals["rest_mult"] = float(predict_rest_mult(gc).get("mult", 1.0))
    except Exception:
        signals["rest_mult"] = 1.0

    try:
        from src.prediction.back_to_back_model import predict_b2b_mult
        b2b = predict_b2b_mult(gc)
        signals["b2b_pts"] = float(b2b.get("pts", 1.0))
        signals["b2b_reb"] = float(b2b.get("reb", 1.0))
        signals["b2b_ast"] = float(b2b.get("ast", 1.0))
    except Exception:
        signals["b2b_pts"] = signals["b2b_reb"] = signals["b2b_ast"] = 1.0

    try:
        from src.prediction.travel_impact_model import predict_travel_adj
        signals["travel_adj"] = float(predict_travel_adj(gc).get("adj", 1.0))
    except Exception:
        signals["travel_adj"] = 1.0

    try:
        from src.prediction.altitude_model import predict_altitude_adj
        signals["altitude_adj"] = float(predict_altitude_adj(gc).get("adj", 1.0))
    except Exception:
        signals["altitude_adj"] = 1.0

    try:
        from src.prediction.home_away_model import predict_home_away
        signals["home_away_adj"] = float(predict_home_away(gc).get("adj", 1.0))
    except Exception:
        signals["home_away_adj"] = 1.0

    try:
        from src.prediction.shot_type_model import predict_shot_type_adj
        signals["shot_type_mult"] = float(predict_shot_type_adj(gc).get("mult", 1.0))
    except Exception:
        signals["shot_type_mult"] = 1.0

    # ── Contextual / confidence signals ──────────────────────────────────────
    try:
        from src.prediction.rotation_predictor import predict_rotation
        rot = predict_rotation({**gc, "player_id": player_id})
        signals["starter_prob"]  = float(rot.get("starter_prob", 0.5))
        signals["expected_min"]  = float(rot.get("expected_min", 24.0))
    except Exception:
        signals["starter_prob"] = 0.5
        signals["expected_min"] = 24.0

    try:
        from src.prediction.garbage_time_detector import predict_garbage_time
        gt = predict_garbage_time(gc)
        signals["garbage_time_prob"] = float(gt.get("garbage_time_prob", 0.1))
    except Exception:
        signals["garbage_time_prob"] = 0.1

    try:
        from src.prediction.foul_trouble_predictor import predict_foul_trouble
        ft = predict_foul_trouble(pid_int, gc)
        signals["foul_out_prob"]  = float(ft.get("foul_out_prob", 0.05))
        signals["min_reduction"]  = float(ft.get("min_reduction", 0.0))
    except Exception:
        signals["foul_out_prob"] = 0.05
        signals["min_reduction"] = 0.0

    try:
        from src.prediction.usage_rate_model import predict_usage
        signals["proj_usg_pct"] = float(predict_usage(gc).get("proj_usg_pct", 0.2))
    except Exception:
        signals["proj_usg_pct"] = 0.2

    try:
        from src.prediction.true_shooting_model import predict_ts
        signals["proj_ts_pct"] = float(predict_ts(gc).get("proj_ts_pct", 0.55))
    except Exception:
        signals["proj_ts_pct"] = 0.55

    try:
        from src.prediction.plus_minus_predictor import predict_pm
        signals["proj_pm"] = float(predict_pm(gc).get("proj_pm", 0.0))
    except Exception:
        signals["proj_pm"] = 0.0

    try:
        from src.prediction.clutch_lineup_model import predict_clutch_prob
        signals["clutch_prob"] = float(predict_clutch_prob(gc).get("prob", 0.5))
    except Exception:
        signals["clutch_prob"] = 0.5

    try:
        from src.prediction.contested_rate_model import predict_contested_rate
        signals["contested_rate"] = float(predict_contested_rate(gc).get("rate", 0.5))
    except Exception:
        signals["contested_rate"] = 0.5

    return signals


# Per-stat b2b multiplier lookup
_B2B_STAT_KEY: Dict[str, str] = {
    "pts": "b2b_pts", "reb": "b2b_reb", "ast": "b2b_ast",
    "fg3m": "b2b_pts", "stl": "b2b_reb", "blk": "b2b_reb", "tov": "b2b_ast",
}


def _load_quarantine() -> set:
    """Load set of quarantined stats from JSON file."""
    if not os.path.exists(_QUARANTINE_PATH):
        return set()
    try:
        data = json.load(open(_QUARANTINE_PATH, encoding="utf-8"))
        return set(data.get("quarantined", []))
    except Exception:
        return set()


def quarantine_stat(stat: str) -> None:
    """Add stat to quarantine list (persists to disk)."""
    current = _load_quarantine()
    current.add(stat)
    os.makedirs(_MODELS_DIR, exist_ok=True)
    with open(_QUARANTINE_PATH, "w", encoding="utf-8") as f:
        json.dump({"quarantined": sorted(current)}, f)


def clear_quarantine(stat: str) -> None:
    """Remove stat from quarantine list."""
    current = _load_quarantine()
    current.discard(stat)
    os.makedirs(_MODELS_DIR, exist_ok=True)
    with open(_QUARANTINE_PATH, "w", encoding="utf-8") as f:
        json.dump({"quarantined": sorted(current)}, f)


def stack_predict(
    player_id: str,
    game_context: Optional[dict] = None,
    lines: Optional[Dict[str, float]] = None,
) -> PropStackResult:
    """
    Generate stacked prop predictions for a player with confidence gating.

    Args:
        player_id:    NBA player ID string.
        game_context: Optional dict passed to predict_props() as extra context.
        lines:        Optional dict of stat → sportsbook line for edge calculation.

    Returns:
        PropStackResult with adjusted predictions, confidence scores, and edges.
    """
    game_context = game_context or {}
    lines = lines or {}

    # ── Resolve player name from ID ────────────────────────────────────────────
    player_name = ""
    try:
        from nba_api.stats.static import players as _players_static
        matches = [p for p in _players_static.get_players()
                   if str(p["id"]) == str(player_id)]
        if matches:
            player_name = matches[0]["full_name"]
    except Exception:
        pass

    # ── Pull base predictions from player_props ──────────────────────────────
    opp_team = game_context.get("away_team", "")
    # If this player is on the away team, opponent is home
    # (heuristic: caller should set player_team in game_context if known)
    try:
        from src.prediction.player_props import predict_props
        base_raw = predict_props(
            player_name or str(player_id),
            opp_team=opp_team,
            season=game_context.get("season", "2025-26"),
        ) if player_name else {}
    except Exception:
        base_raw = {}

    base_preds: Dict[str, float] = {}
    for stat in STATS:
        val = base_raw.get(stat) or base_raw.get(f"predicted_{stat}")
        base_preds[stat] = float(val) if val is not None else float("nan")

    # ── Suppression checks ───────────────────────────────────────────────────
    dnp_prob     = _get_dnp_prob(player_id)
    injury_mult  = _get_injury_mult(player_id)
    suppressed   = False
    suppression_reason = ""

    if dnp_prob >= _DNP_GATE:
        suppressed = True
        suppression_reason = f"DNP probability {dnp_prob:.2f} ≥ {_DNP_GATE}"
    elif injury_mult <= _INJURY_GATE:
        suppressed = True
        suppression_reason = f"Injury multiplier {injury_mult:.2f} ≤ {_INJURY_GATE}"

    # ── Carry raw predictions forward (injury already applied upstream) ───────
    # Injury availability is applied ONCE, in predict_player_pergame via
    # apply_availability (the single source of truth). injury_mult here is used
    # only for the suppression gate and confidence scaling above/below — NOT
    # re-multiplied into the point estimates (that was a triple-application bug).
    _quarantined = _load_quarantine()
    adjusted: Dict[str, float] = {}
    for stat, val in base_preds.items():
        if stat in _quarantined:
            adjusted[stat] = float("nan")
        else:
            adjusted[stat] = val

    # ── Try applying Ridge meta correction if trained ────────────────────────
    meta_applied = False
    if os.path.exists(_STACK_CACHE):
        try:
            meta_data = json.load(open(_STACK_CACHE, encoding="utf-8"))
            for stat in STATS:
                if stat in meta_data and not np.isnan(adjusted.get(stat, float("nan"))):
                    coef  = meta_data[stat].get("coef", 1.0)
                    intercept = meta_data[stat].get("intercept", 0.0)
                    adjusted[stat] = coef * adjusted[stat] + intercept
            meta_applied = True
        except Exception:
            pass

    # ── Collect and apply micro-model signals ────────────────────────────────
    micro = _collect_micro_signals(player_id, game_context)

    # Shared scalar multiplier (rest, travel, altitude, home/away, shot type)
    scalar_mult = (
        micro["rest_mult"]
        * micro["travel_adj"]
        * micro["altitude_adj"]
        * micro["home_away_adj"]
        * micro["shot_type_mult"]
    )
    for stat in STATS:
        val = adjusted.get(stat, float("nan"))
        if not np.isnan(val):
            # Per-stat b2b mult (pts/reb/ast proxies for other stats)
            b2b_mult = micro.get(_B2B_STAT_KEY.get(stat, "b2b_pts"), 1.0)
            adjusted[stat] = round(val * scalar_mult * b2b_mult, 4)

    # ── Confidence scores ─────────────────────────────────────────────────────
    # Base confidence on: data completeness, injury mult, form consistency,
    # plus micro signals (garbage time, foul trouble, starter probability).
    confidence: Dict[str, float] = {}
    micro_conf_adj = (
        micro["starter_prob"] * 0.10              # starters more predictable
        - micro["garbage_time_prob"] * 0.20       # garbage time = high variance
        - micro["foul_out_prob"] * 0.15           # foul trouble = uncertain minutes
    )
    for stat in STATS:
        if stat in _quarantined:
            confidence[stat] = 0.0
            continue
        val = adjusted.get(stat, float("nan"))
        if np.isnan(val) or suppressed:
            confidence[stat] = 0.0
        else:
            conf = injury_mult * (1.0 - min(dnp_prob, 0.5) * 2) + micro_conf_adj
            conf = max(0.0, min(1.0, conf))
            confidence[stat] = round(_calibration.transform(stat, conf), 3)

    # ── Edge calculation ─────────────────────────────────────────────────────
    edges: Dict[str, float] = {}
    for stat in STATS:
        line = lines.get(stat)
        pred = adjusted.get(stat, float("nan"))
        if line and not np.isnan(pred) and line > 0:
            edges[stat] = round((pred - line) / line, 4)
        else:
            edges[stat] = float("nan")

    motivation_flags = _load_motivation_flags(player_id)

    # Calibrated over/under win probabilities (used by kelly_corr)
    # Prefer cohort-calibrated probabilities; fall back to global CalibrationLayer.
    cohort_calib = _get_cohort_calibrator()
    cohort_ctx = {
        "minutes":   micro.get("expected_min", 25.0),
        "usage":     micro.get("proj_usg_pct", 0.20),
        "rest_days": int(game_context.get("rest_days", 2)),
    }
    calibrated_win_probs: Dict[str, float] = {}
    for stat in STATS:
        pred = adjusted.get(stat, float("nan"))
        line = lines.get(stat)
        if line and not np.isnan(pred) and line > 0:
            raw_wp = _calibration.win_prob(stat, pred, float(line))
            if cohort_calib is not None:
                try:
                    calibrated_win_probs[stat] = cohort_calib.transform(raw_wp, cohort_ctx)
                except Exception:
                    calibrated_win_probs[stat] = raw_wp
            else:
                calibrated_win_probs[stat] = raw_wp

    player_name = base_raw.get("player_name", str(player_id))

    # Set quarantined stats to None in final predictions
    for stat in _quarantined:
        adjusted[stat] = None  # type: ignore[assignment]

    return PropStackResult(
        player_id=str(player_id),
        player_name=player_name,
        predictions=adjusted,
        base_predictions=base_preds,
        confidence=confidence,
        edges=edges,
        suppressed=suppressed,
        suppression_reason=suppression_reason,
        motivation_flags=motivation_flags,
        meta_applied=meta_applied,
        micro_signals=micro,
        calibrated_win_probs=calibrated_win_probs,
    )


def train_meta(
    stat: str = "pts",
    residuals: Optional[List[dict]] = None,
) -> dict:
    """
    Train a Ridge meta-model on recorded prediction residuals.

    Args:
        stat:      Which stat to train ('pts', 'reb', etc.)
        residuals: List of {predicted, actual} dicts.  If None, loads from
                   data/models/prop_residuals.json if it exists.

    Returns:
        {"stat": stat, "coef": float, "intercept": float, "n": int, "r2": float}
    """
    if residuals is None:
        residuals_path = os.path.join(_MODELS_DIR, "prop_residuals.json")
        if not os.path.exists(residuals_path):
            return {"stat": stat, "coef": 1.0, "intercept": 0.0, "n": 0, "r2": 0.0}
        residuals = json.load(open(residuals_path, encoding="utf-8"))

    stat_rows = [(r["predicted"], r["actual"])
                 for r in residuals
                 if r.get("stat") == stat and r.get("predicted") is not None
                 and r.get("actual") is not None]

    if len(stat_rows) < 10:
        return {"stat": stat, "coef": 1.0, "intercept": 0.0, "n": len(stat_rows), "r2": 0.0}

    try:
        from sklearn.linear_model import Ridge
        X = np.array([r[0] for r in stat_rows]).reshape(-1, 1)
        y = np.array([r[1] for r in stat_rows])
        model = Ridge(alpha=1.0).fit(X, y)
        r2 = float(model.score(X, y))
        coef = float(model.coef_[0])
        intercept = float(model.intercept_)
    except Exception:
        coef, intercept, r2 = 1.0, 0.0, 0.0

    # Persist to meta cache
    meta_data: dict = {}
    if os.path.exists(_STACK_CACHE):
        try:
            meta_data = json.load(open(_STACK_CACHE, encoding="utf-8"))
        except Exception:
            pass
    meta_data[stat] = {"coef": coef, "intercept": intercept}
    os.makedirs(_MODELS_DIR, exist_ok=True)
    json.dump(meta_data, open(_STACK_CACHE, "w", encoding="utf-8"), indent=2)

    return {"stat": stat, "coef": coef, "intercept": intercept,
            "n": len(stat_rows), "r2": r2}


def train_all_meta(residuals: Optional[List[dict]] = None) -> dict:
    """Train Ridge meta for all 7 stats. Returns summary dict."""
    results = {stat: train_meta(stat, residuals) for stat in STATS}

    # Log each stat's training run to MLflow (no-op if mlflow not installed)
    try:
        from src.prediction import mlflow_logger
        for _stat, _r in results.items():
            mlflow_logger.log_training_run(
                stat=_stat,
                coef=float(_r.get("coef", 1.0)),
                intercept=float(_r.get("intercept", 0.0)),
                r2=float(_r.get("r2", 0.0)),
                n=int(_r.get("n", 0)),
            )
    except Exception:
        pass

    # Champion/challenger: update champion R² from meta results
    try:
        from src.prediction.champion_challenger import _load_state, _save_state
        _cc = _load_state()
        for _stat, _r in results.items():
            if _r.get("r2") is not None and _stat in _cc.get("stats", {}):
                _cc["stats"][_stat]["champion_r2"] = float(_r["r2"])
        _save_state(_cc)
    except Exception:
        pass
    return results


def train_calibration(
    stat: Optional[str] = None,
    residuals_path: Optional[str] = None,
) -> dict:
    """Fit isotonic win-probability calibration from prop_residuals.json.

    Each row in residuals must have: {stat, predicted, actual, line}.
    Rows without a 'line' field are skipped.  Trains one IsotonicRegression
    per stat and saves to data/models/calibration_win_{stat}.joblib.

    Args:
        stat:           Specific stat to train, or None to train all.
        residuals_path: Override path; defaults to data/models/prop_residuals.json.

    Returns:
        {stat: {"n": int, "over_rate": float, "fitted": bool}, ...}
    """
    if residuals_path is None:
        residuals_path = os.path.join(_MODELS_DIR, "prop_residuals.json")
    if not os.path.exists(residuals_path):
        print(f"  [calib] {residuals_path} not found — nothing to calibrate")
        return {}

    all_rows: List[dict] = json.load(open(residuals_path, encoding="utf-8"))
    stats_to_train = [stat] if stat else STATS
    results: dict = {}

    for s in stats_to_train:
        rows = [
            r for r in all_rows
            if r.get("stat") == s
            and r.get("predicted") is not None
            and r.get("actual") is not None
            and r.get("line") is not None
        ]
        n = len(rows)
        if n < 10:
            results[s] = {"n": n, "over_rate": float("nan"), "fitted": False}
            print(f"  [calib] {s}: only {n} rows with line data — skipping (need ≥10)")
            continue
        preds   = np.array([float(r["predicted"]) for r in rows])
        lines_  = np.array([float(r["line"])      for r in rows])
        actuals = np.array([float(r["actual"])     for r in rows])
        over_rate = float((actuals > lines_).mean())
        _calibration.train_win_prob(s, preds, lines_, actuals)
        results[s] = {"n": n, "over_rate": round(over_rate, 3), "fitted": True}
        print(f"  [calib] {s}: n={n}  over_rate={over_rate:.3f}  fitted=True")

    return results


def train_cohort_calibration(
    residuals_path: Optional[str] = None,
    stat: Optional[str] = None,
) -> dict:
    """Fit CohortCalibrator from prop_residuals.json and compare vs global Brier.

    Each residuals row must have: {stat, predicted, actual, line}.
    Rows without 'line' are skipped.  Cohort context keys minutes/usage/rest_days
    are read when present; otherwise defaults are used.

    Args:
        residuals_path: Override path; defaults to data/models/prop_residuals.json.
        stat:           Single stat to evaluate (default: first available stat).

    Returns:
        compare_brier result dict plus {"fitted": bool, "saved": str}.
    """
    from src.calibration.cohort_calibrator import CohortCalibrator, compare_brier

    if residuals_path is None:
        residuals_path = os.path.join(_MODELS_DIR, "prop_residuals.json")
    if not os.path.exists(residuals_path):
        print(f"  [cohort_calib] {residuals_path} not found — nothing to fit")
        return {"fitted": False, "saved": ""}

    all_rows: List[dict] = json.load(open(residuals_path, encoding="utf-8"))
    target_stat = stat or (STATS[0] if STATS else "pts")

    records = []
    for r in all_rows:
        if r.get("stat") != target_stat:
            continue
        if r.get("predicted") is None or r.get("actual") is None or r.get("line") is None:
            continue
        pred_val  = float(r["predicted"])
        actual    = float(r["actual"])
        line_val  = float(r["line"])
        # Convert to win probability: P(actual > line)
        prob      = max(0.05, min(0.95, pred_val / max(line_val, 0.01) - 0.5 + 0.5))
        outcome   = 1.0 if actual > line_val else 0.0
        records.append({
            "prob":      prob,
            "outcome":   outcome,
            "minutes":   float(r.get("minutes",   25.0)),
            "usage":     float(r.get("usage",     0.20)),
            "rest_days": int(r.get("rest_days",    2)),
        })

    if len(records) < 10:
        print(f"  [cohort_calib] only {len(records)} rows for {target_stat} — skipping")
        return {"fitted": False, "saved": "", "n": len(records)}

    comparison = compare_brier(records)

    # Fit on full dataset and save
    cc = CohortCalibrator().fit(records)
    save_path = cc.save(os.path.join(_MODELS_DIR, "cohort_calibrator.pkl"))

    # Invalidate module-level singleton so next call reloads
    global _cohort_calibrator
    _cohort_calibrator = cc

    return {**comparison, "fitted": True, "saved": save_path, "stat": target_stat}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Prop model stacker")
    parser.add_argument("--predict", type=str, help="Player ID to predict")
    parser.add_argument("--train-meta", action="store_true", help="Train all meta models")
    parser.add_argument("--train-calibration", action="store_true",
                        help="Fit isotonic win-prob calibration from prop_residuals.json")
    parser.add_argument("--train-cohort-calibration", action="store_true",
                        help="Fit CohortCalibrator from prop_residuals.json")
    parser.add_argument("--stat", type=str, default=None,
                        help="Stat to calibrate (default: all / first)")
    args = parser.parse_args()

    if getattr(args, "train_cohort_calibration", False):
        result = train_cohort_calibration(stat=args.stat)
        print(f"  stat={result.get('stat')} fitted={result.get('fitted')}")
        if result.get("fitted"):
            print(f"  global_brier={result['global_brier']:.5f}  "
                  f"cohort_brier={result['cohort_brier']:.5f}  "
                  f"improvement={result['improvement']:+.5f}")
    elif args.train_calibration:
        results = train_calibration(stat=args.stat)
        for s, r in results.items():
            status = "fitted" if r["fitted"] else "skipped"
            print(f"  {s}: n={r['n']}  over_rate={r['over_rate']}  {status}")
    elif args.train_meta:
        results = train_all_meta()
        for stat, r in results.items():
            print(f"  {stat}: coef={r['coef']:.4f} intercept={r['intercept']:.4f} n={r['n']} r2={r['r2']:.3f}")
    elif args.predict:
        result = stack_predict(args.predict)
        print(f"\nPlayer: {result.player_name}")
        print(f"Suppressed: {result.suppressed} ({result.suppression_reason})")
        print(f"Meta applied: {result.meta_applied}")
        for stat in STATS:
            base = result.base_predictions.get(stat, float("nan"))
            adj  = result.predictions.get(stat, float("nan"))
            conf = result.confidence.get(stat, 0.0)
            print(f"  {stat:5s}: base={base:.2f}  adj={adj:.2f}  conf={conf:.2f}")
    else:
        parser.print_help()
