"""Relabel unregistered basketball detections as image-pixel teacher data.

This migration is deliberately fail-closed: each output must be rejected by
the frozen tracking harness because source pixels are not court coordinates.
"""
from __future__ import annotations

import argparse
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from scripts.platformkit import coordinate_provenance
from scripts.platformkit.coordinate_provenance import stamp_image_space_rows, write_tracking_csv
from scripts.platformkit.tracking_harness import evaluate
from scripts.platformkit.tracking_schema import copy_ball_telemetry_declaration

_REASON = "no_court_calibration_sidecar"
_BACKUP_SUFFIX = ".pre_relabel"
CALIBRATION_REASON = getattr(
    coordinate_provenance, "CALIBRATION_REASON", "coordinate_calibration_reason"
)
_OUTPUT_SCHEMA = ("frame", "track_id", "cls", "x", "y", CALIBRATION_REASON,
                  "map2d_x", "map2d_y")
_BBOX_COLUMNS = ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2")


@dataclass(frozen=True)
class RelabelResult:
    """One basketball corpus file's before/after harness result."""

    path: str
    sport: str
    rows: int
    frames: int
    verdict_before: str
    verdict_after: str
    failures_before: list[str]
    failures_after: list[str]


def basketball_tracking_csvs(tracking_root: Path) -> list[Path]:
    """Return only the WNBA and NCAA tracking files in deterministic order."""
    return sorted(
        path for path in tracking_root.glob("*/tracking_data.csv")
        if path.parent.name.startswith(("wnba", "ncaa"))
    )


def sport_for(path: Path) -> str:
    """Keep the WNBA harness label distinct from NCAA basketball."""
    return "wnba" if path.parent.name.startswith("wnba") else "basketball"


def _image_pixel_rows(rows: pd.DataFrame, width: int | None = None,
                      height: int | None = None) -> pd.DataFrame:
    """Emit SOURCE-PLANE detection pixels; the map_2d canvas keeps its own name.

    ``x_position``/``y_position`` are NOT image pixels.  The tracker warps the
    source foot point through ``M1 @ (M @ kpt)`` into the minimap canvas and
    stores only the warped point (src/tracking/advanced_tracker.py:1426-1428 and
    :627-640); the pipeline copies it straight into ``x_position``
    (src/pipeline/unified_pipeline.py:2697-2698).  The only source-plane values
    that survive to CSV are ``bbox_x1..bbox_y2``, so ``x``/``y`` are the bbox
    foot point -- bottom-edge midpoint, the same point the tracker warped --
    and the canvas rides in ``map2d_x``/``map2d_y`` under its own honest name.

    A row whose bbox is missing has no source-plane evidence at all and is
    dropped rather than filled.
    """
    required = {"frame", "player_id", "x_position", "y_position"}.union(_BBOX_COLUMNS)
    missing = sorted(required - set(rows.columns))
    if missing:
        raise ValueError("source rows missing columns: {}".format(", ".join(missing)))
    bbox = {name: pd.to_numeric(rows[name], errors="coerce") for name in _BBOX_COLUMNS}
    image_rows = pd.DataFrame({
        "frame": rows["frame"],
        "track_id": rows["player_id"],
        "cls": "player",
        "x": (bbox["bbox_x1"] + bbox["bbox_x2"]) / 2.0,
        "y": bbox["bbox_y2"],
        "map2d_x": rows["x_position"],
        "map2d_y": rows["y_position"],
    })
    image_rows = image_rows[image_rows["x"].notna() & image_rows["y"].notna()]
    image_rows = stamp_image_space_rows(image_rows)
    image_rows[CALIBRATION_REASON] = _REASON
    if width is not None and height is not None:
        image_rows["frame_width"] = int(width)
        image_rows["frame_height"] = int(height)
    return image_rows


def _verdict(rows: pd.DataFrame, sport: str, source: Path) -> tuple[str, list[str]]:
    report = evaluate(rows, sport, source=str(source))
    return ("PASS" if report.passed else "FAIL", report.failures)


def restore_backups(paths: list[Path]) -> None:
    """Restore every backed-up corpus file after the pre-registered kill."""
    for path in paths:
        backup = path.with_name(path.name + _BACKUP_SUFFIX)
        if backup.exists():
            shutil.copy2(backup, path)


