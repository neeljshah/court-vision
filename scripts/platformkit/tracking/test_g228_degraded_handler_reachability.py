"""Focused invariants for the G228 local-only forced-control helper."""

from scripts.platformkit.tracking.g228_degraded_handler_reachability import (
    detector_observation,
    m1_sanity_observation,
)


def test_detector_forced_failure_matches_clean_empty_output_shape() -> None:
    clean = detector_observation("clean_empty")
    forced = detector_observation("forced_failure")

    assert clean["caller_return"] == forced["caller_return"] == []
    assert clean["returned_detection_count"] == forced["returned_detection_count"] == 0
    assert clean["python_stdout"] == forced["python_stdout"] == ""
    assert clean["python_stderr"] == forced["python_stderr"] == ""


def test_m1_forced_sanity_failure_matches_the_clean_installation() -> None:
    clean = m1_sanity_observation(force_sanity_failure=False)
    forced = m1_sanity_observation(force_sanity_failure=True)

    for key in ("installed_candidate", "raw_clip_candidate", "last_good_candidate"):
        assert clean[key] is forced[key] is True
    assert clean["caller_return"] is forced["caller_return"] is None
    assert clean["failed_attempts"] == forced["failed_attempts"] == 0
    assert clean["python_stdout"] == forced["python_stdout"] == ""
    assert clean["python_stderr"] == forced["python_stderr"] == ""
