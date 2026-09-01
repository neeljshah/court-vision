"""Focused tests for the sport-aware tracking quality harness."""
import pandas as pd

from scripts.platformkit.tracking_harness import (
    DEFAULT_CONFIG_VERSION,
    SPORTS,
    evaluate,
)


def _good_game(n_frames=100, n_players=10):
    rows = []
    for frame in range(n_frames):
        for player_id in range(n_players):
            rows.append({"frame": frame, "track_id": player_id, "cls": "player",
                         "x": 10.0 + player_id * 5 + frame * 0.02, "y": 25.0})
        rows.append({"frame": frame, "track_id": 99, "cls": "ball",
                     "x": 47.0, "y": 25.0})
    return pd.DataFrame(rows)


def test_good_game_has_versioned_provenance_aware_report():
    report = evaluate(_good_game(), "basketball",
                      source_metadata={"resolution": "1280x720", "frame_rate": 60})
    assert report.passed, report.failures
    assert report.config_version == DEFAULT_CONFIG_VERSION
    assert report.n_unique_games == 1 and report.n_duplicate_frame_track_rows == 0
    assert report.ball_rows == 100 and report.ball_valid_pct == 1.0
    assert report.source_resolution == "1280x720" and report.source_frame_rate == 60.0
    assert report.self_consistency_only is True
    assert report.liveness_verdict == "LIVE" and report.zero_step_share == 0.0


def test_frozen_game_fails_liveness_gate():
    df = _good_game()
    df.loc[df["cls"] == "player", ["x", "y"]] = (20.0, 25.0)
    report = evaluate(df, "basketball")
    assert not report.passed and report.liveness_verdict == "FROZEN"
    assert any("liveness verdict FROZEN" == failure for failure in report.failures)


def test_live_game_passes_liveness_gate():
    report = evaluate(_good_game(), "basketball")
    assert report.passed and report.liveness_verdict == "LIVE"


def test_oob_and_teleport_fail():
    df = _good_game()
    df.loc[df["cls"] == "player", "x"] = 500.0
    report = evaluate(df, "basketball")
    assert not report.passed and any("oob" in failure for failure in report.failures)


def test_ball_stub_without_rows_fails_nonzero_threshold():
    report = evaluate(_good_game().query("cls != 'ball'"), "basketball")
    assert not report.passed
    assert report.ball_rows == 0
    assert any("ball_valid" in failure for failure in report.failures)


def test_duplicate_frame_track_rows_are_visible_failures():
    df = _good_game()
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    report = evaluate(df, "basketball")
    assert not report.passed and report.n_duplicate_frame_track_rows == 1
    assert any("duplicate" in failure for failure in report.failures)


def test_unknown_config_version_is_a_visible_failure():
    report = evaluate(_good_game(), "basketball", config_version="missing-v0")
    assert not report.passed and report.config_version == "missing-v0"
    assert report.failures == ["unknown config version missing-v0"]


def test_shared_adapters_retain_distinct_sport_labels():
    for sport in ("wnba", "npb", "kbo", "football"):
        report = evaluate(_good_game(), sport)
        assert report.sport == sport


def test_all_sports_have_complete_configs():
    keys = {"bounds", "min_players", "ball_valid_min", "coverage_min",
            "oob_max", "jump_p95_max"}
    expected = {"basketball", "wnba", "tennis", "soccer", "baseball", "npb", "kbo",
                "football"}
    assert expected <= set(SPORTS)
    for sport, config in SPORTS.items():
        assert keys <= set(config), sport


def test_empty_input_fails():
    report = evaluate(pd.DataFrame(columns=["frame", "track_id", "cls", "x", "y"]),
                      "tennis")
    assert not report.passed and report.n_unique_games == 0
