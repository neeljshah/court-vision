"""LANE D -- h2h_history_resolver tests. Synthetic per-sport calendars
(monkeypatched _SOURCES / _TENNIS_PATH, no real parquet dependency) -- pins
the series-aggregate math (games played, W/L split, differential, last-N
form) and the fail-closed no_data / not_supported paths.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/answers/test_h2h_history_resolver.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.answers import h2h_history_resolver as R


def _write(tmp_path, name, df):
    path = tmp_path / name
    df.to_parquet(path)
    return str(path)


# ---------------------------------------------------------------------------
# NBA (linescores-style: home_abbr/away_abbr + home_q*/away_q* quarter cols)
# ---------------------------------------------------------------------------

def test_nba_series_aggregate_math(tmp_path, monkeypatch):
    df = pd.DataFrame([
        {"home_abbr": "LAL", "away_abbr": "BOS", "date": pd.Timestamp("2024-01-01"),
         "home_q1": 25, "home_q2": 25, "home_q3": 25, "home_q4": 25,  # 100
         "away_q1": 20, "away_q2": 20, "away_q3": 20, "away_q4": 20},  # 80 -> LAL +20
        {"home_abbr": "BOS", "away_abbr": "LAL", "date": pd.Timestamp("2024-02-01"),
         "home_q1": 30, "home_q2": 20, "home_q3": 20, "home_q4": 20,  # 90
         "away_q1": 25, "away_q2": 25, "away_q3": 25, "away_q4": 25},  # 100 -> LAL +10
    ])
    monkeypatch.setitem(R._SOURCES, "nba", (str(_write(tmp_path, "ls.parquet", df)), "home_abbr", "away_abbr", "quarters"))
    r = R.resolve("nba", "LAL", "BOS")
    assert r["status"] == "ok"
    assert r["games_played"] == 2
    assert r["wins_a"] == 2 and r["wins_b"] == 0 and r["draws"] == 0
    assert r["series_leader"] == "LAL"
    # LAL margin: game1 +20 (LAL home), game2 +10 (LAL away) -> pair-perspective mean 15, cumulative 30
    assert r["differential_pair_perspective_mean"] == 15.0
    assert r["differential_pair_perspective_cumulative"] == 30
    # home-perspective: game1 home(LAL)+20, game2 home(BOS) -10 -> mean 5, cumulative 10
    assert r["differential_home_perspective_mean"] == 5.0
    assert r["differential_home_perspective_cumulative"] == 10
    assert len(r["last_n_form"]) == 2
    assert r["last_n_form"][0]["date"] == "2024-02-01"  # most recent first


def test_nba_zero_rows_is_no_data(tmp_path, monkeypatch):
    df = pd.DataFrame([{"home_abbr": "LAL", "away_abbr": "GSW", "date": pd.Timestamp("2024-01-01"),
                        "home_q1": 25, "home_q2": 25, "home_q3": 25, "home_q4": 25,
                        "away_q1": 20, "away_q2": 20, "away_q3": 20, "away_q4": 20}])
    monkeypatch.setitem(R._SOURCES, "nba", (str(_write(tmp_path, "ls2.parquet", df)), "home_abbr", "away_abbr", "quarters"))
    r = R.resolve("nba", "LAL", "BOS")  # BOS never appears
    assert r["status"] == "no_data"


def test_as_of_truncates_walk_forward(tmp_path, monkeypatch):
    df = pd.DataFrame([
        {"home_abbr": "LAL", "away_abbr": "BOS", "date": pd.Timestamp("2024-01-01"),
         "home_q1": 25, "home_q2": 25, "home_q3": 25, "home_q4": 25,
         "away_q1": 20, "away_q2": 20, "away_q3": 20, "away_q4": 20},
        {"home_abbr": "BOS", "away_abbr": "LAL", "date": pd.Timestamp("2024-06-01"),
         "home_q1": 30, "home_q2": 20, "home_q3": 20, "home_q4": 20,
         "away_q1": 25, "away_q2": 25, "away_q3": 25, "away_q4": 25},
    ])
    monkeypatch.setitem(R._SOURCES, "nba", (str(_write(tmp_path, "ls3.parquet", df)), "home_abbr", "away_abbr", "quarters"))
    r = R.resolve("nba", "LAL", "BOS", as_of="2024-03-01")
    assert r["status"] == "ok"
    assert r["games_played"] == 1  # only the Jan game is before 2024-03-01
    assert r["as_of"] == "2024-03-01"


# ---------------------------------------------------------------------------
# MLB (games.parquet-style: home_team/away_team/home_runs/away_runs)
# ---------------------------------------------------------------------------

def test_mlb_run_differential(tmp_path, monkeypatch):
    df = pd.DataFrame([
        {"home_team": "NYY", "away_team": "BOS", "date": pd.Timestamp("2024-04-01"), "home_runs": 5, "away_runs": 2},
        {"home_team": "BOS", "away_team": "NYY", "date": pd.Timestamp("2024-05-01"), "home_runs": 3, "away_runs": 6},
    ])
    monkeypatch.setitem(R._SOURCES, "mlb", (str(_write(tmp_path, "mlb.parquet", df)), "home_team", "away_team", "runs"))
    r = R.resolve("mlb", "NYY", "BOS")
    assert r["status"] == "ok"
    assert r["wins_a"] == 2 and r["wins_b"] == 0
    # NYY margin: +3 (home), +3 (away) -> pair mean 3, cumulative 6
    assert r["differential_pair_perspective_mean"] == 3.0
    assert r["differential_pair_perspective_cumulative"] == 6


def test_mlb_unresolvable_team_is_no_data(tmp_path, monkeypatch):
    df = pd.DataFrame([{"home_team": "NYY", "away_team": "BOS", "date": pd.Timestamp("2024-04-01"),
                        "home_runs": 5, "away_runs": 2}])
    monkeypatch.setitem(R._SOURCES, "mlb", (str(_write(tmp_path, "mlb2.parquet", df)), "home_team", "away_team", "runs"))
    r = R.resolve("mlb", "Nonexistent Team", "BOS")
    assert r["status"] == "no_data"


# ---------------------------------------------------------------------------
# Soccer (matches.parquet-style: fthg/ftag, draws allowed)
# ---------------------------------------------------------------------------

def test_soccer_goal_differential_with_draw(tmp_path, monkeypatch):
    df = pd.DataFrame([
        {"home_team": "Arsenal", "away_team": "Chelsea", "date": pd.Timestamp("2024-01-01"), "fthg": 2, "ftag": 2},
        {"home_team": "Chelsea", "away_team": "Arsenal", "date": pd.Timestamp("2024-02-01"), "fthg": 1, "ftag": 3},
    ])
    monkeypatch.setitem(R._SOURCES, "soccer",
                        (str(_write(tmp_path, "soc.parquet", df)), "home_team", "away_team", "goals"))
    r = R.resolve("soccer", "Arsenal", "Chelsea")
    assert r["status"] == "ok"
    assert r["games_played"] == 2
    assert r["draws"] == 1
    assert r["wins_a"] == 1 and r["wins_b"] == 0
    assert r["series_leader"] == "Arsenal"


# ---------------------------------------------------------------------------
# Tennis (prebuilt atlas_h2h.parquet-style: p1_name/p2_name/winner/surface)
# ---------------------------------------------------------------------------

def test_tennis_surface_split_and_last_n(tmp_path, monkeypatch):
    df = pd.DataFrame([
        {"p1_name": "Rafael Nadal", "p2_name": "Roger Federer", "winner": 1,
         "surface": "Clay", "date": pd.Timestamp("2010-01-01")},
        {"p1_name": "Roger Federer", "p2_name": "Rafael Nadal", "winner": 2,
         "surface": "Grass", "date": pd.Timestamp("2011-01-01")},
        {"p1_name": "Rafael Nadal", "p2_name": "Roger Federer", "winner": 2,
         "surface": "Hard", "date": pd.Timestamp("2012-01-01")},
    ])
    path = _write(tmp_path, "atlas_h2h.parquet", df)
    monkeypatch.setattr(R, "_TENNIS_PATH", path)
    r = R.resolve("tennis", "Nadal", "Federer")
    assert r["status"] == "ok"
    assert r["games_played"] == 3
    assert r["wins_a"] == 2 and r["wins_b"] == 1  # Nadal wins games 1 (p1=1) and 2 (p2 loses so winner=2=Nadal)
    assert set(r["surface_split"]) == {"Clay", "Grass", "Hard"}
    assert "differential_pair_perspective_mean" not in r  # no score margin in this store


def test_tennis_unresolved_player_is_no_data(tmp_path, monkeypatch):
    df = pd.DataFrame([{"p1_name": "Rafael Nadal", "p2_name": "Roger Federer", "winner": 1,
                        "surface": "Clay", "date": pd.Timestamp("2010-01-01")}])
    path = _write(tmp_path, "atlas_h2h2.parquet", df)
    monkeypatch.setattr(R, "_TENNIS_PATH", path)
    r = R.resolve("tennis", "Someone Unknown", "Roger Federer")
    assert r["status"] == "no_data"


# ---------------------------------------------------------------------------
# Not-supported / missing-artifact fail-closed paths
# ---------------------------------------------------------------------------

def test_unsupported_sport_is_not_supported():
    r = R.resolve("wnba", "Team A", "Team B")
    assert r["status"] == "not_supported"


def test_missing_artifact_is_no_data(monkeypatch):
    monkeypatch.setitem(R._SOURCES, "nba", ("data/does/not/exist.parquet", "home_abbr", "away_abbr", "quarters"))
    r = R.resolve("nba", "LAL", "BOS")
    assert r["status"] == "no_data"
    assert r["source_artifact"] == "data/does/not/exist.parquet"
