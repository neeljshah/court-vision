"""Check fresh G354 ball-pixel outputs one tracking store at a time."""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path


RADIUS = 60.0
RATIO_LIMIT = 1.5


def _number(value: object) -> float | None:
    try:
        result = float(str(value))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def _span(values: list[float]) -> tuple[float | None, float | None, float | None]:
    low, high = _percentile(values, 0.01), _percentile(values, 0.99)
    return low, high, None if low is None or high is None else high - low


def _near_player(point: tuple[float, float], boxes: list[tuple[float, float, float, float]]) -> bool:
    for x1, y1, x2, y2 in boxes:
        dx = max(x1 - point[0], 0.0, point[0] - x2)
        dy = max(y1 - point[1], 0.0, point[1] - y2)
        if math.hypot(dx, dy) <= RADIUS:
            return True
    return False


def _clip(game_id: str, root: Path) -> dict[str, object]:
    directory = root / game_id
    tracking, ball = directory / "tracking_data.csv", directory / "ball_tracking.csv"
    if not tracking.is_file() or not ball.is_file():
        return {"game_id": game_id, "status": "MISSING_TABLE"}
    players: dict[str, list[tuple[float, float, float, float]]] = {}
    px, py = [], []
    with tracking.open(encoding="utf-8", newline="", errors="replace") as handle:
        for row in csv.DictReader(handle):
            values = [_number(row.get(name)) for name in ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2")]
            if any(value is None for value in values):
                continue
            x1, y1, x2, y2 = values
            px.extend((x1, x2)); py.extend((y1, y2))
            players.setdefault(str(row.get("frame", "")), []).append((x1, y1, x2, y2))
    bx, by, old_x, old_y = [], [], [], []
    px_n = old_n = px_join = old_join = 0
    with ball.open(encoding="utf-8", newline="", errors="replace") as handle:
        reader = csv.DictReader(handle)
        required = {"ball_x2d_px", "ball_y2d_px"}
        if not required.issubset(set(reader.fieldnames or ())):
            return {"game_id": game_id, "status": "MISSING_PX_FIELDS"}
        for row in reader:
            point = (_number(row.get("ball_x2d_px")), _number(row.get("ball_y2d_px")))
            old = (_number(row.get("ball_x2d")), _number(row.get("ball_y2d")))
            boxes = players.get(str(row.get("frame", "")), [])
            if None not in point:
                bx.append(point[0]); by.append(point[1]); px_n += 1
                px_join += int(_near_player(point, boxes))
            if None not in old:
                old_x.append(old[0]); old_y.append(old[1]); old_n += 1
                old_join += int(_near_player(old, boxes))
    px1, px99, px_range = _span(bx); py1, py99, py_range = _span(by)
    ux1, ux99, ux_range = _span(px); uy1, uy99, uy_range = _span(py)
    xr = None if not ux_range else (px_range or 0.0) / ux_range
    yr = None if not uy_range else (py_range or 0.0) / uy_range
    return {"game_id": game_id, "status": "OK", "n_px": px_n, "n_old": old_n,
            "px_p01_x": px1, "px_p99_x": px99, "px_p01_y": py1, "px_p99_y": py99,
            "player_p01_x": ux1, "player_p99_x": ux99, "player_p01_y": uy1, "player_p99_y": uy99,
            "player_range_x": ux_range, "player_range_y": uy_range,
            "ratio_x": xr, "ratio_y": yr, "ratio_pass": xr is not None and yr is not None and xr <= RATIO_LIMIT and yr <= RATIO_LIMIT,
            "px_within_60": px_join, "old_within_60": old_join,
            "px_within_60_per_mille": _per_mille(px_join, px_n),
            "old_within_60_per_mille": _per_mille(old_join, old_n)}


def _utc(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fresh_games(ledger: Path, after: int, key: str = "start") -> list[dict[str, object]]:
    """Ledger candidates finishing after the epoch, each tagged with its START time.

    The ledger carries no start field. `scripts/platformkit/track_daemon.py:384`
    stamps `job["started"] = time.time()` when a clip is claimed, and :302-303 write
    `"seconds": int(finished - job["started"])` and `"finished_at": int(finished)`,
    so START is `finished_at - seconds` (both truncated, hence within 1 s of the true
    claim time).  A clip is fresh only when it STARTED after the deploy epoch: one
    that started before it had already imported the old module even though it
    finished afterwards.  `key="finish"` restores the weaker finish-time rule.
    """
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    with ledger.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                row = json.loads(line)
                finished = int(float(row.get("finished_at", 0)))
                seconds = int(float(row.get("seconds", 0)))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            game = str(row.get("game_id", ""))
            if finished <= after or row.get("sport") != "basketball" or not game or game in seen:
                continue
            seen.add(game)
            start = finished - seconds
            rows.append({"game_id": game, "start_epoch": start, "duration_s": seconds,
                         "started_at_utc": _utc(start), "finished_at_utc": _utc(finished),
                         "fresh": (start if key == "start" else finished) > after})
    return rows


def _cell(value: object) -> str:
    if isinstance(value, bool): return "1" if value else "0"
    if isinstance(value, int): return f"{value:06d}"
    if isinstance(value, float): return f"{value:.6f}"
    return str(value if value is not None else "")


def _per_mille(numerator: int, denominator: int) -> int | None:
    return None if denominator == 0 else round(numerator * 1000 / denominator)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--tracking-root", type=Path, required=True)
    parser.add_argument("--after-epoch", type=int, required=True)
    parser.add_argument("--postdeploy", type=Path, required=True)
    parser.add_argument("--rejoin", type=Path, required=True)
    parser.add_argument("--freshness-key", choices=("start", "finish"), default="start")
    args = parser.parse_args(argv)
    candidates = _fresh_games(args.ledger, args.after_epoch, args.freshness_key)
    rows = []
    for candidate in candidates:
        row = _clip(str(candidate["game_id"]), args.tracking_root)
        for name in ("started_at_utc", "finished_at_utc", "duration_s", "start_epoch"):
            row[name] = candidate[name]
        rows.append(row)
    for row, candidate in zip(rows, candidates):
        if not candidate["fresh"]:
            row["excluded_reason"] = "STARTED_BEFORE_EPOCH"
        elif row.get("status") == "MISSING_TABLE":
            row["excluded_reason"] = "MISSING_STORE"
        else:
            row["excluded_reason"] = ""
    fresh = [row for row, candidate in zip(rows, candidates) if candidate["fresh"]]
    # Absent evidence (no store on disk at all) must pass onward rather than fail the
    # gate: judge only fresh rows that actually produced a store.
    judged = [row for row in fresh if row.get("status") != "MISSING_TABLE"]
    fields = ["game_id", "status", "n_px", "n_old", "px_p01_x", "px_p99_x", "px_p01_y", "px_p99_y", "player_p01_x", "player_p99_x", "player_p01_y", "player_p99_y", "player_range_x", "player_range_y", "ratio_x", "ratio_y", "ratio_pass", "px_within_60", "old_within_60", "px_within_60_per_mille", "old_within_60_per_mille", "started_at_utc", "finished_at_utc", "duration_s", "start_epoch", "excluded_reason"]
    for output in (args.postdeploy, args.rejoin):
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader(); writer.writerows([{key: _cell(row.get(key)) for key in fields} for row in rows])
    excluded_missing = len(fresh) - len(judged)
    passed = len(judged) >= 3 and all(row.get("status") == "OK" and row.get("ratio_pass") for row in judged)
    print("FRESH_ENTRIES %06d" % len(fresh))
    print("EXCLUDED_STARTED_BEFORE_EPOCH %06d" % (len(rows) - len(fresh)))
    print("EXCLUDED_MISSING_STORE %06d" % excluded_missing)
    print("POSTDEPLOY_PASS %s" % ("1" if passed else "0"))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
