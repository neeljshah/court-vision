"""Render G253's unchanged amateur map and a blind image-translation ladder."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.g253_line_conic_calibration import render_high_school_court


ROOT = Path(__file__).resolve().parents[3]
G253 = ROOT / "docs/evidence/tracking/g253_line_and_conic_calibration_2026-09-04_artifact"
DEFAULT_OUTPUT = ROOT / "docs/evidence/tracking/g257_eye_gate_discrimination_2026-09-04_artifact"
LADDER_PX = (5, 10, 20, 40, 100)
ARC_RECT = (0, 190, 500, 300)
PAINT_RECT = (0, 300, 390, 250)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_translation_homography(dx_px: float, dy_px: float = 0.0) -> np.ndarray:
    """Return an image-coordinate homogeneous translation."""
    return np.array(((1.0, 0.0, dx_px), (0.0, 1.0, dy_px), (0.0, 0.0, 1.0)))


def translated_image_to_court(candidate: np.ndarray, dx_px: float, dy_px: float = 0.0) -> np.ndarray:
    """Shift every candidate court projection by a stated image-plane vector."""
    shifted = image_translation_homography(dx_px, dy_px) @ np.linalg.inv(candidate)
    result = np.linalg.inv(shifted)
    return result / result[2, 2]


def _crop_and_scale(image: np.ndarray, rect: tuple[int, int, int, int], width: int, height: int) -> np.ndarray:
    x, y, crop_width, crop_height = rect
    crop = image[y : y + crop_height, x : x + crop_width]
    scale = min(width / crop.shape[1], height / crop.shape[0])
    return cv2.resize(crop, (round(crop.shape[1] * scale), round(crop.shape[0] * scale)), interpolation=cv2.INTER_CUBIC)


def render_board(image: np.ndarray, image_to_court: np.ndarray, board_number: int) -> np.ndarray:
    """Render one full-resolution overlay with two enlarged withheld-geometry insets."""
    full = render_high_school_court(image, image_to_court, (0, 255, 255))
    for rect, label in ((ARC_RECT, "WITHHELD LEFT ARC"), (PAINT_RECT, "WITHHELD PAINTED END")):
        x, y, width, height = rect
        cv2.rectangle(full, (x, y), (x + width, y + height), (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(full, label, (x + 5, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(full, "BLIND BOARD %02d" % board_number, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)
    insets = np.full((390, full.shape[1], 3), 24, dtype=np.uint8)
    arc = _crop_and_scale(full, ARC_RECT, 620, 370)
    paint = _crop_and_scale(full, PAINT_RECT, 600, 370)
    insets[10 : 10 + arc.shape[0], 20 : 20 + arc.shape[1]] = arc
    insets[10 : 10 + paint.shape[0], 660 : 660 + paint.shape[1]] = paint
    return np.vstack((full, insets))


def build_blind_set(image_path: Path, map_path: Path, output_dir: Path) -> dict[str, object]:
    """Create opaque-board renders and keep the condition key out of the blind manifest."""
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)
    payload = json.loads(map_path.read_text(encoding="ascii"))
    candidate = np.asarray(payload["homography_image_to_court"], dtype=float)
    conditions = [{"condition": "candidate_unchanged", "magnitude_px": 0, "dx_px": 0.0}]
    conditions.extend({"condition": "translate_right_%d_px" % magnitude, "magnitude_px": magnitude, "dx_px": float(magnitude)} for magnitude in LADDER_PX)
    secrets.SystemRandom().shuffle(conditions)
    output_dir.mkdir(parents=True, exist_ok=True)
    blind_order = []
    key = []
    for board_number, condition in enumerate(conditions, start=1):
        rendered_map = candidate if condition["magnitude_px"] == 0 else translated_image_to_court(candidate, condition["dx_px"])
        board_name = "blind_board_%02d.jpg" % board_number
        board_path = output_dir / board_name
        if not cv2.imwrite(str(board_path), render_board(image, rendered_map, board_number), [cv2.IMWRITE_JPEG_QUALITY, 92]):
            raise OSError(board_path)
        blind_order.append({"board": board_name, "sha256": _sha256(board_path)})
        key.append({"board": board_name, **condition})
    blind_manifest = {
        "purpose": "Commit this randomized opaque-board order and blind verdicts before opening unblind_key.json.",
        "board_order": blind_order,
        "render_layout": {
            "main_panel": "native 1280x720 frame at 1:1 pixels; no main-panel downscale",
            "insets": {"left_end_three_point_arc": list(ARC_RECT), "painted_end_markings": list(PAINT_RECT)},
            "composite_resolution_px": [int(image.shape[1]), int(image.shape[0] + 390)],
        },
    }
    (output_dir / "blind_order.json").write_text(json.dumps(blind_manifest, indent=2) + "\n", encoding="ascii")
    metadata = {
        "source": {"path": str(image_path), "bytes": image_path.stat().st_size, "resolution_px": [int(image.shape[1]), int(image.shape[0])], "sha256": _sha256(image_path)},
        "candidate_map": {"path": str(map_path), "bytes": map_path.stat().st_size, "sha256": _sha256(map_path), "homography_image_to_court": candidate.tolist()},
        "magnitude_definition": "For each noncandidate condition, left-multiply the court-to-image projection by an image-plane translation (+N, 0). Therefore every finite projected court point is translated exactly N pixels horizontally to camera right; N is not a physical or real-calibration-error estimate.",
        "ladder_px": list(LADDER_PX),
        "unblind_key": key,
    }
    (output_dir / "unblind_key.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="ascii")
    return blind_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=G253 / "amateur_frame_0540.jpg")
    parser.add_argument("--map", type=Path, default=G253 / "amateur_fit_measurement.json")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build_blind_set(args.image, args.map, args.output_dir)
    print("G257_BLIND_BOARDS=" + str(len(result["board_order"])))


if __name__ == "__main__":
    main()
