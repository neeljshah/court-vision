"""tmp reliability-map file -> caveat_for mapped + UNMAPPED paths.

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/calibration_grid/test_caveats.py -q
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.calibration_grid import caveats as cv


@pytest.fixture(autouse=True)
def _clear_cache():
    cv.load_reliability_map.cache_clear()
    yield
    cv.load_reliability_map.cache_clear()


def test_bucket_for_nba_ot_and_regulation():
    key = cv.bucket_for("nba", {"elapsed": 20.0, "home_score": 60, "away_score": 55})
    assert key == "lead_+05_10|rem_24_36|reg"
    ot_key = cv.bucket_for("nba", {"elapsed": 50.0, "home_score": 100, "away_score": 100})
    assert ot_key.endswith("|ot|ot")


def test_bucket_for_nba_missing_elapsed_returns_none():
    assert cv.bucket_for("nba", {"home_score": 1, "away_score": 0}) is None


def test_bucket_for_mlb():
    key = cv.bucket_for("mlb", {"inning": 7, "home_score": 5, "away_score": 2})
    assert key == "inn_07|diff_+03|reg"
    key_ex = cv.bucket_for("mlb", {"inning": 11, "home_score": 1, "away_score": 9})
    assert key_ex == "extras|diff_-06|extras"


def test_bucket_for_soccer_intl_alias():
    key = cv.bucket_for("soccer_intl", {"elapsed": 52.0, "home_score": 2, "away_score": 1})
    assert key == "min_45_60|diff_+01"
    key_no_score = cv.bucket_for("soccer", {"elapsed": 52.0})
    assert key_no_score == "min_45_60|score_unknown"


def test_bucket_for_unknown_sport_returns_none():
    assert cv.bucket_for("tennis", {"elapsed": 1.0}) is None


def test_caveat_for_no_reliability_map_built_yet(tmp_path, monkeypatch):
    monkeypatch.setitem(cv._MAP_PATHS, "nba", tmp_path / "missing_map.json")
    result = cv.caveat_for("nba", {"elapsed": 20.0, "home_score": 60, "away_score": 55})
    assert result["can_price"] is False
    assert "UNMAPPED_STATE" in result["reason"]
    assert result["state_bucket"] == "lead_+05_10|rem_24_36|reg"


def test_caveat_for_unknown_sport_never_mapped():
    result = cv.caveat_for("tennis", {"elapsed": 1.0})
    assert result == {"state_bucket": None, "can_price": False,
                      "reason": "UNMAPPED_STATE -- no reliability data for this state"}


def test_caveat_for_mapped_state(tmp_path, monkeypatch):
    key = "lead_+05_10|rem_24_36|reg"
    doc = {"sport": "nba", "buckets": {key: {
        "can_price": True, "reason": "ok", "n_games": 40,
        "model_brier": 0.18, "market_brier": 0.19}}}
    p = tmp_path / "nba_reliability_map.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setitem(cv._MAP_PATHS, "nba", p)
    result = cv.caveat_for("nba", {"elapsed": 20.0, "home_score": 60, "away_score": 55})
    assert result == {"state_bucket": key, "can_price": True, "reason": "ok",
                      "n_games": 40, "model_brier": 0.18, "market_brier": 0.19}


def test_caveat_for_bucket_absent_from_existing_map(tmp_path, monkeypatch):
    doc = {"sport": "nba", "buckets": {"lead_00|rem_00_02|reg": {"can_price": True, "reason": "ok"}}}
    p = tmp_path / "nba_reliability_map.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setitem(cv._MAP_PATHS, "nba", p)
    result = cv.caveat_for("nba", {"elapsed": 20.0, "home_score": 60, "away_score": 55})
    assert result["can_price"] is False
    assert "UNMAPPED_STATE" in result["reason"]


def test_load_reliability_map_corrupt_json_returns_none(tmp_path, monkeypatch):
    p = tmp_path / "nba_reliability_map.json"
    p.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setitem(cv._MAP_PATHS, "nba", p)
    assert cv.load_reliability_map("nba") is None
