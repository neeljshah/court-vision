"""Integration check for the fixed G229 native-frame diagnostic."""
from scripts.platformkit.tracking.g229_keypoint_gate_funnel import GATE_1, GATE_2, GATE_NAMES, run


def test_g229_reproduces_g227_and_accounts_for_every_construct_frame():
    summary = run()
    assert summary["control"] == {"abstentions": 17, "all_four_g205": 0, "corners_g205": 0}
    assert summary["frames"] == 17
    assert sum(summary["first_reject_distribution"].values()) == 17
    assert set(summary["first_reject_distribution"]) == set(GATE_NAMES)
    assert summary["first_reject_distribution"] == {GATE_1: 1, GATE_2: 16, GATE_NAMES[2]: 0, GATE_NAMES[3]: 0}
