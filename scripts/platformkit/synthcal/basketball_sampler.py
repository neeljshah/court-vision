"""CPU-only NBA high-sideline broadcast sampler with invisible landmark labels."""
from __future__ import annotations

from dataclasses import dataclass
from math import radians

import cv2
import numpy as np

# NBA Rule 1 court diagram: 94 x 50 ft court, 16 ft lane, 19 ft lane depth,
# 6 ft free-throw/centre circles, and 23 ft 9 in arc with 3 ft corner lines.
# Source: https://official.nba.com/rule-no-1-court-dimensions-equipment/
COURT_LENGTH_FT = 94.0
COURT_WIDTH_FT = 50.0
LANE_WIDTH_FT = 16.0
LANE_DEPTH_FT = 19.0
FREE_THROW_CIRCLE_RADIUS_FT = 6.0
THREE_POINT_ARC_RADIUS_FT = 23.75
THREE_POINT_CORNER_DISTANCE_FT = 22.0
FRAME_SIZE = (1280, 720)

# Provisional NBA main-camera prior. No basketball equivalent of SCCvSD is
# measured here: ranges encode an elevated, near-midcourt sideline camera.
# They are deliberately documented assumptions pending a measured NBA corpus.
CAMERA_X_FT = (39.0, 55.0)
CAMERA_Y_FT = (-48.0, -30.0)
CAMERA_HEIGHT_FT = (24.0, 38.0)
PAN_DEG = (-14.0, 14.0)
TILT_DEG = (-10.0, 6.0)
FOCAL_PX = (1550.0, 2450.0)
MIN_COURT_SHARE = 0.30
MIN_VISIBLE_LANDMARKS = 6


@dataclass(frozen=True)
class BasketballSample:
    """Rendered frame and aligned invisible template-point labels."""

    image: np.ndarray
    names: tuple[str, ...]
    points: np.ndarray
    visible: np.ndarray
    pose: dict[str, float]


def nba_landmarks() -> dict[str, tuple[float, float]]:
    """Return named NBA-template points in feet from the left end line."""
    lane_top, lane_bottom = 17.0, 33.0
    points = {
        "left_top_corner": (0.0, 0.0), "left_bottom_corner": (0.0, 50.0),
        "right_top_corner": (94.0, 0.0), "right_bottom_corner": (94.0, 50.0),
        "top_midcourt": (47.0, 0.0), "bottom_midcourt": (47.0, 50.0),
        "centre_spot": (47.0, 25.0),
        "left_lane_top_end": (0.0, lane_top), "left_lane_top_ft": (19.0, lane_top),
        "left_lane_bottom_ft": (19.0, lane_bottom), "left_lane_bottom_end": (0.0, lane_bottom),
        "right_lane_top_end": (94.0, lane_top), "right_lane_top_ft": (75.0, lane_top),
        "right_lane_bottom_ft": (75.0, lane_bottom), "right_lane_bottom_end": (94.0, lane_bottom),
    }
    for label, cx in (("left_ft", 19.0), ("right_ft", 75.0), ("centre", 47.0)):
        for direction, dx, dy in (("top", 0.0, -6.0), ("bottom", 0.0, 6.0),
                                  ("left", -6.0, 0.0), ("right", 6.0, 0.0)):
            points["%s_circle_%s" % (label, direction)] = (cx + dx, 25.0 + dy)
    return points


def _normalize(vector: np.ndarray) -> np.ndarray:
    return vector / np.linalg.norm(vector)


def _camera_matrix(axes: dict[str, object]) -> tuple[np.ndarray, np.ndarray, float]:
    camera = np.asarray(axes["camera"], dtype=float)
    pan, tilt = radians(float(axes["pan"])), radians(float(axes["tilt"]))
    target = np.array([47.0 + 30.0 * np.sin(pan), 25.0 + 5.0 * np.sin(tilt), 0.0])
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


def _court_share(rotation: np.ndarray, camera: np.ndarray, focal: float) -> float:
    court = np.array([[0, 0, 0], [94, 0, 0], [94, 50, 0], [0, 50, 0]], dtype=float)
    if ((rotation @ (court - camera).T).T[:, 2] <= 0).any():
        return 0.0
    pixels, _ = _project(court, rotation, camera, focal)
    mask = np.zeros((FRAME_SIZE[1], FRAME_SIZE[0]), dtype=np.uint8)
    cv2.fillConvexPoly(mask, np.rint(pixels).astype(np.int32), 1)
    return float(mask.mean())


