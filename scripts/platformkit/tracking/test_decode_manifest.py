"""Focused anti-tautology tests for per-decoded-frame manifests."""
import csv

import pytest

from scripts.platformkit.tracking.decode_manifest import build_decode_manifest


def _csv(tmp_path, frames):
    path = tmp_path / "tracking.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("frame", "track_id"))
        writer.writeheader()
        for frame in frames:
            writer.writerow({"frame": frame, "track_id": "player"})
    return path


def test_tautology_guard_uses_decoded_frames_not_emitted_rows(tmp_path):
    manifest = build_decode_manifest(100, _csv(tmp_path, [4, 23, 88]))
    summary = manifest.summary
    assert (summary.decoded, summary.solved, summary.unsolved, summary.non_play) == (100, 3, 97, 0)
    assert summary.completeness == pytest.approx(0.03)
    assert summary.completeness < 0.95


def test_non_play_callback_cannot_change_the_decoded_row_count(tmp_path):
    manifest = build_decode_manifest(6, _csv(tmp_path, [0, 1, 2]), lambda index: index in {1, 4})
    summary = manifest.summary
    assert [row.status for row in manifest.rows] == ["solved", "non_play", "solved", "unsolved", "non_play", "unsolved"]
    assert (summary.decoded, summary.solved, summary.unsolved, summary.non_play) == (6, 2, 2, 2)
    assert summary.completeness == pytest.approx(0.5)


def test_compound_hook_preserves_independent_solved_accuracy(tmp_path):
    summary = build_decode_manifest(4, _csv(tmp_path, [0, 1])).summary
    compound = summary.with_accuracy(0.8)
    assert compound.accuracy_on_solved_frames == 0.8
    assert compound.completeness_times_accuracy == pytest.approx(0.4)
