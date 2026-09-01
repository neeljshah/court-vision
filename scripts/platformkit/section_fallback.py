"""Validate section resolution and cut a native full download locally."""
from __future__ import annotations

import subprocess
from pathlib import Path


MIN_SECTION_HEIGHT = 720


def video_height(video: Path) -> int:
    """Return a video's measured pixel height, or zero if probing fails."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=height", "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, check=True, timeout=60)
        return int((result.stdout or "").strip().splitlines()[0])
    except (subprocess.SubprocessError, OSError, ValueError, IndexError):
        return 0


def section_seconds(section: str) -> tuple[int, int]:
    """Parse the bridge's ``*HH:MM:SS-HH:MM:SS`` section syntax."""
    try:
        start_text, end_text = section.lstrip("*").split("-", 1)
        to_seconds = lambda value: sum(
            int(unit) * multiplier
            for unit, multiplier in zip(value.split(":"), (3600, 60, 1)))
        start, end = to_seconds(start_text), to_seconds(end_text)
    except (AttributeError, ValueError):
        raise ValueError("invalid section: %s" % section)
    if end <= start:
        raise ValueError("invalid section: %s" % section)
    return start, end - start


def cut_full_download(full_video: Path, destination: Path, section: str) -> Path:
    """Copy one requested range from a full native download into destination."""
    start, duration = section_seconds(section)
    temporary = destination.with_name(destination.stem + ".section" + destination.suffix)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start),
         "-t", str(duration), "-i", str(full_video), "-map", "0", "-c", "copy",
         "-avoid_negative_ts", "make_zero", str(temporary)],
        check=True, capture_output=True, text=True, timeout=900)
    if not temporary.is_file() or temporary.stat().st_size == 0:
        raise RuntimeError("ffmpeg reported success but produced no section")
    full_video.unlink()
    temporary.replace(destination)
    return destination
