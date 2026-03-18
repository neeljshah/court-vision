"""
tracking_pipeline.py — Thin CLI wrapper around unified_pipeline.py.

Functions
---------
    run_tracking(video_path, game_id, output_csv)  -> dict
    batch_tracking(video_dir, game_id_map)         -> list[dict]

The wrapper never imports OpenCV or any tracking library directly —
all heavy imports live inside unified_pipeline. This keeps test imports
fast and allows the pipeline to be exercised without a GPU.

Manifest
--------
Each completed run appends an entry to ``data/tracking_results.json``:
    {
        "game_id": str,
        "video_path": str,
        "output_csv": str,
        "rows": int,           # rows written to output_csv
        "frames": int,
        "players": int,
        "status": "ok" | "error",
        "error": str | null,
        "timestamp": ISO-8601 str,
    }
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA_DIR   = os.path.join(PROJECT_DIR, "data")
_MANIFEST   = os.path.join(_DATA_DIR, "tracking_results.json")

_UNIFIED_MODULE = os.path.join(PROJECT_DIR, "src", "pipeline", "unified_pipeline.py")


# ── Manifest helpers ──────────────────────────────────────────────────────────

def _load_manifest() -> List[dict]:
    """Load existing manifest or return empty list."""
    if os.path.exists(_MANIFEST):
        try:
            with open(_MANIFEST, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []
    return []


def _save_manifest(entries: List[dict]) -> None:
    """Persist manifest to disk."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_MANIFEST, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)


def _append_manifest(entry: dict) -> None:
    """Append a single run entry to the manifest."""
    entries = _load_manifest()
    entries.append(entry)
    _save_manifest(entries)


# ── CSV result reader ─────────────────────────────────────────────────────────

def _read_csv_stats(csv_path: str) -> dict:
    """Return row/frame/player counts from a tracking CSV without pandas."""
    rows = frames = players = 0
    frame_set: set = set()
    player_set: set = set()
    if not os.path.exists(csv_path):
        return {"rows": 0, "frames": 0, "players": 0}
    try:
        import csv
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows += 1
                if "frame" in row:
                    frame_set.add(row["frame"])
                if "player_id" in row:
                    player_set.add(row["player_id"])
        frames  = len(frame_set)
        players = len(player_set)
    except Exception:
        pass
    return {"rows": rows, "frames": frames, "players": players}


# ── Public API ────────────────────────────────────────────────────────────────

def run_tracking(
    video_path: str,
    game_id: str,
    output_csv: Optional[str] = None,
    max_frames: Optional[int] = None,
) -> dict:
    """
    Run the full tracking pipeline on a single video clip.

    Delegates to ``unified_pipeline.py`` via a subprocess call so the
    caller process is never polluted with OpenCV/YOLO imports.  The
    function then reads back the CSV written by the pipeline and returns
    a summary manifest entry.

    Args:
        video_path: Absolute or relative path to the .mp4 clip.
        game_id:    NBA game ID string (e.g. '0022401001').
        output_csv: Destination CSV path.  Defaults to
                    ``data/tracking_data.csv`` (unified_pipeline default).
        max_frames: Hard cap on frames processed (passed as --frames to
                    unified_pipeline).  ``None`` means process all frames.

    Returns:
        Manifest entry dict (see module docstring for schema).
        ``status`` is ``"ok"`` on success, ``"error"`` on failure.

    Notes:
        - No video is processed if ``video_path`` does not exist.
        - Subprocess stdout/stderr is captured; set env var
          ``TRACKING_DEBUG=1`` to stream it to the terminal instead.
    """
    if output_csv is None:
        output_csv = os.path.join(_DATA_DIR, "tracking_data.csv")

    entry: dict = {
        "game_id":    game_id,
        "video_path": video_path,
        "output_csv": output_csv,
        "rows":       0,
        "frames":     0,
        "players":    0,
        "status":     "error",
        "error":      None,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    }

    if not os.path.exists(video_path):
        entry["error"] = f"Video not found: {video_path}"
        _append_manifest(entry)
        return entry

    cmd = [
        sys.executable,
        _UNIFIED_MODULE,
        "--video",   video_path,
        "--game-id", game_id,
        "--output",  output_csv,
        "--no-show",  # always headless when called from pipeline
    ]
    if max_frames is not None:
        cmd += ["--frames", str(max_frames)]

    debug = os.environ.get("TRACKING_DEBUG", "").strip() == "1"
    pipe  = None if debug else subprocess.PIPE

    try:
        proc = subprocess.run(
            cmd,
            stdout=pipe,
            stderr=pipe,
            timeout=3600,   # 1-hour hard cap per clip
        )
        if proc.returncode != 0:
            stderr_text = (proc.stderr.decode(errors="replace")
                           if proc.stderr else "")
            entry["error"] = f"unified_pipeline exit {proc.returncode}: {stderr_text[:400]}"
        else:
            stats = _read_csv_stats(output_csv)
            entry.update(stats)
            entry["status"] = "ok"
    except subprocess.TimeoutExpired:
        entry["error"] = "Timeout after 3600 s"
    except Exception as exc:
        entry["error"] = str(exc)

    _append_manifest(entry)
    return entry


def batch_tracking(
    video_dir: str,
    game_id_map: Dict[str, str],
) -> List[dict]:
    """
    Run tracking on every clip in ``video_dir`` that has an entry in
    ``game_id_map``.

    Args:
        video_dir:   Directory containing .mp4 clip files.
        game_id_map: Mapping of filename (no path) → game_id string.
                     Only files present in this map are processed.

    Returns:
        List of manifest entry dicts, one per clip attempted.
        Files not in ``game_id_map`` are silently skipped.

    Example:
        results = batch_tracking(
            "data/videos/",
            {"game_001.mp4": "0022401001", "game_002.mp4": "0022401002"},
        )
    """
    results: List[dict] = []
    if not os.path.isdir(video_dir):
        return results

    for filename in sorted(os.listdir(video_dir)):
        if not filename.lower().endswith(".mp4"):
            continue
        if filename not in game_id_map:
            continue
        video_path = os.path.join(video_dir, filename)
        game_id    = game_id_map[filename]
        result     = run_tracking(video_path, game_id)
        results.append(result)

    return results


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Tracking pipeline wrapper")
    ap.add_argument("--video",    required=True, help="Path to video clip")
    ap.add_argument("--game-id",  required=True, help="NBA game ID")
    ap.add_argument("--output",   default=None,  help="Output CSV path")
    args = ap.parse_args()

    entry = run_tracking(args.video, args.game_id, args.output)
    print(json.dumps(entry, indent=2))
