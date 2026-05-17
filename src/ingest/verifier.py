"""Video verifier: ffprobe-based codec/duration/fps checks."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

FFPROBE_CANDIDATES = [
    "ffprobe",
    "/usr/bin/ffprobe",
    "/usr/local/bin/ffprobe",
    # Windows: conda environments common install locations
    r"C:\ProgramData\anaconda3\Library\bin\ffprobe.exe",
    r"C:\Users\Public\anaconda3\Library\bin\ffprobe.exe",
]

MIN_DURATION = 1800.0
ALLOWED_CODECS = {"h264"}
FPS_MIN = 20.0
FPS_MAX = 61.0
QUARANTINE_DIR = Path(__file__).parents[2] / "data" / "videos" / "full_games_av1_quarantine"


def _find_ffprobe() -> Optional[str]:
    for candidate in FFPROBE_CANDIDATES:
        if shutil.which(candidate):
            return candidate
        p = Path(candidate)
        if p.exists():
            return str(p)
    return None


def probe(video_path: Path) -> Dict:
    """Run ffprobe and return stream metadata dict."""
    ffprobe = _find_ffprobe()
    if ffprobe is None:
        raise RuntimeError("ffprobe not found — install ffmpeg or activate basketball_ai conda env")

    cmd = [
        ffprobe, "-v", "quiet", "-print_format", "json",
        "-show_streams", "-show_format", str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffprobe timed out on {video_path}")

    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr.strip()}")

    data = json.loads(result.stdout)
    video_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    if not video_streams:
        raise RuntimeError("No video stream found")

    vs = video_streams[0]
    fmt = data.get("format", {})

    # Parse fps from avg_frame_rate "30/1" or "30000/1001"
    fps_str = vs.get("avg_frame_rate", "0/1")
    try:
        num, den = fps_str.split("/")
        fps = float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        fps = 0.0

    return {
        "codec": vs.get("codec_name", "unknown"),
        "duration_s": float(fmt.get("duration") or vs.get("duration") or 0),
        "fps": fps,
        "has_video": True,
        "width": vs.get("width"),
        "height": vs.get("height"),
    }


def verify(video_path: Path) -> Tuple[bool, Optional[str], Dict]:
    """
    Returns (ok, reject_reason, probe_data).
    If not ok, caller should quarantine the file.
    """
    try:
        info = probe(video_path)
    except RuntimeError as exc:
        return False, str(exc), {}

    reasons = []
    if info["duration_s"] < MIN_DURATION:
        reasons.append(f"duration {info['duration_s']:.0f}s < {MIN_DURATION:.0f}s")
    if info["codec"] not in ALLOWED_CODECS:
        reasons.append(f"codec={info['codec']} not in {ALLOWED_CODECS}")
    if not (FPS_MIN <= info["fps"] <= FPS_MAX):
        reasons.append(f"fps={info['fps']:.1f} outside [{FPS_MIN},{FPS_MAX}]")

    if reasons:
        return False, "; ".join(reasons), info
    return True, None, info


def quarantine(video_path: Path, reason: str) -> Path:
    """Move file to quarantine dir atomically. Returns new path."""
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    dest = QUARANTINE_DIR / video_path.name
    video_path.rename(dest)
    return dest
