from scripts.platformkit.tracking.g273_detector_precision_blind_sample import blind_order, select_evenly


def test_all_detection_sample_uses_each_frame_bin_without_id_or_speed_filtering():
    rows = [{"source_frame": frame, "track_id": 1, "foot_x_px": 2.0, "foot_y_px": 3.0,
             "court_x_ft": 4.0, "court_y_ft": 5.0} for frame in range(100, 220)]
    sample = select_evenly(rows, sample_size=12)
    assert [row["frame_bin"] for row in sample] == list(range(1, 13))
    assert len({row["source_frame"] for row in sample}) == 12
    ordered = blind_order(sample)
    assert sorted(row["blind_index"] for row in ordered) == list(range(1, 13))
