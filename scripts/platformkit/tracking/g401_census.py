"""Census, draw, and window arithmetic for G401.

Pure functions over receipt text. Nothing here opens a video, touches the pod,
or reads a production path.
"""
from __future__ import annotations

import math
from pathlib import Path

SHADOW_FPS_LOW = 59.0
SHADOW_FPS_HIGH = 61.0
MIN_SPAN_SECONDS = 100.0
DRAW_SIZE = 30
# Fixed before the draw. avg_frame_rate is duration-derived and drifts from the
# container r_frame_rate by well under a tenth of a frame; the strict gate is the
# decoded-PTS constant-rate check, not this reader-agreement tolerance.
READER_TOLERANCE_FPS = 0.1


def parse_rate(text: str | None) -> float | None:
    """Parse an ffprobe rational rate; return None when it is not positive."""
    if not text or "/" not in text:
        return None
    num, den = text.split("/", 1)
    try:
        value = float(num) / float(den)
    except (ValueError, ZeroDivisionError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def validated_fps(avg_rate: str | None, r_rate: str | None) -> tuple[float | None, str]:
    """Cross-validate two independent ffprobe readers of the native rate."""
    avg = parse_rate(avg_rate)
    r_value = parse_rate(r_rate)
    if avg is None or r_value is None:
        return None, "UNKNOWN_READER"
    if abs(avg - r_value) > READER_TOLERANCE_FPS:
        return None, "READER_DISAGREEMENT"
    return r_value, "TWO_READER_AGREEMENT"


def split_name(name: str) -> tuple[str, str, int]:
    """Split a corpus file name into competition, game and section keys."""
    stem = name[:-4] if name.endswith(".mp4") else name
    competition, _, rest = stem.partition("__")
    game, _, section = rest.rpartition("_s")
    try:
        index = int(section)
    except ValueError:
        index = -1
    return competition, game, index


def load_probe(path: Path) -> list[dict]:
    """Read the pod probe table into typed rows."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        name = parts[0]
        fps, basis = validated_fps(parts[1], parts[2])
        competition, game, section = split_name(name)
        rows.append({
            "name": name, "competition": competition, "game": game,
            "section": section, "avg_frame_rate": parts[1],
            "r_frame_rate": parts[2], "nb_frames": int(parts[3]) if parts[3].isdigit() else None,
            "stream_duration_s": float(parts[4]) if parts[4] not in ("", "None") else None,
            "width": int(parts[5]), "height": int(parts[6]), "codec": parts[7],
            "format_duration_s": float(parts[8]) if parts[8] not in ("", "None") else None,
            "bytes": int(parts[10]), "mtime_epoch": int(parts[11]),
            "validated_fps": fps, "fps_basis": basis,
        })
    return rows


def load_digests(path: Path) -> dict[str, str]:
    """Read a sha256sum output file into {name: digest}."""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition("  ")
        out[name.strip()] = digest.strip()
    return out


def shadow_population(rows: list[dict], digests: dict[str, str]) -> list[dict]:
    """Retained native 59-61 fps sections with at least a 100 s span."""
    keep = []
    for row in rows:
        fps = row["validated_fps"]
        span = row["stream_duration_s"] or 0.0
        if fps is None or not (SHADOW_FPS_LOW <= fps <= SHADOW_FPS_HIGH):
            continue
        if span < MIN_SPAN_SECONDS or row["name"] not in digests:
            continue
        item = dict(row)
        item["digest"] = digests[row["name"]]
        keep.append(item)
    keep.sort(key=lambda r: (r["competition"], r["game"], r["section"], r["digest"]))
    return keep


def even_draw(population: list[dict], size: int = DRAW_SIZE) -> list[dict]:
    """Sealed even draw: floor(j*(N-1)/(size-1)+0.5), no replacement."""
    count = len(population)
    if count < size:
        raise ValueError("population %d smaller than draw %d" % (count, size))
    picked = []
    seen = set()
    for j in range(size):
        index = int(math.floor(j * (count - 1) / (size - 1) + 0.5))
        if index in seen:
            raise ValueError("even draw collided at j=%d index=%d" % (j, index))
        seen.add(index)
        item = dict(population[index])
        item["draw_j"] = j
        item["draw_index"] = index
        picked.append(item)
    return picked
