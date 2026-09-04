"""Render the preregistered G243b high-school seed-label geometries."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np


WIDTH_FT = 50.0
LENGTH_FT = 84.0
LANE_FT = 12.0
PAINT_DEPTH_FT = 19.0
THREE_POINT_FT = 19.75
SEED_FRAME = 2760
LABEL_SETS = {
    "clustered": {
        "court_points_ft": ((19, 0), (31, 0), (19, 19), (31, 19)),
        "labels_px": (
            ((45, 385), (283, 276), (363, 424), (624, 306)),
            ((48, 382), (280, 279), (366, 420), (620, 309)),
            ((42, 388), (287, 273), (358, 427), (628, 302)),
        ),
    },
    "spread": {
        "court_points_ft": ((19, 19), (31, 19), (25, 36), (25, 48)),
        "labels_px": (
            ((363, 424), (624, 306), (1140, 359), (1160, 468)),
            ((366, 420), (620, 309), (1137, 362), (1164, 464)),
            ((358, 427), (628, 302), (1144, 356), (1156, 472)),
        ),
    },
}


def decode_frame_exact(video: Path, frame: int, width: int, height: int) -> np.ndarray:
    """Decode one zero-based frame with ffmpeg select, never input-side seek."""
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
        "-vf", f"select=eq(n\\,{frame})", "-vsync", "0", "-frames:v", "1",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1",
    ]
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE)
    expected = width * height * 3
    if len(result.stdout) != expected:
        raise RuntimeError(f"frame {frame}: expected {expected} BGR bytes, got {len(result.stdout)}")
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape(height, width, 3).copy()


def _arc(center: tuple[float, float], radius: float, start: float, end: float) -> np.ndarray:
    angle = np.linspace(start, end, 121)
    return np.column_stack((center[0] + radius * np.cos(angle), center[1] + radius * np.sin(angle))).astype(np.float32)


def court_lines() -> list[np.ndarray]:
    """Return the row-local 84-by-50 ft high-school court line contract."""
    left, right = (WIDTH_FT - LANE_FT) / 2, (WIDTH_FT + LANE_FT) / 2
    lines = [
        np.float32(((0, 0), (WIDTH_FT, 0), (WIDTH_FT, LENGTH_FT), (0, LENGTH_FT), (0, 0))),
        np.float32(((0, LENGTH_FT / 2), (WIDTH_FT, LENGTH_FT / 2))),
        np.float32(((left, 0), (right, 0), (right, PAINT_DEPTH_FT), (left, PAINT_DEPTH_FT), (left, 0))),
        np.float32(((left, LENGTH_FT), (right, LENGTH_FT), (right, LENGTH_FT - PAINT_DEPTH_FT), (left, LENGTH_FT - PAINT_DEPTH_FT), (left, LENGTH_FT))),
        _arc((WIDTH_FT / 2, LENGTH_FT / 2), 6, 0, 2 * np.pi),
    ]
    for baseline, direction in ((0.0, 1.0), (LENGTH_FT, -1.0)):
        basket = baseline + direction * 4
        free_throw = baseline + direction * PAINT_DEPTH_FT
        lines += [np.float32(((left, free_throw), (right, free_throw))), _arc((WIDTH_FT / 2, free_throw), LANE_FT / 2, 0, np.pi)]
        arc = _arc((WIDTH_FT / 2, basket), THREE_POINT_FT, 0, np.pi)
        if direction < 0:
            arc[:, 1] = 2 * basket - arc[:, 1]
        lines += [arc, np.float32(((arc[0, 0], baseline), arc[0])), np.float32(((arc[-1, 0], baseline), arc[-1]))]
    return lines


def solve_and_render(image: np.ndarray, labels: np.ndarray, court: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Fit four inputs and return the overlay, matrix, and self-fit round-trip RMS."""
    homography = cv2.getPerspectiveTransform(labels, court)
    inverse = np.linalg.inv(homography)
    rendered = image.copy()
    for line in court_lines():
        projected = cv2.perspectiveTransform(line.reshape(1, -1, 2), inverse)[0]
        if np.isfinite(projected).all() and np.abs(projected).max() < 1_000_000:
            cv2.polylines(rendered, [np.round(projected).astype(np.int32)], False, (0, 255, 255), 2, cv2.LINE_AA)
    for point in labels:
        cv2.circle(rendered, tuple(np.round(point).astype(int)), 7, (0, 0, 255), -1, cv2.LINE_AA)
    mapped = cv2.perspectiveTransform(labels.reshape(1, -1, 2), homography)[0]
    recovered = cv2.perspectiveTransform(mapped.reshape(1, -1, 2), inverse)[0]
    rms = float(np.sqrt(np.mean(np.square(np.linalg.norm(recovered - labels, axis=1)))))
    return rendered, homography, rms


def run(video: Path, output_dir: Path, width: int = 1280, height: int = 720) -> dict[str, object]:
    """Write G243b seed renders and label-sensitivity records from the fixed inputs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    image = decode_frame_exact(video, SEED_FRAME, width, height)
    if not cv2.imwrite(str(output_dir / "seed_frame_2760.jpg"), image):
        raise OSError("could not write exact seed image")
    report: dict[str, object] = {"seed_frame": SEED_FRAME, "resolution_px": [width, height], "sets": {}}
    for name, source in LABEL_SETS.items():
        court = np.float32(source["court_points_ft"])
        labelings = [np.float32(values) for values in source["labels_px"]]
        primary = labelings[0]
        primary_render, primary_h, primary_rms = solve_and_render(image, primary, court)
        set_dir = output_dir / name
        set_dir.mkdir(exist_ok=True)
        if not cv2.imwrite(str(set_dir / "render_labelling_1.jpg"), primary_render):
            raise OSError(f"could not write {name} primary render")
        alternates = []
        for index, labels in enumerate(labelings[1:], start=2):
            rendered, matrix, self_rms = solve_and_render(image, labels, court)
            if not cv2.imwrite(str(set_dir / f"render_labelling_{index}.jpg"), rendered):
                raise OSError(f"could not write {name} alternate render")
            projected = cv2.perspectiveTransform(court.reshape(1, -1, 2), np.linalg.inv(primary_h))[0]
            alternates.append({"labelling": index, "self_fit_round_trip_rms_px": self_rms,
                               "rms_against_labelling_1_projection_px": float(np.sqrt(np.mean(np.square(np.linalg.norm(projected - labels, axis=1))))),
                               "homography_image_to_court": matrix.astype(float).tolist()})
        report["sets"][name] = {"court_points_ft": court.astype(float).tolist(), "labelings_px": [row.astype(float).tolist() for row in labelings], "labelling_used_for_fit": 1, "self_fit_round_trip_rms_px": primary_rms, "homography_image_to_court": primary_h.astype(float).tolist(), "alternate_labellings": alternates}
    (output_dir / "measurement.json").write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.video, args.output_dir)
    print("G243B_SEED_FRAME=" + str(result["seed_frame"]))
    print("G243B_LABEL_SETS=" + str(len(result["sets"])))


if __name__ == "__main__":
    main()
