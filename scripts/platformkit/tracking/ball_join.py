"""Join per-frame player tracking with the separate ball table."""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Iterable


def _number(value: str | None) -> float | None:
    try:
        number = float(value) if value not in (None, "") else None
        return number if number is not None and math.isfinite(number) else None
    except ValueError:
        return None


def _truth(value: str | None) -> int:
    return int(str(value).strip().lower() in {"1", "true", "yes"})


def _player_point(row: dict[str, str]) -> tuple[float, float] | None:
    for x_name, y_name in (("x", "y"), ("x_position", "y_position"), ("x2d", "y2d")):
        x, y = _number(row.get(x_name)), _number(row.get(y_name))
        if x is not None and y is not None:
            return x, y
    return None


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def join_tables(tracking_path: Path, ball_path: Path) -> list[dict[str, object]]:
    """Return one joined record for every frame present in either input table."""
    players_by_frame: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _read_rows(tracking_path):
        players_by_frame[row["frame"]].append(row)
    ball_by_frame = {row["frame"]: row for row in _read_rows(ball_path)}
    frames = sorted(set(players_by_frame) | set(ball_by_frame), key=lambda value: int(value))
    joined: list[dict[str, object]] = []
    for frame in frames:
        ball = ball_by_frame.get(frame, {})
        ball_x, ball_y = _number(ball.get("ball_x2d")), _number(ball.get("ball_y2d"))
        nearest_id, distance = "", None
        if ball_x is not None and ball_y is not None:
            candidates = []
            for player in players_by_frame[frame]:
                point = _player_point(player)
                if point is not None:
                    candidates.append((math.hypot(ball_x - point[0], ball_y - point[1]),
                                       player.get("track_id") or player.get("player_id") or ""))
            if candidates:
                distance, nearest_id = min(candidates)
        joined.append({"frame": int(frame), "players": len(players_by_frame[frame]),
                       "ball_detected": _truth(ball.get("detected")),
                       "ball_inferred": _truth(ball.get("ball_inferred")),
                       "ball_x2d": ball_x, "ball_y2d": ball_y,
                       "nearest_player": nearest_id, "nearest_player_distance_px": distance})
    return joined


def report_rows(joined: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    """Return descriptive frame and nearest-distance counts for a joined view."""
    rows = list(joined)
    distances = sorted(float(row["nearest_player_distance_px"]) for row in rows
                       if row["nearest_player_distance_px"] is not None)
    def quantile(q: float) -> float | str:
        if not distances:
            return ""
        return distances[round((len(distances) - 1) * q)]
    detected = sum(int(row["ball_detected"]) for row in rows)
    return [{"metric": "frames", "n": len(rows)},
            {"metric": "frames_with_detected_ball", "n": detected},
            {"metric": "frames_without_detected_ball", "n": len(rows) - detected},
            {"metric": "nearest_player_distance_px", "n": len(distances),
             "min": quantile(0), "p50": quantile(0.5), "p95": quantile(0.95),
             "max": quantile(1)}]


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tracking_csv", type=Path)
    parser.add_argument("ball_csv", type=Path)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    joined = join_tables(args.tracking_csv, args.ball_csv)
    rows = report_rows(joined) if args.report else joined
    writer = csv.DictWriter(__import__("sys").stdout,
                            fieldnames=sorted({key for row in rows for key in row}),
                            lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


if __name__ == "__main__":
    _main()
