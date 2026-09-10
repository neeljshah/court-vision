"""G363 blind rater sheets: one reference frame over its causal 3-frame strip.

Sealed by docs/evidence/tracking/g363_ball_coverage_2026-09-09/g363_prereg_2026-09-09.md
section 6.  A sheet carries no candidate box, no detector score, no arm name and
no burned-in text; the rater sees the image and the fixed instruction only.
"""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.tracking.g363_ball_coverage import SHEET_PANEL_WIDTH, file_sha256

SHEET_STRIP_WIDTH = 320
SHEET_MAX_BYTES = 200_000
SHEET_FIELDS = ("frame_key", "sheet", "sheet_sha256", "sheet_bytes", "sheet_scale")


def build_sheet(cv2, np, centre, minus1, minus2):
    """Blind sheet: the reference frame over its causal 3-frame strip, no text."""
    def scaled(image, width):
        height = max(1, round(image.shape[0] * width / image.shape[1]))
        return cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)

    panel = scaled(centre, SHEET_PANEL_WIDTH)
    strip = np.hstack([scaled(image, SHEET_STRIP_WIDTH) for image in (minus2, minus1, centre)])
    if strip.shape[1] != panel.shape[1]:
        strip = scaled(strip, panel.shape[1])
    sheet = np.vstack([panel, strip])
    buffer = None
    for quality in (92, 85, 75, 65, 55, 45, 35):
        ok, buffer = cv2.imencode(".jpg", sheet, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if ok and buffer.nbytes <= SHEET_MAX_BYTES:
            break
    return buffer


def sheets(frames: list[dict], cache: Path, out_dir: Path) -> list[dict]:
    """Write one blind sheet per sealed reference frame plus a sheet manifest."""
    import cv2
    import numpy as np

    cv2.setNumThreads(1)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    for row in frames:
        images = [cv2.imread(str(Path(cache) / (row[key] + ".png")))
                  for key in ("frame_key", "m1_sha256", "m2_sha256")]
        if any(image is None for image in images):
            print("ABSENT-CACHE " + row["frame_key"])
            continue
        target = out_dir / (row["frame_key"][:12] + ".jpg")
        target.write_bytes(build_sheet(cv2, np, images[0], images[1], images[2]).tobytes())
        manifest.append({"frame_key": row["frame_key"], "sheet": target.name,
                         "sheet_sha256": file_sha256(target),
                         "sheet_bytes": target.stat().st_size,
                         "sheet_scale": row["sheet_scale"]})
    return manifest
