"""Analytics API router — queries PostgreSQL tracking database."""
import os
import sys

from fastapi import APIRouter, HTTPException, Query

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.db import get_connection

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
    track_ids: str = Query(..., description="Comma-separated list of 5 track IDs"),
):
    """Score a 5-player lineup. NOTE: Lineup optimizer requires Phase 6 CV data."""
    raise HTTPException(
        status_code=503,
        detail="Lineup optimizer not yet available. Requires 20+ full games of CV data (Phase 6)."
    )


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
