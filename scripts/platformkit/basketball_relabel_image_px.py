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

_REASON = "no_court_calibration_sidecar"
_BACKUP_SUFFIX = ".pre_relabel"
CALIBRATION_REASON = getattr(
    coordinate_provenance, "CALIBRATION_REASON", "coordinate_calibration_reason"
)
_OUTPUT_SCHEMA = ("frame", "track_id", "cls", "x", "y", CALIBRATION_REASON)


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


def _image_pixel_rows(rows: pd.DataFrame) -> pd.DataFrame:
    """Keep raw detection pixels and discard all derived court-like fields."""
    required = {"frame", "player_id", "x_position", "y_position"}
    missing = sorted(required - set(rows.columns))
    if missing:
        raise ValueError("source rows missing columns: {}".format(", ".join(missing)))
    image_rows = pd.DataFrame({
        "frame": rows["frame"],
        "track_id": rows["player_id"],
        "cls": "player",
        "x": rows["x_position"],
        "y": rows["y_position"],
    })
    image_rows = stamp_image_space_rows(image_rows)
    image_rows[CALIBRATION_REASON] = _REASON
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


def main() -> int:
    """Run the one-time migration and print a machine-readable audit table."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracking-root", type=Path, default=Path("data/tracking"))
    args = parser.parse_args()
    for result in relabel_all(args.tracking_root):
        print(asdict(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
