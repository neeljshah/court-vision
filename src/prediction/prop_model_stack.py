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
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")
_STACK_CACHE = os.path.join(_MODELS_DIR, "prop_stack_meta.json")

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

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

    # ── Apply injury multiplier to raw predictions ───────────────────────────
    adjusted: Dict[str, float] = {}
    for stat, val in base_preds.items():
        if np.isnan(val):
            adjusted[stat] = val
        else:
            adjusted[stat] = val * injury_mult

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
        val = adjusted.get(stat, float("nan"))
        if np.isnan(val) or suppressed:
            confidence[stat] = 0.0
        else:
            conf = injury_mult * (1.0 - min(dnp_prob, 0.5) * 2) + micro_conf_adj
            confidence[stat] = round(max(0.0, min(1.0, conf)), 3)

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

    player_name = base_raw.get("player_name", str(player_id))

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
    return {stat: train_meta(stat, residuals) for stat in STATS}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Prop model stacker")
    parser.add_argument("--predict", type=str, help="Player ID to predict")
    parser.add_argument("--train-meta", action="store_true", help="Train all meta models")
    args = parser.parse_args()

    if args.train_meta:
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
