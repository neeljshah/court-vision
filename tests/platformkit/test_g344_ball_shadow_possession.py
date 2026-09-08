"""Focused construct tests for the G344 abstaining shadow-possession state."""
from scripts.platformkit.tracking.ball_shadow_possession import shadow_states
from scripts.platformkit.tracking.g344_synthetic import case, evaluate


def test_sealed_200_case_construct_exact_matches_known_truth() -> None:
    rows = evaluate()
    assert len(rows) == 200
    assert {row["pass"] for row in rows} == {"000001"}
    assert {row["kind"] for row in rows} == {
        "valid", "cut", "missing", "duplicate", "motion_disagreement"}


def test_prefix_invariance_cut_stop_and_stale_age() -> None:
    _, players, balls, _, _, _ = case(0)
    short = shadow_states(players, balls, 0, 3, 720)
    long = shadow_states(players, balls, 0, 6, 720)
    assert short == long[:4]

    _, players, balls, cuts, _, _ = case(1)
    cut_result = shadow_states(players, balls, 0, 3, 720, cuts)[-1]
    assert cut_result["owner_id"] == ""
    assert cut_result["abstention_reason"] == "cut"

    _, players, balls, _, _, _ = case(0)
    stale = shadow_states(players, balls[:1], 0, 31, 720)
    assert all(row["state"] != "OBSERVED_VALID" for row in stale[1:])


def test_history_prerequisite_is_additive_provenance() -> None:
    _, players, balls, _, _, _ = case(0)
    rows = shadow_states(players, balls, 0, 3, 720)
    assert [row["prerequisite_available"] for row in rows] == [0, 0, 0, 1]
