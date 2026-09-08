"""G351 local per-clip ball/player coordinate-scale census and screening re-join."""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

RADIUS = 60.0
G349_IDS = ("0022500630", "0022500906", "0022500799")
FIELDS = ("clip_id", "status", "tracking_path", "tracking_bytes", "ball_path", "ball_bytes",
          "player_x_p01", "player_x_p99", "player_y_p01", "player_y_p99", "ball_x_p01",
          "ball_x_p99", "ball_y_p01", "ball_y_p99", "ratio_x", "ratio_y", "source_width",
          "source_height", "league", "daemon_code_version", "ball_frame", "anomalous")
REJOIN_FIELDS = ("game_id", "clip_id", "status", "tracking_path", "tracking_bytes", "ball_path",
                 "ball_bytes", "frames_with_finite_detected_ball", "before_within_radius",
                 "after_within_radius", "rescale_x", "rescale_y")


def _num(value: str | None) -> float | None:
    try:
        value = float(value) if value not in (None, "") else None
        return value if value is not None and math.isfinite(value) else None
    except ValueError:
        return None


def _truth(value: str | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _p(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values.sort(); index = (len(values) - 1) * q; lo = int(index); hi = math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def _text(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def _ratio(low: float | None, high: float | None, base_low: float | None,
           base_high: float | None) -> float | None:
    if None in (low, high, base_low, base_high):
        return None
    denominator = base_high - base_low  # type: ignore[operator]
    return None if denominator <= 0 else (high - low) / denominator  # type: ignore[operator]


def _table_stats(path: Path, player: bool) -> dict[str, object]:
    xs: list[float] = []; ys: list[float] = []; widths: list[float] = []; heights: list[float] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            x_keys = ("bbox_x1", "bbox_x2") if player else ("ball_x2d",)
            y_keys = ("bbox_y1", "bbox_y2") if player else ("ball_y2d",)
            xs.extend(v for key in x_keys if (v := _num(row.get(key))) is not None)
            ys.extend(v for key in y_keys if (v := _num(row.get(key))) is not None)
            if (v := _num(row.get("source_width"))) is not None: widths.append(v)
            if (v := _num(row.get("source_height"))) is not None: heights.append(v)
    return {"x1": _p(xs, .01), "x99": _p(xs, .99), "y1": _p(ys, .01), "y99": _p(ys, .99),
            "width": _p(widths, .5), "height": _p(heights, .5)}


def _sidecar(clip: Path) -> tuple[str, str]:
    for name in ("metadata.json", "manifest.json", "sidecar.json"):
        path = clip / name
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return str(data.get("league", "")), str(data.get("daemon_code_version", data.get("code_version", "")))
            except (OSError, ValueError, AttributeError):
                return "", ""
    return "", ""


def _frame(stats: dict[str, object], width: float | None, height: float | None) -> str:
    x, y = stats["x99"], stats["y99"]
    if x is None or y is None: return "UNKNOWN_NO_FINITE_BALL_COORDINATES"
    if width is None or height is None: return "UNKNOWN_NO_SOURCE_DIMENSIONS"
    known = (("original", width, height), ("crop", width, max(height - 60, 1)),
             ("detector", 640.0, 352.0), ("panorama", 3698.0, 500.0))
    return min(known, key=lambda item: math.hypot((float(x) - item[1]) / item[1],
                                                   (float(y) - item[2]) / item[2]))[0]


def census(tracking_root: Path) -> tuple[list[dict[str, str]], dict[str, dict[str, object]]]:
    rows: list[dict[str, str]] = []; stats_by_clip: dict[str, dict[str, object]] = {}
    for clip in sorted((p for p in tracking_root.iterdir() if p.is_dir()), key=lambda p: p.name):
        tracking, ball = clip / "tracking_data.csv", clip / "ball_tracking.csv"
        row = dict.fromkeys(FIELDS, ""); row["clip_id"] = clip.name
        row["tracking_path"], row["ball_path"] = str(tracking), str(ball)
        if not tracking.exists() or not ball.exists(): row["status"] = "MISSING_TRACKING_OR_BALL_TABLE"; rows.append(row); continue
        row["tracking_bytes"], row["ball_bytes"] = f"{tracking.stat().st_size:06d}", f"{ball.stat().st_size:06d}"
        player, ball_stats = _table_stats(tracking, True), _table_stats(ball, False)
        width = player["width"] if player["width"] is not None else ball_stats["width"]
        height = player["height"] if player["height"] is not None else ball_stats["height"]
        league, version = _sidecar(clip); rx = _ratio(ball_stats["x1"], ball_stats["x99"], player["x1"], player["x99"]); ry = _ratio(ball_stats["y1"], ball_stats["y99"], player["y1"], player["y99"])
        for key, value in (("player_x_p01", player["x1"]), ("player_x_p99", player["x99"]), ("player_y_p01", player["y1"]), ("player_y_p99", player["y99"]), ("ball_x_p01", ball_stats["x1"]), ("ball_x_p99", ball_stats["x99"]), ("ball_y_p01", ball_stats["y1"]), ("ball_y_p99", ball_stats["y99"]), ("ratio_x", rx), ("ratio_y", ry), ("source_width", width), ("source_height", height)): row[key] = _text(value)  # type: ignore[arg-type]
        row.update(league=league, daemon_code_version=version, ball_frame=_frame(ball_stats, width, height), anomalous=str(int((rx or 0) > 1.5 or (ry or 0) > 1.5)), status="OK")
        rows.append(row); stats_by_clip[clip.name] = {**player, **{"bx1": ball_stats["x1"], "bx99": ball_stats["x99"], "by1": ball_stats["y1"], "by99": ball_stats["y99"]}}
    return rows, stats_by_clip


def _boxes(path: Path) -> dict[str, list[tuple[float, float, float, float]]]:
    found: dict[str, list[tuple[float, float, float, float]]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            values = tuple(_num(row.get(key)) for key in ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"))
            if row.get("frame") and None not in values: found[row["frame"]].append(values)  # type: ignore[arg-type]
    return found


def _inside(point: tuple[float, float], boxes: list[tuple[float, float, float, float]]) -> bool:
    for x1, y1, x2, y2 in boxes:
        if math.hypot(point[0] - min(max(point[0], x1), x2), point[1] - min(max(point[1], y1), y2)) <= RADIUS: return True
    return False


def rejoin(clip: Path, values: dict[str, object], game_id: str) -> dict[str, str]:
    tracking, ball = clip / "tracking_data.csv", clip / "ball_tracking.csv"; row = dict.fromkeys(REJOIN_FIELDS, "")
    row.update(game_id=game_id, clip_id=clip.name, status="OK", tracking_path=str(tracking), ball_path=str(ball), tracking_bytes=f"{tracking.stat().st_size:06d}", ball_bytes=f"{ball.stat().st_size:06d}")
    px, py = values["x99"] - values["x1"], values["y99"] - values["y1"]  # type: ignore[operator]
    bx, by = values["bx99"] - values["bx1"], values["by99"] - values["by1"]  # type: ignore[operator]
    if min(px, py, bx, by) <= 0: row["status"] = "NO_FINITE_RESCALE"; return row
    sx, sy = px / bx, py / by; boxes = _boxes(tracking); total = before = after = 0
    with ball.open(encoding="utf-8", newline="") as handle:
        for item in csv.DictReader(handle):
            x, y = _num(item.get("ball_x2d")), _num(item.get("ball_y2d")); frame = item.get("frame", "")
            if x is None or y is None or not _truth(item.get("detected")): continue
            total += 1; before += _inside((x, y), boxes.get(frame, [])); after += _inside(((x - values["bx1"]) * sx + values["x1"], (y - values["by1"]) * sy + values["y1"]), boxes.get(frame, []))  # type: ignore[operator]
    row.update(frames_with_finite_detected_ball=f"{total:06d}", before_within_radius=f"{before:06d}", after_within_radius=f"{after:06d}", rescale_x=f"{sx:.6f}", rescale_y=f"{sy:.6f}")
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--tracking-root", type=Path, default=Path("data/tracking")); parser.add_argument("--ranges", type=Path, required=True); parser.add_argument("--rejoin", type=Path, required=True); args = parser.parse_args(argv)
    if not args.tracking_root.is_dir():
        print(f"ABSENT-IN-WORKTREE {args.tracking_root}")
        args.ranges.parent.mkdir(parents=True, exist_ok=True)
        for path, fields in ((args.ranges, FIELDS), (args.rejoin, REJOIN_FIELDS)):
            with path.open("w", encoding="utf-8", newline="") as handle:
                csv.DictWriter(handle, fieldnames=fields, lineterminator="\n").writeheader()
        return 0
    rows, values = census(args.tracking_root); args.ranges.parent.mkdir(parents=True, exist_ok=True)
    with args.ranges.open("w", encoding="utf-8", newline="") as handle: writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n"); writer.writeheader(); writer.writerows(rows)
    rejoined = []; seen = set()
    for clip in sorted((p for p in args.tracking_root.iterdir() if p.is_dir()), key=lambda p: p.name):
        for game in G349_IDS:
            if game in clip.name and clip.name in values: rejoined.append(rejoin(clip, values[clip.name], game)); seen.add(game)
    rejoined.extend(dict(dict.fromkeys(REJOIN_FIELDS, ""), game_id=game, status="MISSING_G349_WINDOW") for game in G349_IDS if game not in seen)
    with args.rejoin.open("w", encoding="utf-8", newline="") as handle: writer = csv.DictWriter(handle, fieldnames=REJOIN_FIELDS, lineterminator="\n"); writer.writeheader(); writer.writerows(rejoined)
    anomalous = sum(row["anomalous"] == "1" for row in rows); print(f"clips={len(rows):06d} anomalous={anomalous:06d} anomalous_per_mille={1000 * anomalous // max(1, len(rows)):04d}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
