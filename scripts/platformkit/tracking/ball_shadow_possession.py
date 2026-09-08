"""Build abstaining image-space ball ownership hypotheses, never floor possession."""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

FIELDS = ("window_id", "frame", "state", "source", "age_frames", "confidence", "owner_id",
          "abstention_reason", "nearest_distance_px", "motion_cosine", "motion_ratio",
          "prerequisite_available")
RADIUS_AT_720 = 60.0
MAX_AGE = 30


def _num(value: str | None) -> float | None:
    try:
        value = float(value) if value not in (None, "") else None
        return value if value is not None and math.isfinite(value) else None
    except ValueError:
        return None


def _detected(row: dict[str, str]) -> bool:
    return str(row.get("detected", "")).lower() in {"1", "true", "yes"}


def _point(row: dict[str, str]) -> tuple[float, float] | None:
    x1, y1, x2, y2 = (_num(row.get(key)) for key in ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"))
    if None not in (x1, y1, x2, y2):
        return ((x1 + x2) / 2, y2)  # type: ignore[operator]
    x, y = _num(row.get("x_position") or row.get("x")), _num(row.get("y_position") or row.get("y"))
    return (x, y) if x is not None and y is not None else None


def _ball_point(row: dict[str, str]) -> tuple[float, float] | None:
    x, y = _num(row.get("ball_x2d")), _num(row.get("ball_y2d"))
    return (x, y) if x is not None and y is not None else None


def _by_frame(rows: Iterable[dict[str, str]]) -> dict[int, list[dict[str, str]]]:
    grouped: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        try:
            grouped[int(row["frame"])].append(row)
        except (KeyError, ValueError):
            continue
    return grouped


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_window(path: Path, lo: int, hi: int) -> list[dict[str, str]]:
    """Read only rows whose frame falls in [lo, hi] -- bounds memory on multi-hundred-MB mirrors."""
    with path.open(encoding="utf-8", newline="") as handle:
        kept = []
        for row in csv.DictReader(handle):
            try:
                frame = int(row["frame"])
            except (KeyError, ValueError):
                continue
            if lo <= frame <= hi:
                kept.append(row)
        return kept


def _motion(ball_now: tuple[float, float], ball_then: tuple[float, float],
            player_now: tuple[float, float], player_then: tuple[float, float]) -> tuple[float, float] | None:
    bx, by = ball_now[0] - ball_then[0], ball_now[1] - ball_then[1]
    px, py = player_now[0] - player_then[0], player_now[1] - player_then[1]
    bm, pm = math.hypot(bx, by), math.hypot(px, py)
    if bm == 0 or pm == 0:
        return None
    return ((bx * px + by * py) / (bm * pm), bm / pm)


def shadow_states(player_rows: Iterable[dict[str, str]], ball_rows: Iterable[dict[str, str]],
                  start: int, end: int, source_height: int = 720,
                  cut_frames: Iterable[int] = ()) -> list[dict[str, Any]]:
    """Return one explicitly abstaining ownership hypothesis for each frame in [start, end]."""
    players, balls, cuts = _by_frame(player_rows), _by_frame(ball_rows), set(cut_frames)
    radius, last_detected, output = RADIUS_AT_720 * source_height / 720, None, []
    for frame in range(start, end + 1):
        rows = balls.get(frame, [])
        points = [(row, _ball_point(row)) for row in rows]
        points = [(row, point) for row, point in points if point is not None]
        direct = [(row, point) for row, point in points if _detected(row)]
        if direct:
            last_detected = frame
        age = "" if last_detected is None else frame - last_detected
        state, source, reason, confidence = "ABSENT", "none", "no_ball", ""
        owner, distance, cosine, ratio, prerequisite = "", "", "", "", 0
        if len(points) > 1:
            state, source, reason = "AMBIGUOUS", "detected" if direct else "inferred", "duplicate_ball"
        elif points:
            ball_row, ball = points[0]
            if direct:
                state, source, confidence = "OBSERVED_VALID", "detected", ball_row.get("confidence", "")
            else:
                state, source, reason = "INFERRED", "inferred", ""
            candidates = []
            for row in players.get(frame, []):
                point = _point(row)
                if point is not None:
                    candidates.append((math.dist(ball, point), row, point))
            candidates.sort(key=lambda item: item[0])
            if not candidates or candidates[0][0] > radius:
                reason = "no_player_in_radius"
            elif len(candidates) > 1 and candidates[1][0] - candidates[0][0] <= 10:
                state, reason, distance = "AMBIGUOUS", "two_players_within_10px", candidates[0][0]
            else:
                distance, player, player_point = candidates[0]
                owner_id = player.get("track_id") or player.get("player_id") or ""
                previous = frame - 3
                old_ball = [(row, point) for row, point in
                            ((row, _ball_point(row)) for row in balls.get(previous, [])) if point is not None]
                old_player = next((_point(row) for row in players.get(previous, [])
                                   if (row.get("track_id") or row.get("player_id") or "") == owner_id), None)
                prerequisite = int(len(old_ball) == 1 and old_player is not None)
                if any(previous < cut <= frame for cut in cuts):
                    reason = "cut"
                elif len(old_ball) != 1 or old_player is None:
                    reason = "motion_disagreement"
                else:
                    agreement = _motion(ball, old_ball[0][1], player_point, old_player)
                    if agreement is None:
                        reason = "motion_disagreement"
                    else:
                        cosine, ratio = agreement
                        if cosine >= 0.5 and 0.5 <= ratio <= 2.0:
                            owner, reason = owner_id, ""
                        else:
                            reason = "motion_disagreement"
        output.append({"frame": frame, "state": state, "source": source, "age_frames": age,
                       "confidence": confidence, "owner_id": owner, "abstention_reason": reason,
                       "nearest_distance_px": distance, "motion_cosine": cosine, "motion_ratio": ratio,
                       "prerequisite_available": prerequisite})
    return output


def summary(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return additive state, accepted-owner, and abstention counts over the full frame denominator."""
    rows = list(rows)
    result = [{"metric": "frames", "value": len(rows)}]
    for state in ("OBSERVED_VALID", "INFERRED", "ABSENT", "AMBIGUOUS"):
        result.append({"metric": "state_" + state, "value": sum(row["state"] == state for row in rows)})
    result.append({"metric": "accepted_owner", "value": sum(bool(row["owner_id"]) for row in rows)})
    for reason in sorted({str(row["abstention_reason"]) for row in rows if row["abstention_reason"]}):
        result.append({"metric": "abstain_" + reason, "value": sum(row["abstention_reason"] == reason for row in rows)})
    return result


def _cuts(path: Path | None) -> set[int]:
    if path is None:
        return set()
    return {int(row["cut_frame"]) for row in _read(path) if row.get("cut_frame", "").isdigit()}


def _artifact_rows(rows: Iterable[dict[str, Any]], window_id: str) -> list[dict[str, Any]]:
    return [{**row, "window_id": window_id, "frame": f"{row['frame']:06d}",
             "age_frames": "" if row["age_frames"] == "" else f"{row['age_frames']:06d}"}
            for row in rows]


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tracking_csv", type=Path)
    parser.add_argument("ball_csv", type=Path)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--source-height", type=int, required=True)
    parser.add_argument("--cuts", type=Path)
    parser.add_argument("--ball-shift", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window-id", default="")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    lo = max(0, args.start - 3)
    ball_rows = _read_window(args.ball_csv, lo - args.ball_shift, args.end - args.ball_shift)
    if args.ball_shift:
        ball_rows = [{**row, "frame": str(int(row["frame"]) + args.ball_shift)} for row in ball_rows]
    rows = shadow_states(_read_window(args.tracking_csv, lo, args.end), ball_rows, args.start, args.end,
                         args.source_height, _cuts(args.cuts))
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(_artifact_rows(rows, args.window_id))
    if args.report:
        writer = csv.DictWriter(__import__("sys").stdout, fieldnames=("metric", "value"), lineterminator="\n")
        writer.writeheader()
        writer.writerows(summary(rows))


if __name__ == "__main__":
    _main()
