from scripts.platformkit.tracking.g276b_unconditioned_step_endpoint_baseline import (
    SAMPLE_SIZE,
    _binary_summary,
    blind_mapping,
    select_evenly,
)


def _steps():
    return [{"source_frame": frame, "prior_source_frame": frame - 1, "emitted_track_id": frame % 11,
             "prior_foot_x_px": 1.0, "prior_foot_y_px": 2.0, "current_foot_x_px": 3.0,
             "current_foot_y_px": 4.0} for frame in range(100, 700)]


def test_selection_spans_time_and_blind_mapping_pools_unrelated_endpoints():
    selected = select_evenly(_steps())
    assert len(selected) == SAMPLE_SIZE
    assert [row["time_bin"] for row in selected] == list(range(1, SAMPLE_SIZE + 1))
    mapping = blind_mapping(selected)
    assert len(mapping) == 2 * SAMPLE_SIZE
    assert sorted(row["blind_index"] for row in mapping) == list(range(1, 2 * SAMPLE_SIZE + 1))
    assert {row["endpoint"] for row in mapping} == {"prior", "current"}


def test_joint_summary_handles_cannot_judge_including_and_excluding_it():
    rows = [{"step_index": "1", "endpoint": "prior", "verdict": "NOT A PERSON"},
            {"step_index": "1", "endpoint": "current", "verdict": "PLAYER"},
            {"step_index": "2", "endpoint": "prior", "verdict": "NOT A PERSON"},
            {"step_index": "2", "endpoint": "current", "verdict": "NOT A PERSON"},
            {"step_index": "3", "endpoint": "prior", "verdict": "CANNOT JUDGE"},
            {"step_index": "3", "endpoint": "current", "verdict": "PLAYER"}]
    assert _binary_summary(rows, True)["steps"] == 3
    assert _binary_summary(rows, False)["steps"] == 2
    assert _binary_summary(rows, False)["table_prior_by_current"] == {"00": 0, "01": 0, "10": 1, "11": 1}
