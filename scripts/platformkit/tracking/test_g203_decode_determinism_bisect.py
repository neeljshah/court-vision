"""Focused tests for G203's measurement-only comparison helpers."""

from scripts.platformkit.tracking.g203_decode_determinism_bisect import (
    compare_runs,
    decoder_summary,
)


def _record(digest: str = "a", frame_index: int = 0) -> dict[str, object]:
    return {"frames": [{"frame_index": frame_index, "sha256": digest, "decoder": "pyav"}]}


def test_compare_runs_reports_count_and_first_differing_frame() -> None:
    comparison = compare_runs([_record(), _record("b"), _record("c")])
    assert comparison["per_frame_hash_sequences_identical_across_three_runs"] is False
    assert comparison["per_run"][0]["hashes_differ_from_run_1"] == 0
    assert comparison["per_run"][1]["first_differing_frame_index"] == 0


def test_decoder_summary_detects_mid_run_change() -> None:
    summary = decoder_summary([
        {"decoder": "pyav"}, {"decoder": "pyav"}, {"decoder": "decord"},
    ])
    assert summary["decoder_path_changed_mid_run"] is True
    assert summary["decoder_path_change_count"] == 1
