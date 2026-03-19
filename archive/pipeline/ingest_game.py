"""
Layer 1 — Game Ingestion.

Accepts:
  --video <path>           Run full tracking + features pipeline on a video file.
  --tracking-file <path>   Import pre-processed tracking data (.parquet or .json).

Outputs a game_id and writes a game record into the database.
Usage:
  python -m pipeline.ingest_game --video game.mp4 --home "Celtics" --away "Warriors"
  python -m pipeline.ingest_game --tracking-file tracking.parquet --game-id <uuid>
"""
import argparse
import subprocess
import sys
import uuid
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent


def ingest_video(
    video_path: str,
    game_id: str | None = None,
    home_team: str = "Home",
    away_team: str = "Away",
    game_date: str = "2024-01-01",
    season: str = "2024-25",
) -> str:
    """Run full tracking + features pipeline on a video file. Returns game_id."""
    game_id = game_id or str(uuid.uuid4())
    _register_game(game_id, home_team, away_team, game_date, season)

    print(f"[ingest] Running tracking pipeline for game {game_id}…")
    _run(sys.executable, "-m", "pipelines.run_pipeline",
         "--video", video_path, "--game-id", game_id, "--skip", "2")

    print(f"[ingest] Running features pipeline…")
    _run(sys.executable, "-m", "features.feature_pipeline", "--game-id", game_id)

    print(f"[ingest] Done — game_id: {game_id}")
    return game_id


def ingest_tracking_file(
    file_path: str,
    game_id: str | None = None,
    home_team: str = "Home",
    away_team: str = "Away",
    game_date: str = "2024-01-01",
    season: str = "2024-25",
) -> str:
    """Import pre-processed tracking data (.parquet or .json) and run features."""
    from tracking.database import get_connection

    path = Path(file_path)
    game_id = game_id or str(uuid.uuid4())
    _register_game(game_id, home_team, away_team, game_date, season)

    print(f"[ingest] Loading tracking file: {path.name}")
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    elif path.suffix == ".json":
        df = pd.read_json(path)
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}. Use .parquet or .json")

    df["game_id"] = game_id

    _COLS = [
        "game_id", "track_id", "frame_number", "timestamp_ms",
        "x", "y", "x_ft", "y_ft", "velocity_x", "velocity_y",
        "speed", "direction_degrees", "object_type", "confidence", "team",
    ]
    present = [c for c in _COLS if c in df.columns]
    rows = df[present].to_dict("records")

    col_str = ", ".join(present)
    placeholders = ", ".join(["%s"] * len(present))
    sql = (f"INSERT INTO tracking_coordinates ({col_str}) VALUES ({placeholders}) "
           f"ON CONFLICT DO NOTHING")

    print(f"[ingest] Writing {len(rows):,} rows to DB…")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, [tuple(r[c] for c in present) for r in rows])
        conn.commit()

    print(f"[ingest] Running features pipeline…")
    _run(sys.executable, "-m", "features.feature_pipeline", "--game-id", game_id)

    print(f"[ingest] Done — game_id: {game_id}")
    return game_id


def _register_game(game_id: str, home_team: str, away_team: str,
                   game_date: str, season: str) -> None:
    from tracking.database import get_connection
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO games (id, home_team, away_team, game_date, season) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (game_id, home_team, away_team, game_date, season),
            )
        conn.commit()


def _run(*cmd: str) -> None:
    subprocess.run(list(cmd), cwd=str(ROOT), check=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Ingest a game into the NBA AI system")
    p.add_argument("--video", help="Video file path")
    p.add_argument("--tracking-file", help="Pre-processed tracking data (.parquet/.json)")
    p.add_argument("--game-id", help="Game UUID (auto-generated if omitted)")
    p.add_argument("--home", default="Home")
    p.add_argument("--away", default="Away")
    p.add_argument("--date", default="2024-01-01")
    p.add_argument("--season", default="2024-25")
    args = p.parse_args()

    meta = dict(home_team=args.home, away_team=args.away,
                game_date=args.date, season=args.season)

    if args.video:
        gid = ingest_video(args.video, game_id=args.game_id, **meta)
    elif args.tracking_file:
        gid = ingest_tracking_file(args.tracking_file, game_id=args.game_id, **meta)
    else:
        p.error("Provide --video or --tracking-file")

    print(gid)
