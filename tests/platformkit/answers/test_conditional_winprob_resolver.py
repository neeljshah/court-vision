"""LANE D -- conditional_winprob_resolver tests. Synthetic per-sport game logs
(monkeypatched _SOURCES, no real parquet dependency) -- pins the b2b/rest-
bucket win-rate split (the NBA self-check: a real, reproducible descriptive
delta, never a fabricated conditional probability), the MLB/soccer derived-
rest path (incl. dropping a doubleheader-nightcap negative-rest artifact),
and the fail-closed no_data / not_supported paths.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/answers/test_conditional_winprob_resolver.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.answers import conditional_winprob_resolver as R


def _write(tmp_path, name, df):
    path = tmp_path / name
    df.to_parquet(path)
    return str(path)


# ---------------------------------------------------------------------------
# NBA -- native rest_days_home / home_b2b / home_win columns
# ---------------------------------------------------------------------------

def test_nba_b2b_vs_non_b2b_split_is_a_real_empirical_delta(tmp_path, monkeypatch):
    # 4 b2b games (1 home win), 4 non-b2b games (3 home wins) -> a real,
    # reproducible split, never invented.
    rows = []
    for i in range(4):
        rows.append({"home_team": "LAL", "rest_days_home": 0, "home_b2b": True,
                     "home_win": (i == 0), "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i)})
    for i in range(4):
        rows.append({"home_team": "LAL", "rest_days_home": 2, "home_b2b": False,
                     "home_win": (i != 0), "date": pd.Timestamp("2024-02-01") + pd.Timedelta(days=i)})
    df = pd.DataFrame(rows)
    monkeypatch.setitem(R._SOURCES, "nba", str(_write(tmp_path, "games.parquet", df)))
    r = R.resolve("nba")
    assert r["status"] == "ok"
    assert r["b2b"]["n"] == 4 and r["b2b"]["p_home_win"] == 0.25
    assert r["non_b2b"]["n"] == 4 and r["non_b2b"]["p_home_win"] == 0.75
    assert r["b2b"]["ci95"] is not None and r["non_b2b"]["ci95"] is not None
    assert r["overall"]["n"] == 8


def test_nba_rest_bucket_table_labels(tmp_path, monkeypatch):
    rows = [
        {"home_team": "LAL", "rest_days_home": 0, "home_b2b": True, "home_win": True, "date": pd.Timestamp("2024-01-01")},
        {"home_team": "LAL", "rest_days_home": 1, "home_b2b": False, "home_win": False, "date": pd.Timestamp("2024-01-05")},
        {"home_team": "LAL", "rest_days_home": 2, "home_b2b": False, "home_win": True, "date": pd.Timestamp("2024-01-10")},
        {"home_team": "LAL", "rest_days_home": 5, "home_b2b": False, "home_win": True, "date": pd.Timestamp("2024-01-20")},
    ]
    df = pd.DataFrame(rows)
    monkeypatch.setitem(R._SOURCES, "nba", str(_write(tmp_path, "games2.parquet", df)))
    r = R.resolve("nba")
    assert r["rest_buckets"]["b2b_or_1d"]["n"] == 2  # rest_days 0 and 1
    assert r["rest_buckets"]["2-3d"]["n"] == 1
    assert r["rest_buckets"]["4d_plus"]["n"] == 1


def test_nba_team_filter_scopes_to_home_games(tmp_path, monkeypatch):
    rows = [
        {"home_team": "LAL", "rest_days_home": 0, "home_b2b": True, "home_win": True, "date": pd.Timestamp("2024-01-01")},
        {"home_team": "BOS", "rest_days_home": 0, "home_b2b": True, "home_win": False, "date": pd.Timestamp("2024-01-02")},
    ]
    df = pd.DataFrame(rows)
    monkeypatch.setitem(R._SOURCES, "nba", str(_write(tmp_path, "games3.parquet", df)))
    r = R.resolve("nba", team="Lakers")
    assert r["status"] == "ok"
    assert r["team"] == "LAL"
    assert r["overall"]["n"] == 1


def test_nba_unresolved_team_is_no_data(tmp_path, monkeypatch):
    df = pd.DataFrame([{"home_team": "LAL", "rest_days_home": 0, "home_b2b": True,
                        "home_win": True, "date": pd.Timestamp("2024-01-01")}])
    monkeypatch.setitem(R._SOURCES, "nba", str(_write(tmp_path, "games4.parquet", df)))
    r = R.resolve("nba", team="Nonexistent Team XYZ")
    assert r["status"] == "no_data"


def test_as_of_truncates(tmp_path, monkeypatch):
    rows = [
        {"home_team": "LAL", "rest_days_home": 0, "home_b2b": True, "home_win": True, "date": pd.Timestamp("2024-01-01")},
        {"home_team": "LAL", "rest_days_home": 0, "home_b2b": True, "home_win": False, "date": pd.Timestamp("2024-06-01")},
    ]
    df = pd.DataFrame(rows)
    monkeypatch.setitem(R._SOURCES, "nba", str(_write(tmp_path, "games5.parquet", df)))
    r = R.resolve("nba", as_of="2024-03-01")
    assert r["overall"]["n"] == 1
    assert r["as_of"] == "2024-03-01"


# ---------------------------------------------------------------------------
# MLB -- derived rest from date deltas + target_home_win, doubleheader guard
# ---------------------------------------------------------------------------

def test_mlb_derived_rest_and_home_win(tmp_path, monkeypatch):
    # NYY: game 4/1 (vs BOS away appearance not present), then home 4/3 (rest=1),
    # then home 4/8 (rest=4). BOS just fills the opponent slot.
    rows = [
        {"home_team": "NYY", "away_team": "BOS", "date": pd.Timestamp("2024-04-01"), "target_home_win": True},
        {"home_team": "NYY", "away_team": "BOS", "date": pd.Timestamp("2024-04-03"), "target_home_win": False},
        {"home_team": "NYY", "away_team": "BOS", "date": pd.Timestamp("2024-04-08"), "target_home_win": True},
    ]
    df = pd.DataFrame(rows)
    monkeypatch.setitem(R._SOURCES, "mlb", str(_write(tmp_path, "mlb.parquet", df)))
    r = R.resolve("mlb")
    assert r["status"] == "ok"
    # game1 has no prior game -> NaN rest -> dropped everywhere (overall + buckets), not just the bucket table
    assert r["overall"]["n"] == 2
    assert r["rest_buckets"]["b2b_or_1d"]["n"] + r["rest_buckets"]["2-3d"]["n"] + r["rest_buckets"]["4d_plus"]["n"] == 2


def test_mlb_doubleheader_negative_rest_dropped(tmp_path, monkeypatch):
    # Two games on the SAME date for NYY (doubleheader): game1 is NYY's first
    # appearance (NaN rest), game2 is the nightcap (derived rest = -1) --
    # neither is a real short-rest game and both must be excluded. game3,
    # 4 days later, gets a correct rest_days=3 off the LATEST of the two
    # same-date games, not double-counted or confused by the doubleheader.
    rows = [
        {"home_team": "NYY", "away_team": "BOS", "date": pd.Timestamp("2024-04-01"), "target_home_win": True},
        {"home_team": "NYY", "away_team": "BOS", "date": pd.Timestamp("2024-04-01"), "target_home_win": False},
        {"home_team": "NYY", "away_team": "BOS", "date": pd.Timestamp("2024-04-05"), "target_home_win": True},
    ]
    df = pd.DataFrame(rows)
    monkeypatch.setitem(R._SOURCES, "mlb", str(_write(tmp_path, "mlb_dh.parquet", df)))
    r = R.resolve("mlb")
    assert r["status"] == "ok"
    assert r["overall"]["n"] == 1  # only game3 survives the NaN/negative-rest guard
    assert r["rest_buckets"]["2-3d"]["n"] == 1
    assert r["rest_buckets"]["b2b_or_1d"]["n"] == 0


# ---------------------------------------------------------------------------
# Soccer -- derived rest + ftr-based home win
# ---------------------------------------------------------------------------

def test_soccer_ftr_home_win(tmp_path, monkeypatch):
    rows = [
        {"home_team": "Arsenal", "away_team": "Chelsea", "date": pd.Timestamp("2024-01-01"), "ftr": "H"},
        {"home_team": "Arsenal", "away_team": "Everton", "date": pd.Timestamp("2024-01-05"), "ftr": "A"},
        {"home_team": "Arsenal", "away_team": "Fulham", "date": pd.Timestamp("2024-01-10"), "ftr": "D"},
    ]
    df = pd.DataFrame(rows)
    monkeypatch.setitem(R._SOURCES, "soccer", str(_write(tmp_path, "soc.parquet", df)))
    r = R.resolve("soccer")
    assert r["status"] == "ok"
    # game1 (1/1) has no prior appearance -> dropped; games 2 (ftr=A) and 3
    # (ftr=D) survive, neither is a home win -> p_home_win = 0/2
    assert r["overall"]["n"] == 2
    assert r["overall"]["p_home_win"] == 0.0


# ---------------------------------------------------------------------------
# Fail-closed paths
# ---------------------------------------------------------------------------

def test_unsupported_sport_is_not_supported():
    r = R.resolve("tennis")
    assert r["status"] == "not_supported"


def test_missing_artifact_is_no_data(monkeypatch):
    monkeypatch.setitem(R._SOURCES, "nba", "data/does/not/exist.parquet")
    r = R.resolve("nba")
    assert r["status"] == "no_data"
    assert r["source_artifact"] == "data/does/not/exist.parquet"


def test_wilson_ci_none_for_zero_n():
    assert R._wilson_ci(0, 0) is None


def test_wilson_ci_shrinks_toward_half_for_small_n():
    lo, hi = R._wilson_ci(1, 2)
    assert 0.0 <= lo < 0.5 < hi <= 1.0