def relabel_game(path: Path) -> RelabelResult:
    """Back up, relabel, and reject one file if pixels become scorable."""
    source_rows = pd.read_csv(path)
    sport = sport_for(path)
    before, before_failures = _verdict(source_rows, sport, path)
    backup = path.with_name(path.name + _BACKUP_SUFFIX)
    if backup.exists():
        raise FileExistsError("refusing to overwrite existing backup: {}".format(backup))
    shutil.copy2(path, backup)
    relabeled = _image_pixel_rows(source_rows)
    write_tracking_csv(relabeled, path, _OUTPUT_SCHEMA)
    after, after_failures = _verdict(pd.read_csv(path), sport, path)
    if after == "PASS":
        shutil.copy2(backup, path)
        raise RuntimeError("KILL: relabeled image_px rows passed {}; backup restored".format(path))
    return RelabelResult(
        path=str(path), sport=sport, rows=len(source_rows),
        frames=int(source_rows["frame"].nunique()), verdict_before=before,
        verdict_after=after, failures_before=before_failures,
        failures_after=after_failures,
    )


def relabel_all(tracking_root: Path) -> list[RelabelResult]:
    """Relabel every target, restoring all completed files on any kill/error."""
    paths = basketball_tracking_csvs(tracking_root)
    if len(paths) != 11:
        raise RuntimeError("expected 11 basketball files, found {}".format(len(paths)))
    results: list[RelabelResult] = []
    try:
        for path in paths:
            results.append(relabel_game(path))
    except Exception:
        restore_backups(paths)
        raise
    return results


def reemit_game(shipped_csv: Path, nba_csv: Path, video: Path,
                out_csv: Path) -> dict:
    """Rebuild one game in the source plane, into a NEW path. Never overwrites.

    ``shipped_csv`` is what the daemon plus the original relabel produced and is
    only read, to measure containment before the fix.  ``nba_csv`` is the
    NBA-production table that still carries the source-plane bbox columns.
    """
    from scripts.platformkit.tracking.image_px_containment import (
        containment, source_resolution)

    if out_csv.exists():
        raise FileExistsError("refusing to overwrite {}".format(out_csv))
    width, height = source_resolution(str(video))
    fixed = _image_pixel_rows(pd.read_csv(nba_csv, low_memory=False), width, height)
    write_tracking_csv(fixed, out_csv,
                       _OUTPUT_SCHEMA + ("frame_width", "frame_height"))
    copy_ball_telemetry_declaration(shipped_csv, out_csv)
    before = containment(pd.read_csv(shipped_csv, low_memory=False), width, height)
    after = containment(fixed, width, height)
    sport = sport_for(shipped_csv)
    verdict, failures = _verdict(pd.read_csv(out_csv, low_memory=False), sport, out_csv)
    return {"game": shipped_csv.parent.name, "sport": sport,
            "resolution": "{}x{}".format(width, height),
            "rows_before": before.n_rows, "rows_after": after.n_rows,
            "containment_before": before.inside_share,
            "containment_after": after.inside_share,
            "verdict_before": before.verdict, "verdict_after": after.verdict,
            "harness_verdict": verdict, "harness_failures": failures}


def main() -> int:
    """Run the one-time migration and print a machine-readable audit table."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracking-root", type=Path, default=Path("data/tracking"))
    parser.add_argument("--reemit-out", type=Path,
                        help="write source-plane rows here instead of migrating")
    parser.add_argument("--footage-root", type=Path,
                        default=Path("data/footage_corpus"))
    args = parser.parse_args()
    if args.reemit_out:
        for shipped in basketball_tracking_csvs(args.tracking_root):
            game = shipped.parent.name
            sport = "wnba" if game.startswith("wnba") else "ncaa_basketball"
            video = args.footage_root / "{}__{}.mp4".format(sport, game)
            nba_csv = shipped.with_name(shipped.name + _BACKUP_SUFFIX)
            if not video.exists() or not nba_csv.exists():
                print({"game": game, "skipped": "no footage" if not video.exists()
                       else "no pre_relabel source"})
                continue
            out_csv = args.reemit_out / game / "tracking_data.csv"
            print(reemit_game(shipped, nba_csv, video, out_csv))
        return 0
    for result in relabel_all(args.tracking_root):
        print(asdict(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
