"""Stream native soccer candidates and fit a homography from four box lines."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np


POD_CONFIG = r"C:\Users\neelj\.ssh\config.pod"
POD_HOST = "pod"
SOURCE = "/workspace/nba-ai-system/data/footage_corpus/soccer__soccer_Z6NTDyxcODs.mp4"


def ssh_command(remote: str) -> list[str]:
    """Build the batch-mode SSH invocation for read-only pod streaming."""
    return ["ssh.exe", "-F", POD_CONFIG, "-o", "BatchMode=yes", POD_HOST, remote]


def native_frames_command(frames: Sequence[int]) -> str:
    """Return a no-input-seek command for distinct, zero-based frames."""
    if not frames or any(frame < 0 for frame in frames):
        raise ValueError("frames must be nonempty and nonnegative")
    if list(frames) != sorted(set(frames)):
        raise ValueError("frames must be strictly increasing and unique")
    selector = "+".join(f"eq(n\\,{frame})" for frame in frames)
    return (
        f"ffmpeg -v error -i '{SOURCE}' -vf 'select={selector}' -vsync 0 "
        "-f image2pipe -vcodec mjpeg -"
    )


def jpeg_images(payload: bytes) -> list[bytes]:
    """Split a complete concatenated JPEG stream without accepting trailing bytes."""
    images: list[bytes] = []
    cursor = 0
    while True:
        start = payload.find(b"\xff\xd8", cursor)
        if start < 0:
            break
        end = payload.find(b"\xff\xd9", start + 2)
        if end < 0:
            raise ValueError("pod stream ended inside a JPEG")
        images.append(payload[start : end + 2])
        cursor = end + 2
    if not images or payload[cursor:].strip():
        raise ValueError("pod stream was not a complete JPEG sequence")
    return images


def stream_native_frames(frames: Sequence[int], output_dir: Path) -> list[Path]:
    """Write exact selected native frames streamed from one no-seek pod decode."""
    result = subprocess.run(
        ssh_command(native_frames_command(frames)), check=True, capture_output=True
    )
    images = jpeg_images(result.stdout)
    if len(images) != len(frames):
        raise ValueError("pod stream frame count did not match requested frames")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for frame, image in zip(frames, images):
        path = output_dir / f"frame_{frame:06d}.jpg"
        path.write_bytes(image)
        paths.append(path)
    return paths


def split_native_stream(stream: Path, frames: Sequence[int], output_dir: Path) -> list[Path]:
    """Split an already-streamed selected-frame JPEG sequence into named images."""
    images = jpeg_images(stream.read_bytes())
    if len(images) != len(frames):
        raise ValueError("stream frame count did not match requested frames")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for frame, image in zip(frames, images):
        path = output_dir / f"frame_{frame:06d}.jpg"
        path.write_bytes(image)
        paths.append(path)
    return paths


def crop_image(source: Path, output: Path, bounds: tuple[int, int, int, int]) -> None:
    """Write a bounded crop from a native confirmation image."""
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(source)
    left, top, right, bottom = bounds
    height, width = image.shape[:2]
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError("crop must be nonempty and inside the source image")
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), image[top:bottom, left:right]):
        raise OSError(output)


def normalise_line(line: Sequence[float]) -> np.ndarray:
    """Scale a homogeneous image or world line to unit normal length."""
    value = np.asarray(line, dtype=float)
    scale = float(np.hypot(value[0], value[1]))
    if value.shape != (3,) or scale == 0.0:
        raise ValueError("line must have a nonzero two-dimensional normal")
    return value / scale


def line_homography(world_lines: Sequence[Sequence[float]], image_lines: Sequence[Sequence[float]]) -> tuple[np.ndarray, float]:
    """Solve world-to-image homography from four homogeneous line correspondences."""
    if len(world_lines) != 4 or len(image_lines) != 4:
        raise ValueError("exactly four line correspondences are required")
    rows: list[np.ndarray] = []
    for world, image in zip(world_lines, image_lines):
        w = normalise_line(world)
        i = normalise_line(image)
        skew = np.array([[0.0, -i[2], i[1]], [i[2], 0.0, -i[0]], [-i[1], i[0], 0.0]])
        rows.extend(np.kron(w.reshape(1, 3), skew))
    design = np.asarray(rows)
    _, singular, right = np.linalg.svd(design)
    dual = right[-1].reshape(3, 3, order="F")
    if abs(np.linalg.det(dual)) < 1e-12:
        raise ValueError("dual line homography is singular")
    homography = np.linalg.inv(dual).T
    homography /= homography[2, 2]
    return homography, float(singular[0] / singular[-1])


def vanishing_point(first: Sequence[float], second: Sequence[float]) -> np.ndarray:
    """Return the homogeneous intersection of an image-line pair."""
    point = np.cross(normalise_line(first), normalise_line(second))
    if np.hypot(point[0], point[1]) == 0.0 and point[2] == 0.0:
        raise ValueError("identical lines have no unique vanishing point")
    return point / np.linalg.norm(point)


def line_angle_degrees(first: Sequence[float], second: Sequence[float]) -> float:
    """Return the acute angle between two image-line normals in degrees."""
    a, b = normalise_line(first), normalise_line(second)
    cosine = float(np.clip(abs(np.dot(a[:2], b[:2])), -1.0, 1.0))
    return float(np.degrees(np.arccos(cosine)))
