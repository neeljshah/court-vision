"""CPU-only broadcast-style soccer pitch sampler with invisible landmark labels."""
from __future__ import annotations

from dataclasses import dataclass
from math import radians

import cv2
import numpy as np

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
CENTRE_CIRCLE_RADIUS_M = 9.15
FRAME_SIZE = (1280, 720)

# SCCvSD (lood339/SCCvSD, BSD-2) measured broadcast-pose prior.
PAN_DEG = (-35.0, 35.0)
TILT_DEG = (-15.0, -5.0)
FOCAL_PX = (1000.0, 6000.0)
CAMERA_MEAN_M = np.array([52.0, -45.0, 17.0])
CAMERA_SD_M = np.array([2.0, 9.0, 3.0])
_BROADCAST_FOCAL_PX = (2000.0, 2600.0)
MIN_PITCH_SHARE = 0.30
MIN_VISIBLE_LANDMARKS = 6


@dataclass(frozen=True)
class SoccerSample:
    """Rendered frame and aligned invisible-marker labels."""

    image: np.ndarray
    names: tuple[str, ...]
    points: np.ndarray
    visible: np.ndarray
    pose: dict[str, float]


def fifa_landmarks() -> dict[str, tuple[float, float]]:
    """Return named FIFA-template points in metres from the left goal line."""
    penalty_y = (PITCH_WIDTH_M - 40.32) / 2
    goal_y = (PITCH_WIDTH_M - 18.32) / 2
    return {
        "top_midline": (52.5, 0.0), "bottom_midline": (52.5, 68.0),
        "centre_spot": (52.5, 34.0), "left_penalty_spot": (11.0, 34.0),
        "right_penalty_spot": (94.0, 34.0),
        "centre_circle_top": (52.5, 34.0 - CENTRE_CIRCLE_RADIUS_M),
        "centre_circle_bottom": (52.5, 34.0 + CENTRE_CIRCLE_RADIUS_M),
        "centre_circle_left": (52.5 - CENTRE_CIRCLE_RADIUS_M, 34.0),
        "left_penalty_top_goal": (0.0, penalty_y),
        "left_penalty_top_inner": (16.5, penalty_y),
        "left_penalty_bottom_inner": (16.5, 68.0 - penalty_y),
        "left_penalty_bottom_goal": (0.0, 68.0 - penalty_y),
        "right_penalty_top_inner": (88.5, penalty_y),
        "right_penalty_top_goal": (105.0, penalty_y),
        "right_penalty_bottom_goal": (105.0, 68.0 - penalty_y),
        "right_penalty_bottom_inner": (88.5, 68.0 - penalty_y),
        "left_goal_top_goal": (0.0, goal_y), "left_goal_top_inner": (5.5, goal_y),
        "left_goal_bottom_inner": (5.5, 68.0 - goal_y),
        "left_goal_bottom_goal": (0.0, 68.0 - goal_y),
        "right_goal_top_inner": (99.5, goal_y), "right_goal_top_goal": (105.0, goal_y),
        "right_goal_bottom_goal": (105.0, 68.0 - goal_y),
        "right_goal_bottom_inner": (99.5, 68.0 - goal_y),
    }


def _normalize(vector: np.ndarray) -> np.ndarray:
    return vector / np.linalg.norm(vector)


def _sample_axes(rng: np.random.Generator) -> dict[str, float | int | tuple[int, int, int]]:
    """Sample SoccerSynth-Field axes in measured priority order."""
    # Priority: lighting hue, viewpoint, grass/ground, then decoy lines.
    # Reject framing failures here, so a caller cannot silently create the
    # sky-heavy samples this sampler is intended to exclude.
    landmarks = np.array([[x, y, 0.0] for x, y in fifa_landmarks().values()])
    for _ in range(64):
        hue = float(rng.uniform(-18.0, 18.0))
        pan, tilt = float(rng.uniform(*PAN_DEG)), float(rng.uniform(*TILT_DEG))
        # The source prior spans 1k--6k pixels, but the 720p main-camera
        # renderer retains its measured mid-field framing band.
        focal = float(rng.uniform(*_BROADCAST_FOCAL_PX))
        camera = rng.normal(CAMERA_MEAN_M, CAMERA_SD_M).astype(float)
        axes = {"hue": hue, "pan": pan, "tilt": tilt, "focal": focal,
                "camera": camera, "grass": tuple(int(value) for value in rng.integers(62, 150, size=3)),
                "pattern": int(rng.integers(0, 4)), "decoys": int(rng.integers(0, 5))}
        rotation, _, _ = _camera_matrix(axes)
        if (_pitch_share(rotation, camera, focal) >= MIN_PITCH_SHARE and
                int(_project(landmarks, rotation, camera, focal)[1].sum()) >= MIN_VISIBLE_LANDMARKS):
            return axes
    raise RuntimeError("could not sample a valid soccer broadcast pose")


