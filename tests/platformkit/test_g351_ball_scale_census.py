"""G351 construct tests: additive range census, fixed rescale, and prereg seal."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from scripts.platformkit.tracking.g351_ball_scale_census import main


def _write(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def _clip(root: Path, game: str) -> None:
    clip = root / game; clip.mkdir()
    player_fields = ["frame", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "source_width", "source_height"]
    ball_fields = ["frame", "ball_x2d", "ball_y2d", "detected", "source_width", "source_height"]
    _write(clip / "tracking_data.csv", player_fields, [
        {"frame": 1, "bbox_x1": 100, "bbox_y1": 100, "bbox_x2": 200, "bbox_y2": 200, "source_width": 1280, "source_height": 720},
        {"frame": 2, "bbox_x1": 200, "bbox_y1": 200, "bbox_x2": 300, "bbox_y2": 300, "source_width": 1280, "source_height": 720},
    ])
    _write(clip / "ball_tracking.csv", ball_fields, [
        {"frame": 1, "ball_x2d": 1000, "ball_y2d": 1000, "detected": 1, "source_width": 1280, "source_height": 720},
        {"frame": 2, "ball_x2d": 2000, "ball_y2d": 2000, "detected": 1, "source_width": 1280, "source_height": 720},
    ])


def test_census_marks_scale_anomaly_and_rejoin_uses_fixed_affine_rule(tmp_path: Path) -> None:
    root = tmp_path / "tracking"; root.mkdir()
    for game in ("0022500630", "0022500906", "0022500799"): _clip(root, game)
    ranges, rejoin = tmp_path / "ranges.csv", tmp_path / "rejoin.csv"
    assert main(["--tracking-root", str(root), "--ranges", str(ranges), "--rejoin", str(rejoin)]) == 0
    range_rows = list(csv.DictReader(ranges.open(encoding="utf-8", newline="")))
    assert len(range_rows) == 3 and {row["anomalous"] for row in range_rows} == {"1"}
    assert {row["ball_frame"] for row in range_rows} <= {"original", "crop", "detector", "panorama"}
    joined = list(csv.DictReader(rejoin.open(encoding="utf-8", newline="")))
    assert len(joined) == 3
    assert {(row["before_within_radius"], row["after_within_radius"]) for row in joined} == {("000000", "000002")}


def test_prereg_seal_hashes_lf_normalized_bytes_above_seal() -> None:
    path = Path("docs/evidence/tracking/g351_prereg_2026-09-08.md")
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    above, seal = raw.rsplit(b"SEAL sha256 ", 1)
    assert hashlib.sha256(above).hexdigest() == seal.strip().decode("ascii")
