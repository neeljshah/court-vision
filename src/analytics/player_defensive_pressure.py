"""Per-player defensive pressure metrics (per-frame, pure computation).

Computes nearest defender distance and closing speed per player.
Complements defense_pressure.py (team-level pressure score) —
this module provides per-player raw values.
"""
import math

from src.analytics.spatial_types import DefensivePressure


def compute_player_defensive_pressure(
    player_rows: list[dict],
    game_id: str,
    frame_number: int,
    timestamp_ms: float,
    prev_distances: dict[int, float],
) -> list[DefensivePressure]:
    """Compute defensive pressure metrics for all players in a frame.

    Args:
        player_rows: List of dicts with keys: track_id, x, y, team (optional).
        game_id: UUID of the game.
        frame_number: Video frame index.
        timestamp_ms: Frame timestamp in milliseconds.
        prev_distances: Mutable dict {track_id: prev_nearest_dist}, updated in place.

    Returns:
        One DefensivePressure instance per offensive player.
    """
    if not player_rows:
        return []

    all_have_team = all(r["team"] is not None for r in player_rows)

    if all_have_team:
        offense = [r for r in player_rows if r["team"] != "defense"]
        defense = [r for r in player_rows if r["team"] == "defense"]
        targets = offense
        defender_pool = {r["track_id"]: defense for r in offense}
    else:
        targets = player_rows
        defender_pool = {
            r["track_id"]: [o for o in player_rows if o["track_id"] != r["track_id"]]
            for r in player_rows
        }

    results: list[DefensivePressure] = []

    for player in targets:
        tid = player["track_id"]
        px, py = player["x"], player["y"]
        defenders = defender_pool[tid]

        if defenders:
            nearest_dist = min(
                math.hypot(d["x"] - px, d["y"] - py) for d in defenders
            )
        else:
            nearest_dist = float("inf")

        prev = prev_distances.get(tid)
        closing_speed = 0.0 if prev is None else nearest_dist - prev
        prev_distances[tid] = nearest_dist

        results.append(
            DefensivePressure(
                game_id=game_id,
                track_id=tid,
                frame_number=frame_number,
                nearest_defender_distance=nearest_dist,
                closing_speed=closing_speed,
                timestamp_ms=timestamp_ms,
            )
        )

    return results
