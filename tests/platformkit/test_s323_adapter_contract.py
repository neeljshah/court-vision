"""S323 construct coverage: four planted rejects, clean control, and replay."""
from __future__ import annotations

import tempfile
from copy import deepcopy
from pathlib import Path

import pytest

from domains.cross_sport_market.ingame_census_adapter import classify_columns, discover_inplay_parquets
from scripts.platformkit.eval_gate.adapter_contract import (
    AdapterContractError,
    CENSUS_FIELDS,
    assert_prefix_predictions_identical,
    require_accepted,
    validate,
)


def _frames() -> tuple[list[dict], list[dict]]:
    feature = {
        "sport": "basketball", "league": "NBA", "rule_version": "S323-v1", "game_id": "g1",
        "home_team_id": "H", "away_team_id": "A", "season": "2025-26", "corpus": "construct", "venue": "construct",
        "target_id": "home_win", "line": 0.5, "class_order": ("away", "home"),
        "settlement_rule": "home_win", "void_rule": "none", "event_id": "e1", "sequence": 0,
        "event_time": "2025-01-01T12:00:00", "received_at": "2025-01-01T12:00:00",
        "feature_available_at": "2025-01-01T12:00:01", "prediction_at": "2025-01-01T12:00:02",
        "state": {"period": 1, "clock_seconds": 600}, "score_home": 0, "score_away": 0,
        "status": "live", "unknown_flags": (), "provenance": {"source": "construct"},
        "m0_source": "market", "m0_time": "2025-01-01T12:00:00", "m0_probabilities": (0.5, 0.5),
        "ml_source": "baseline", "ml_time": "2025-01-01T12:00:01", "ml_probabilities": (0.5, 0.5),
        "candidate_probabilities": (0.5, 0.5), "null_probabilities": (0.5, 0.5),
        "state_key": "g1|000000|home_win", "exclusions": (), "weight": 1.0, "fold_id": "fold_a",
        "input_hash": "input", "code_hash": "code", "seal_hash": "seal", "maximum_feed_delay_seconds": 1,
        "features": {"margin": 0.0},
    }
    label = {"game_id": "g1", "target_id": "home_win", "state_key": feature["state_key"],
             "outcome": 1, "outcome_known_at": "2025-01-01T15:00:00"}
    return [feature], [label]


def _state(game_id: str, stamp: str, value: float) -> dict:
    return {"game_id": game_id, "state_ts": stamp, "home": "H" + game_id,
            "away": "A" + game_id, "season": "2025-26", "sport": "basketball",
            "game_date": stamp[:10], "features": {"signal": value},
            "feature_avail": {"signal": "2025-01-01T00:00:00"}, "outcome": 1}


def _predict(_train: list[dict], test: dict, _inside: bool) -> float:
    return float(test["features"]["signal"])


def test_s323_clean_control_accepts_and_prefix_is_identical() -> None:
    features, labels = _frames()
    assert require_accepted(features, labels).accepted
    prefix = [_state("g1", "2025-01-02T12:00:00", 0.2), _state("g2", "2025-01-03T12:00:00", 0.3)]
    extended = prefix + [_state("g3", "2025-01-04T12:00:00", 0.4)]
    assert_prefix_predictions_identical(prefix, extended, _predict)


def test_s323_rejects_next_event_future_availability_before_fitting() -> None:
    features, labels = _frames()
    features[0]["feature_available_at"] = "2025-01-01T12:00:03"
    report = validate(features, labels)
    assert not report.accepted and any("nonmonotone" in item for item in report.violations)


def test_s323_rejects_disguised_final_outcome_before_fitting() -> None:
    features, labels = _frames()
    features[0]["features"] = {"final_outcome_proxy": 1.0}
    report = validate(features, labels)
    assert not report.accepted and any("outcome-like" in item for item in report.violations)


def test_s323_rejects_duplicate_game_across_folds_before_fitting() -> None:
    features, labels = _frames()
    duplicate, duplicate_label = deepcopy(features[0]), deepcopy(labels[0])
    duplicate["event_id"], duplicate["sequence"], duplicate["fold_id"] = "e2", 1, "fold_b"
    duplicate["state_key"] = "g1|000001|home_win"
    duplicate_label["state_key"] = duplicate["state_key"]
    report = validate(features + [duplicate], labels + [duplicate_label])
    assert not report.accepted and any("game crosses folds" in item for item in report.violations)


