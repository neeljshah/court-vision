"""G264 evidence-only NCAA line-conic fit and blind-ladder renderer."""

from __future__ import annotations

import hashlib
import json
import secrets
import subprocess
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.g253_line_conic_calibration import (
    LineCorrespondence,
    circle_conic,
    ellipse_conic,
    fit_line_conic,
    image_line_angle_deg,
    render_court,
)
from scripts.platformkit.tracking.g196_homography_from_labelled_corners import (
    court_points_for_sport,
)
from scripts.platformkit.tracking.g257_eye_gate_discrimination import (
    translated_image_to_court,
)


LADDER_PX = (5, 10, 20, 40, 100)
SURVEY_SIZE = (320, 180)


def remote_survey_command(stride: int) -> list[str]:
    """Return a no-seek pod command for fixed-stride NCAA survey frames."""
    if stride < 1:
        raise ValueError("stride must be positive")
    width, height = SURVEY_SIZE
    video = "/workspace/nba-ai-system/data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4"
    remote = "ffmpeg -hide_banner -loglevel error -i " + video + " -vf 'select=not(mod(n\\," + str(stride) + ")),scale=" + str(width) + ":" + str(height) + "' -vsync 0 -f rawvideo -pix_fmt bgr24 pipe:1"
    return ["ssh", "config.pod", remote]


