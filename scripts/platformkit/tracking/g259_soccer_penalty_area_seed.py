"""Pod-streamed G259 soccer survey and evidence-image utility."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import cv2


POD_CONFIG = r"C:\Users\neelj\.ssh\config.pod"
POD_HOST = "pod"
SOURCE = "/workspace/nba-ai-system/data/footage_corpus/soccer__soccer_Z6NTDyxcODs.mp4"
SURVEY_SECONDS = 5


def ssh_command(remote: str) -> list[str]:
    """Build the batch-mode SSH invocation used for read-only pod streaming."""
    return ["ssh.exe", "-F", POD_CONFIG, "-o", "BatchMode=yes", POD_HOST, remote]


def survey_command(interval_seconds: int = SURVEY_SECONDS) -> str:
    """Return a whole-clip no-seek command producing small chronological panels."""
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    return (
        f"ffmpeg -v error -i '{SOURCE}' -vf "
        f"'fps=1/{interval_seconds},scale=192:108,tile=10x10:padding=2:margin=2' "
        "-f image2pipe -vcodec mjpeg -"
    )


def exact_frame_command(frame: int) -> str:
    """Return a no-input-seek command for one zero-based native source frame."""
    if frame < 0:
        raise ValueError("frame must be non-negative")
    return (
        f"ffmpeg -v error -i '{SOURCE}' -vf 'select=eq(n\\,{frame})' "
        "-frames:v 1 -f image2pipe -vcodec mjpeg -"
    )


def _jpeg_images(payload: bytes) -> list[bytes]:
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


def stream_survey(output_dir: Path, interval_seconds: int = SURVEY_SECONDS) -> list[Path]:
    """Stream small panel JPEGs to committed evidence without pod frame files."""
    result = subprocess.run(
        ssh_command(survey_command(interval_seconds)), check=True, capture_output=True
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, image in enumerate(_jpeg_images(result.stdout), start=1):
        path = output_dir / f"survey_panel_{index:02d}.jpg"
        path.write_bytes(image)
        paths.append(path)
    return paths


def stream_frame(frame: int, output: Path) -> None:
    """Stream one exact native-resolution decoded frame to local evidence."""
    result = subprocess.run(ssh_command(exact_frame_command(frame)), check=True, capture_output=True)
    images = _jpeg_images(result.stdout)
    if len(images) != 1:
        raise ValueError("exact-frame stream did not contain exactly one JPEG")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(images[0])


def crop_image(source: Path, output: Path, bounds: tuple[int, int, int, int]) -> None:
    """Write a validated source-image crop for a named identity feature."""
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


def main() -> None:
    """Provide the minimal evidence operations used by the G259 measurement."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--survey", action="store_true")
    mode.add_argument("--frame", type=int)
    mode.add_argument("--crop", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bounds", type=int, nargs=4, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    args = parser.parse_args()
    if args.survey:
        if args.bounds is not None:
            parser.error("--bounds is only valid with --crop")
        paths = stream_survey(args.output)
        print("WROTE_PANELS=" + str(len(paths)))
    elif args.frame is not None:
        if args.bounds is not None:
            parser.error("--bounds is only valid with --crop")
        stream_frame(args.frame, args.output)
        print("WROTE_JPEG=" + args.output.as_posix())
    else:
        if args.bounds is None:
            parser.error("--crop requires --bounds")
        crop_image(args.crop, args.output, tuple(args.bounds))
        print("WROTE_JPEG=" + args.output.as_posix())


if __name__ == "__main__":
    main()
