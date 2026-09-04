from scripts.platformkit.tracking.g275_footage_census import (
    FRAME_COUNT,
    SAMPLE_SIZE,
    blind_plan,
    rejudge_plan,
    uniform_indices,
)


def test_g275_centred_uniform_sample_is_fixed_unique_and_clip_wide() -> None:
    indices = uniform_indices()
    assert len(indices) == SAMPLE_SIZE
    assert len(set(indices)) == SAMPLE_SIZE
    assert indices[0] == 484
    assert indices[-1] == 173_945
    gaps = [right - left for left, right in zip(indices, indices[1:])]
    assert set(gaps) == {969, 970}
    assert all(0 <= index < FRAME_COUNT for index in indices)
    first = blind_plan(indices)
    second = blind_plan(indices)
    assert first == second
    assert [item.blind_id for item in first] == list(range(SAMPLE_SIZE))
    assert {item.source_frame for item in first} == set(indices)


def test_g275_rejudge_is_a_fixed_fresh_40_frame_permutation() -> None:
    order = rejudge_plan()
    assert len(order) == 40
    assert len(set(order)) == 40
    assert order == rejudge_plan()
    assert all(0 <= blind_id < SAMPLE_SIZE for blind_id in order)
