from scripts.platformkit.tracking.g281_identity_purity_one_second import (
    GAP, PER_ID_CAP, SAMPLE_SIZE, select_evenly, wilson,
)


def _pairs():
    return [{"first_source_frame": frame, "second_source_frame": frame + GAP,
             "emitted_track_id": (frame // 4) % 80} for frame in range(100, 700)]


def test_selection_uses_all_time_bins_and_honors_id_cap_without_outcome_fields():
    selected = select_evenly(_pairs())
    assert len(selected) == SAMPLE_SIZE
    assert [row["time_bin"] for row in selected] == list(range(1, SAMPLE_SIZE + 1))
    assert max(sum(row["emitted_track_id"] == track for row in selected) for track in range(80)) <= PER_ID_CAP


def test_wilson_interval_has_no_sampled_pair_denominator_fallback():
    assert wilson(0, 0) is None
    lower, upper = wilson(48, 60)
    assert round(lower, 6) == 0.682182
    assert round(upper, 6) == 0.881715
