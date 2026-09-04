"""Build a high-resolution, evenly spaced court-corner survey contact sheet."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import cv2
import numpy as np


REMOTE_HOST = "config.pod"
REMOTE_VIDEO = "/workspace/nba-ai-system/data/footage_corpus/basketball__amateur_jh3fnwMi7dM.mp4"
SURVEY_SIZE = (640, 360)


def remote_survey_command(stride: int) -> list[str]:
    """Return a no-seek remote command for evenly spaced frames."""
    if stride < 1:
        raise ValueError("stride must be positive")
    width, height = SURVEY_SIZE
    remote = (
        "ffmpeg -hide_banner -loglevel error -i " + REMOTE_VIDEO +
        " -vf 'select=not(mod(n\\," + str(stride) + ")),scale=" +
        str(width) + ":" + str(height) + "' -vsync 0 -f rawvideo -pix_fmt bgr24 pipe:1"
    )
    return ["ssh", REMOTE_HOST, remote]


def write_contact_sheet(stride: int, output: Path) -> int:
    """Write every selected frame in an indexed contact sheet."""
    result = subprocess.run(remote_survey_command(stride), check=True, stdout=subprocess.PIPE)
    width, height = SURVEY_SIZE
    bytes_per_frame = width * height * 3
    if not result.stdout or len(result.stdout) % bytes_per_frame:
        raise RuntimeError("survey decode did not contain complete frames")
    count = len(result.stdout) // bytes_per_frame
    frames = np.frombuffer(result.stdout, dtype=np.uint8).reshape(count, height, width, 3)
    tiles = []
    for index, frame in enumerate(frames):
        tile = frame.copy()
        cv2.putText(tile, "frame " + str(index * stride), (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
        tiles.append(tile)
    columns = 4
    while len(tiles) % columns:
        tiles.append(np.zeros_like(tiles[0]))
    sheet = np.vstack([np.hstack(tiles[index:index + columns])
                       for index in range(0, len(tiles), columns)])
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), sheet, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise OSError("could not write contact sheet")
    return count


def write_local_probe_sheet(video: Path, output: Path, samples: int = 12) -> int:
    """Write evenly spaced labelled frames from a downloaded probe section."""
    if samples < 1:
        raise ValueError("samples must be positive")
    capture = cv2.VideoCapture(str(video))
    decoded_count = 0
    while True:
        ok, _ = capture.read()
        if not ok:
            break
        decoded_count += 1
    capture.release()
    if decoded_count < 1:
        raise RuntimeError("probe has no decodable frames")
    indices = np.linspace(0, decoded_count - 1, num=min(samples, decoded_count), dtype=int)
    tiles = []
    wanted = iter(indices.tolist())
    target = next(wanted, None)
    capture = cv2.VideoCapture(str(video))
    for current in range(decoded_count):
        ok, frame = capture.read()
        if not ok:
            capture.release()
            raise RuntimeError("could not sequentially decode probe frame " + str(current))
        if current != target:
            continue
        tile = cv2.resize(frame, SURVEY_SIZE)
        cv2.putText(tile, "local frame " + str(current), (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
        tiles.append(tile)
        target = next(wanted, None)
        if target is None:
            break
    capture.release()
    if len(tiles) != len(indices):
        raise RuntimeError("probe ended before every selected frame decoded")
    columns = 4
    while len(tiles) % columns:
        tiles.append(np.zeros_like(tiles[0]))
    sheet = np.vstack([np.hstack(tiles[index:index + columns])
                       for index in range(0, len(tiles), columns)])
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), sheet, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise OSError("could not write probe contact sheet")
    return len(indices)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stride", type=int, default=60)
    parser.add_argument("--local-video", type=Path)
    parser.add_argument("--samples", type=int, default=12)
    args = parser.parse_args()
    if args.local_video:
        count = write_local_probe_sheet(args.local_video, args.output, args.samples)
        print("G249_PROBE_FRAMES=" + str(count))
    else:
        print("G249_SURVEY_FRAMES=" + str(write_contact_sheet(args.stride, args.output)))


if __name__ == "__main__":
    main()
