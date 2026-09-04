from scripts.platformkit.tracking.g275_footage_census import (
    FRAME_COUNT,
    SAMPLE_SIZE,
    blind_plan,
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
