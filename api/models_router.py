"""Models API router — serves predictions from trained src/prediction/ models.

Routes:
    GET /predictions/shot          xFG probability (CV spatial features)
    GET /predictions/win           Pre-game win probability (XGBoost)
    GET /predictions/player-impact Player EPA (Phase 6+ — needs CV game data)
"""
import os
import sys
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.prediction.xfg_model import XFGModel
from src.prediction.win_probability import WinProbModel

router = APIRouter()

_shot_model_cache: Optional[XFGModel] = None
_win_model_cache: Optional[WinProbModel] = None

_XFG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models", "xfg_v1.pkl")
_WIN_PATH  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models", "win_probability.pkl")


def _get_shot_model() -> XFGModel:
    global _shot_model_cache
    if _shot_model_cache is None:
        if not os.path.exists(_XFG_PATH):
            raise FileNotFoundError(
                f"xFG model not found at {_XFG_PATH}. "
                "Run: python src/prediction/xfg_model.py --train"
            )
        _shot_model_cache = XFGModel.load(_XFG_PATH)
    return _shot_model_cache


def _get_win_model() -> WinProbModel:
    global _win_model_cache
    if _win_model_cache is None:
        if not os.path.exists(_WIN_PATH):
            raise FileNotFoundError(
                f"Win prob model not found at {_WIN_PATH}. "
                "Run: python src/prediction/win_probability.py --train"
            )
        _win_model_cache = WinProbModel.load(_WIN_PATH)
    return _win_model_cache


def _get_impact_model():
    """Player impact model — not yet trained (Phase 6+)."""
    return None


# ── /predictions/shot ─────────────────────────────────────────────────────────

@router.get("/shot")
def shot_probability(
    defender_dist: float = Query(...,  description="Defender distance in court pixels"),
    shot_angle:    float = Query(...,  description="Shot angle in degrees"),
    fatigue_proxy: float = Query(0.0,  description="Fatigue proxy 0–1"),
    court_zone:    str   = Query("paint", description="Court zone label"),
):
    """
    Predict shot probability using spatial features.
    Backed by xFG v1 model (Brier 0.226, 221K shots).
    """
    try:
        model = _get_shot_model()
        # Map spatial inputs to xFG feature space
        is_3pt      = 1 if "3" in court_zone.lower() or "corner" in court_zone.lower() else 0
        shot_dist   = max(0, int(defender_dist / 10))   # pixels → approximate feet
        prob = model.predict({
            "shot_zone_basic":  court_zone,
            "shot_zone_area":   "Center(C)",
            "shot_zone_range":  "8-16 ft.",
            "shot_distance":    shot_dist,
            "is_3pt":           is_3pt,
            "action_type":      "Jump Shot",
        })
        # Adjust for fatigue
        prob = float(prob) * (1.0 - fatigue_proxy * 0.05)
        prob = round(max(0.0, min(1.0, prob)), 4)
        return {
            "probability": prob,
            "model": "xfg_v1",
            "inputs": {
                "defender_dist": defender_dist,
                "shot_angle":    shot_angle,
                "fatigue_proxy": fatigue_proxy,
                "court_zone":    court_zone,
            },
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── /predictions/win ──────────────────────────────────────────────────────────

@router.get("/win")
def win_probability(
    convex_hull_area:      float = Query(...,  description="Team spacing hull area (sq court units)"),
    avg_inter_player_dist: float = Query(0.0,  description="Average inter-player distance"),
    scoring_run:           int   = Query(0,    description="Current scoring run length"),
    possession_streak:     int   = Query(0,    description="Consecutive possession wins"),
    swing_point:           int   = Query(0,    ge=0, le=1, description="1 if momentum-swing possession"),
):
    """
    In-game win probability using spatial momentum features.
    Backed by WinProbModel (XGBoost, 69.1% accuracy).
    """
    try:
        model = _get_win_model()
        # Build feature dict for win prob model — use spatial features as proxies
        result = model.predict(
            home_team="HOM",
            away_team="AWY",
            season="2024-25",
            extra_features={
                "convex_hull_area":      convex_hull_area,
                "avg_inter_player_dist": avg_inter_player_dist,
                "scoring_run":           scoring_run,
                "possession_streak":     possession_streak,
                "swing_point":           swing_point,
            },
        )
        # Normalise to always return win_probability key
        if isinstance(result, dict):
            prob = result.get("win_probability", result.get("home_win_prob", 0.5))
        else:
            prob = float(result)
        return {"win_probability": round(float(prob), 4)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── /predictions/player-impact ────────────────────────────────────────────────

@router.get("/player-impact")
def player_impact(
    track_id:    int   = Query(...,  description="CV tracker player slot ID (0-9)"),
    made_rate:   float = Query(0.0,  description="Shot make rate this game"),
    shots_taken: int   = Query(0,    description="Shots taken this game"),
):
    """
    Player EPA (Expected Points Added per 100 possessions).
    Phase 6+ model — requires 20+ games of CV data.
    Returns a placeholder until model is trained.
    """
    try:
        model = _get_impact_model()
        if model is not None:
            result = model.predict({
                "track_id":    track_id,
                "made_rate":   made_rate,
                "shots_taken": shots_taken,
            })
            if isinstance(result, dict):
                return result
            return {"epa_per_100": float(result)}

        # Placeholder: simple linear estimate until Phase 6 model trains
        epa = round((made_rate - 0.45) * shots_taken * 2.5, 3)
        return {
            "epa_per_100":    epa,
            "track_id":       track_id,
            "model":          "placeholder_linear",
            "note":           "Phase 6 model trains after 20 CV games",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