def _sample_axes(rng: np.random.Generator) -> dict[str, object]:
    landmarks = np.array([[x, y, 0.0] for x, y in nba_landmarks().values()])
    for _ in range(64):
        axes: dict[str, object] = {
            "hue": float(rng.uniform(-13.0, 13.0)), "pan": float(rng.uniform(*PAN_DEG)),
            "tilt": float(rng.uniform(*TILT_DEG)), "focal": float(rng.uniform(*FOCAL_PX)),
            "camera": np.array([rng.uniform(*CAMERA_X_FT), rng.uniform(*CAMERA_Y_FT),
                                rng.uniform(*CAMERA_HEIGHT_FT)]),
            "wood": tuple(int(value) for value in rng.integers(95, 185, size=3)),
            "decoys": int(rng.integers(1, 5)),
        }
        rotation, camera, focal = _camera_matrix(axes)
        if (_court_share(rotation, camera, focal) >= MIN_COURT_SHARE and
                int(_project(landmarks, rotation, camera, focal)[1].sum()) >= MIN_VISIBLE_LANDMARKS):
            return axes
    raise RuntimeError("could not sample a valid basketball broadcast pose")


def geometry_metrics(seed: int) -> tuple[float, int]:
    """Measure court coverage and visible template labels for one sampled pose."""
    axes = _sample_axes(np.random.default_rng(seed))
    rotation, camera, focal = _camera_matrix(axes)
    world = np.array([[x, y, 0.0] for x, y in nba_landmarks().values()])
    return _court_share(rotation, camera, focal), int(_project(world, rotation, camera, focal)[1].sum())


def _polyline(image: np.ndarray, world: np.ndarray, rotation: np.ndarray, camera: np.ndarray, focal: float,
              color: tuple[int, int, int] = (230, 235, 240), thickness: int = 2) -> None:
    pixels, _ = _project(world, rotation, camera, focal)
    rect = (0, 0, FRAME_SIZE[0], FRAME_SIZE[1])
    for start, end in zip(pixels[:-1], pixels[1:]):
        clipped, a, b = cv2.clipLine(rect, tuple(np.rint(start).astype(int)), tuple(np.rint(end).astype(int)))
        if clipped:
            cv2.line(image, a, b, color, thickness, cv2.LINE_AA)


def _circle(cx: float, cy: float, radius: float) -> np.ndarray:
    angles = np.linspace(0, 2 * np.pi, 121)
    return np.column_stack((cx + radius * np.cos(angles), cy + radius * np.sin(angles), np.zeros_like(angles)))


def _draw_paint_occluders(image: np.ndarray, rotation: np.ndarray, camera: np.ndarray, focal: float,
                          rng: np.random.Generator) -> None:
    """Draw player-like rectangles from in-paint world positions, not global noise."""
    for _ in range(int(rng.integers(7, 14))):
        x = rng.uniform(1.0, 18.0) if rng.random() < 0.5 else rng.uniform(76.0, 93.0)
        y = rng.uniform(18.0, 32.0)
        pixel, visible = _project(np.array([[x, y, 0.0]]), rotation, camera, focal)
        if visible[0]:
            px, py = np.rint(pixel[0]).astype(int)
            cv2.rectangle(image, (px - int(rng.integers(6, 12)), py - int(rng.integers(14, 28))),
                          (px + int(rng.integers(6, 12)), py + int(rng.integers(14, 28))),
                          tuple(int(v) for v in rng.integers(20, 220, size=3)), -1)


