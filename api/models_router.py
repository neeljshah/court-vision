"""Models API router — serves predictions from trained src/prediction/ models.

NOTE: /shot uses xfg_model (trained on 221K real shots, Brier 0.226).
      /win uses win_probability (XGBoost, 27 features, 67.7% accuracy).
      /player-impact is not yet available (Phase 7 — needs CV game data).
"""
import os
import sys

from fastapi import APIRouter, HTTPException, Query

# Ensure src/ is importable when running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.prediction.xfg_model import XFGModel
from src.prediction.win_probability import WinProbModel

router = APIRouter()

_xfg_model: XFGModel | None = None
_win_model: WinProbModel | None = None

_XFG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models", "xfg_v1.pkl")
_WIN_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models", "win_probability.pkl")


def _get_xfg_model() -> XFGModel:
    global _xfg_model
    if _xfg_model is None:
        if not os.path.exists(_XFG_PATH):
            raise FileNotFoundError(f"xFG model not found at {_XFG_PATH}. Run: python src/prediction/xfg_model.py --train")
        _xfg_model = XFGModel.load(_XFG_PATH)
    return _xfg_model


def _get_win_model() -> WinProbModel:
    global _win_model
    if _win_model is None:
        if not os.path.exists(_WIN_PATH):
            raise FileNotFoundError(f"Win prob model not found at {_WIN_PATH}. Run: python src/prediction/win_probability.py --train")
        _win_model = WinProbModel.load(_WIN_PATH)
    return _win_model


@router.get("/shot")
def shot_probability(
    shot_zone_basic: str = Query("Mid-Range", description="Zone: 'Restricted Area', 'In The Paint (Non-RA)', 'Mid-Range', 'Left Corner 3', 'Right Corner 3', 'Above the Break 3', 'Backcourt'"),
    shot_zone_range: str = Query("8-16 ft.", description="Range: '8-16 ft.', '16-24 ft.', 'Less Than 8 ft.', '24+ ft.', 'Back Court Shot'"),
    shot_distance: int = Query(15, description="Distance in feet"),
    is_3pt: int = Query(0, ge=0, le=1, description="1 if 3-pointer"),
    action_type: str = Query("Jump Shot", description="Shot action type"),
):
    """Predict xFG (expected field goal %) for a shot. Trained on 221K real NBA shots."""
    try:
        model = _get_xfg_model()
        prob = model.predict({
            "shot_zone_basic": shot_zone_basic,
            "shot_zone_area": "Center(C)",
            "shot_zone_range": shot_zone_range,
            "shot_distance": shot_distance,
            "is_3pt": is_3pt,
            "action_type": action_type,
        })
        return {"xfg": prob, "model": "xfg_v1", "brier_score": 0.226}
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/win")
def win_probability(
    home_team: str = Query(..., description="Home team abbreviation, e.g. 'BOS'"),
    away_team: str = Query(..., description="Away team abbreviation, e.g. 'GSW'"),
    season: str = Query("2024-25", description="Season string, e.g. '2024-25'"),
):
    """Pre-game win probability. XGBoost, 27 features, 67.7% accuracy on 3 seasons."""
    try:
        model = _get_win_model()
        result = model.predict(home_team=home_team, away_team=away_team, season=season)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/player-impact")
def player_impact_unavailable():
    """Player EPA model — not yet trained (requires Phase 6 full game data)."""
    raise HTTPException(
        status_code=503,
        detail="Player impact model not yet available. Requires 20+ full games of CV data (Phase 6)."
    )