def write_survey_sheets(stride: int, output_dir: Path) -> dict[str, object]:
    """Stream evenly spaced pod frames into paginated, frame-indexed review sheets."""
    result = subprocess.run(remote_survey_command(stride), check=True, stdout=subprocess.PIPE)
    width, height = SURVEY_SIZE
    unit = width * height * 3
    if not result.stdout or len(result.stdout) % unit:
        raise RuntimeError("survey decode did not contain complete BGR frames")
    frames = np.frombuffer(result.stdout, dtype=np.uint8).reshape(-1, height, width, 3)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for start in range(0, len(frames), 20):
        tiles = []
        for index, frame in enumerate(frames[start : start + 20], start=start):
            tile = frame.copy()
            cv2.putText(tile, "frame %d" % (index * stride), (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 255), 1, cv2.LINE_AA)
            tiles.append(tile)
        while len(tiles) < 20:
            tiles.append(np.zeros_like(frames[0]))
        page = np.vstack([np.hstack(tiles[row : row + 5]) for row in range(0, 20, 5)])
        path = output_dir / ("survey_%02d.jpg" % (start // 20 + 1))
        if not cv2.imwrite(str(path), page, [cv2.IMWRITE_JPEG_QUALITY, 95]):
            raise OSError(path)
        paths.append({"path": path.name, "sha256": sha256(path)})
    return {"stride_frames": stride, "sampled_frames": int(len(frames)), "survey_size_px": [width, height], "pages": paths}


def remote_frame_command(frame: int) -> list[str]:
    """Return a no-seek pod command that emits one exact native frame as JPEG."""
    if frame < 0:
        raise ValueError("frame must be nonnegative")
    video = "/workspace/nba-ai-system/data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4"
    remote = "ffmpeg -hide_banner -loglevel error -i " + video + " -vf 'select=eq(n\\," + str(frame) + ")' -vsync 0 -frames:v 1 -f image2pipe -vcodec mjpeg pipe:1"
    return ["ssh", "config.pod", remote]


def write_remote_frame(frame: int, output: Path) -> dict[str, object]:
    """Stream an exact no-input-seek pod frame directly to retained JPEG evidence."""
    result = subprocess.run(remote_frame_command(frame), check=True, stdout=subprocess.PIPE)
    if not result.stdout:
        raise RuntimeError("remote decode returned no frame")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result.stdout)
    image = cv2.imread(str(output), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("remote JPEG cannot be decoded locally")
    return {"source_frame": frame, "jpeg_bytes": output.stat().st_size, "jpeg_sha256": sha256(output), "native_resolution_px": [int(image.shape[1]), int(image.shape[0])], "native_bgr_sha256": hashlib.sha256(image.tobytes()).hexdigest()}


def sha256(path: Path) -> str:
    """Return the SHA-256 of one retained evidence file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_fit_inputs(path: Path) -> tuple[list[LineCorrespondence], np.ndarray]:
    """Read two named line inputs and one named image ellipse from committed JSON."""
    payload = json.loads(path.read_text(encoding="ascii"))
    lines = [
        LineCorrespondence(
            item["name"],
            np.asarray(item["image_endpoints_px"], dtype=float),
            np.asarray(item["court_endpoints_ft"], dtype=float),
        )
        for item in payload["lines"]
    ]
    if len(lines) != 2:
        raise ValueError("G264 uses G253's unchanged two-line-plus-one-conic solver")
    conic = payload["centre_circle_image_ellipse"]
    return lines, np.asarray(
        [[float(conic["center_px"][0]), float(conic["center_px"][1])],
         [float(conic["axes_px"][0]), float(conic["axes_px"][1])],
         [float(conic["angle_deg"])]],
        dtype=float,
    )


def fit_from_inputs(path: Path) -> dict[str, object]:
    """Run G253's unchanged solver against the declared NCAA model inputs."""
    payload = json.loads(path.read_text(encoding="ascii"))
    lines, ellipse = read_fit_inputs(path)
    image_conic = ellipse_conic(tuple(ellipse[0]), tuple(ellipse[1]), float(ellipse[2, 0]))
    court_conic = circle_conic((25.0, 47.0), 6.0)
    homography, residual, condition = fit_line_conic(lines, image_conic, court_conic)
    return {
        "input_json_sha256": sha256(path),
        "sport": "ncaa_basketball",
        "court_points_for_sport": court_points_for_sport("ncaa_basketball").astype(float).tolist(),
        "line_names": [line.name for line in lines],
        "image_line_angle_deg": image_line_angle_deg(lines[0].image_endpoints, lines[1].image_endpoints),
        "observed_conic_fraction": float(payload["centre_circle_observed_fraction"]),
        "fit_objective_residual": residual,
        "jacobian_condition_number": condition,
        "homography_image_to_court": homography.tolist(),
    }


def write_fit_render(image_path: Path, measurement: dict[str, object], output: Path) -> None:
    """Write one NCAA candidate overlay with G253's existing court renderer."""
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)
    fitted = np.asarray(measurement["homography_image_to_court"], dtype=float)
    if not cv2.imwrite(str(output), render_court(image, fitted, "ncaa_basketball", (0, 255, 255))):
        raise OSError(output)


def write_identity_crop(image_path: Path, rectangle: tuple[int, int, int, int], output: Path) -> None:
    """Write an exact zoom crop from one source frame for pre-fit identity review."""
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)
    x, y, width, height = rectangle
    crop = image[y : y + height, x : x + width]
    if crop.size == 0:
        raise ValueError("identity crop is outside the source frame")
    enlarged = cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    if not cv2.imwrite(str(output), enlarged, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise OSError(output)


def _inset(image: np.ndarray, rectangle: tuple[int, int, int, int], width: int, height: int) -> np.ndarray:
    x, y, crop_width, crop_height = rectangle
    crop = image[y : y + crop_height, x : x + crop_width]
    scale = min(width / crop.shape[1], height / crop.shape[0])
    return cv2.resize(crop, (round(crop.shape[1] * scale), round(crop.shape[0] * scale)), interpolation=cv2.INTER_CUBIC)


def render_board(
    image: np.ndarray,
    image_to_court: np.ndarray,
    board_number: int,
    withheld_rectangles: list[tuple[int, int, int, int]],
) -> np.ndarray:
    """Render native NCAA overlay plus enlarged independent-geometry evidence crops."""
    full = render_court(image, image_to_court, "ncaa_basketball", (0, 255, 255))
    cv2.putText(full, "BLIND BOARD %02d" % board_number, (24, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    strip = np.full((410, full.shape[1], 3), 24, dtype=np.uint8)
    targets = ((20, "WITHHELD FAR PAINT"), (990, "WITHHELD FAR ARC"))
    for rect, (x, label) in zip(withheld_rectangles, targets):
        left, top, width, height = rect
        cv2.rectangle(full, (left, top), (left + width, top + height), (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(full, label, (left + 8, top + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
        inset = _inset(full, rect, 880, 380)
        strip[20 : 20 + inset.shape[0], x : x + inset.shape[1]] = inset
    return np.vstack((full, strip))


def build_blind_set(
    image_path: Path,
    measurement_path: Path,
    output_dir: Path,
    withheld_rectangles: list[tuple[int, int, int, int]],
) -> dict[str, object]:
    """Create randomized opaque boards; commit order/verdicts before opening the key."""
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)
    measurement = json.loads(measurement_path.read_text(encoding="ascii"))
    candidate = np.asarray(measurement["homography_image_to_court"], dtype=float)
    conditions = [{"condition": "candidate_unchanged", "magnitude_px": 0, "dx_px": 0.0}]
    conditions.extend({"condition": "translate_right_%d_px" % value, "magnitude_px": value, "dx_px": float(value)} for value in LADDER_PX)
    secrets.SystemRandom().shuffle(conditions)
    output_dir.mkdir(parents=True, exist_ok=True)
    order, key = [], []
    for number, condition in enumerate(conditions, start=1):
        rendered = candidate if not condition["magnitude_px"] else translated_image_to_court(candidate, condition["dx_px"])
        name = "blind_board_%02d.jpg" % number
        path = output_dir / name
        if not cv2.imwrite(str(path), render_board(image, rendered, number, withheld_rectangles), [cv2.IMWRITE_JPEG_QUALITY, 92]):
            raise OSError(path)
        order.append({"board": name, "sha256": sha256(path)})
        key.append({"board": name, **condition})
    manifest = {
        "purpose": "Commit this opaque randomized board order and blind verdicts before opening unblind_key.json.",
        "board_order": order,
        "displacement_definition": "For N>0, P_N=T(N,0)P where P=inverse(H); every finite projected court point moves exactly N image pixels right.",
        "ladder_px": list(LADDER_PX),
        "main_panel": "native source pixels at 1:1 scale",
        "withheld_rectangles_px": [list(item) for item in withheld_rectangles],
    }
    (output_dir / "blind_order.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")
    (output_dir / "unblind_key.json").write_text(json.dumps({"source_image": str(image_path), "measurement": str(measurement_path), "key": key}, indent=2) + "\n", encoding="ascii")
    return manifest
