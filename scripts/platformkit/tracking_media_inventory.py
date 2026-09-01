"""Read-only resolution inventory and conservative refresh-manifest planner.

This never deletes, moves, downloads, or queues footage.  It makes old source
quality visible and emits an auditable manifest whose new game ids preserve the
pre-refresh tracking corpus for before/after comparison.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


VIDEO_SUFFIXES = {".avi", ".mkv", ".mov", ".mp4", ".webm"}
MIN_REFRESH_HEIGHT = 720
DEFAULT_REFRESH_PER_HOUR = 2


def probe_media(path: Path) -> dict[str, Any]:
    """Return observed video metadata, with nulls when ffprobe cannot read it."""
    command = ["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height,r_frame_rate,bit_rate",
               "-of", "json", str(path)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   check=False, timeout=30)
        stream = json.loads(completed.stdout).get("streams", [{}])[0]
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        stream = {}
    rate = str(stream.get("r_frame_rate", ""))
    try:
        numerator, denominator = rate.split("/", 1)
        fps = float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        fps = None
    return {"width": stream.get("width"), "height": stream.get("height"),
            "frame_rate": fps, "bit_rate": _integer(stream.get("bit_rate")),
            "path": str(path)}


def _integer(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _identity(path: Path) -> tuple[str, str]:
    prefix, separator, game_id = path.stem.partition("__")
    return (prefix, game_id) if separator else ("unknown", path.stem)


def inventory(footage_dir: Path) -> list[dict[str, Any]]:
    """Inventory video files by observed dimensions, bitrate, and source fps."""
    rows = []
    for path in sorted(footage_dir.glob("*")):
        if not path.is_file() or path.suffix.lower() not in VIDEO_SUFFIXES:
            continue
        sport, game_id = _identity(path)
        row = probe_media(path)
        row.update({"sport": sport, "game_id": game_id,
                    "legacy_low_resolution": bool(
                        row["height"] is not None and row["height"] < MIN_REFRESH_HEIGHT)})
        rows.append(row)
    return rows


def tracking_rows(tracking_dir: Path, game_id: str) -> int:
    """Count persisted rows without loading a potentially large CSV."""
    path = tracking_dir / game_id / "tracking_data.csv"
    try:
        with path.open(encoding="utf-8") as handle:
            return max(0, sum(1 for _ in handle) - 1)
    except OSError:
        return 0


def refresh_manifest(rows: list[dict[str, Any]], tracking_dir: Path,
                     min_rows: int = 500) -> list[dict[str, Any]]:
    """Plan superseding refreshes, retaining each predecessor under its old id."""
    candidates = []
    for row in rows:
        existing_rows = tracking_rows(tracking_dir, str(row["game_id"]))
        if not row["legacy_low_resolution"] or existing_rows < min_rows:
            continue
        height = int(row["height"])
        candidates.append({
            "sport": row["sport"], "supersedes_game_id": row["game_id"],
            "refresh_game_id": "{}__refresh_720p".format(row["game_id"]),
            "source_resolution": "{}x{}".format(row["width"], height),
            "source_bit_rate": row["bit_rate"], "existing_tracking_rows": existing_rows,
            "action": "redownload_at_720p_or_higher_then_track_under_refresh_game_id",
        })
    return sorted(candidates, key=lambda row: (-row["existing_tracking_rows"],
                                                 row["sport"], row["supersedes_game_id"]))


def render(rows: list[dict[str, Any]], manifest: list[dict[str, Any]]) -> str:
    """Render a compact ASCII report suitable for logs and review."""
    lines = ["GAME SPORT RESOLUTION FPS BITRATE_BPS LEGACY_360P"]
    for row in rows:
        resolution = "{}x{}".format(row["width"], row["height"])
        fps = "NA" if row["frame_rate"] is None else "{:.3f}".format(row["frame_rate"])
        lines.append("{} {} {} {} {} {}".format(
            row["game_id"], row["sport"], resolution, fps,
            row["bit_rate"] if row["bit_rate"] is not None else "NA",
            "yes" if row["legacy_low_resolution"] else "no"))
    lines.append("refresh_candidates={} rate_limit_per_hour={}".format(
        len(manifest), DEFAULT_REFRESH_PER_HOUR))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory footage resolution and plan safe refreshes.")
    parser.add_argument("--footage-dir", type=Path, default=Path("data/footage_bridge"))
    parser.add_argument("--tracking-dir", type=Path, default=Path("data/tracking"))
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    rows = inventory(args.footage_dir)
    manifest = refresh_manifest(rows, args.tracking_dir)
    print(render(rows, manifest))
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps({"schema_version": 1,
            "policy": {"min_height": MIN_REFRESH_HEIGHT,
                       "max_refreshes_per_hour": DEFAULT_REFRESH_PER_HOUR,
                       "preserve_predecessor": True}, "candidates": manifest},
            indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("manifest_written={}".format(args.manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
