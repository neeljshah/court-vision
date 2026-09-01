"""Focused tests for the live runtime feature contract."""
import pytest

from scripts.platformkit.runtime_contract import (
    RUNTIME,
    TRAINING_ONLY,
    UNKNOWN,
    assert_runtime_safe,
    classify_feature,
    validate_manifest,
)


def test_allowlisted_live_inputs_pass():
    names = ["market_price", "home_score", "rest_days", "player_id", "injury_flag"]
    assert validate_manifest(names) == {"ok": True, "violations": [], "unknowns": []}
    assert classify_feature("market_price") == RUNTIME


def test_tracking_feature_fails_and_is_named():
    result = validate_manifest(["market_price", "tracking_defender_distance"])
    assert result["ok"] is False
    assert result["violations"] == ["tracking_defender_distance"]
    assert result["unknowns"] == []
    assert classify_feature("tracking_defender_distance") == TRAINING_ONLY
    with pytest.raises(ValueError, match="tracking_defender_distance"):
        assert_runtime_safe(["tracking_defender_distance"])


def test_unknown_feature_fails_closed():
    result = validate_manifest(["mystery_signal"])
    assert result == {
        "ok": False,
        "violations": ["mystery_signal"],
        "unknowns": ["mystery_signal"],
    }
    assert classify_feature("mystery_signal") == UNKNOWN


def test_static_prior_prefix_passes():
    assert classify_feature("prior_player_points") == RUNTIME
    assert validate_manifest(["prior_player_points", "team_strength_prior"])["ok"] is True