def _camera_matrix(axes: dict[str, object]) -> tuple[np.ndarray, np.ndarray, float]:
    camera = np.asarray(axes["camera"], dtype=float)
    # SCCvSD's negative camera-y lies outside the near touchline.  Its optical
    # axis therefore points toward the pitch, not along negative y.  Building
    # the basis from a pitch look-at target avoids the old handedness/tilt bug
    # that aimed the lens above the field.
    pan, tilt = radians(float(axes["pan"])), radians(float(axes["tilt"]))
    target = np.array([
        PITCH_LENGTH_M / 2 + 35.0 * np.sin(pan),
        PITCH_WIDTH_M / 2 + 1.5 * np.sin(tilt),
        0.0,
    ])
    forward = _normalize(target - camera)
    right = _normalize(np.cross(forward, np.array([0.0, 0.0, 1.0])))
    up = _normalize(np.cross(right, forward))
    return np.vstack([right, up, forward]), camera, float(axes["focal"])


def _project(world: np.ndarray, rotation: np.ndarray, camera: np.ndarray, focal: float) -> tuple[np.ndarray, np.ndarray]:
    width, height = FRAME_SIZE
    camera_points = (rotation @ (world - camera).T).T
    depth = camera_points[:, 2]
    safe_depth = np.maximum(depth, 1e-6)
    pixels = np.column_stack((width / 2 + focal * camera_points[:, 0] / safe_depth,
                              height / 2 - focal * camera_points[:, 1] / safe_depth))
    visible = ((depth > 0) & (pixels[:, 0] >= 0) & (pixels[:, 0] < width) &
               (pixels[:, 1] >= 0) & (pixels[:, 1] < height))
    return pixels, visible


def _pitch_share(rotation: np.ndarray, camera: np.ndarray, focal: float) -> float:
    """Return clipped screen share occupied by the projected pitch polygon."""
    pitch = np.array([[0, 0, 0], [105, 0, 0], [105, 68, 0], [0, 68, 0]], dtype=float)
    if ((rotation @ (pitch - camera).T).T[:, 2] <= 0).any():
        return 0.0
    pixels, _ = _project(pitch, rotation, camera, focal)
    mask = np.zeros((FRAME_SIZE[1], FRAME_SIZE[0]), dtype=np.uint8)
    cv2.fillConvexPoly(mask, np.rint(pixels).astype(np.int32), 1)
    return float(mask.mean())


def geometry_metrics(seed: int) -> tuple[float, int]:
    """Measure pitch coverage and visible template labels for one sampled pose."""
    axes = _sample_axes(np.random.default_rng(seed))
    rotation, camera, focal = _camera_matrix(axes)
    world = np.array([[x, y, 0.0] for x, y in fifa_landmarks().values()])
    return _pitch_share(rotation, camera, focal), int(_project(world, rotation, camera, focal)[1].sum())


def _polyline(image: np.ndarray, world: np.ndarray, rotation: np.ndarray, camera: np.ndarray, focal: float,
              color: tuple[int, int, int] = (235, 245, 235), thickness: int = 2) -> None:
    pixels, _ = _project(world, rotation, camera, focal)
    rect = (0, 0, FRAME_SIZE[0], FRAME_SIZE[1])
    for start, end in zip(pixels[:-1], pixels[1:]):
        start_i, end_i = tuple(np.rint(start).astype(int)), tuple(np.rint(end).astype(int))
        clipped, start_i, end_i = cv2.clipLine(rect, start_i, end_i)
        if clipped:
            cv2.line(image, start_i, end_i, color, thickness, cv2.LINE_AA)


