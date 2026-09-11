"""G397 source probing: measured width/height/fps rationals, digests, decoded PTS."""
from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g397_census import classify_format, sha256_file

STREAM_FIELDS = ("width", "height", "avg_frame_rate", "r_frame_rate", "time_base",
                 "codec_name", "nb_frames", "duration", "start_time")

__all__ = ["rational", "probe_object", "decoded_pts_census", "probe_directory",
           "source_filename"]


def rational(text: Any) -> float | None:
    """Return a measured rational frame rate as a float, never inferred from a label."""
    if text in (None, "", "0/0"):
        return None
    try:
        return float(Fraction(str(text)))
    except (ValueError, ZeroDivisionError):
        return None


def source_filename(sport: str, game_id: str) -> str:
    """Return the corpus/bridge filename convention <sport>__<game_id>.mp4."""
    return "%s__%s.mp4" % (sport, game_id)


def probe_object(path: Path) -> dict[str, Any]:
    """Probe one candidate object for raw stream metadata plus its byte digest."""
    path = Path(path)
    row: dict[str, Any] = {"path": str(path).replace("\\", "/"), "probe_status": "UNKNOWN"}
    if not path.is_file():
        row["probe_status"] = "ABSENT"
        return row
    stat = path.stat()
    row["bytes"] = stat.st_size
    try:
        raw = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=" + ",".join(STREAM_FIELDS) + ":format=duration,format_name",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        row["probe_status"] = "PROBE_ERROR"
        row["probe_error"] = type(exc).__name__
        return row
    if raw.returncode != 0:
        row["probe_status"] = "PROBE_ERROR"
        row["probe_error"] = "ffprobe_rc_%d" % raw.returncode
        return row
    parsed = json.loads(raw.stdout or "{}")
    streams = parsed.get("streams") or [{}]
    stream, fmt = streams[0], parsed.get("format") or {}
    for field in STREAM_FIELDS:
        row[field] = stream.get(field)
    row["format_duration"] = fmt.get("duration")
    row["format_name"] = fmt.get("format_name")
    row["avg_fps"] = rational(stream.get("avg_frame_rate"))
    row["r_fps"] = rational(stream.get("r_frame_rate"))
    row["fps"] = row["avg_fps"] if row["avg_fps"] is not None else row["r_fps"]
    row["sha256"] = sha256_file(path)
    row["probe_status"] = "OK"
    row["format_kind"] = classify_format(row)
    return row


def decoded_pts_census(path: Path, limit: int | None = None) -> dict[str, Any]:
    """Decode the video stream and account for every decoded presentation timestamp."""
    path = Path(path)
    if not path.is_file():
        return {"pts_status": "ABSENT"}
    command = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "frame=pts_time", "-of", "csv=p=0", str(path)]
    if limit:
        command[2:2] = ["-read_intervals", "%%+#%d" % limit]
    try:
        raw = subprocess.run(command, capture_output=True, text=True, timeout=1800)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"pts_status": "PTS_ERROR", "pts_error": type(exc).__name__}
    if raw.returncode != 0:
        return {"pts_status": "PTS_ERROR", "pts_error": "ffprobe_rc_%d" % raw.returncode}
    values: list[float] = []
    for token in raw.stdout.split():
        token = token.strip().rstrip(",")
        try:
            values.append(float(token))
        except ValueError:
            continue
    if not values:
        return {"pts_status": "PTS_EMPTY", "decoded_pts_frames": 0}
    span = values[-1] - values[0]
    return {"pts_status": "OK", "decoded_pts_frames": len(values),
            "pts_first": values[0], "pts_last": values[-1], "pts_elapsed": span,
            "pts_implied_fps": None if span <= 0 else (len(values) - 1) / span}


def probe_directory(directory: Path, pattern: str = "*.mp4") -> list[dict[str, Any]]:
    """Probe every candidate object currently present in one caller-named directory."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    rows = []
    for path in sorted(directory.glob(pattern)):
        row = probe_object(path)
        row["directory"] = str(directory).replace("\\", "/")
        row["filename"] = path.name
        rows.append(row)
    return rows
