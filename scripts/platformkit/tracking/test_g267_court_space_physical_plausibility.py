from scripts.platformkit.tracking.g267_court_space_physical_plausibility import analyze, local_scale, PUBLISHED_H


def test_local_scale_is_position_dependent_and_bounds_pixel_error():
    near = local_scale(PUBLISHED_H, (25.0, 0.0))
    middle = local_scale(PUBLISHED_H, (25.0, 47.0))
    assert near["principal_scale_ft_per_px_min"] > 0.0
    assert middle["principal_scale_ft_per_px_max"] != near["principal_scale_ft_per_px_max"]
    assert near["error_19px_ft_range"][1] > near["error_5px_ft_range"][1]


def test_analysis_retains_outside_rows_and_marks_same_id_speed_steps():
    frames = [
        {"detections": [{"track_id": 1, "source_frame": 1, "foot_x_px": 1., "foot_y_px": 1., "court_x_ft": 0., "court_y_ft": 0., "finite": True, "nearest_previous_id_changed": False},
                        {"track_id": 2, "source_frame": 1, "foot_x_px": 2., "foot_y_px": 2., "court_x_ft": 60., "court_y_ft": 1., "finite": True, "nearest_previous_id_changed": False}]},
        {"detections": [{"track_id": 1, "source_frame": 2, "foot_x_px": 200., "foot_y_px": 1., "court_x_ft": 2., "court_y_ft": 0., "finite": True, "nearest_previous_id_changed": True},
                        {"track_id": 2, "source_frame": 2, "foot_x_px": 2., "foot_y_px": 2., "court_x_ft": 60., "court_y_ft": 1., "finite": True, "nearest_previous_id_changed": False}]},
    ]
    report = analyze(frames)
    assert report["denominator"]["all_finite_detector_box_feet"] == 4
    assert report["in_court"]["inside_rows"] == 2
    assert report["speed_ft_per_s"]["implausible_steps"] == 1
    assert report["attribution"]["nearest_previous_id_changed_among_implausible"] == 1
    assert report["attribution"]["implausible_with_pixel_jump_counts"]["100"] == 1
