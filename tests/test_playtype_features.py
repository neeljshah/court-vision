"""tests/test_playtype_features.py -- R10_M14 SHIP verification.

Pins three properties of the Synergy play-type wire-in:

1. The pt_<playtype>_freq columns sit inside feature_columns() (live in prod).
2. The training-path join uses PRIOR-SEASON (S-1) -- never the current season.
   Verified by stubbing _PlayTypes with a fixture that only returns non-zero
   values for the PRIOR season and asserting the produced row picks them up.
3. _PLAYTYPE_PRIOR_SEASON_JOIN flag default is True so the leak fix is active
   on fresh checkouts, and _PLAYTYPE_SHIPPED_STATS gates the retrain set.

Run:
    python -m pytest tests/test_playtype_features.py -q
"""
from __future__ import annotations

import json
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction import prop_pergame  # noqa: E402
from src.prediction.prop_pergame import (  # noqa: E402
    _PLAY_TYPES,
    _PLAYTYPE_DEFAULTS,
    _PLAYTYPE_PRIOR_SEASON_JOIN,
    _PLAYTYPE_SHIPPED_STATS,
    _prior_season,
    build_pergame_dataset,
    build_prediction_row,
    feature_columns,
)


# Flag invariants ----------------------------------------------------------

def test_prior_season_join_flag_default_on():
    """The leak fix is active out of the box."""
    assert _PLAYTYPE_PRIOR_SEASON_JOIN is True


def test_shipped_stats_set():
    """PTS + FG3M only -- the two stats with WF 4/4 + production retrain."""
    assert _PLAYTYPE_SHIPPED_STATS == {"pts", "fg3m"}


def test_prior_season_helper():
    assert _prior_season("2024-25") == "2023-24"
    assert _prior_season("2023-24") == "2022-23"
    assert _prior_season("2022-23") == "2021-22"
    assert _prior_season("bad") == ""


# Feature-columns invariant -----------------------------------------------

def test_playtype_columns_in_feature_columns():
    cols = feature_columns()
    for pt in _PLAY_TYPES:
        assert f"pt_{pt}_freq" in cols


# Build-prediction-row uses prior season ----------------------------------

def _write_minimal_gamelog(tmp_path, pid: int, season: str, n_games: int = 10):
    games = []
    for d in range(1, n_games + 1):
        games.append({
            "GAME_DATE": f"Jan {d:02d}, 2025",
            "MATCHUP": "SAS vs. TOR",
            "PTS": 20, "REB": 5, "AST": 4, "FG3M": 2,
            "STL": 1, "BLK": 0, "TOV": 2, "MIN": 30.0,
        })
    path = tmp_path / f"gamelog_{pid}_{season}.json"
    path.write_text(json.dumps(games), encoding="utf-8")
    return path


def test_predict_row_join_is_prior_season_only(tmp_path, monkeypatch):
    """build_prediction_row must look up the playtype vector under S-1, not S.

    Setup: stub _get_playtypes with a fixture that returns NON-ZERO values
    ONLY for the prior season (2023-24). If the production code mistakenly
    queried the current season (2024-25), it would get all-zero defaults
    and the assertion would fail.
    """
    pid = 42
    season = "2024-25"
    _write_minimal_gamelog(tmp_path, pid, season)

    class _StubPlayTypes:
        def features(self, player_id, season_arg):
            if int(player_id) == pid and season_arg == "2023-24":
                # Non-zero only when called with the PRIOR season
                return {f"pt_{pt}_freq": 0.11 for pt in _PLAY_TYPES}
            # Anything else -> zero defaults (leak/wrong-key path)
            return dict(_PLAYTYPE_DEFAULTS)

    stub = _StubPlayTypes()
    monkeypatch.setattr(prop_pergame, "_get_playtypes", lambda: stub)

    row = build_prediction_row(
        player_id=pid,
        opp_team="TOR",
        season=season,
        gamelog_dir=str(tmp_path),
    )
    assert row is not None
    # Every playtype column should reflect the prior-season fixture value.
    for pt in _PLAY_TYPES:
        key = f"pt_{pt}_freq"
        assert key in row
        assert row[key] == pytest.approx(0.11), (
            f"Expected prior-season join (0.11) for {key}, got {row[key]} -- "
            f"looks like the join still uses the current season."
        )