def test_s323_rejects_history_rewrite_by_strict_truncation_replay() -> None:
    prefix = [_state("g1", "2025-01-02T12:00:00", 0.2), _state("g2", "2025-01-03T12:00:00", 0.3)]
    rewritten = deepcopy(prefix) + [_state("g3", "2025-01-04T12:00:00", 0.4)]
    rewritten[0]["features"]["signal"] = 0.9  # future raw outcome was rewritten with a forged early timestamp
    with pytest.raises(AdapterContractError, match="truncation replay"):
        assert_prefix_predictions_identical(prefix, rewritten, _predict)


def test_s323_rejects_unknown_flag_naming_present_field() -> None:
    features, labels = _frames()
    features[0]["unknown_flags"] = ("sport",)
    report = validate(features, labels)
    assert not report.accepted and any("sport" in item and "present field" in item for item in report.violations)


def test_s323_accepts_legitimate_flag_on_none_feature() -> None:
    features, labels = _frames()
    features[0]["provenance"] = None
    features[0]["unknown_flags"] = ("provenance",)
    report = validate(features, labels)
    assert report.accepted


def test_s323_census_soccer_checkpoints_exact_name_available() -> None:
    # real soccer_checkpoints_wc2026.parquet schema (14 columns; source column names read, no data load)
    columns = ["game_id", "game_date", "home_team", "away_team", "ts", "minute", "score_home",
               "score_away", "margin", "market_ticker", "market_prob", "tie_prob", "traded", "outcome"]
    assert classify_columns(columns, "game_id") == "AVAILABLE"
    assert classify_columns(columns, "score_home") == "AVAILABLE"
    assert classify_columns(columns, "score_away") == "AVAILABLE"
    assert classify_columns(columns, "outcome") == "AVAILABLE"


def test_s323_census_nba_checkpoints_outcome_alias_available() -> None:
    # real nba_checkpoints_full.parquet schema (13 columns; source column names read, no data load)
    columns = ["game_id", "game_date", "ts", "period", "game_clock_s", "score_home", "score_away",
               "margin", "market_prob", "traded", "market_ticker", "outcome_home_win", "venue"]
    assert "outcome" not in columns  # no exact-name match; AVAILABLE must come from the alias
    assert classify_columns(columns, "outcome") == "AVAILABLE"
    assert classify_columns(columns, "score_home") == "AVAILABLE"  # exact-name, not alias
    assert classify_columns(columns, "score_away") == "AVAILABLE"  # exact-name, not alias


def test_s323_all_inplay_enumerates_every_parquet_in_a_directory() -> None:
    names = ["kbo_price_series.parquet", "nba_checkpoints_full.parquet", "soccer_price_series.parquet"]
    with tempfile.TemporaryDirectory() as raw_dir:
        tmp_path = Path(raw_dir)
        for name in names:
            (tmp_path / name).touch()
        (tmp_path / "not_a_parquet.txt").touch()
        discovered = discover_inplay_parquets(tmp_path)
    assert [path.name for _, path in discovered] == sorted(names)
    assert not [path for _, path in discovered if path.suffix != ".parquet"]
    sports = {path.name: sport for sport, path in discovered}
    assert sports["kbo_price_series.parquet"] == "KBO"
    assert sports["nba_checkpoints_full.parquet"] == "NBA"
    assert sports["soccer_price_series.parquet"] == "soccer"


def test_s323_census_covers_every_contract_field() -> None:
    generic = {"sport", "venue", "game_date", "ticker_or_slug", "event_key", "market_type",
               "side", "ts", "prob", "traded", "close_time", "result_where_known"}
    availability = {field: classify_columns(generic, field) for field in CENSUS_FIELDS}
    assert set(availability) == set(CENSUS_FIELDS)
    assert availability["m0_probabilities"] == "AVAILABLE"
    assert availability["ml_probabilities"] == "UNAVAILABLE"
