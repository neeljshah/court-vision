"""Decode frame-exact remote amateur frames for G243c point-identity review."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import cv2
import numpy as np


REMOTE_HOST = "config.pod"
REMOTE_VIDEO = "/workspace/nba-ai-system/data/footage_corpus/basketball__amateur_jh3fnwMi7dM.mp4"
IMAGE_SIZE = (1280, 720)


def remote_decode_command(frame: int) -> list[str]:
    """Return the frame-exact remote ffmpeg command without input-side seeking."""
    if frame < 0:
        raise ValueError("frame must be non-negative")
    remote = (
        "ffmpeg -hide_banner -loglevel error -i " + REMOTE_VIDEO +
        " -vf 'select=eq(n\\," + str(frame) + ")' -vsync 0 -frames:v 1 "
        "-f rawvideo -pix_fmt bgr24 pipe:1"
    )
    return ["ssh", REMOTE_HOST, remote]


def decode_remote_frame_exact(frame: int) -> np.ndarray:
    """Decode one zero-based remote frame through ffmpeg select=eq(n,N)."""
    result = subprocess.run(remote_decode_command(frame), check=True, stdout=subprocess.PIPE)
    width, height = IMAGE_SIZE
    expected = width * height * 3
    if len(result.stdout) != expected:
        raise RuntimeError(f"frame {frame}: expected {expected} BGR bytes, got {len(result.stdout)}")
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape(height, width, 3).copy()


def remote_survey_command(stride: int) -> list[str]:
    """Return a low-resolution whole-clip survey command; it does not seek."""
    if stride < 1:
        raise ValueError("stride must be positive")
    remote = (
        "ffmpeg -hide_banner -loglevel error -i " + REMOTE_VIDEO +
        " -vf 'select=not(mod(n\\," + str(stride) + ")),scale=320:180' "
        "-vsync 0 -f rawvideo -pix_fmt bgr24 pipe:1"
    )
    return ["ssh", REMOTE_HOST, remote]


def write_survey_contact_sheet(stride: int, output: Path) -> int:
    """Write a labelled survey contact sheet from evenly spaced decoded frames."""
    result = subprocess.run(remote_survey_command(stride), check=True, stdout=subprocess.PIPE)
    pixels_per_frame = 320 * 180 * 3
    if len(result.stdout) == 0 or len(result.stdout) % pixels_per_frame:
        raise RuntimeError("survey decode did not contain complete 320x180 frames")
    count = len(result.stdout) // pixels_per_frame
    frames = np.frombuffer(result.stdout, dtype=np.uint8).reshape(count, 180, 320, 3)
    tiles = []
    for index, frame in enumerate(frames):
        tile = frame.copy()
        cv2.putText(tile, f"frame {index * stride}", (5, 18), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45, (0, 0, 255), 1, cv2.LINE_AA)
        tiles.append(tile)
    columns = 5
    while len(tiles) % columns:
        tiles.append(np.zeros_like(tiles[0]))
    sheet = np.vstack([np.hstack(tiles[index:index + columns])
                       for index in range(0, len(tiles), columns)])
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), sheet):
        raise OSError(f"could not write {output}")
    return count


def write_exact_frame(frame: int, output: Path) -> None:
    """Write an exact decoded frame for pre-fit visual point-identity review."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), decode_remote_frame_exact(frame)):
        raise OSError(f"could not write {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--survey-stride", type=int)
    args = parser.parse_args()
    if args.survey_stride:
        count = write_survey_contact_sheet(args.survey_stride, args.output)
        print("G243C_SURVEY_FRAMES=" + str(count))
    else:
        write_exact_frame(args.frame, args.output)
        print("G243C_FRAME=" + str(args.frame))


if __name__ == "__main__":
    main()