def test_predict_row_zero_when_flag_off(tmp_path, monkeypatch):
    """Flipping _PLAYTYPE_PRIOR_SEASON_JOIN to False reverts to current-season.

    Stub returns non-zero ONLY for current season -> with flag off, we should
    see those values. This locks in the rollback path.
    """
    pid = 42
    season = "2024-25"
    _write_minimal_gamelog(tmp_path, pid, season)

    class _StubCurrentOnly:
        def features(self, player_id, season_arg):
            if int(player_id) == pid and season_arg == "2024-25":
                return {f"pt_{pt}_freq": 0.22 for pt in _PLAY_TYPES}
            return dict(_PLAYTYPE_DEFAULTS)

    stub = _StubCurrentOnly()
    monkeypatch.setattr(prop_pergame, "_get_playtypes", lambda: stub)
    monkeypatch.setattr(prop_pergame, "_PLAYTYPE_PRIOR_SEASON_JOIN", False)

    row = build_prediction_row(
        player_id=pid,
        opp_team="TOR",
        season=season,
        gamelog_dir=str(tmp_path),
    )
    assert row is not None
    # With the flag off, the join key reverts to the current season.
    for pt in _PLAY_TYPES:
        assert row[f"pt_{pt}_freq"] == pytest.approx(0.22)


# Training-path join uses prior season ------------------------------------

def test_train_path_join_is_prior_season(tmp_path, monkeypatch):
    """build_pergame_dataset must thread file_season through _prior_season().

    We point gamelog_dir at a tmp directory holding ONE gamelog with the
    minimum number of played games (5+ rows), stub the playtype builder
    so the test focuses on the playtype join only.
    """
    pid = 99
    season = "2024-25"
    n_games = 12
    games = []
    for d in range(1, n_games + 1):
        games.append({
            "GAME_DATE": f"Jan {d:02d}, 2025",
            "MATCHUP": "SAS vs. TOR",
            "PTS": 20, "REB": 5, "AST": 4, "FG3M": 2,
            "STL": 1, "BLK": 0, "TOV": 2, "MIN": 30.0,
        })
    gamelog = tmp_path / f"gamelog_{pid}_{season}.json"
    gamelog.write_text(json.dumps(games), encoding="utf-8")

    seasons_seen = []

    class _RecorderPlayTypes:
        def features(self, player_id, season_arg):
            seasons_seen.append(season_arg)
            # Return a unique value when called with prior season so we
            # can also assert the row dict carries that value.
            if season_arg == "2023-24":
                return {f"pt_{pt}_freq": 0.33 for pt in _PLAY_TYPES}
            return dict(_PLAYTYPE_DEFAULTS)

    monkeypatch.setattr(
        prop_pergame, "build_playtypes", lambda *a, **k: _RecorderPlayTypes(),
    )

    rows, fcols = build_pergame_dataset(str(tmp_path), min_prior=3)
    assert len(rows) > 0, "No training rows produced -- gamelog/min_prior mismatch"

    # Every season the playtype builder saw should be the PRIOR season,
    # never the current one. file_season for this gamelog is 2024-25.
    assert seasons_seen, "Playtype features() was never called"
    assert all(s == "2023-24" for s in seasons_seen), (
        f"Training loop leaked current-season key into playtype join: {set(seasons_seen)}"
    )

    # And the row dict carries the prior-season values.
    for r in rows:
        for pt in _PLAY_TYPES:
            key = f"pt_{pt}_freq"
            assert key in r
            assert r[key] == pytest.approx(0.33), (
                f"Row missing prior-season playtype value for {key}: {r[key]}"
            )
