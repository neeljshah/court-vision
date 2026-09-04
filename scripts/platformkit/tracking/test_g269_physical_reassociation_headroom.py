from scripts.platformkit.tracking.g269_physical_reassociation_headroom import (
    MAX_SPEED_FTPS,
    _summary,
    reassociate,
    reproduce_baseline,
)


def _row(track_id, frame, x):
    return {
        "track_id": track_id, "source_frame": frame, "foot_x_px": float(x),
        "foot_y_px": 0.0, "court_x_ft": float(x), "court_y_ft": 0.0,
        "finite": True, "nearest_previous_id_changed": False,
    }


def test_reassociation_keeps_feasible_edges_and_starts_only_infeasible_boxes():
    frames = [
        {"source_frame": 19599, "detections": [_row(9, 19599, 0), _row(3, 19599, 20)]},
        {"source_frame": 19600, "detections": [_row(3, 19600, 1), _row(9, 19600, 100)]},
    ]
    reassociated = reassociate(frames)
    first, second = reassociated[0]["detections"], reassociated[1]["detections"]
    assert [row["track_id"] for row in first] == [0, 1]
    assert second[0]["track_id"] == 0
    assert second[1]["track_id"] == 2
    assert second[0]["emitted_track_id"] == 3
    assert MAX_SPEED_FTPS == 40.0
    assert _summary(reassociated)["implausible_steps_strictly_over_40_ft_per_s"] == 0


def test_baseline_requires_the_named_g267_counts():
    frames = [{"source_frame": 1, "detections": [_row(1, 1, 0)]}]
    try:
        reproduce_baseline(frames)
    except RuntimeError as exc:
        assert "G267 baseline mismatch" in str(exc)
    else:
        raise AssertionError("a non-G267 fixture must not pass baseline reproduction")
