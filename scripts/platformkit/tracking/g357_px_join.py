"""Run G344/G349 unchanged against additive G354 pixel-space ball coordinates."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any, Iterable

from scripts.platformkit.tracking.ball_shadow_possession import FIELDS, _num, _point, _read_window
from scripts.platformkit.tracking.g349_ball_survival import (
    FIELDNAMES, analyze_window, artifact_rows,
)

PX_FIELDS = ("ball_x2d_px", "ball_y2d_px")
SURVIVAL_FIELDS = FIELDNAMES + ("join_source", "ratio_x", "ratio_y")
STATE_FIELDS = FIELDS + ("join_source",)


def has_px_header(path: Path) -> bool:
    """Return whether a ball CSV declares both additive G354 pixel fields."""
    with path.open(encoding="utf-8", newline="") as handle:
        fields = set(csv.DictReader(handle).fieldnames or ())
    return set(PX_FIELDS).issubset(fields)


def px_rows(rows: Iterable[dict[str, str]], header_present: bool) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Copy finite pixel rows into the legacy ball fields, preserving the input rows."""
    accepted: list[dict[str, str]] = []
    reasons = {"missing_px_header": 0, "missing_px_coordinate": 0}
    for row in rows:
        if not header_present:
            reasons["missing_px_header"] += 1
            continue
        x, y = _num(row.get(PX_FIELDS[0])), _num(row.get(PX_FIELDS[1]))
        if x is None or y is None:
            reasons["missing_px_coordinate"] += 1
            continue
        accepted.append({**row, "ball_x2d": str(x), "ball_y2d": str(y), "join_source": "px"})
    return accepted, reasons


def _span(values: list[float]) -> float | None:
    return None if len(values) < 2 else max(values) - min(values)


def coordinate_ratios(player_rows: Iterable[dict[str, str]], ball_rows: Iterable[dict[str, str]]) -> tuple[float | None, float | None]:
    """Return G351 ball-span/player-span ratios for the two image-space axes."""
    players = [point for point in (_point(row) for row in player_rows) if point is not None]
    balls = [(x, y) for row in ball_rows
             if (x := _num(row.get(PX_FIELDS[0]))) is not None and (y := _num(row.get(PX_FIELDS[1]))) is not None]
    p_x, p_y = _span([point[0] for point in players]), _span([point[1] for point in players])
    b_x, b_y = _span([point[0] for point in balls]), _span([point[1] for point in balls])
    return (None if p_x in (None, 0) or b_x is None else b_x / p_x,
            None if p_y in (None, 0) or b_y is None else b_y / p_y)


def px_analysis(window_id: str, player_rows: Iterable[dict[str, str]], ball_rows: Iterable[dict[str, str]],
                start: int, end: int, source_height: int, header_present: bool,
                cut_frames: Iterable[int] = ()) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return additive px states and survival rows; G344/G349 decisions are not changed."""
    players, balls = list(player_rows), list(ball_rows)
    joined, reasons = px_rows(balls, header_present)
    states, rows = analyze_window(window_id, players, joined, start, end, source_height, cut_frames)
    ratio_x, ratio_y = coordinate_ratios(players, balls)
    for state in states:
        state["join_source"] = "px"
    full = end - start + 1
    extra = [{"window_id": window_id, "record_type": "exclusion", "stage": reason,
              "n": count, "share_per_mille": round(1000 * count / full),
              "detail": "px_ball_rows_excluded", "source_height": source_height,
              "join_source": "px", "ratio_x": "", "ratio_y": ""}
             for reason, count in reasons.items()]
    for row in rows:
        row["join_source"] = "px"
        row["ratio_x"] = "" if ratio_x is None else f"{ratio_x:.6f}"
        row["ratio_y"] = "" if ratio_y is None else f"{ratio_y:.6f}"
    return states, rows + extra


def _write(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, Any]], states: bool = False) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            out = {key: row.get(key, "") for key in fields}
            if states and out["frame"] != "":
                out["frame"] = f"{int(out['frame']):06d}"
            writer.writerow(out)


def formatted_survival_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Format G349 columns while retaining G357's additive source and ratio columns."""
    originals = list(rows)
    rendered = artifact_rows(originals)
    for original, formatted in zip(originals, rendered):
        for key in ("join_source", "ratio_x", "ratio_y"):
            formatted[key] = str(original.get(key, ""))
    return rendered


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tracking_csv", type=Path)
    parser.add_argument("ball_csv", type=Path)
    parser.add_argument("--start", required=True, type=int)
    parser.add_argument("--end", required=True, type=int)
    parser.add_argument("--source-height", required=True, type=int)
    parser.add_argument("--window-id", required=True)
    parser.add_argument("--states-output", required=True, type=Path)
    parser.add_argument("--survival-output", required=True, type=Path)
    parser.add_argument("--old-survival-output", type=Path)
    parser.add_argument("--ball-shift", type=int, default=0)
    args = parser.parse_args()
    players = _read_window(args.tracking_csv, args.start - 3, args.end)
    balls = _read_window(args.ball_csv, args.start - 3 - args.ball_shift, args.end - args.ball_shift)
    if args.ball_shift:
        balls = [{**row, "frame": str(int(row["frame"]) + args.ball_shift)} for row in balls]
    states, rows = px_analysis(args.window_id, players, balls, args.start, args.end,
                               args.source_height, has_px_header(args.ball_csv))
    _write(args.states_output, STATE_FIELDS, states, states=True)
    _write(args.survival_output, SURVIVAL_FIELDS, formatted_survival_rows(rows))
    if args.old_survival_output:
        _, old_rows = analyze_window(args.window_id, players, balls, args.start, args.end,
                                     args.source_height)
        for row in old_rows:
            row["join_source"] = "court_map"
        _write(args.old_survival_output, SURVIVAL_FIELDS, formatted_survival_rows(old_rows))


if __name__ == "__main__":
    _main()
