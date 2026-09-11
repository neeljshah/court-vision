"""Timeline eye-check cards for the 30 drawn G401 sources.

One small JPEG per source: the native frames sitting either side of each cap
endpoint, plus a proportional timeline of the available span, arm A's reach,
arm B's reach and the loss between them.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

CARD = (640, 360)
THUMB = (148, 84)
BAR_TOP = 190
BAR_HEIGHT = 26
MARGIN = 16
INK = (18, 18, 18)
PAPER = (250, 250, 248)
ARM_A = (70, 110, 190)
ARM_B = (40, 140, 90)
LOSS = (200, 90, 60)


def grab(video: Path, pts: float | None, out: Path) -> bool:
    """Extract one native frame at a PTS into a small JPEG."""
    if pts is None:
        return False
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", "%.6f" % max(0.0, pts - 0.001),
         "-i", str(video), "-frames:v", "1", "-vf",
         "scale=%d:%d" % THUMB, "-q:v", "6", str(out)],
        capture_output=True, text=True)
    return result.returncode == 0 and out.exists()


def _bar(draw: ImageDraw.ImageDraw, row: dict) -> None:
    width = CARD[0] - 2 * MARGIN
    span = float(row["arm_b_span_s"] or 0.0)
    available = max(span, 1e-6)
    full = float(row.get("available_span_s") or span)
    scale = width / max(full, available, 1e-6)
    draw.rectangle([MARGIN, BAR_TOP, MARGIN + width, BAR_TOP + BAR_HEIGHT],
                   outline=INK, fill=(235, 235, 232))
    a_end = MARGIN + scale * float(row["arm_a_span_s"] or 0.0)
    b_end = MARGIN + scale * span
    draw.rectangle([MARGIN, BAR_TOP, a_end, BAR_TOP + BAR_HEIGHT], fill=ARM_A)
    draw.rectangle([a_end, BAR_TOP, b_end, BAR_TOP + BAR_HEIGHT], fill=LOSS)
    draw.line([b_end, BAR_TOP - 6, b_end, BAR_TOP + BAR_HEIGHT + 6],
              fill=ARM_B, width=3)
    draw.text((MARGIN, BAR_TOP + BAR_HEIGHT + 8),
              "arm A cap %d -> %.3f s | arm B cap %d -> %.3f s | interval %.5f s"
              % (row["arm_a_frame_cap"], row["arm_a_span_s"] or 0.0,
                 row["arm_b_frame_cap"], span,
                 row["native_frame_interval_s"] or 0.0), fill=INK)


def card(row: dict, video: Path, out: Path, work: Path) -> Path:
    """Render one source's paired-cap timeline card."""
    work.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", CARD, PAPER)
    draw = ImageDraw.Draw(image)
    labels = [("A last admitted", row["arm_a_last_admitted_pts"]),
              ("A first excluded", row["arm_a_first_excluded_pts"]),
              ("B last admitted", row["arm_b_last_admitted_pts"]),
              ("B first excluded", row["arm_b_first_excluded_pts"])]
    for index, (label, pts) in enumerate(labels):
        left = MARGIN + index * (THUMB[0] + 10)
        thumb = work / ("%s_%d.jpg" % (out.stem, index))
        if grab(video, pts, thumb):
            image.paste(Image.open(thumb), (left, 60))
        else:
            draw.rectangle([left, 60, left + THUMB[0], 60 + THUMB[1]],
                           outline=INK)
            draw.text((left + 8, 60 + THUMB[1] // 2), "ABSENT", fill=LOSS)
        draw.text((left, 48), label, fill=INK)
        draw.text((left, 60 + THUMB[1] + 4),
                  "pts %s" % ("none" if pts is None else "%.4f" % pts), fill=INK)
    draw.text((MARGIN, 12), "j=%02d  %s" % (row["draw_j"], row["source_name"]),
              fill=INK)
    draw.text((MARGIN, 28),
              "fps %.5f  basis %s  source frames %d  reaches 100 s: %s"
              % (row["validated_fps"] or 0.0, row["cap_basis"],
                 row["source_frame_count"], row["arm_b_reaches_target"]),
              fill=INK)
    _bar(draw, row)
    draw.text((MARGIN, BAR_TOP + BAR_HEIGHT + 26),
              "arm A read %d frames, arm B read %d frames; arm A loss %.3f s, "
              "arm B loss %.3f s" % (row["arm_a_read_frames"],
                                     row["arm_b_read_frames"],
                                     row["arm_a_loss_s"], row["arm_b_loss_s"]),
              fill=INK)
    draw.text((MARGIN, BAR_TOP + BAR_HEIGHT + 44),
              "DECLARED stride opportunities: %s. Emitted coverage NOT VERIFIED."
              % row["declared_stride_opportunities"], fill=INK)
    image.save(out, "JPEG", quality=72, optimize=True)
    return out


def render_all(paired: list[dict], spans: dict, sources: Path, out_dir: Path,
               work: Path) -> list[dict]:
    """Render every drawn card and return the eye index rows."""
    out_dir.mkdir(parents=True, exist_ok=True)
    index = []
    for row in sorted(paired, key=lambda r: r["draw_j"]):
        merged = dict(row)
        merged["available_span_s"] = spans.get(row["source_name"])
        target = out_dir / ("j%02d_%s.jpg" % (row["draw_j"],
                                              row["source_name"][:-4]))
        card(merged, sources / row["source_name"], target, work)
        index.append({"draw_j": row["draw_j"], "source_name": row["source_name"],
                      "render": target.name, "bytes": target.stat().st_size})
    return index
