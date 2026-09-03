"""Focused tests for the sport-aware tracking quality harness."""
import pandas as pd
import pytest

from scripts.platformkit.tracking_harness import (
    DEFAULT_CONFIG_VERSION,
    SPORTS,
    evaluate,
)
from scripts.platformkit.tracking_schema import (
    CoordinateTransformUnavailable,
    normalize_tracking_frame,
    write_ball_telemetry_declaration,
)


def _good_game(n_frames=100, n_players=10, coordinate_space="court_feet"):
    rows = []
    for frame in range(n_frames):
        for player_id in range(n_players):
            rows.append({"frame": frame, "track_id": player_id, "cls": "player",
                         "x": 10.0 + player_id * 5 + frame * 0.02, "y": 25.0})
        rows.append({"frame": frame, "track_id": 99, "cls": "ball",
                     "x": 47.0, "y": 25.0})
    game = pd.DataFrame(rows)
    game["attempted_frames"] = n_frames
    if coordinate_space is not None:
        game["coordinate_space"] = coordinate_space
    return game


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


def test_sampling_interval_is_additive_and_never_changes_the_verdict():
    cases = (
        ({"frame_rate": 25, "frame_stride": 1}, 0.04, None),
        ({"frame_rate": 25, "frame_stride": 3}, 0.12, None),
        ({"frame_stride": 3}, None, "source frame rate unavailable"),
        ({"frame_rate": 30, "frame_stride": 5}, 0.1667, None),
    )
    baseline = evaluate(_good_game(), "basketball",
                        source_metadata={"frame_rate": 25})

    for metadata, interval, reason in cases:
        report = evaluate(_good_game(), "basketball", source_metadata=metadata)
        assert report.passed == baseline.passed
        assert report.verdict == baseline.verdict
        assert report.failures == baseline.failures
        assert report.sampling_interval_s == interval
        assert report.sampling_interval_reason == reason
        assert report.jump_p95_ft_per_s == (
            round(report.jump_p95 / interval, 2) if interval is not None else None
        )

    with_interval = evaluate(_good_game(), "basketball",
                             source_metadata={"frame_rate": 25, "frame_stride": 3})
    new_fields = {"sampling_interval_s", "sampling_interval_reason", "jump_p95_ft_per_s"}
    assert {key: value for key, value in baseline.__dict__.items() if key not in new_fields} == {
        key: value for key, value in with_interval.__dict__.items() if key not in new_fields
    }


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
    players = df["cls"] == "player"
    df.loc[players, "x"] += df.loc[players, "frame"] * 10.0
    report = evaluate(df, "basketball")
    assert not report.passed and any("oob" in failure for failure in report.failures)
    assert any("median_step_distance" in failure for failure in report.failures)


