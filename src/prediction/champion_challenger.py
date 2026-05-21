"""champion_challenger.py — Track shadow challenger models vs production champions.

State file: data/models/champion_challenger.json
Schema: {
  "stats": {
    "<stat>": {
      "champion_r2": float,
      "challenger_r2": float | null,
      "challenger_model_path": str | null,
      "bets_evaluated": int,
      "champion_predictions": [float, ...],   # rolling last 200
      "challenger_predictions": [float, ...], # rolling last 200
      "actuals": [float, ...],                # rolling last 200
      "last_promotion": str | null            # ISO date of last promotion
    }
  }
}
"""
from __future__ import annotations

import json
import os
from datetime import date
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")
_CC_PATH = os.path.join(_MODELS_DIR, "champion_challenger.json")
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
_MAX_HISTORY = 200  # Rolling window for paired predictions
_MIN_BETS_PROMOTE = 100  # Minimum evaluations before promotion considered


def _load_state() -> dict:
    if not os.path.exists(_CC_PATH):
        return {"stats": {s: {
            "champion_r2": None, "challenger_r2": None,
            "challenger_model_path": None, "bets_evaluated": 0,
            "champion_predictions": [], "challenger_predictions": [],
            "actuals": [], "last_promotion": None,
        } for s in STATS}}
    try:
        return json.load(open(_CC_PATH, encoding="utf-8"))
    except Exception:
        return {"stats": {}}


def _save_state(state: dict) -> None:
    os.makedirs(_MODELS_DIR, exist_ok=True)
    with open(_CC_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def record_evaluation(
    stat: str,
    champion_pred: float,
    challenger_pred: Optional[float],
    actual: float,
) -> None:
    """Record one prediction evaluation for both champion and challenger."""
    state = _load_state()
    s = state["stats"].setdefault(stat, {
        "champion_r2": None, "challenger_r2": None,
        "challenger_model_path": None, "bets_evaluated": 0,
        "champion_predictions": [], "challenger_predictions": [],
        "actuals": [], "last_promotion": None,
    })
    # Rolling append (trim to _MAX_HISTORY)
    s["champion_predictions"].append(float(champion_pred))
    s["champion_predictions"] = s["champion_predictions"][-_MAX_HISTORY:]
    if challenger_pred is not None:
        s["challenger_predictions"].append(float(challenger_pred))
        s["challenger_predictions"] = s["challenger_predictions"][-_MAX_HISTORY:]
    s["actuals"].append(float(actual))
    s["actuals"] = s["actuals"][-_MAX_HISTORY:]
    s["bets_evaluated"] = s.get("bets_evaluated", 0) + 1
    # Recompute R² values
    s["champion_r2"] = _compute_r2(s["champion_predictions"], s["actuals"])
    if s["challenger_predictions"] and len(s["challenger_predictions"]) == len(s["actuals"]):
        s["challenger_r2"] = _compute_r2(s["challenger_predictions"], s["actuals"])
    _save_state(state)


def _compute_r2(preds: List[float], actuals: List[float]) -> Optional[float]:
    if len(preds) < 2 or len(preds) != len(actuals):
        return None
    mean_a = sum(actuals) / len(actuals)
    ss_tot = sum((a - mean_a) ** 2 for a in actuals)
    if ss_tot == 0:
        return None
    ss_res = sum((p - a) ** 2 for p, a in zip(preds, actuals))
    return round(1.0 - ss_res / ss_tot, 4)


def check_and_promote(stat: str, alpha: float = 0.05) -> bool:
    """Check if challenger should be promoted. Returns True if promoted.

    Criteria:
    - bets_evaluated >= _MIN_BETS_PROMOTE
    - challenger R² > champion R²
    - Paired t-test p < alpha (scipy.stats.ttest_rel)
    """
    state = _load_state()
    s = state["stats"].get(stat)
    if not s:
        return False

    n = s.get("bets_evaluated", 0)
    c_r2 = s.get("champion_r2")
    ch_r2 = s.get("challenger_r2")

    if n < _MIN_BETS_PROMOTE or c_r2 is None or ch_r2 is None:
        return False
    if ch_r2 <= c_r2:
        return False

    # Paired t-test on prediction errors
    champ_preds = s.get("champion_predictions", [])
    chall_preds = s.get("challenger_predictions", [])
    actuals = s.get("actuals", [])
    n_paired = min(len(champ_preds), len(chall_preds), len(actuals))
    if n_paired < 30:
        return False

    try:
        from scipy import stats as _stats
        champ_errs = [abs(champ_preds[i] - actuals[i]) for i in range(n_paired)]
        chall_errs = [abs(chall_preds[i] - actuals[i]) for i in range(n_paired)]
        _, p_val = _stats.ttest_rel(champ_errs, chall_errs)
        if p_val >= alpha:
            return False
    except ImportError:
        # scipy not available: promote based on R² alone if challenger has 100+ bets
        pass

    # Promote: challenger becomes new champion
    s["champion_r2"] = ch_r2
    s["challenger_r2"] = None
    s["challenger_model_path"] = None
    s["champion_predictions"] = chall_preds
    s["challenger_predictions"] = []
    s["last_promotion"] = str(date.today())
    _save_state(state)
    return True


def get_summary() -> Dict[str, dict]:
    """Return champion/challenger summary for all stats."""
    state = _load_state()
    return state.get("stats", {})
