from fastapi import APIRouter, HTTPException, Query
from models.shot_probability import ShotProbabilityModel
from models.win_probability import WinProbabilityModel
from models.player_impact import PlayerImpactModel

router = APIRouter()

# Lazy-load models once per process (module-level cache)
_shot_model: ShotProbabilityModel | None = None
_win_model: WinProbabilityModel | None = None
_impact_model: PlayerImpactModel | None = None


def _get_shot_model() -> ShotProbabilityModel:
    global _shot_model
    if _shot_model is None:
        _shot_model = ShotProbabilityModel.load("shot_probability")
    return _shot_model


def _get_win_model() -> WinProbabilityModel:
    global _win_model
    if _win_model is None:
        _win_model = WinProbabilityModel.load("win_probability")
    return _win_model


def _get_impact_model() -> PlayerImpactModel:
    global _impact_model
    if _impact_model is None:
        _impact_model = PlayerImpactModel.load("player_impact")
    return _impact_model


@router.get("/shot")
def shot_probability(
    defender_dist: float = Query(..., description="Distance to nearest defender in pixels"),
    shot_angle: float = Query(..., description="Shot angle in degrees"),
    fatigue_proxy: float = Query(0.5, description="Fatigue proxy [0,1]; 0=fresh, 1=fatigued"),
    court_zone: str = Query("midrange", description="'paint', 'midrange', or 'three'"),
):
    """Predict shot make probability for given shot context."""
    try:
        model = _get_shot_model()
        prob = model.predict({
            "defender_dist": defender_dist,
            "shot_angle": shot_angle,
            "fatigue_proxy": fatigue_proxy,
            "court_zone": court_zone,
        })
        return {"probability": prob}
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"Model artifact missing: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/win")
def win_probability(
    convex_hull_area: float = Query(..., description="Offensive team hull area in px\u00b2"),
    avg_inter_player_dist: float = Query(..., description="Average inter-player distance in px"),
    scoring_run: int = Query(0, description="Current scoring run (positive=team leading, negative=trailing)"),
    possession_streak: int = Query(0, description="Current possession streak length"),
    swing_point: int = Query(0, ge=0, le=1, description="1 if this is a swing-point possession, else 0"),
):
    """Predict win probability for current game state."""
    try:
        model = _get_win_model()
        prob = model.predict({
            "convex_hull_area": convex_hull_area,
            "avg_inter_player_dist": avg_inter_player_dist,
            "scoring_run": scoring_run,
            "possession_streak": possession_streak,
            "swing_point": swing_point,
        })
        return {"win_probability": prob}
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"Model artifact missing: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/player-impact")
def player_impact(
    track_id: int = Query(..., description="Player track ID"),
    made_rate: float = Query(..., ge=0.0, le=1.0, description="Shot made rate for this player"),
    shots_taken: int = Query(..., ge=1, description="Total shots taken"),
    cut_events: int = Query(0, description="Number of cut events"),
    screen_events: int = Query(0, description="Number of screen events"),
):
    """Predict player EPA per 100 possessions."""
    try:
        model = _get_impact_model()
        result = model.predict({
            "track_id": track_id,
            "made_rate": made_rate,
            "shots_taken": shots_taken,
            "event_mix": {"cut": cut_events, "screen": screen_events},
        })
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"Model artifact missing: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
