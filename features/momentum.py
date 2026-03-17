"""Momentum computation module.

Computes per-segment momentum snapshots from shot event data.
Groups shot events into segments by possession number, then
computes scoring runs, possession streaks, and swing points.

No database dependencies — pure computation module.
"""

import math
from features.types import MomentumSnapshot


def compute_momentum(
    shot_events: list[dict],
    game_id: str,
    segment_size_possessions: int = 5,
) -> list[MomentumSnapshot]:
    """Compute momentum snapshots from a list of shot events.

    Segments are defined by possession_num // segment_size_possessions.
    For each segment:
    - scoring_run: length of the final consecutive made-shot streak by the
      same team in the segment (0 if no made shots)
    - possession_streak: length of the longest consecutive sequence of
      possessions where the same team scored (made shot)
    - swing_point: True if the leading team (by cumulative made shots)
      changed between this segment and the previous one
    - timestamp_ms: timestamp_ms of the last event in the segment

    Args:
        shot_events: List of dicts with keys:
            'team' (str), 'made' (bool), 'possession_num' (int),
            'timestamp_ms' (float), 'game_id' (str).
        game_id: UUID string for the game.
        segment_size_possessions: Number of possessions per segment (default 5).

    Returns:
        List of MomentumSnapshot sorted by segment_id ascending.
        Returns [] if shot_events is empty.
    """
    if not shot_events:
        return []

    # Group events by segment
    segments: dict[int, list[dict]] = {}
    for event in shot_events:
        seg_id = event["possession_num"] // segment_size_possessions
        segments.setdefault(seg_id, []).append(event)

    # Sort each segment by possession_num to maintain order
    for seg_id in segments:
        segments[seg_id].sort(key=lambda e: (e["possession_num"], e["timestamp_ms"]))

    sorted_seg_ids = sorted(segments.keys())

    # Track cumulative team scores across segments for swing point detection
    cumulative_scores: dict[str, int] = {}
    prev_leader: str | None = None

    results: list[MomentumSnapshot] = []

    for i, seg_id in enumerate(sorted_seg_ids):
        events = segments[seg_id]

        # ---------------------------------------------------------------
        # scoring_run: length of the final consecutive made-shot streak
        # ---------------------------------------------------------------
        scoring_run = 0
        run_team: str | None = None
        current_run = 0
        current_run_team: str | None = None

        for ev in events:
            if ev["made"]:
                if ev["team"] == current_run_team:
                    current_run += 1
                else:
                    current_run = 1
                    current_run_team = ev["team"]
            else:
                # Missed shot resets run
                current_run = 0
                current_run_team = None

        scoring_run = current_run  # length of final run at segment end

        # ---------------------------------------------------------------
        # possession_streak: max consecutive possessions with same team scoring
        # Each possession_num that has at least one made shot counts as "won"
        # ---------------------------------------------------------------
        # Build ordered sequence of (possession_num, team_scored) for made shots
        scored_poss: dict[int, str] = {}
        for ev in events:
            if ev["made"]:
                # First scorer in a possession wins it (simplified)
                if ev["possession_num"] not in scored_poss:
                    scored_poss[ev["possession_num"]] = ev["team"]

        possession_streak = 0
        if scored_poss:
            ordered = sorted(scored_poss.items())
            best_streak = 1
            cur_streak = 1
            for j in range(1, len(ordered)):
                if ordered[j][1] == ordered[j - 1][1]:
                    cur_streak += 1
                    best_streak = max(best_streak, cur_streak)
                else:
                    cur_streak = 1
            possession_streak = best_streak

        # ---------------------------------------------------------------
        # Update cumulative scores and detect swing point
        # ---------------------------------------------------------------
        seg_scores: dict[str, int] = {}
        for ev in events:
            if ev["made"]:
                seg_scores[ev["team"]] = seg_scores.get(ev["team"], 0) + 1

        for team, pts in seg_scores.items():
            cumulative_scores[team] = cumulative_scores.get(team, 0) + pts

        # Determine current leader (by segment scores, not cumulative)
        current_leader: str | None = None
        if seg_scores:
            max_pts = max(seg_scores.values())
            leaders = [t for t, p in seg_scores.items() if p == max_pts]
            if len(leaders) == 1:
                current_leader = leaders[0]
            # else: tied → no clear leader

        # Swing point: previous segment had a different non-None leader
        swing_point = False
        if i > 0 and prev_leader is not None and current_leader is not None:
            swing_point = current_leader != prev_leader

        prev_leader = current_leader

        # ---------------------------------------------------------------
        # timestamp_ms = timestamp of last event in segment
        # ---------------------------------------------------------------
        timestamp_ms = events[-1]["timestamp_ms"]

        results.append(
            MomentumSnapshot(
                game_id=game_id,
                segment_id=seg_id,
                scoring_run=scoring_run,
                possession_streak=possession_streak,
                swing_point=swing_point,
                timestamp_ms=timestamp_ms,
            )
        )

    return results