def test_step_held_game_fails_liveness_gate():
    df = _good_game()
    players = df["cls"] == "player"
    df.loc[players, "x"] = (10.0 + df.loc[players, "track_id"] * 5
                              + (df.loc[players, "frame"] // 20))
    report = evaluate(df, "basketball")
    assert not report.passed and report.liveness_verdict == "SUSPECT"
    assert any("zero_step_share" in failure for failure in report.failures)


def test_ball_stub_without_rows_fails_nonzero_threshold(tmp_path):
    output_path = tmp_path / "tracking_data.csv"
    write_ball_telemetry_declaration(output_path, "basketball", True)
    report = evaluate(_good_game().query("cls != 'ball'"), "basketball",
                      source=str(output_path))
    assert not report.passed
    assert report.ball_rows == 0
    assert any("ball_valid" in failure for failure in report.failures)


def test_no_sidecar_zero_ball_tennis_fails_closed_at_existing_threshold():
    report = evaluate(_good_game().query("cls != 'ball'"), "tennis")

    assert not report.passed and report.verdict == "FAIL"
    assert report.ball_telemetry_available is None
    assert report.ball_telemetry_rule == "unknown_no_sidecar"
    assert report.ball_valid == "evaluated" and report.ball_valid_pct == 0.0
    assert report.failures == ["ball_valid_attempted_frames 0.00 < 0.20"]


def test_declared_tennis_ball_telemetry_without_rows_fails_ball_gate(tmp_path):
    output_path = tmp_path / "tracking_data.csv"
    write_ball_telemetry_declaration(output_path, "tennis", True)

    report = evaluate(_good_game().query("cls != 'ball'"), "tennis",
                      source=str(output_path))

    assert not report.passed and report.verdict == "FAIL"
    assert report.ball_telemetry_available is True
    assert report.ball_valid == "evaluated" and report.ball_valid_pct == 0.0
    assert report.failures == ["ball_valid_attempted_frames 0.00 < 0.20"]


def test_declared_no_ball_telemetry_skips_gate_and_uses_weaker_pass_label(tmp_path):
    output_path = tmp_path / "tracking_data.csv"
    write_ball_telemetry_declaration(output_path, "basketball", False)

    report = evaluate(_good_game().query("cls != 'ball'"), "basketball",
                      source=str(output_path))

    assert report.passed and report.verdict == "PASS_NO_BALL"
    assert report.ball_valid == "not_evaluated"
    assert report.ball_valid_pct is None
    assert report.ball_telemetry_available is False
    assert report.ball_telemetry_rule == "producer_declaration"
    assert not any("ball_valid" in failure for failure in report.failures)


def test_declared_ball_telemetry_without_rows_still_fails_ball_gate(tmp_path):
    output_path = tmp_path / "tracking_data.csv"
    write_ball_telemetry_declaration(output_path, "basketball", True)

    report = evaluate(_good_game().query("cls != 'ball'"), "basketball",
                      source=str(output_path))

    assert not report.passed and report.verdict == "FAIL"
    assert report.ball_valid == "evaluated" and report.ball_valid_pct == 0.0
    assert any("ball_valid" in failure for failure in report.failures)


def test_no_sidecar_with_ball_rows_keeps_telemetry_unknown():
    report = evaluate(_good_game(), "basketball")

    assert report.passed and report.verdict == "PASS"
    assert report.ball_telemetry_available is None
    assert report.ball_telemetry_rule == "unknown_no_sidecar"
    assert report.ball_valid == "evaluated" and report.ball_valid_pct == 1.0


def test_coordinate_contract_failure_keeps_unknown_no_sidecar_rule():
    report = evaluate(_good_game(coordinate_space="image_px").query("cls != 'ball'"),
                      "basketball")

    assert not report.passed
    assert report.ball_valid == "not_evaluated"
    assert report.ball_telemetry_available is None
    assert report.ball_telemetry_rule == "unknown_no_sidecar"


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
            "oob_max", "jump_p95_max", "min_median_track_len"}
    expected = {"basketball", "wnba", "tennis", "soccer", "baseball", "npb", "kbo",
                "football"}
    assert expected <= set(SPORTS)
    for sport, config in SPORTS.items():
        assert keys <= set(config), sport


def test_singleton_tracks_cannot_pass_any_sport():
    coordinate_spaces = {
        "basketball": "court_feet", "soccer": "pitch_metres",
        "football": "court_feet", "tennis": "court_feet", "baseball": "court_feet",
    }
    for sport in coordinate_spaces:
        x0, x1, y0, y1 = SPORTS[sport]["bounds"]
        rows = []
        for frame in range(300):
            for player in range(SPORTS[sport]["min_players"]):
                rows.append({"frame": frame, "track_id": frame * 1000 + player,
                             "cls": "player", "x": (x0 + x1) / 2,
                             "y": (y0 + y1) / 2})
            rows.append({"frame": frame, "track_id": frame * 1000 + 999,
                         "cls": "ball", "x": (x0 + x1) / 2, "y": (y0 + y1) / 2})
        df = pd.DataFrame(rows)
        df["coordinate_space"] = coordinate_spaces[sport]
        df["observation"] = "observed"
        df["calibration"] = "homography"

        report = evaluate(df, sport)
        assert not report.passed
        assert any("median_track_len" in failure or "jump_p95" in failure
                   for failure in report.failures)


def test_empty_input_fails():
    report = evaluate(pd.DataFrame(columns=["frame", "track_id", "cls", "x", "y", "coordinate_space"]),
                      "tennis")
    assert not report.passed and report.n_unique_games == 0


def test_nba_production_rows_fail_closed_without_persisted_homography():
    nba = pd.DataFrame({
        "frame": [0, 1], "timestamp": [0.0, 0.1], "player_id": [7, 7],
        "team": ["home", "home"], "x_position": [10.0, 10.1],
        "y_position": [25.0, 25.0],
    })
    with pytest.raises(CoordinateTransformUnavailable, match="image pixels"):
        normalize_tracking_frame(nba)
    report = evaluate(nba, "basketball")
    assert report.passed is False
    assert report.failures[0].startswith("coordinate_contract:")


def test_normalized_frame_is_passed_through_unchanged():
    normalized = _good_game()
    assert normalize_tracking_frame(normalized, sport="basketball") is normalized


def test_undeclared_in_bounds_pixels_fail_unless_audited_legacy_mode_is_explicit():
    pixels_laundered_into_bounds = _good_game(coordinate_space=None)
    report = evaluate(pixels_laundered_into_bounds, "basketball")

    assert not report.passed
    assert report.failures[0].startswith("coordinate_contract: rows omit coordinate_space")
    legacy = evaluate(pixels_laundered_into_bounds, "basketball",
                      allow_legacy_undeclared=True)
    assert legacy.passed, legacy.failures


def test_coordinate_space_must_match_the_scored_sport():
    report = evaluate(_good_game(coordinate_space="pitch_metres"), "basketball")

    assert not report.passed
    assert report.failures[0].startswith("coordinate_contract: rows declare coordinate_space")


def test_unrecognized_tracking_schema_fails_closed():
    with pytest.raises(ValueError, match="unrecognized tracking schema"):
        evaluate(pd.DataFrame({"frame": [1], "x": [2]}), "basketball")
