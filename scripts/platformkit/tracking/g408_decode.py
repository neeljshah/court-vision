"""G408 presentation-timestamp decode and source rehash (PC, CPU only).

Reads the retained G401 originals read-only, rehashes every byte, and records
the decoded presentation schedule with ffprobe.  Two independent readers are
kept: the decoded frame schedule (``frames``) that the production route would
see, and the container packet schedule (``packets``) in presentation order.
Nothing here opens a production route, a model, or a pod job.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

FRAME_READER = "ffprobe.frame.best_effort_timestamp_time"
PACKET_READER = "ffprobe.packet.pts_time"


def sha256_file(path: Path) -> tuple[str, int]:
    """Return ``(sha256, bytes)`` for one retained original."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _ffprobe(args: list[str], path: Path) -> list[str]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          *args, "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return [line.strip().rstrip(",") for line in out.stdout.splitlines()
            if line.strip().rstrip(",")]


def decode_frame_pts(path: Path) -> list[float | None]:
    """Decoded presentation schedule; ``None`` marks an unusable timestamp."""
    rows = _ffprobe(["-show_entries", "frame=best_effort_timestamp_time"], path)
    return [None if row in ("N/A", "") else float(row) for row in rows]


def packet_pts(path: Path) -> list[float]:
    """Container packet timestamps sorted into presentation order."""
    rows = _ffprobe(["-show_entries", "packet=pts_time"], path)
    return sorted(float(row) for row in rows if row not in ("N/A", ""))


def stream_probe(path: Path) -> dict[str, str]:
    """Native stream description used for the source receipt."""
    keys = ("width", "height", "avg_frame_rate", "r_frame_rate", "codec_name",
            "nb_read_frames", "duration")
    rows = _ffprobe(["-show_entries",
                     "stream=width,height,avg_frame_rate,r_frame_rate,"
                     "codec_name,duration"], path)
    parts = rows[0].split(",") if rows else []
    order = ("codec_name", "width", "height", "duration", "r_frame_rate",
             "avg_frame_rate")
    out = {key: "" for key in keys}
    for name, value in zip(order, parts):
        out[name] = value
    return out


def schedule_stats(pts: list[float | None]) -> dict[str, object]:
    """Anomaly census over one decoded schedule."""
    valid = [value for value in pts if value is not None]
    duplicates = sum(1 for i in range(1, len(valid)) if valid[i] == valid[i - 1])
    backwards = sum(1 for i in range(1, len(valid)) if valid[i] < valid[i - 1])
    steps = [valid[i] - valid[i - 1] for i in range(1, len(valid))]
    positive = [step for step in steps if step > 0]
    median = sorted(positive)[len(positive) // 2] if positive else 0.0
    gaps = sum(1 for step in steps if step > 1.5 * median) if median else 0
    dropped = 0
    if median:
        dropped = sum(int(round(step / median)) - 1 for step in steps
                      if step > 1.5 * median)
    return {"pts_count": len(pts), "valid_count": len(valid),
            "missing_count": len(pts) - len(valid),
            "duplicate_pts_steps": duplicates, "backwards_steps": backwards,
            "gap_steps": gaps, "dropped_frames": dropped,
            "median_step_s": median,
            "first_pts": valid[0] if valid else None,
            "last_pts": valid[-1] if valid else None,
            "monotonic": backwards == 0}


def harvest(source_dir: Path, names: list[str], cache_dir: Path) -> list[dict]:
    """Rehash and decode every drawn name; cache schedules under ``cache_dir``."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    receipts = []
    for name in names:
        path = source_dir / name
        digest, size = sha256_file(path)
        target = cache_dir / (name + ".frames.json")
        if target.exists():
            frames = json.loads(target.read_text())
        else:
            frames = decode_frame_pts(path)
            target.write_text(json.dumps(frames), newline="\n")
        stats = schedule_stats(frames)
        receipt = {"source_name": name, "source_path": str(path),
                   "sha256": digest, "bytes": size,
                   "frame_reader": FRAME_READER, "packet_reader": PACKET_READER,
                   **stream_probe(path), **stats}
        receipts.append(receipt)
    return receipts


def write_csv(rows: list[dict], path: Path, fields: list[str]) -> str:
    """Write one LF CSV and return its sha256."""
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})
    return hashlib.sha256(path.read_bytes()).hexdigest()