def _draw_pitch(image: np.ndarray, axes: dict[str, object], rotation: np.ndarray, camera: np.ndarray, focal: float,
                rng: np.random.Generator) -> None:
    grass = np.array(axes["grass"], dtype=np.uint8)
    hsv = cv2.cvtColor(grass.reshape(1, 1, 3), cv2.COLOR_BGR2HSV).astype(np.int16)
    hsv[..., 0] = (hsv[..., 0] + round(float(axes["hue"]) / 2)) % 180
    grass = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).reshape(3)
    image[:] = (64, 53, 43)
    # Structured stands and crowd plates, rather than noise, make the top of
    # the frame read as a broadcast venue even when the pitch horizon is high.
    for row, color in ((0, (72, 67, 62)), (54, (91, 83, 72)), (118, (54, 52, 49))):
        cv2.rectangle(image, (0, row), (FRAME_SIZE[0], row + 58), color, -1)
    for y in range(10, 170, 12):
        for x in range((y * 7) % 23, FRAME_SIZE[0], 23):
            cv2.circle(image, (x, y), 2, (125, 116, 101), -1)
    corners = np.array([[0, 0, 0], [105, 0, 0], [105, 68, 0], [0, 68, 0]], dtype=float)
    polygon, _ = _project(corners, rotation, camera, focal)
    depths = (rotation @ (corners - camera).T).T[:, 2]
    if (depths > 0).all():
        cv2.fillConvexPoly(image, np.rint(polygon).astype(np.int32), tuple(int(value) for value in grass))
        shadow = polygon.astype(np.float32) + np.array([18.0, 28.0], dtype=np.float32)
        overlay = image.copy()
        cv2.fillConvexPoly(overlay, np.rint(shadow).astype(np.int32), (20, 30, 20))
        cv2.addWeighted(overlay, 0.18, image, 0.82, 0.0, image)
    if int(axes["pattern"]) > 0:
        for x in np.linspace(0, 105, 15):
            shade = (int(axes["pattern"]) * 7) * (1 if int(x / 7) % 2 else -1)
            stripe = np.clip(grass.astype(int) + shade, 0, 255).astype(np.uint8)
            area = np.array([[x, 0, 0], [x + 7.2, 0, 0], [x + 7.2, 68, 0], [x, 68, 0]], dtype=float)
            pixels, _ = _project(area, rotation, camera, focal)
            cv2.fillConvexPoly(image, np.rint(pixels).astype(np.int32), tuple(int(value) for value in stripe))
    lines = [np.array([[0, 0, 0], [105, 0, 0], [105, 68, 0], [0, 68, 0], [0, 0, 0]], dtype=float),
             np.array([[52.5, 0, 0], [52.5, 68, 0]], dtype=float)]
    for x, y0, y1 in ((0, 13.84, 54.16), (105, 13.84, 54.16)):
        inner = 16.5 if x == 0 else 88.5
        lines.append(np.array([[x, y0, 0], [inner, y0, 0], [inner, y1, 0], [x, y1, 0]], dtype=float))
    for x, y0, y1 in ((0, 24.84, 43.16), (105, 24.84, 43.16)):
        inner = 5.5 if x == 0 else 99.5
        lines.append(np.array([[x, y0, 0], [inner, y0, 0], [inner, y1, 0], [x, y1, 0]], dtype=float))
    for line in lines:
        _polyline(image, line, rotation, camera, focal)
    angles = np.linspace(0, 2 * np.pi, 121)
    circle = np.column_stack((52.5 + CENTRE_CIRCLE_RADIUS_M * np.cos(angles), 34 + CENTRE_CIRCLE_RADIUS_M * np.sin(angles), np.zeros_like(angles)))
    _polyline(image, circle, rotation, camera, focal)
    for _ in range(int(axes["decoys"])):
        x, y = rng.uniform(8, 97), rng.uniform(8, 60)
        _polyline(image, np.array([[x, y, 0], [x + rng.uniform(-7, 7), y + rng.uniform(-4, 4), 0]]), rotation, camera, focal, (160, 180, 160), 1)
    # A compact scorebug and occasional lower-third mimic broadcast graphics;
    # neither is a label and both deliberately compete with line-like texture.
    cv2.rectangle(image, (32, 28), (250, 68), (28, 28, 28), -1)
    cv2.putText(image, "SYNTHCAL  52:18", (42, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1, cv2.LINE_AA)
    if int(axes["decoys"]) >= 3:
        cv2.rectangle(image, (840, 642), (1240, 690), (40, 40, 40), -1)
        cv2.putText(image, "REPLAY REVIEW", (860, 672), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1, cv2.LINE_AA)


def sample_soccer_frame(seed: int | None = None) -> SoccerSample:
    """Render one CPU-only soccer frame and its invisible template-point labels."""
    rng = np.random.default_rng(seed)
    axes = _sample_axes(rng)
    rotation, camera, focal = _camera_matrix(axes)
    share = _pitch_share(rotation, camera, focal)
    image = np.empty((FRAME_SIZE[1], FRAME_SIZE[0], 3), dtype=np.uint8)
    _draw_pitch(image, axes, rotation, camera, focal, rng)
    landmarks = fifa_landmarks()
    names = tuple(landmarks)
    world = np.array([[x, y, 0.0] for x, y in landmarks.values()])
    pitch_world = np.array([[0, 0, 0], [105, 0, 0], [105, 68, 0], [0, 68, 0]], dtype=float)
    pitch_pixels, _ = _project(pitch_world, rotation, camera, focal)
    homography = cv2.getPerspectiveTransform(pitch_world[:, :2].astype(np.float32), pitch_pixels.astype(np.float32))
    points = cv2.perspectiveTransform(world[:, :2].reshape(1, -1, 2).astype(np.float32), homography).reshape(-1, 2)
    _, visible = _project(world, rotation, camera, focal)
    if share < MIN_PITCH_SHARE or int(visible.sum()) < MIN_VISIBLE_LANDMARKS:
        raise RuntimeError("soccer broadcast pose failed geometry guard")
    pose = {key: float(axes[key]) for key in ("pan", "tilt", "focal", "hue")}
    return SoccerSample(image, names, points.astype(np.float32), visible.astype(bool), pose)
