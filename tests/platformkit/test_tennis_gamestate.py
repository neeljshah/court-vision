"""Per-file tests for tennis GAMES-WITHIN-SET detail layer (OFFLINE, SYNTHETIC).

Covers the frozen detail schema + the two RAILS-critical invariants:
  - LEAK-FREE AS-OF: a row at asof_idx i is reconstructed only from sets 0..i;
    no future set, no match-final aggregate ever appears in a per-tick value.
  - NO WINNER-LEAK: columns are signed by the STABLE p1 identity, NOT by the
    winner.  Same on-court score with p1 as winner vs p1 as loser must MIRROR
    (regression for the Sackmann winner-first orientation bug).

NO file I/O.  NO network.  SYNTHETIC data only.

Run (per-file ONLY -- full pytest freezes this box):
  cd /c/Users/neelj/nba-ai-system && \\
    python -m pytest tests/platformkit/test_tennis_gamestate.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.tennis.ingest_gamestate_states import (
    build_corpus,
    build_detail_rows,
    _set_break_proxy,
)
from domains.tennis.ingest_ingame_states import parse_score

DETAIL_COLS = {
    "sport", "game_id", "asof_idx",
    "games_diff_in_set", "sets_diff",
    "break_pts_converted_diff", "serve_holds_streak",
}


def _rows(score: str, winner: int, drop_terminal: bool = True) -> list[dict]:
    sets = parse_score(score)
    assert sets is not None
    return build_detail_rows("m", sets, winner, drop_terminal=drop_terminal)


# --------------------------------------------------------------- break proxy
def test_break_proxy_dominant_set_more_than_tiebreak():
    assert _set_break_proxy(6, 0) == 4      # 6-0 -> margin 6 -> decisive 4
    assert _set_break_proxy(6, 4) == 0      # 6-4 -> margin 2 -> hold-only
    assert _set_break_proxy(7, 6) == 0      # tiebreak -> margin 1 -> 0


def test_break_proxy_signed_toward_p1():
    assert _set_break_proxy(6, 1) == 3
    assert _set_break_proxy(1, 6) == -3
    assert _set_break_proxy(6, 6) == 0


# --------------------------------------------------------------- schema
def test_schema_required_cols():
    rows = _rows("6-3 6-1", 1, drop_terminal=False)
    assert rows
    assert DETAIL_COLS <= set(rows[0].keys())
    assert all(r["sport"] == "tennis" for r in rows)


def test_schema_asof_idx_sequential():
    rows = _rows("4-6 6-3 6-4", 1, drop_terminal=False)
    assert [r["asof_idx"] for r in rows] == [0, 1, 2]


def test_terminal_dropped_by_default():
    # "6-3 6-1": raw=2 boundaries, default drops the match-ending one -> 1 row.
    assert len(_rows("6-3 6-1", 1)) == 1
    assert len(_rows("6-3 6-1", 1, drop_terminal=False)) == 2


# --------------------------------------------------------------- games_diff_in_set
def test_games_diff_in_set_is_last_completed_set():
    # asof 0 sees set1 6-3 -> (6-3)/12 = 0.25
    rows = _rows("6-3 6-1", 1, drop_terminal=False)
    assert rows[0]["games_diff_in_set"] == pytest.approx(3.0 / 12.0)
    # asof 1 sees set2 6-1 -> (6-1)/12
    assert rows[1]["games_diff_in_set"] == pytest.approx(5.0 / 12.0)


def test_sets_diff_cumulative():
    rows = _rows("6-3 4-6 6-2", 1, drop_terminal=False)
    assert rows[0]["sets_diff"] == pytest.approx(1.0)   # p1 up 1-0
    assert rows[1]["sets_diff"] == pytest.approx(0.0)   # tied 1-1
    assert rows[2]["sets_diff"] == pytest.approx(1.0)   # p1 up 2-1


def test_serve_holds_streak_runs():
    rows = _rows("6-3 6-1 4-6 6-2", 1, drop_terminal=False)
    assert rows[0]["serve_holds_streak"] == pytest.approx(1.0)
    assert rows[1]["serve_holds_streak"] == pytest.approx(2.0)   # two in a row
    assert rows[2]["serve_holds_streak"] == pytest.approx(-1.0)  # p2 breaks run
    assert rows[3]["serve_holds_streak"] == pytest.approx(1.0)   # p1 again


# --------------------------------------------------------------- NO WINNER-LEAK
def test_no_winner_leak_mirror():
    # Same on-court score; p1-as-winner vs p1-as-loser must MIRROR every column.
    won = _rows("6-3 6-4", winner=1, drop_terminal=False)
    lost = _rows("6-3 6-4", winner=2, drop_terminal=False)
    assert len(won) == len(lost)
    for rw, rl in zip(won, lost):
        for c in ("games_diff_in_set", "sets_diff",
                  "break_pts_converted_diff", "serve_holds_streak"):
            assert rl[c] == pytest.approx(-rw[c], abs=1e-5), c


def test_loser_columns_negative():
    # winner-first "6-3 6-1" with winner=2 -> p1 LOST both sets -> all signed cols
    # must be <= 0 (p1 never ahead).
    rows = _rows("6-3 6-1", winner=2, drop_terminal=False)
    for r in rows:
        assert r["sets_diff"] <= 0
        assert r["break_pts_converted_diff"] <= 0
        assert r["games_diff_in_set"] <= 0


# --------------------------------------------------------------- LEAK-FREE as-of
def test_leak_free_no_future_set_in_break_proxy():
    # "6-0 0-6 6-3": cumulative break proxy at asof 0 must reflect ONLY set1.
    rows = _rows("6-0 0-6 6-3", 1, drop_terminal=False)
    assert rows[0]["break_pts_converted_diff"] == pytest.approx(4.0)   # 6-0 only
    # asof 1 adds set2 (0-6 -> -4) -> cumulative 0.
    assert rows[1]["break_pts_converted_diff"] == pytest.approx(0.0)
    # asof 2 adds set3 (6-3 -> +1) -> cumulative 1.
    assert rows[2]["break_pts_converted_diff"] == pytest.approx(1.0)


def test_leak_free_values_independent_of_match_winner():
    # The as-of value at idx 0 must NOT depend on who eventually wins the match:
    # set1 6-3 from p1 view is identical whether p1 or p2 wins later.
    a = _rows("6-3 6-1", winner=1, drop_terminal=False)[0]
    # winner=2 means score is p2's: p1 view of set1 is 3-6 -> mirror, NOT leaked.
    b = _rows("6-3 6-1", winner=2, drop_terminal=False)[0]
    assert a["games_diff_in_set"] == pytest.approx(-b["games_diff_in_set"])


# --------------------------------------------------------------- edge cases
def test_single_set_returns_empty():
    assert build_detail_rows("x", parse_score("6-3"), 1) == []


def test_empty_and_bad_winner_returns_empty():
    assert build_detail_rows("x", [], 1) == []
    assert build_detail_rows("x", parse_score("6-3 6-1"), 0) == []
    assert build_detail_rows("x", parse_score("6-3 6-1"), 3) == []


# --------------------------------------------------------------- date column
def test_build_detail_rows_date_column_constant():
    """game_date threads through unchanged on every set-boundary row."""
    sets = parse_score("6-3 6-1")
    rows = build_detail_rows("m", sets, 1, drop_terminal=False, game_date="2015-01-04")
    assert rows
    assert all(r["date"] == "2015-01-04" for r in rows)


def test_build_corpus_carries_date_from_matches_df():
    """build_corpus reads the local matches.parquet 'date' col -- no network needed."""
    syn = pd.DataFrame([
        {"event_id": "m1", "winner": 1, "score": "6-3 6-1",
         "retirement": False, "date": "2015-01-04"},
    ])
    out = build_corpus(syn)
    assert not out.empty
    assert (out["date"] == "2015-01-04").all()


# --------------------------------------------------------------- build_corpus
def test_build_corpus_dtypes_and_keys():
    syn = pd.DataFrame([
        {"event_id": "m1", "winner": 1, "score": "6-3 6-1", "retirement": False},
        {"event_id": "m2", "winner": 2, "score": "6-4 6-3 6-2", "retirement": False},
        {"event_id": "m3", "winner": 1, "score": "6-3", "retirement": False},  # 1 set
        {"event_id": "m4", "winner": 1, "score": "6-0 6-0", "retirement": True},  # ret
    ])
    out = build_corpus(syn)
    assert not out.empty
    assert DETAIL_COLS <= set(out.columns)
    assert out["asof_idx"].dtype.name == "int32"
    for c in ("games_diff_in_set", "sets_diff",
              "break_pts_converted_diff", "serve_holds_streak"):
        assert out[c].dtype.name == "float32"
    # m3 (single set) and m4 (retirement) dropped; m1+m2 remain.
    assert set(out["game_id"]) == {"m1", "m2"}
    # No match-final/terminal row leaked: m1 (2 sets) -> 1 row, m2 (3 sets) -> 2.
    assert (out["game_id"] == "m1").sum() == 1
    assert (out["game_id"] == "m2").sum() == 2
