from scripts.platformkit.tracking.g278_census_followup import (
    G275_SPAN_INDICES,
    PART_A_SIZE,
    SPAN_END,
    SPAN_START,
    span_indices,
    two_proportion,
    wilson_interval,
)


def test_g278_part_a_sample_is_new_uniform_and_within_study_span() -> None:
    indices = span_indices()
    assert len(indices) == PART_A_SIZE == 61
    assert len(set(indices)) == 61
    assert SPAN_START <= min(indices) <= max(indices) <= SPAN_END
    assert not G275_SPAN_INDICES.intersection(indices)
    assert set(right - left for left, right in zip(indices, indices[1:])) == {62, 63}


def test_g278_two_proportion_and_interval_have_named_fixed_denominators() -> None:
    stats = two_proportion(60, 60, 118, 180)
    assert stats["pooled_p"] == 178 / 240
    assert stats["z"] > 0
    assert 0 < stats["p_two_sided_nominal"] < 1
    lower, upper = wilson_interval(60, 60)
    assert 0 < lower < upper <= 1
