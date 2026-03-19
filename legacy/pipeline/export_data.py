"""
Layer 2 — Data Export.

Reads from PostgreSQL and writes structured files to data/{game_id}/:

  game_summary.json        — counts, teams, FG%
  frame_data.parquet       — tracking_coordinates (all objects, all frames)
  events.parquet           — shots + drives + play detections
  player_stats.parquet     — per-player aggregations
  team_stats.parquet       — per-team aggregations
  spacing.parquet          — per-frame spacing metrics (feature_vectors)
  game_flow.parquet        — per-frame momentum/flow metrics
  defensive_schemes.parquet — per-possession scheme labels

Cache: if all files exist, skips re-export unless --force is passed.

Usage:
  python -m pipeline.export_data --game-id <uuid>
  python -m pipeline.export_data --game-id <uuid> --force
"""
import argparse
import json
from pathlib import Path

import pandas as pd

from legacy.tracking.database import get_connection

DATA_DIR = Path(__file__).parent.parent / "data"

_EXPORTS = [
    "game_summary.json", "frame_data.parquet", "events.parquet",
    "player_stats.parquet", "team_stats.parquet",
]


def export_game(game_id: str, force: bool = False) -> Path:
    """Export all data for game_id. Returns output directory path."""
    out = DATA_DIR / game_id
    out.mkdir(parents=True, exist_ok=True)

    if not force and all((out / f).exists() for f in _EXPORTS):
        print(f"[export] Cache hit — {game_id}")
        return out

    with get_connection() as conn:
        summary = _export_summary(conn, game_id, out)
        frame_df = _export_frames(conn, game_id, out)
        _export_events(conn, game_id, out)
        _export_player_stats(frame_df, out)
        _export_team_stats(frame_df, out)
        _export_spacing(conn, game_id, out)
        _export_game_flow(conn, game_id, out)
        _export_defensive_schemes(conn, game_id, out)

    print(f"[export] Exported {game_id} → {out}")
    return out


# ── Per-section helpers ────────────────────────────────────────────────────────

def _export_summary(conn, game_id: str, out: Path) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT home_team, away_team, game_date, season FROM games WHERE id=%s",
            (game_id,),
        )
        row = cur.fetchone()

    info: dict = {"game_id": game_id}
    if row:
        info.update(home_team=row[0], away_team=row[1],
                    game_date=str(row[2]), season=row[3])

    counts = {
        "total_frames":     ("SELECT COUNT(DISTINCT frame_number) FROM tracking_coordinates WHERE game_id=%s",),
        "total_detections": ("SELECT COUNT(*) FROM tracking_coordinates WHERE game_id=%s",),
        "total_shots":      ("SELECT COUNT(*) FROM shot_logs WHERE game_id=%s",),
        "shots_made":       ("SELECT COUNT(*) FROM shot_logs WHERE game_id=%s AND made=true",),
        "total_possessions":("SELECT COUNT(*) FROM possessions WHERE game_id=%s",),
        "total_drives":     ("SELECT COUNT(*) FROM drive_events WHERE game_id=%s",),
        "total_plays":      ("SELECT COUNT(*) FROM play_detections WHERE game_id=%s",),
    }
    with conn.cursor() as cur:
        for key, (sql,) in counts.items():
            cur.execute(sql, (game_id,))
            info[key] = cur.fetchone()[0] or 0

    shots = info["total_shots"]
    info["fg_pct"] = round(info["shots_made"] / shots, 4) if shots else 0.0

    (out / "game_summary.json").write_text(json.dumps(info, indent=2))
    return info


def _export_frames(conn, game_id: str, out: Path) -> pd.DataFrame:
    df = pd.read_sql(
        """
        SELECT track_id, frame_number, timestamp_ms,
               COALESCE(x_ft, x) AS x, COALESCE(y_ft, y) AS y,
               velocity_x, velocity_y, speed, direction_degrees,
               object_type, confidence, team
        FROM tracking_coordinates
        WHERE game_id = %s
        ORDER BY frame_number, track_id
        """,
        conn, params=(game_id,),
    )
    df.to_parquet(out / "frame_data.parquet", index=False)
    return df


