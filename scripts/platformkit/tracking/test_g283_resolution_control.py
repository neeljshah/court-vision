from scripts.platformkit.tracking.g283_resolution_control import SAMPLE_SIZE, canonical_hash, select_evenly, two_proportion


def test_even_frame_bin_sample_has_one_raw_box_per_bin():
    rows = [{"source_frame": frame, "track_id": 4, "foot_x_px": 1.0, "foot_y_px": 2.0}
            for frame in range(19599, 23400)]
    sample = select_evenly(rows)
    assert len(sample) == SAMPLE_SIZE
    assert [row["frame_bin"] for row in sample] == list(range(1, SAMPLE_SIZE + 1))


def test_commitment_is_canonical_and_test_is_symmetric():
    assert canonical_hash([{"a": 1, "b": 2}]) == canonical_hash([{"b": 2, "a": 1}])
    assert two_proportion(43, 25)["z"] == -two_proportion(25, 43)["z"]
