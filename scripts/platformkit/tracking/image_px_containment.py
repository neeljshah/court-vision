"""Check that rows declaring image_px actually lie in the source image plane.

The coordinate contract decides scorability from the DECLARATION, which is
correct: magnitudes cannot separate court feet from rescaled pixels. But it
never checks the other direction -- that a table declaring ``image_px`` is in
the source image plane at all. A derived canvas (a 2D minimap, a stitched
panorama) is also "pixels", and declaring it ``image_px`` makes the corpus
unusable as a teacher without anyone noticing, because every contract check
still passes on the declaration alone.

This is the missing independent check: points must land inside the decoded
frame. Basketball anchors (FT circle 6.00 ft, arc 22.146 ft, midcourt x=47 ft)
are court validators and play no part here -- the only reference is the source
resolution, read from the video itself.
"""
from __future__ import annotations

import sys
from dataclasses import asdict, dataclass

import pandas as pd

from scripts.platformkit.coordinate_provenance import (
    COORDINATE_SPACE,
    IMAGE_COORDINATE_SPACE,
)

# A tracker that clips or drops off-frame detections still leaves a few points
# on the border, so the gate is share-based rather than all-or-nothing.
INSIDE_SHARE_MIN = 0.99

NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class ImagePxContainment:
    """How much of a declared image_px table lies inside the decoded frame."""

    width: int
    height: int
    n_rows: int
    n_inside: int
    inside_share: float
    max_x: float
    max_y: float
    verdict: str

    def to_dict(self) -> dict:
        return asdict(self)


def containment(rows: pd.DataFrame, width: int, height: int) -> ImagePxContainment:
    """Score only the rows that declare image_px against the frame bounds."""
    if width <= 0 or height <= 0:
        raise ValueError("source resolution must be positive: %dx%d" % (width, height))
    declared = (rows[rows[COORDINATE_SPACE] == IMAGE_COORDINATE_SPACE]
                if COORDINATE_SPACE in rows.columns else rows.iloc[0:0])
    n_rows = int(len(declared))
    if not n_rows:
        return ImagePxContainment(width, height, 0, 0, 0.0, 0.0, 0.0, NOT_APPLICABLE)
    x, y = pd.to_numeric(declared["x"]), pd.to_numeric(declared["y"])
    inside = x.between(0, width - 1) & y.between(0, height - 1)
    n_inside = int(inside.sum())
    share = n_inside / n_rows
    return ImagePxContainment(
        width=width, height=height, n_rows=n_rows, n_inside=n_inside,
        inside_share=round(share, 4), max_x=float(x.max()), max_y=float(y.max()),
        verdict="PASS" if share >= INSIDE_SHARE_MIN else "FAIL",
    )


def source_resolution(video_path: str) -> tuple[int, int]:
    """Read the decoded frame size from the video, not from a config."""
    import cv2  # deferred: the contract check itself needs no decoder

    capture = cv2.VideoCapture(video_path)
    try:
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        capture.release()
    if width <= 0 or height <= 0:
        raise ValueError("could not read a frame size from %s" % video_path)
    return width, height


def main(argv: list[str]) -> int:
    """Usage: image_px_containment.py <tracking.csv> <source_video>"""
    import json

    csv_path, video_path = argv[0], argv[1]
    width, height = source_resolution(video_path)
    result = containment(pd.read_csv(csv_path, low_memory=False), width, height)
    sys.stdout.write(json.dumps(result.to_dict()) + "\n")
    return 0 if result.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
