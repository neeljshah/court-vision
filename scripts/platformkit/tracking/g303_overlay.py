"""G303 eye check -- six EVENLY SPACED frames of the 24, ground truth and both arms drawn.

Headless render (cv2.imwrite only, never imshow). The sample positions are fixed in
`g303_prereg_supplement_2026-09-07b.md` section 6 -- round(i*23/5) for i = 0..5, so
0, 5, 9, 14, 18, 23 of the 24 sorted frame indices. No head slice. The detections drawn
come from the SAME run whose CSVs are committed (contract B11).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.platformkit.tracking.g296_merge_locators import consensus
from scripts.platformkit.tracking.g298_compare import read_csv

SAMPLES = 6
MAX_BYTES = 300 * 1024
QUALITIES = (88, 80, 72, 64, 55, 45, 35, 25)
GT = (60, 220, 60)        # adjudicated ground-truth point (BGR)
CONS = (0, 215, 255)      # consensus-86 point
ARM = {"P": (255, 160, 60), "R": (60, 60, 255)}


def positions(count: int = 24, samples: int = SAMPLES) -> list[int]:
    """Evenly spaced sample positions over the whole set -- never a head slice."""
    return [round(i * (count - 1) / (samples - 1)) for i in range(samples)]


def cross(image, point, colour, size=13, thickness=2):
    """An X centred on a detection footpoint."""
    import cv2
    x, y = int(point[0]), int(point[1])
    cv2.line(image, (x - size, y - size), (x + size, y + size), colour, thickness)
    cv2.line(image, (x - size, y + size), (x + size, y - size), colour, thickness)


def by_frame(rows, fx, fy, fid):
    """Group any point-bearing rows into {frame_id: [(x, y), ...]}."""
    out: dict[int, list[tuple[float, float]]] = {}
    for r in rows:
        out.setdefault(int(r[fid]), []).append((float(r[fx]), float(r[fy])))
    return out


def render(args):
    """Write one JPEG per sampled frame, each at most 300 KB."""
    import cv2
    order = [int(r["source_frame"]) for r in read_csv(args.frames_csv)]
    paths = sorted(args.frames.glob("frame_*.jpg"))
    assert len(order) == len(paths) == 24, "expect the 24 committed frames"
    truth = by_frame([r for r in read_csv(args.ground_truth) if r["source"] != "dropped"],
                     "x", "y", "frame_id")
    cons = by_frame(consensus(), "foot_x_px", "foot_y_px", "source_frame")
    dets = {arm: by_frame(read_csv(args.artifact / f"{arm}.csv"),
                          "foot_x_px", "foot_y_px", "source_frame") for arm in ARM}
    meta = json.loads((args.artifact / "g303_detect.json").read_text())["arms"]
    args.output.mkdir(parents=True, exist_ok=True)
    written = []
    for pos in positions(len(order)):
        frame_id, path = order[pos], paths[pos]
        image = cv2.imread(str(path))
        assert image is not None, path
        for arm, colour in ARM.items():
            for point in dets[arm].get(frame_id, []):
                cross(image, point, colour)
        for point in cons.get(frame_id, []):
            cv2.circle(image, (int(point[0]), int(point[1])), 16, CONS, 2)
        for point in truth.get(frame_id, []):
            cv2.circle(image, (int(point[0]), int(point[1])), 9, GT, -1)
            cv2.circle(image, (int(point[0]), int(point[1])), 10, (0, 0, 0), 1)
        legend = [
            f"G303 eye check  sample {pos} of 23  frame_id {frame_id}",
            f"filled green = adjudicated ground truth ({len(truth.get(frame_id, []))})",
            f"yellow ring = consensus-86 point ({len(cons.get(frame_id, []))})",
            f"orange X = ARM P conf {meta['P']['conf']} imgsz {meta['P']['imgsz']}"
            f" ({len(dets['P'].get(frame_id, []))})",
            f"red X = ARM R conf {meta['R']['conf']} imgsz {meta['R']['imgsz']}"
            f" ({len(dets['R'].get(frame_id, []))})",
        ]
        cv2.rectangle(image, (0, 0), (760, 26 * len(legend) + 14), (0, 0, 0), -1)
        for i, line in enumerate(legend):
            cv2.putText(image, line, (10, 26 * i + 26), cv2.FONT_HERSHEY_SIMPLEX, 0.62,
                        (255, 255, 255), 1, cv2.LINE_AA)
        out = args.output / f"eyecheck_pos{pos:02d}_frame{frame_id:06d}.jpg"
        for quality in QUALITIES:
            cv2.imwrite(str(out), image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            if out.stat().st_size <= MAX_BYTES:
                break
        assert out.stat().st_size <= MAX_BYTES, f"{out} still above 300 KB"
        written.append((out.name, out.stat().st_size, quality))
        print(f"{out.name} {out.stat().st_size} bytes quality={quality}", flush=True)
    return written


def main():
    parser = argparse.ArgumentParser()
    for flag in ("frames", "frames-csv", "ground-truth", "artifact", "output"):
        parser.add_argument("--" + flag, type=Path, required=True)
    render(parser.parse_args())


if __name__ == "__main__":
    main()
