"""G372 phase-A sampling and denominator tests -- the three the att1 REJECT named."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.platformkit.tracking import g372_phase_a as phase_a
from scripts.platformkit.tracking import g372_window as window

SEED = "1547d32d82d5909bb43a8f5f6d82d5f4b76c5e6d145121cc5563e0a3a8945efe"


def _manifest(tmp_path: Path) -> Path:
    """One collectable attempt plus two retained failures, as the seal requires."""
    source = tmp_path / "fiba-video__demo_s01.mp4"
    source.write_bytes(b"not a real video, but real bytes")
    rows = [
        {"index": 0, "game_id": "demo_s01", "sport": "fiba-video",
         "first_claim_utc": "2026-09-10T17:00:00Z", "location": "CORPUS",
         "src_path": str(source), "src_bytes": source.stat().st_size, "copy_status": "OK",
         "reason": "", "scratch_path": str(source), "scratch_bytes": source.stat().st_size},
        {"index": 3, "game_id": "demo_s02", "sport": "fiba-video",
         "first_claim_utc": "2026-09-10T17:10:00Z", "location": "GONE", "src_path": "",
         "src_bytes": "UNKNOWN", "copy_status": "BYTES_GONE", "reason": "no file under any store",
         "scratch_path": "", "scratch_bytes": "UNKNOWN"},
        {"index": 6, "game_id": "demo_s03", "sport": "fiba-video",
         "first_claim_utc": "2026-09-10T17:20:00Z", "location": "CORPUS",
         "src_path": "/gone/x.mp4", "src_bytes": "UNKNOWN", "copy_status": "ERROR_OSError",
         "reason": "copy failed", "scratch_path": "", "scratch_bytes": "UNKNOWN"},
    ]
    target = tmp_path / "collect_manifest.csv"
    with target.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(window.MANIFEST_FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    return target


class _Args:
    def __init__(self, manifest: Path, out: Path, scratch: Path) -> None:
        self.manifest, self.out, self.scratch = str(manifest), str(out), str(scratch)
        self.deploy_manifest = "d" * 64


def test_g372_even_sampler_is_never_a_head_slice() -> None:
    k, start, indices = phase_a.even_sample(149, SEED)
    assert k == 3 and start < k
    assert indices[:len(indices)] != list(range(len(indices)))
    assert indices[-1] >= 149 - k
    assert len(set(indices)) == len(indices)
    assert all(later - earlier == k for earlier, later in zip(indices, indices[1:]))


def test_g372_small_window_samples_every_attempt() -> None:
    assert phase_a.even_sample(12, SEED) == (1, 0, list(range(12)))


def test_g372_coverage_denominator_counts_failed_attempts(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    phase_a.cmd_exercise(_Args(_manifest(tmp_path), out, tmp_path / "scratch"))
    summary = json.loads((out / "summary.json").read_text(encoding="ascii"))
    assert summary["coverage"]["sampled_attempts"] == 3
    assert summary["coverage"]["sidecars_committed"] == 1
    assert summary["independent_agreement"]["n"] == 3
    assert summary["independent_agreement"]["joined_rows"] == 1
    assert summary["failure_classes"]["BYTES_GONE"] == 1
    assert summary["failure_classes"]["ERROR_OSError"] == 1


def test_g372_failed_attempt_is_left_joined_with_its_status(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    phase_a.cmd_exercise(_Args(_manifest(tmp_path), out, tmp_path / "scratch"))
    with (out / "join.csv").open(encoding="ascii", newline="") as handle:
        joins = {row["game_id"]: row for row in csv.DictReader(handle)}
    assert set(joins) == {"demo_s01", "demo_s02", "demo_s03"}
    assert joins["demo_s02"]["status"] == "BYTES_GONE"
    assert joins["demo_s03"]["status"] == "ERROR_OSError"
    assert joins["demo_s02"]["agreement"] == "False"
