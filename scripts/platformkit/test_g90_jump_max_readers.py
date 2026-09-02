"""G90 regression: live summaries must read the current jump gate field.

Run: python -m pytest scripts/platformkit/test_g90_jump_max_readers.py -q
"""
from scripts.platformkit.tracking_brain import _profile_scorecard
from scripts.platformkit.tracking_corpus_ab import baseline_diff
from scripts.platformkit.tracking_harness import SPORTS


def test_jump_max_readers_prefer_current_field_and_accept_legacy_baseline():
    current = {
        "coverage_pct": 1.0, "ball_valid_pct": 1.0, "oob_pct": 0.0,
        "jump_p95": 1.0, "jump_max": 10.0, "passed": False,
    }
    card = _profile_scorecard([current], SPORTS["tennis"])

    assert card["worst_metric"] == "jump_max"
    assert card["metric_medians"]["jump_max"] == 10.0

    legacy = dict(current)
    legacy.pop("jump_max")
    assert _profile_scorecard([legacy], SPORTS["tennis"])["metric_medians"]["jump_max"] == 1.0

    baseline = {"g": {"game_id": "g", "status": "completed", "passed": False,
                        "coverage_pct": 1.0, "ball_valid_pct": 1.0, "oob_pct": 0.0,
                        "jump_p95": 1.0}}
    current_row = {"game_id": "g", "status": "completed", **current}
    assert "jump_max 1.000->10.000" in baseline_diff(baseline, [current_row])[1]
