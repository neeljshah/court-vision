"""Hand-pinned fixed-box checks for G345 ARM_C."""
from pathlib import Path

from scripts.platformkit.tracking.g345_associate import (
    RECONNECT_AGE, assert_identical_digests, associate_arm_c, detection_digest,
    read_detection_csv, simultaneous_merges,
)
from scripts.platformkit.tracking import g345_inject
from scripts.platformkit.tracking.g345_inject import apply_crossing, apply_gap


def _det(frame: int, name: str, x: float) -> dict:
    return {"section": "s", "frame": frame, "score": 0.9,
            "bbox": [x, 20.0, x + 20.0, 60.0], "obs_key": f"s:{frame:06d}:{name}"}


def test_arm_c_generation_ids_reconnects_gap_and_does_not_merge_crossing() -> None:
    # Three fixed tracks: A has a sealed three-frame gap; B and C exchange positions
    # for five frames. No visual or appearance value is supplied to the associator.
    source = []
    for frame in range(8):
        source.extend([_det(frame, "A", float(frame)), _det(frame, "B", 40.0 + frame),
                       _det(frame, "C", 100.0 - frame)])
    digest = detection_digest(source)
    assert assert_identical_digests(digest, digest, digest) == digest
    gap = {"removed_keys": [f"s:{frame:06d}:A" for frame in (2, 3, 4)]}
    crossing = {"left_keys": [f"s:{frame:06d}:B" for frame in range(2, 7)],
                "right_keys": [f"s:{frame:06d}:C" for frame in range(2, 7)]}
    altered = apply_crossing(apply_gap(source, gap), crossing)
    records = associate_arm_c(altered, generation="sealed")
    ids = {row["obs_key"]: row["track_id"] for row in records}
    assert ids["s:000001:A"] == ids["s:000005:A"]
    assert ids["s:000001:A"].startswith("s:sealed:")
    assert simultaneous_merges(records) == 0
    assert len(records) == len(altered)


def test_stride_three_reader_keeps_source_frames_for_association_and_injections() -> None:
    csv_path = Path(__file__).with_name("fixtures") / "g345_stride3_source_frames.csv"
    association_rows = read_detection_csv(csv_path)
    injection_rows = g345_inject.read_detection_csv(csv_path)
    for rows in (association_rows, injection_rows):
        assert [row["frame"] for row in rows] == list(range(540, 571, 3))
        assert [row["obs_key"] for row in (rows[0], rows[-1])] == [
            "stride3:000540:000000", "stride3:000570:000010"]
        assert [row["tick"] for row in rows] == list(range(11))
        assert [row["tick_stride"] for row in rows] == [3] * 11
    assert association_rows[-1]["frame"] - association_rows[0]["frame"] == RECONNECT_AGE
    assert association_rows[-1]["tick"] - association_rows[0]["tick"] == RECONNECT_AGE // 3
    records = associate_arm_c(association_rows, generation="source_frames")
    assert records[0]["track_id"] == records[-1]["track_id"]
