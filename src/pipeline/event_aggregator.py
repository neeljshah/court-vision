"""
event_aggregator.py -- Phase D1: CV events -> per-player ML feature rows.

Consumes EventDetector output (screen_set, cut, drive, closeout, rebound_position,
shot, pass, dribble) and produces per-game, per-player aggregated feature rows.

These feed Tier 3+ models:
  - xFG v2 (closeout_speed, shot_clock_pressure, fatigue_penalty, defender_dist)
  - Play type classifier (drive%, cut%, screen_set%, ISO frequency)
  - Defensive pressure model (closeout frequency, drive frequency allowed)
  - Spacing model (built upstream from position data)

Public API
----------
    aggregate_game_events(events, game_id, season)  -> list[dict]
    aggregate_from_file(events_path, game_id)       -> list[dict]
    save_features(rows, game_id)                    -> str (path)
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_EVENTS_DIR = os.path.join(PROJECT_DIR, "data", "events")


# ── Core aggregation ──────────────────────────────────────────────────────────

def aggregate_game_events(
    events: list,
    game_id: str,
    season: str = "2024-25",
    fps: float = 30.0,
) -> list:
    """
    Aggregate raw CV events into per-player feature rows.

    Args:
        events:  List of event dicts from EventDetector.events
                 Each event has at minimum: {"type": str, "frame": int, ...}
        game_id: NBA game ID
        season:  Season string
        fps:     Video frame rate (used to convert frames to seconds)

    Returns:
        List of player feature dicts, one per player seen in events:
        [
            {
                "game_id": str,
                "player_id": int | None,
                "season": str,
                # Event counts (per game)
                "drives":              int,
                "cuts":                int,
                "screen_sets":         int,
                "closeouts":           int,
                "rebound_positions":   int,
                "shots":               int,
                "passes":              int,
                "dribbles":            int,
                # Rates (per 36 min proxy based on frame count)
                "drive_rate":          float,
                "cut_rate":            float,
                "screen_rate":         float,
                "closeout_rate":       float,
                # Derived quality metrics
                "avg_drive_speed":     float,  # pixels/frame
                "avg_closeout_speed":  float,
                "shot_after_cut_rate": float,  # shots within 60 frames of a cut
                "n_events":            int,
            }, ...
        ]
    """
    if not events:
        return []

    # Bucket events by player_id (None = team event)
    player_buckets: dict = defaultdict(lambda: defaultdict(list))
    total_frames = 0

    for ev in events:
        ev_type = ev.get("type", "")
        frame   = int(ev.get("frame", 0))
        pid     = ev.get("player_id")   # may be None for screen_set / rebound_position

        if frame > total_frames:
            total_frames = frame

        player_buckets[pid][ev_type].append(ev)

    # Convert total_frames to seconds
    total_seconds = max(total_frames / fps, 1.0)
    # per-36-minute scale factor
    scale_36 = (36 * 60) / total_seconds

    rows = []
    for pid, buckets in player_buckets.items():
        drives      = buckets.get("drive",            [])
        cuts        = buckets.get("cut",              [])
        screens     = buckets.get("screen_set",       [])
        closeouts   = buckets.get("closeout",         [])
        rebounds    = buckets.get("rebound_position", [])
        shots       = buckets.get("shot",             [])
        passes      = buckets.get("pass",             [])
        dribbles    = buckets.get("dribble",          [])

        # Average speed for drives and closeouts
        avg_drive_speed   = _mean_field(drives,    "speed")
        avg_closeout_speed = _mean_field(closeouts, "speed")

        # Shot-after-cut: shot within 2 seconds (60 frames at 30fps) of a cut
        cut_frames = {int(c.get("frame", 0)) for c in cuts}
        shots_after_cut = sum(
            1 for s in shots
            if any(abs(int(s.get("frame", 0)) - cf) <= 60 for cf in cut_frames)
        )
        shot_after_cut_rate = shots_after_cut / max(len(shots), 1)

        n_events = sum(len(v) for v in buckets.values())

        rows.append({
            "game_id":              game_id,
            "player_id":            pid,
            "season":               season,
            # Raw counts
            "drives":               len(drives),
            "cuts":                 len(cuts),
            "screen_sets":          len(screens),
            "closeouts":            len(closeouts),
            "rebound_positions":    len(rebounds),
            "shots":                len(shots),
            "passes":               len(passes),
            "dribbles":             len(dribbles),
            # Per-36-min rates
            "drive_rate":           round(len(drives)    * scale_36, 2),
            "cut_rate":             round(len(cuts)      * scale_36, 2),
            "screen_rate":          round(len(screens)   * scale_36, 2),
            "closeout_rate":        round(len(closeouts) * scale_36, 2),
            # Quality metrics
            "avg_drive_speed":      avg_drive_speed,
            "avg_closeout_speed":   avg_closeout_speed,
            "shot_after_cut_rate":  round(shot_after_cut_rate, 4),
            # Metadata
            "n_events":             n_events,
            "total_seconds":        round(total_seconds, 1),
        })

    return rows


def _mean_field(events: list, field: str) -> float:
    """Return mean of a numeric field from a list of event dicts. 0.0 on miss."""
    vals = [float(e[field]) for e in events if field in e and e[field] is not None]
    return round(sum(vals) / len(vals), 3) if vals else 0.0


def aggregate_from_file(events_path: str, game_id: str, season: str = "2024-25") -> list:
    """
    Load events JSON from disk and aggregate.

    Args:
        events_path: Path to {game_id}_events.json from unified_pipeline
        game_id:     NBA game ID
        season:      Season string

    Returns:
        List of player feature dicts (same as aggregate_game_events).
    """
    try:
        with open(events_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[event_aggregator] Cannot load {events_path}: {e}")
        return []

    # events JSON may be {"events": [...]} or a raw list
    if isinstance(data, dict):
        events = data.get("events", data.get("all_events", []))
    elif isinstance(data, list):
        events = data
    else:
        return []

    return aggregate_game_events(events, game_id, season)


def save_features(rows: list, game_id: str) -> str:
    """
    Save aggregated feature rows to data/events/{game_id}_cv_features.json.

    Returns:
        Absolute path to written file.
    """
    os.makedirs(_EVENTS_DIR, exist_ok=True)
    out_path = os.path.join(_EVENTS_DIR, f"{game_id}_cv_features.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    return out_path


def load_cv_features(game_id: str) -> list:
    """Load saved CV feature rows for a game. Returns [] on miss."""
    path = os.path.join(_EVENTS_DIR, f"{game_id}_cv_features.json")
    try:
        return json.load(open(path))
    except Exception:
        return []


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Aggregate CV events for a game")
    parser.add_argument("--events", required=True, help="Path to events JSON file")
    parser.add_argument("--game-id", required=True, help="NBA game ID")
    parser.add_argument("--season", default="2024-25")
    args = parser.parse_args()

    rows = aggregate_from_file(args.events, args.game_id, args.season)
    out  = save_features(rows, args.game_id)
    print(f"[event_aggregator] {len(rows)} player rows saved to {out}")
    for row in rows:
        pid = row.get("player_id", "team")
        print(f"  player={pid}: drives={row['drives']} cuts={row['cuts']} "
              f"screen_sets={row['screen_sets']} closeouts={row['closeouts']} "
              f"drive_rate={row['drive_rate']:.1f}/36 n_events={row['n_events']}")