def _export_events(conn, game_id: str, out: Path) -> None:
    shots = pd.read_sql(
        """SELECT frame_number,
                  COALESCE(x_ft, x) AS x, COALESCE(y_ft, y) AS y,
                  shot_type, made, defender_distance, shot_angle
           FROM shot_logs WHERE game_id = %s""",
        conn, params=(game_id,),
    )
    shots["event_category"] = "shot"

    drives = pd.read_sql(
        """SELECT start_frame AS frame_number, track_id,
                  drive_angle_to_rim, penetration_depth, defender_beaten,
                  outcome, blow_by_probability, drive_kick_probability, foul_probability
           FROM drive_events WHERE game_id = %s""",
        conn, params=(game_id,),
    )
    drives["event_category"] = "drive"

    plays = pd.read_sql(
        """SELECT play_start_frame AS frame_number, play_type,
                  play_end_frame, confidence
           FROM play_detections WHERE game_id = %s""",
        conn, params=(game_id,),
    )
    plays["event_category"] = "play"

    events = pd.concat([shots, drives, plays], ignore_index=True, sort=False)
    events.to_parquet(out / "events.parquet", index=False)


def _export_player_stats(frame_df: pd.DataFrame, out: Path) -> None:
    players = frame_df[frame_df["object_type"] == "player"]
    if players.empty:
        pd.DataFrame().to_parquet(out / "player_stats.parquet", index=False)
        return

    stats = players.groupby("track_id").agg(
        frames_tracked=("frame_number", "count"),
        avg_speed=("speed", "mean"),
        max_speed=("speed", "max"),
        avg_x=("x", "mean"),
        avg_y=("y", "mean"),
        team=("team", "first"),
    ).round(3).reset_index()

    # Distance: sum of per-frame displacements
    sorted_p = players.sort_values(["track_id", "frame_number"])
    dx = sorted_p.groupby("track_id")["x"].diff().fillna(0)
    dy = sorted_p.groupby("track_id")["y"].diff().fillna(0)
    dist = ((dx ** 2 + dy ** 2) ** 0.5).groupby(sorted_p["track_id"]).sum()
    stats = stats.merge(dist.rename("distance_ft").reset_index(), on="track_id", how="left")

    stats.to_parquet(out / "player_stats.parquet", index=False)


def _export_team_stats(frame_df: pd.DataFrame, out: Path) -> None:
    players = frame_df[frame_df["object_type"] == "player"]
    if players.empty:
        pd.DataFrame().to_parquet(out / "team_stats.parquet", index=False)
        return

    stats = players.groupby("team").agg(
        avg_speed=("speed", "mean"),
        max_speed=("speed", "max"),
        total_detections=("frame_number", "count"),
        avg_x=("x", "mean"),
    ).round(3).reset_index()
    stats.to_parquet(out / "team_stats.parquet", index=False)


def _export_spacing(conn, game_id: str, out: Path) -> None:
    df = pd.read_sql(
        """SELECT frame_number, avg_inter_player_dist, convex_hull_area,
                  nearest_defender_dist, closing_speed
           FROM feature_vectors WHERE game_id = %s ORDER BY frame_number""",
        conn, params=(game_id,),
    )
    if not df.empty:
        df.to_parquet(out / "spacing.parquet", index=False)


def _export_game_flow(conn, game_id: str, out: Path) -> None:
    df = pd.read_sql(
        """SELECT frame_number, momentum_index, scoring_run_probability,
                  possession_pressure_index, comeback_probability, offensive_flow_score
           FROM game_flow WHERE game_id = %s ORDER BY frame_number""",
        conn, params=(game_id,),
    )
    if not df.empty:
        df.to_parquet(out / "game_flow.parquet", index=False)


def _export_defensive_schemes(conn, game_id: str, out: Path) -> None:
    df = pd.read_sql(
        """SELECT frame_number, scheme_label, switch_frequency, help_frequency,
                  paint_collapse_frequency, weakside_rotation_speed, cohesion_score
           FROM defensive_schemes WHERE game_id = %s ORDER BY frame_number""",
        conn, params=(game_id,),
    )
    if not df.empty:
        df.to_parquet(out / "defensive_schemes.parquet", index=False)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Export game data to parquet/json")
    p.add_argument("--game-id", required=True)
    p.add_argument("--force", action="store_true", help="Re-export even if cached")
    args = p.parse_args()
    export_game(args.game_id, force=args.force)
