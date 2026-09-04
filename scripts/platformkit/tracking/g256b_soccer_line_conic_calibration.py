"""Pod-streamed survey and exact-frame acquisition for G256b evidence only."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import cv2


POD_CONFIG = r"C:\Users\neelj\.ssh\config.pod"
POD_HOST = "pod"
SOURCE = "/workspace/nba-ai-system/data/footage_corpus/soccer__soccer_Z6NTDyxcODs.mp4"


def ssh_command(remote: str) -> list[str]:
    """Build the read-only SSH command used to stream a pod image."""
    return ["ssh.exe", "-F", POD_CONFIG, "-o", "BatchMode=yes", POD_HOST, remote]


def stream_jpeg(remote: str, output: Path) -> None:
    """Stream one JPEG from pod ffmpeg stdout into a local evidence path."""
    result = subprocess.run(ssh_command(remote), check=True, capture_output=True)
    if not result.stdout.startswith(b"\xff\xd8") or not result.stdout.rstrip().endswith(b"\xff\xd9"):
        raise ValueError("pod stream was not a complete JPEG")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result.stdout)


def survey_command(interval_seconds: int) -> str:
    """Return a whole-clip, no-seek contact-sheet ffmpeg command."""
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    return (
        f"ffmpeg -v error -i '{SOURCE}' -vf "
        f"'fps=1/{interval_seconds},scale=384:216,tile=10x10:padding=2:margin=2' "
        "-frames:v 1 -f image2pipe -vcodec mjpeg -"
    )


def exact_frame_command(frame: int) -> str:
    """Return a no-input-seek ffmpeg command for one zero-based source frame."""
    if frame < 0:
        raise ValueError("frame must be non-negative")
    return (
        f"ffmpeg -v error -i '{SOURCE}' -vf 'select=eq(n\\,{frame})' "
        "-frames:v 1 -f image2pipe -vcodec mjpeg -"
    )


def crop_image(image_path: Path, output: Path, left: int, top: int, right: int, bottom: int) -> None:
    """Write an evidence crop after validating its requested image bounds."""
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)
    height, width = image.shape[:2]
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError("crop must be nonempty and inside the source image")
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), image[top:bottom, left:right]):
        raise OSError(output)


def main() -> None:
    """Stream either a contact sheet or one exact decoded frame."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--survey-seconds", type=int)
    group.add_argument("--frame", type=int)
    group.add_argument("--crop", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bounds", type=int, nargs=4, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    args = parser.parse_args()
    if args.crop:
        if args.bounds is None:
            parser.error("--crop requires --bounds")
        crop_image(args.crop, args.output, *args.bounds)
    else:
        if args.bounds is not None:
            parser.error("--bounds is only valid with --crop")
        command = survey_command(args.survey_seconds) if args.survey_seconds else exact_frame_command(args.frame)
        stream_jpeg(command, args.output)
    print("WROTE_JPEG=" + args.output.as_posix())


if __name__ == "__main__":
    main()
