"""Per-segment momentum event computation.

Computes MomentumSnapshot events from shot event data.
Complements momentum.py (per-frame rolling momentum score) —
this module produces discrete possession-segment snapshots.

No database dependencies — pure computation module.
"""
import math
from src.analytics.spatial_types import MomentumSnapshot


def compute_momentum(
    shot_events: list[dict],
    game_id: str,
    segment_size_possessions: int = 5,
) -> list[MomentumSnapshot]:
    """Compute momentum snapshots from a list of shot events.

    Args:
        shot_events: List of dicts with keys:
            'team' (str), 'made' (bool), 'possession_num' (int),
            'timestamp_ms' (float), 'game_id' (str).
        game_id: UUID string for the game.
        segment_size_possessions: Possessions per segment (default 5).

    Returns:
        List of MomentumSnapshot sorted by segment_id ascending.
    """
    if not shot_events:
        return []

    segments: dict[int, list[dict]] = {}
    for event in shot_events:
        seg_id = event["possession_num"] // segment_size_possessions
        segments.setdefault(seg_id, []).append(event)

    for seg_id in segments:
        segments[seg_id].sort(key=lambda e: (e["possession_num"], e["timestamp_ms"]))

    sorted_seg_ids = sorted(segments.keys())
    cumulative_scores: dict[str, int] = {}
    prev_leader: str | None = None
    results: list[MomentumSnapshot] = []

    for i, seg_id in enumerate(sorted_seg_ids):
        events = segments[seg_id]

        # scoring_run: length of final consecutive made-shot streak
        scoring_run = 0
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
                current_run = 0
                current_run_team = None
        scoring_run = current_run

        # possession_streak: max consecutive possessions with same team scoring
        scored_poss: dict[int, str] = {}
        for ev in events:
            if ev["made"] and ev["possession_num"] not in scored_poss:
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

        # swing point detection
        seg_scores: dict[str, int] = {}
        for ev in events:
            if ev["made"]:
                seg_scores[ev["team"]] = seg_scores.get(ev["team"], 0) + 1

        for team, pts in seg_scores.items():
            cumulative_scores[team] = cumulative_scores.get(team, 0) + pts

        current_leader: str | None = None
        if seg_scores:
            max_pts = max(seg_scores.values())
            leaders = [t for t, p in seg_scores.items() if p == max_pts]
            if len(leaders) == 1:
                current_leader = leaders[0]

        swing_point = (
            i > 0 and prev_leader is not None
            and current_leader is not None
            and current_leader != prev_leader
        )
        prev_leader = current_leader

        results.append(
            MomentumSnapshot(
                game_id=game_id,
                segment_id=seg_id,
                scoring_run=scoring_run,
                possession_streak=possession_streak,
                swing_point=swing_point,
                timestamp_ms=events[-1]["timestamp_ms"],
            )
        )

    return results
