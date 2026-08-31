"""Capture and verify local video provenance for tracking runs."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.platformkit.io_atomic import append_jsonl_atomic
from scripts.platformkit.tracking_harness import SPORTS


PROVENANCE_PATH = Path("data/tracking_reports/provenance.jsonl")
_HASH_CHUNK_BYTES = 8 * 1024 * 1024
_PROVENANCE_LOCK = threading.Lock()


def _git_revision() -> str:
    """Return the current repository revision, or ``unknown``."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        revision = (result.stdout or "").strip()
        return revision or "unknown"
    except Exception:
        return "unknown"


def _video_details(path: Path) -> tuple[str, int, dict[str, int] | None, float | None]:
    """Return hash, byte size, resolution, and FPS for a local video."""
    if not path.is_file():
        return "missing", 0, None, None

    digest = hashlib.sha256()
    try:
        with path.open("rb") as video_file:
            for chunk in iter(lambda: video_file.read(_HASH_CHUNK_BYTES), b""):
                digest.update(chunk)
        size_bytes = path.stat().st_size
    except OSError:
        return "missing", 0, None, None
    resolution: dict[str, int] | None = None
    fps: float | None = None
    try:
        import cv2

        capture = cv2.VideoCapture(str(path))
        try:
            if capture.isOpened():
                width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps_value = float(capture.get(cv2.CAP_PROP_FPS))
                if width > 0 and height > 0:
                    resolution = {"width": width, "height": height}
                if fps_value > 0:
                    fps = fps_value
        finally:
            capture.release()
    except Exception:
        pass
    return digest.hexdigest(), size_bytes, resolution, fps


def record_provenance(
    game_id: str,
    sport: str,
    source_url: str,
    video_path: str | Path,
    adapter_module: str,
) -> dict[str, Any]:
    """Append one evidence manifest row for a downloaded video."""
    path = Path(video_path)
    sha256, size_bytes, resolution, fps = _video_details(path)
    revision = _git_revision()
    row: dict[str, Any] = {
        "game_id": game_id,
        "sport": sport,
        "source_url": source_url,
        "video_path": str(path),
        "sha256": sha256,
        "size_bytes": size_bytes,
        "resolution": resolution,
        "fps": fps,
        "capture_ts": datetime.now(timezone.utc).isoformat(),
        "adapter_module": adapter_module,
        "adapter_version": revision,
        "harness_version": revision,
        "thresholds_snapshot": copy.deepcopy(SPORTS.get(sport.lower())),
    }
    with _PROVENANCE_LOCK:
        append_jsonl_atomic(PROVENANCE_PATH, row)
    return row


def verify_provenance(game_id: str) -> dict[str, Any] | None:
    """Return the most recently stored manifest row for ``game_id``."""
    if not PROVENANCE_PATH.is_file():
        return None
    for line in reversed(PROVENANCE_PATH.read_text(encoding="utf-8").splitlines()):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("game_id") == game_id:
            return row
    return None


__all__ = ["record_provenance", "verify_provenance"]
