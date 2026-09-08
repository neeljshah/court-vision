"""Additive G349 survival diagnostics for G344 image-space shadow ownership."""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from scripts.platformkit.tracking.ball_shadow_possession import (
    RADIUS_AT_720, _ball_point, _by_frame, _detected, _motion, _point,
    _read_window, shadow_states,
)

STAGES = ("frames", "any_ball_row", "detected_ball", "player_rows",
          "player_within_radius", "prerequisite_available", "motion_agreement",
          "accepted_ownership")
FIELDNAMES = ("window_id", "record_type", "stage", "n", "share_per_mille", "detail",
              "ball_x_min", "ball_x_max", "ball_y_min", "ball_y_max", "player_x_min",
              "player_x_max", "player_y_min", "player_y_max", "source_height")


def _finite_points(rows: Iterable[dict[str, str]], point_of: Any) -> list[tuple[float, float]]:
    return [point for point in (point_of(row) for row in rows) if point is not None]


def _range(points: list[tuple[float, float]], axis: int) -> tuple[str, str]:
    values = [point[axis] for point in points]
    return ("" if not values else f"{min(values):.3f}", "" if not values else f"{max(values):.3f}")


def analyze_window(window_id: str, player_rows: Iterable[dict[str, str]],
                   ball_rows: Iterable[dict[str, str]], start: int, end: int,
                   source_height: int, cut_frames: Iterable[int] = ()) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return unchanged G344 states plus cumulative, full-frame survival records."""
    players_list, balls_list = list(player_rows), list(ball_rows)
    players, balls = _by_frame(players_list), _by_frame(balls_list)
    states = shadow_states(players_list, balls_list, start, end, source_height, cut_frames)
    states = [{**row, "window_id": window_id} for row in states]
    counts = defaultdict(int)
    radius = RADIUS_AT_720 * source_height / 720
    for state in states:
        frame, previous = int(state["frame"]), int(state["frame"]) - 3
        raw, points = balls.get(frame, []), _finite_points(balls.get(frame, []), _ball_point)
        direct = [row for row in raw if _detected(row) and _ball_point(row) is not None]
        counts["frames"] += 1
        if not raw:
            continue
        counts["any_ball_row"] += 1
        if not direct:
            continue
        counts["detected_ball"] += 1
        if not players.get(frame):
            continue
        counts["player_rows"] += 1
        if len(points) != 1:
            continue
        candidates = [(math.dist(points[0], point), row, point) for row in players.get(frame, [])
                      if (point := _point(row)) is not None]
        candidates.sort(key=lambda item: item[0])
        if not candidates or candidates[0][0] > radius:
            continue
        if len(candidates) > 1 and candidates[1][0] - candidates[0][0] <= 10:
            continue
        counts["player_within_radius"] += 1
        _, player, player_point = candidates[0]
        owner_id = player.get("track_id") or player.get("player_id") or ""
        old_balls = _finite_points(balls.get(previous, []), _ball_point)
        old_player = next((_point(row) for row in players.get(previous, [])
                           if (row.get("track_id") or row.get("player_id") or "") == owner_id), None)
        if len(old_balls) != 1 or old_player is None:
            continue
        counts["prerequisite_available"] += 1
        agreement = _motion(points[0], old_balls[0], player_point, old_player)
        if agreement is None or agreement[0] < 0.5 or not 0.5 <= agreement[1] <= 2.0:
            continue
        counts["motion_agreement"] += 1
        if state["owner_id"]:
            counts["accepted_ownership"] += 1
    full = counts["frames"]
    rows = [{"window_id": window_id, "record_type": "stage", "stage": stage,
             "n": counts[stage], "share_per_mille": round(1000 * counts[stage] / full),
             "detail": "full_frame_denominator", "source_height": source_height}
            for stage in STAGES]
    ball_points = _finite_points((row for row in balls_list if _detected(row)), _ball_point)
    player_points = _finite_points(players_list, _point)
    bx0, bx1, by0, by1 = *_range(ball_points, 0), *_range(ball_points, 1)
    px0, px1, py0, py1 = *_range(player_points, 0), *_range(player_points, 1)
    rows.append({"window_id": window_id, "record_type": "coordinate", "stage": "detected_ball_vs_player_px",
                 "n": len(ball_points), "share_per_mille": "", "detail": "image_px_ranges",
                 "ball_x_min": bx0, "ball_x_max": bx1, "ball_y_min": by0, "ball_y_max": by1,
                 "player_x_min": px0, "player_x_max": px1, "player_y_min": py0, "player_y_max": py1,
                 "source_height": source_height})
    ages = [int(state["age_frames"]) for state in states if state["source"] == "detected"]
    for age in sorted(set(ages)):
        rows.append({"window_id": window_id, "record_type": "age", "stage": "detected_ball_age_frames",
                     "n": ages.count(age), "share_per_mille": round(1000 * ages.count(age) / full),
                     "detail": f"age={age}", "source_height": source_height})
    return states, rows


def artifact_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Format integer counts and additive shares for the committed CSV contract."""
    formatted = []
    for row in rows:
        out = {key: str(row.get(key, "")) for key in FIELDNAMES}
        if out["n"]:
            out["n"] = f"{int(out['n']):06d}"
        if out["share_per_mille"]:
            out["share_per_mille"] = f"{int(out['share_per_mille']):04d}"
        formatted.append(out)
    return formatted


def pooled_stage_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pool only additive stage counts, preserving the named full-frame denominator."""
    stage_rows = [row for row in rows if row["record_type"] == "stage"]
    counts = {stage: sum(int(row["n"]) for row in stage_rows if row["stage"] == stage)
              for stage in STAGES}
    full = counts["frames"]
    return [{"window_id": "POOLED", "record_type": "stage", "stage": stage,
             "n": counts[stage], "share_per_mille": round(1000 * counts[stage] / full),
             "detail": "full_frame_denominator", "source_height": "MIXED"}
            for stage in STAGES]


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tracking_csv", type=Path)
    parser.add_argument("ball_csv", type=Path)
    parser.add_argument("--start", required=True, type=int)
    parser.add_argument("--end", required=True, type=int)
    parser.add_argument("--source-height", required=True, type=int)
    parser.add_argument("--window-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    players = _read_window(args.tracking_csv, args.start - 3, args.end)
    balls = _read_window(args.ball_csv, args.start - 3, args.end)
    _, rows = analyze_window(args.window_id, players, balls, args.start, args.end, args.source_height)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader(); writer.writerows(artifact_rows(rows))


if __name__ == "__main__":
    _main()
