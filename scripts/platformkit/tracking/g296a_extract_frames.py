"""Extract the preregistered native frames for the G296A locator pass."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Sequence


SOURCE_FRAME_COUNT = 174_429
SAMPLE_COUNT = 24
SOURCE_PATH = Path("data/videos/bridge/wnba_01.f137.mp4")
LOCATED_PLAYERS_HEADER = (
    "source_frame",
    "person_index",
    "role",
    "feet_visible",
    "foot_x_px",
    "foot_y_px",
    "confidence",
    "note",
)
FRAMES_HEADER = (
    "source_frame",
    "court_visible",
    "shot_description",
    "players_located",
)


def required_frame_indices() -> tuple[int, ...]:
    """Return the 24 fixed source-frame indices for the independent pass."""
    return tuple(round(index * SOURCE_FRAME_COUNT / (SAMPLE_COUNT - 1)) for index in range(SAMPLE_COUNT))


def probe_source(source: Path) -> dict[str, str]:
    """Read the binding stream identity fields with ffprobe."""
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,avg_frame_rate:format=duration",
        "-of",
        "json",
        str(source),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    stream = payload["streams"][0]
    return {
        "width": str(stream["width"]),
        "height": str(stream["height"]),
        "avg_frame_rate": str(stream["avg_frame_rate"]),
        "duration": str(payload["format"]["duration"]),
    }


def validate_identity(identity: dict[str, str]) -> None:
    """Raise when the local source differs from the mandated stream identity."""
    expected = {
        "width": "1920",
        "height": "1080",
        "avg_frame_rate": "30/1",
        "duration": "5814.333333",
    }
    if identity != expected:
        raise ValueError(f"SOURCE MISMATCH: expected {expected}, got {identity}")


def ffmpeg_command(source: Path, output_dir: Path) -> list[str]:
    """Build the single-pass, exact-frame ffmpeg command."""
    terms = "+".join(f"eq(n\\,{frame})" for frame in required_frame_indices())
    return [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-i",
        str(source),
        "-vf",
        f"select='{terms}'",
        "-vsync",
        "0",
        "-q:v",
        "2",
        str(output_dir / "frame_%02d.jpg"),
    ]


def extract(source: Path, output_dir: Path) -> tuple[int, ...]:
    """Validate then extract exactly the preregistered frames at native resolution."""
    validate_identity(probe_source(source))
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(ffmpeg_command(source, output_dir), check=True)
    outputs = sorted(output_dir.glob("frame_*.jpg"))
    if len(outputs) != SAMPLE_COUNT:
        raise RuntimeError(f"expected {SAMPLE_COUNT} JPEGs, found {len(outputs)}")
    return required_frame_indices()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local CPU-only extractor."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE_PATH)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/evidence/tracking/g296a_located_players_artifact/frames"),
    )
    args = parser.parse_args(argv)
    indices = extract(args.source, args.output_dir)
    print("G296A extracted source frames: " + ",".join(str(index) for index in indices))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
