from fastapi import APIRouter, HTTPException, Query
from tracking.database import get_connection

router = APIRouter()


@router.get("/shot-chart")
def shot_chart(game_id: str = Query(..., description="Game UUID")):
    """Return all shot log records for a game."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT player_id, x, y, made, court_zone,
                       nearest_defender_dist, shot_angle, fatigue_proxy
                FROM shot_logs
                WHERE game_id = %s
                ORDER BY created_at
                """,
                (game_id,),
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.close()
        return {"game_id": game_id, "shots": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lineup-stats")
def lineup_stats(
    track_ids: str = Query(..., description="Comma-separated list of 5 track IDs, e.g. '1,2,3,4,5'"),
):
    """Score a 5-player lineup by EPA and closing speed."""
    from models.lineup_optimizer import LineupOptimizer
    try:
        lineup = [int(t.strip()) for t in track_ids.split(",")]
        if len(lineup) != 5:
            raise HTTPException(status_code=422, detail="Exactly 5 track_ids required")
        model = LineupOptimizer.load("lineup_optimizer")
        result = model.predict({"lineup": lineup})
        result["lineup"] = lineup
        return result
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"Model artifact missing: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tracking")
def tracking_data(
    game_id: str = Query(..., description="Game UUID"),
    frame_start: int = Query(0, description="First frame number (inclusive)"),
    frame_end: int = Query(500, description="Last frame number (inclusive)"),
    object_type: str = Query("player", description="'player' or 'ball'"),
):
    """Return tracking coordinates for a frame range within a game."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT frame_number, track_id, x, y, vx, vy, direction, object_type
                FROM tracking_coordinates
                WHERE game_id = %s
                  AND frame_number BETWEEN %s AND %s
                  AND object_type = %s
                ORDER BY frame_number, track_id
                """,
                (game_id, frame_start, frame_end, object_type),
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.close()
        return {"game_id": game_id, "frame_range": [frame_start, frame_end], "rows": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
