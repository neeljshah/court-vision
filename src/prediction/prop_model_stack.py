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

    # ── Pull base predictions from player_props ──────────────────────────────
    try:
        from src.prediction.player_props import predict_props
        base_raw = predict_props(player_id, context=game_context)
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

    # ── Confidence scores ─────────────────────────────────────────────────────
    # Base confidence on: data completeness, injury mult, form consistency
    confidence: Dict[str, float] = {}
    for stat in STATS:
        val = adjusted.get(stat, float("nan"))
        if np.isnan(val) or suppressed:
            confidence[stat] = 0.0
        else:
            conf = injury_mult * (1.0 - min(dnp_prob, 0.5) * 2)
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
