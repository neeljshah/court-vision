"""Tests for the soccer S1 extension packet builder (no video/network needed)."""
import hashlib
import json

from scripts.platformkit.soccer_s1_ext_packet import split_counts, write_manifest


def test_split_counts_sums_to_total_and_stays_even() -> None:
    counts = split_counts(64, 3)
    assert sum(counts) == 64
    assert counts == [22, 21, 21]
    assert max(counts) - min(counts) <= 1


def test_frame_ids_start_after_the_sealed_36_and_never_collide() -> None:
    original_ids = {"S1_%04d" % n for n in range(1, 37)}
    ext_ids = ["S1_%04d" % n for n in range(37, 37 + 64)]
    assert len(ext_ids) == len(set(ext_ids)) == 64
    assert not (set(ext_ids) & original_ids)
    assert ext_ids[0] == "S1_0037"
    assert ext_ids[-1] == "S1_0100"


def test_manifest_records_matching_sha_of_the_sealed_csv(tmp_path) -> None:
    sealed = tmp_path / "detector_counts_separate_ext.csv"
    sealed.write_text("frame_id,clip,raw_boxes,distinct_track_ids\nS1_0037,x,5,3\n", encoding="ascii")
    result = {
        "frame_ids": ["S1_0037"],
        "clips": ["x"],
        "sealed_csv_sha256": hashlib.sha256(sealed.read_bytes()).hexdigest(),
    }
    write_manifest(tmp_path, seed=20260901, videos=[tmp_path / "x.mp4"], result=result)
    manifest = json.loads((tmp_path / "manifest_ext_2026-09-01.json").read_text(encoding="ascii"))
    assert manifest["sealed_csv_sha256"] == hashlib.sha256(sealed.read_bytes()).hexdigest()
    assert manifest["seed"] == 20260901
    assert manifest["frame_id_count"] == 1
