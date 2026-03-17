"""Defensive pressure metrics computation module (FE-02).

Computes per-player nearest defender distance and closing speed for a frame.
Pure computation — no database or numpy dependencies.
"""
import math

from features.types import DefensivePressure


def compute_defensive_pressure(
    player_rows: list[dict],
    game_id: str,
    frame_number: int,
    timestamp_ms: float,
    prev_distances: dict[int, float],
) -> list[DefensivePressure]:
    """Compute defensive pressure metrics for all players in a frame.

    Args:
        player_rows: List of dicts, each with keys:
            - track_id (int): DeepSORT track ID
            - x (float): Court x coordinate
            - y (float): Court y coordinate
            - team (str | None): Team label (e.g. 'offense', 'defense'). If None,
              all players are treated as both pressured and potential defenders.
        game_id: UUID of the game.
        frame_number: Video frame index.
        timestamp_ms: Frame timestamp in milliseconds.
        prev_distances: Mutable dict mapping track_id → previous nearest defender
            distance. Updated in place after computation.

    Returns:
        One DefensivePressure instance per offensive player (or per player when
        team is None for all rows).
    """
    if not player_rows:
        return []

    all_have_team = all(r["team"] is not None for r in player_rows)

    if all_have_team:
        # Split into offense and defense by team label
        # Players whose team != 'defense' are treated as offensive targets
        offense = [r for r in player_rows if r["team"] != "defense"]
        defense = [r for r in player_rows if r["team"] == "defense"]
        targets = offense
        # Build a per-target defender list (all defensive players)
        defender_pool = {r["track_id"]: defense for r in offense}
    else:
        # team=None for some/all rows: every player is pressured by all others
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

        # closing_speed = current - previous; negative means defender is closing in
        prev = prev_distances.get(tid)
        if prev is None:
            closing_speed = 0.0
        else:
            closing_speed = nearest_dist - prev

        # Mutate prev_distances in place
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
