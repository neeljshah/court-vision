"""Focused tests for the G243b row-local high-school seed harness."""
from scripts.platformkit.tracking import g243b_amateur_seed_gate as subject


def test_high_school_contract_and_two_fixed_label_sets():
    assert (subject.LENGTH_FT, subject.WIDTH_FT, subject.LANE_FT) == (84.0, 50.0, 12.0)
    assert subject.SEED_FRAME == 2760
    assert set(subject.LABEL_SETS) == {"clustered", "spread"}
    assert all(len(values["labels_px"]) == 3 for values in subject.LABEL_SETS.values())


def test_full_court_model_contains_centre_circle_and_both_paints():
    lines = subject.court_lines()
    assert len(lines) == 15
    assert tuple(lines[0][2]) == (50.0, 84.0)
    assert tuple(lines[4][0]) == (31.0, 42.0)