def _draw_court(image: np.ndarray, axes: dict[str, object], rotation: np.ndarray, camera: np.ndarray,
                focal: float, rng: np.random.Generator) -> None:
    image[:] = (48, 42, 37)
    # Structured upper-bowl crowd band. It replaces texture noise with venue-like clutter.
    for top, color in ((0, (60, 57, 54)), (54, (86, 78, 72)), (116, (42, 43, 45))):
        cv2.rectangle(image, (0, top), (1280, top + 58), color, -1)
    for y in range(9, 172, 11):
        for x in range((y * 9) % 29, 1280, 29):
            cv2.circle(image, (x, y), 2, (132, 122, 108), -1)
    wood = np.array(axes["wood"], dtype=np.uint8)
    hsv = cv2.cvtColor(wood.reshape(1, 1, 3), cv2.COLOR_BGR2HSV).astype(np.int16)
    hsv[..., 0] = (hsv[..., 0] + round(float(axes["hue"]) / 2)) % 180
    wood = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).reshape(3)
    court = np.array([[0, 0, 0], [94, 0, 0], [94, 50, 0], [0, 50, 0]], dtype=float)
    pixels, _ = _project(court, rotation, camera, focal)
    cv2.fillConvexPoly(image, np.rint(pixels).astype(np.int32), tuple(int(v) for v in wood))
    for x in np.arange(0, 94, 6):
        strip = np.array([[x, 0, 0], [min(x + 3, 94), 0, 0], [min(x + 3, 94), 50, 0], [x, 50, 0]])
        strip_pixels, _ = _project(strip, rotation, camera, focal)
        cv2.fillConvexPoly(image, np.rint(strip_pixels).astype(np.int32), tuple(int(v) for v in np.clip(wood.astype(int) + 9, 0, 255)))
    lines = [np.array([[0, 0, 0], [94, 0, 0], [94, 50, 0], [0, 50, 0], [0, 0, 0]], dtype=float),
             np.array([[47, 0, 0], [47, 50, 0]], dtype=float)]
    for x, inner in ((0.0, 19.0), (94.0, 75.0)):
        lines.append(np.array([[x, 17, 0], [inner, 17, 0], [inner, 33, 0], [x, 33, 0]], dtype=float))
    for line in lines:
        _polyline(image, line, rotation, camera, focal)
    for cx in (19.0, 75.0, 47.0):
        _polyline(image, _circle(cx, 25.0, 6.0), rotation, camera, focal)
    arc_dx = float(np.sqrt(THREE_POINT_ARC_RADIUS_FT ** 2 - THREE_POINT_CORNER_DISTANCE_FT ** 2))
    for hoop, sign in ((5.25, 1.0), (88.75, -1.0)):
        endpoint = hoop + sign * arc_dx
        _polyline(image, np.array([[0 if sign > 0 else 94, 3, 0], [endpoint, 3, 0]], dtype=float), rotation, camera, focal)
        _polyline(image, np.array([[0 if sign > 0 else 94, 47, 0], [endpoint, 47, 0]], dtype=float), rotation, camera, focal)
        angles = np.linspace(-np.arccos(arc_dx / THREE_POINT_ARC_RADIUS_FT), np.arccos(arc_dx / THREE_POINT_ARC_RADIUS_FT), 121)
        if sign < 0:
            angles += np.pi
        arc = np.column_stack((hoop + THREE_POINT_ARC_RADIUS_FT * np.cos(angles), 25 + THREE_POINT_ARC_RADIUS_FT * np.sin(angles), np.zeros_like(angles)))
        _polyline(image, arc, rotation, camera, focal)
    _draw_paint_occluders(image, rotation, camera, focal, rng)
    cv2.rectangle(image, (30, 26), (290, 70), (25, 25, 25), -1)
    cv2.putText(image, "SYNTHCAL  72 - 68  Q3  04:12", (42, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (235, 235, 235), 1, cv2.LINE_AA)
    if int(axes["decoys"]) >= 2:
        cv2.rectangle(image, (780, 642), (1242, 690), (37, 37, 37), -1)
        cv2.putText(image, "OFFICIAL REVIEW", (808, 672), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (225, 225, 225), 1, cv2.LINE_AA)


def sample_basketball_frame(seed: int | None = None) -> BasketballSample:
    """Render one CPU-only basketball frame and its invisible template-point labels."""
    rng = np.random.default_rng(seed)
    axes = _sample_axes(rng)
    rotation, camera, focal = _camera_matrix(axes)
    image = np.empty((FRAME_SIZE[1], FRAME_SIZE[0], 3), dtype=np.uint8)
    _draw_court(image, axes, rotation, camera, focal, rng)
    landmarks = nba_landmarks()
    names = tuple(landmarks)
    world = np.array([[x, y, 0.0] for x, y in landmarks.values()])
    points, visible = _project(world, rotation, camera, focal)
    share = _court_share(rotation, camera, focal)
    if share < MIN_COURT_SHARE or int(visible.sum()) < MIN_VISIBLE_LANDMARKS:
        raise RuntimeError("basketball broadcast pose failed geometry guard")
    pose = {key: float(axes[key]) for key in ("pan", "tilt", "focal", "hue")}
    return BasketballSample(image, names, points.astype(np.float32), visible.astype(bool), pose)
