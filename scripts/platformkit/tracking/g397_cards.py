"""G397 eye cards: one native interior frame plus output/timeline overlay per section."""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from scripts.platformkit.tracking.g376_schedule import integral, reconstructed_schedule
from scripts.platformkit.tracking.g397_census import sha256_file
from scripts.platformkit.tracking.g397_report import read_csv

CARD_WIDTH = 640
STRIP_HEIGHT = 26
TEXT_HEIGHT = 46

__all__ = ["extract_frame", "overlay_points", "build_card", "main"]


def extract_frame(source: Path, frame_index: int, target: Path) -> str:
    """Extract one native interior frame by exact index, never by a resampled clock."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(source), "-vf",
             "select=eq(n\\,%d),scale=%d:-2" % (frame_index, CARD_WIDTH),
             "-vsync", "0", "-frames:v", "1", "-q:v", "6", str(target)],
            capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "FRAME_ERROR:" + type(exc).__name__
    if result.returncode != 0 or not target.is_file():
        return "FRAME_ERROR:ffmpeg_rc_%d" % result.returncode
    return "OK"


def overlay_points(tracking: Path, frame_index: int) -> list[tuple[float, float]]:
    """Return the producer's own image-space points for exactly one evaluated tick."""
    if not tracking.is_file():
        return []
    points = []
    with tracking.open(encoding="utf-8-sig", newline="", errors="replace") as handle:
        for row in csv.DictReader(handle):
            if integral(row.get("frame")) != frame_index:
                continue
            for x_name, y_name in (("bbox_x1", "bbox_y1"), ("x_position", "y_position")):
                try:
                    points.append((float(row[x_name]), float(row[y_name])))
                    break
                except (KeyError, TypeError, ValueError):
                    continue
    return points


def build_card(section: dict[str, Any], snapshots: Path, renders: Path) -> dict[str, Any]:
    """Compose one card, keeping an absent source as an explicit metadata-only state."""
    name = str(section["section_id"])
    ball = snapshots / name / "ball_tracking.csv"
    schedule = reconstructed_schedule(ball)
    evaluated = sorted(schedule["evaluated"])
    interior = evaluated[len(evaluated) // 2] if evaluated else 0
    card = renders / ("%s_%02d_%s.jpg" % (section["draw_kind"], int(section["draw_order"]), name))
    renders.mkdir(parents=True, exist_ok=True)
    source = Path(str(section.get("source_path") or ""))
    native = renders / ("_native_%s.jpg" % name)
    status = "METADATA_ONLY"
    if str(section.get("source_status")) == "PRESENT" and source.is_file():
        status = extract_frame(source, interior, native)
    if status == "OK" and native.is_file():
        base = Image.open(native).convert("RGB")
        scale = base.width / max(1, float(section.get("measured_width") or base.width))
    else:
        base = Image.new("RGB", (CARD_WIDTH, 360), (24, 24, 24))
        scale = CARD_WIDTH / float(section.get("declared_width") or CARD_WIDTH)
    canvas = Image.new("RGB", (base.width, base.height + STRIP_HEIGHT + TEXT_HEIGHT), (12, 12, 12))
    canvas.paste(base, (0, 0))
    draw = ImageDraw.Draw(canvas)
    points = overlay_points(snapshots / name / "tracking_data.csv", interior)
    for x, y in points:
        px, py = x * scale, y * scale
        if 0 <= px < base.width and 0 <= py < base.height:
            draw.ellipse([px - 4, py - 4, px + 4, py + 4], outline=(255, 210, 0), width=2)
    span = max(evaluated) if evaluated else 1
    for frame in evaluated:
        column = int(frame / max(1, span) * (base.width - 1))
        draw.line([(column, base.height + 4), (column, base.height + STRIP_HEIGHT - 4)],
                  fill=(0, 200, 120))
    for frame in sorted(schedule["suspended"]):
        column = int(frame / max(1, span) * (base.width - 1))
        draw.line([(column, base.height + STRIP_HEIGHT - 8), (column, base.height + STRIP_HEIGHT - 4)],
                  fill=(200, 60, 60))
    lines = ["%s %s tick=%d pts=%s" % (section["draw_kind"], name, interior, status),
             "meas %sx%s/%s decl %s/%s ev=%d susp=%d pts=%d" % (
                 section.get("measured_width"), section.get("measured_height"),
                 section.get("measured_avg_fps"), section.get("declared_height"),
                 section.get("declared_fps"), len(evaluated),
                 len(schedule["suspended"]), len(points))]
    for index, text in enumerate(lines):
        draw.text((6, base.height + STRIP_HEIGHT + 4 + index * 18), text[:96], fill=(235, 235, 235))
    canvas.save(card, "JPEG", quality=72, optimize=True)
    if native.is_file():
        native.unlink()
    return {"section_id": name, "draw_kind": section["draw_kind"],
            "draw_order": section["draw_order"], "card": card.name,
            "native_frame_status": status, "interior_tick": interior,
            "evaluated_ticks": len(evaluated), "suspended_ticks": len(schedule["suspended"]),
            "overlay_points": len(points), "measured_width": section.get("measured_width"),
            "measured_height": section.get("measured_height"),
            "measured_avg_fps": section.get("measured_avg_fps"),
            "declared_height": section.get("declared_height"),
            "declared_fps": section.get("declared_fps"),
            "source_status": section.get("source_status"),
            "card_sha256": sha256_file(card), "card_bytes": card.stat().st_size}


def main(argv: list[str]) -> int:
    """Build the evenly ordered card index for every selected section."""
    scratch = Path(argv[1] if len(argv) > 1 else "/workspace/g397_scratch")
    receipts = read_csv(scratch / "source_receipts.csv")
    declared = {row["section_id"]: row for row in read_csv(scratch / "draw.csv")}
    index = []
    for receipt in sorted(receipts, key=lambda r: (r["draw_kind"], int(r["draw_order"]))):
        merged = dict(receipt)
        source = declared.get(receipt["section_id"], {})
        merged["declared_height"] = source.get("declared_height")
        merged["declared_fps"] = source.get("declared_fps")
        merged["declared_width"] = str(source.get("declared_resolution") or "x").partition("x")[0]
        index.append(build_card(merged, scratch / "snapshots", scratch / "renders"))
        print("CARD %s %s" % (index[-1]["card"], index[-1]["native_frame_status"]))
    names = list(index[0]) if index else []
    with (scratch / "eye_index.csv").open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        writer.writerows(index)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
