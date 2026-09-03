"""Focused regression for G137's deterministic non-head sample and joint cells."""
from scripts.platformkit.g137_qualifying_frame_scale import SEED, joint_distribution, seeded_samples


def test_g137_draws_unique_seeded_temporal_strata_and_keeps_zero_cells() -> None:
    inventory = [
        {"source_clip": "ncaa_basketball__fixture.mp4", "clip": "ncaa_basketball__fixture", "frame_count": "120", "width": "640", "height": "360"},
        {"source_clip": "wnba__fixture.mp4", "clip": "wnba__fixture", "frame_count": "120", "width": "640", "height": "360"},
    ]
    first, second = seeded_samples(inventory), seeded_samples(inventory)
    assert first == second
    assert all(row["seed"] == str(SEED) for row in first)
    assert len(first) == 24
    assert len({(row["clip"], row["frame_index"]) for row in first}) == 24
    assert joint_distribution([{"roles_detected": "0"}, {"roles_detected": "4"}]) == [
        {"roles_detected": "0", "frames": "1"}, {"roles_detected": "1", "frames": "0"},
        {"roles_detected": "2", "frames": "0"}, {"roles_detected": "3", "frames": "0"},
        {"roles_detected": "4", "frames": "1"},
    ]
