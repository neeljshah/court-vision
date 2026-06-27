"""Per-file tests for tennis in-game state spine (OFFLINE, SYNTHETIC only).

Tests the frozen schema and invariants for tennis_states parquets:
  - Schema: all required cols present with correct dtypes
  - state_diff: signed by player1 (winner has positive final state_diff)
  - frac_elapsed: in [0,1] and strictly monotone within a match
  - p0: in [0,1], constant across snapshots, invalid values rejected
  - outcome: 1=p1 won, consistent within match
  - LEAK-FREE: state rows use only games up to asof_idx; no future sets

NO file I/O.  NO network.  SYNTHETIC data only.

Run (per-file ONLY -- full pytest freezes this box):
  cd /c/Users/neelj/nba-ai-system && \\
    python -m pytest tests/platformkit/test_tennis_states.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.tennis.ingest_ingame_states import (
    build_snapshots,
    parse_score,
    set_winner,
)

REQUIRED_COLS = {"sport", "game_id", "asof_idx", "state_diff", "frac_elapsed", "p0", "outcome"}


def _snaps(score: str, winner: int, p0: float = 0.65) -> list[dict]:
    # drop_terminal=False here: these tests assert the PURE per-set-boundary
    # reconstruction GEOMETRY (state_diff / frac_elapsed / game_score math),
    # which includes the match-ending row.  The served/gate corpus DROPS that
    # terminal settled row -- exercised separately in the LIVE-ONLY block below.
    sets = parse_score(score)
    assert sets is not None
    return build_snapshots("test-match", sets, winner, p0=p0, surface="Hard",
                           drop_terminal=False)


def _live_snaps(score: str, winner: int, p0: float = 0.65) -> list[dict]:
    """Default (served) reconstruction: terminal settled row DROPPED."""
    sets = parse_score(score)
    assert sets is not None
    return build_snapshots("test-match", sets, winner, p0=p0, surface="Hard")


# ---------------------------------------------------------------------------
# parse_score
# ---------------------------------------------------------------------------

def test_parse_score_simple():
    assert parse_score("6-3 6-1") == [(6, 3), (6, 1)]


def test_parse_score_tiebreak():
    assert parse_score("6-7(5) 7-6(3) 6-1") == [(6, 7), (7, 6), (6, 1)]


def test_parse_score_five_sets():
    assert parse_score("4-6 6-3 2-6 6-0 7-5") == [(4, 6), (6, 3), (2, 6), (6, 0), (7, 5)]


def test_parse_score_none_on_bad_input():
    assert parse_score("") is None
    assert parse_score(None) is None  # type: ignore[arg-type]
    assert parse_score("ABD") is None
    assert parse_score("W/O") is None


# ---------------------------------------------------------------------------
# set_winner
# ---------------------------------------------------------------------------

def test_set_winner_standard():
    assert set_winner(6, 3) == 1
    assert set_winner(2, 6) == 2
    assert set_winner(7, 6) == 1
    assert set_winner(6, 7) == 2
    assert set_winner(3, 2) is None  # mid-set


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_schema_required_cols_and_sport():
    rows = _snaps("6-3 6-1", winner=1, p0=0.7)
    assert rows
    assert REQUIRED_COLS <= set(rows[0].keys())
    assert {"set_score", "game_score", "surface"} <= set(rows[0].keys())
    assert all(r["sport"] == "tennis" for r in rows)


def test_schema_row_counts():
    assert len(_snaps("6-3 6-1", 1)) == 2           # 2-set match
    assert len(_snaps("4-6 6-3 6-4", 1)) == 3       # 3-setter
    assert len(_snaps("6-3 4-6 6-2 3-6 6-4", 1)) == 5  # 5-setter


def test_schema_asof_idx_sequential():
    rows = _snaps("4-6 6-3 6-4", 1)
    assert [r["asof_idx"] for r in rows] == [0, 1, 2]


# ---------------------------------------------------------------------------
# state_diff
# ---------------------------------------------------------------------------

def test_state_diff_p1_winner_final_positive():
    assert _snaps("6-3 6-1", 1)[-1]["state_diff"] > 0


def test_state_diff_p2_winner_final_negative():
    # Sackmann scores are WINNER-first: "6-3 6-1" with winner=2 means p2 (the
    # winner) took 6-3, 6-1 -> from p1's STABLE perspective p1 lost both sets,
    # so p1's final state_diff must be NEGATIVE.
    assert _snaps("6-3 6-1", 2)[-1]["state_diff"] < 0


def test_state_diff_monotone_dominant_win():
    diffs = [r["state_diff"] for r in _snaps("6-1 6-0", 1)]
    assert diffs[1] > diffs[0]


def test_state_diff_tied_sets_bounded():
    rows = _snaps("6-3 4-6 6-4", 1)
    assert rows[0]["state_diff"] > 0        # p1 up after set1
    assert abs(rows[1]["state_diff"]) < 1.0  # tied sets, small game diff


def test_state_diff_five_set_p1_wins():
    assert _snaps("6-3 4-6 6-2 3-6 6-4", 1)[-1]["state_diff"] > 0


# ---------------------------------------------------------------------------
# STABLE IDENTITY -- p1 is p1_id, NOT the winner.  Score strings are
# winner-first; the reconstruction must re-orient to p1's perspective so the
# signal (state_diff) tracks p1's lead and is NOT collapsed to winner-perspective.
# This is the regression test for the alignment bug (corr~0, leader-win~50%).
# ---------------------------------------------------------------------------

def test_p1_stable_identity_loser_state_diff_negative():
    # Same on-court score "6-3 6-4" interpreted from the two stable identities.
    # winner=1: p1 WON it      -> p1 leads throughout, final state_diff > 0, outcome 1
    # winner=2: p1 LOST it     -> p1 trails throughout, final state_diff < 0, outcome 0
    # The two MUST be mirror images: signal preserved, not winner-collapsed.
    won = _snaps("6-3 6-4", winner=1)
    lost = _snaps("6-3 6-4", winner=2)

    assert all(r["outcome"] == 1 for r in won)
    assert all(r["outcome"] == 0 for r in lost)

    # p1-as-loser: state_diff negative at every as-of point (p1 always trailing)
    assert all(r["state_diff"] < 0 for r in lost), [r["state_diff"] for r in lost]
    assert all(r["state_diff"] > 0 for r in won), [r["state_diff"] for r in won]

    # Exact mirror: lost[i].state_diff == -won[i].state_diff
    for rw, rl in zip(won, lost):
        assert rl["state_diff"] == pytest.approx(-rw["state_diff"], abs=1e-5)


def test_p1_loser_trails_then_loses_signal_preserved():
    # p1 loses a 3-setter: winner-first score "4-6 6-3 6-2" with winner=2 means
    # the WINNER (p2) took 4-6,6-3,6-2.  From p1's perspective p1 went 6-4 (up),
    # then 3-6, then 2-6 -> ends trailing -2 sets.  Signal must NOT collapse:
    # outcome=0 and final state_diff clearly NEGATIVE.
    rows = _snaps("4-6 6-3 6-2", winner=2)
    assert all(r["outcome"] == 0 for r in rows)
    assert rows[0]["state_diff"] > 0     # p1 won the FIRST set (6-4 from p1 view)
    assert rows[-1]["state_diff"] < 0    # p1 lost the match overall


# ---------------------------------------------------------------------------
# frac_elapsed
# ---------------------------------------------------------------------------

def test_frac_elapsed_in_0_1():
    for r in _snaps("6-3 6-1", 1):
        assert 0.0 <= r["frac_elapsed"] <= 1.0


def test_frac_elapsed_strictly_increases():
    fracs = [r["frac_elapsed"] for r in _snaps("4-6 6-3 6-4", 1)]
    assert all(fracs[i] < fracs[i + 1] for i in range(len(fracs) - 1))


def test_frac_elapsed_final_is_1():
    assert _snaps("6-3 6-1", 1)[-1]["frac_elapsed"] == pytest.approx(1.0)


def test_frac_elapsed_after_set1_correct():
    # "6-3 6-1": set1=9 games, set2=7 games, total=16; frac=9/16
    rows = _snaps("6-3 6-1", 1)
    assert rows[0]["frac_elapsed"] == pytest.approx(9.0 / 16.0)


# ---------------------------------------------------------------------------
# p0
# ---------------------------------------------------------------------------

def test_p0_in_0_1():
    assert all(0.0 <= r["p0"] <= 1.0 for r in _snaps("6-3 6-1", 1, p0=0.72))


def test_p0_constant_within_match():
    p0s = [r["p0"] for r in _snaps("4-6 6-3 6-4", 1, p0=0.6)]
    assert len(set(p0s)) == 1


def test_p0_invalid_rejected():
    sets = parse_score("6-3 6-1")
    assert build_snapshots("x", sets, 1, p0=1.5, surface="Hard") == []
    assert build_snapshots("x", sets, 1, p0=-0.1, surface="Hard") == []


# ---------------------------------------------------------------------------
# outcome
# ---------------------------------------------------------------------------

def test_outcome_p1_win_is_1():
    assert all(r["outcome"] == 1 for r in _snaps("6-3 6-1", 1))


def test_outcome_p2_win_is_0():
    # Winner-first score; winner=2 -> p1 lost -> outcome 0 throughout.
    assert all(r["outcome"] == 0 for r in _snaps("6-3 6-1", 2))


def test_outcome_consistent_within_match():
    rows = _snaps("4-6 6-3 6-4", 1)
    assert len({r["outcome"] for r in rows}) == 1


# ---------------------------------------------------------------------------
# LEAK-FREE
# ---------------------------------------------------------------------------

def test_leak_free_state_diff_values():
    # "6-0 0-6 6-3": after set1 p1 leads (state_diff=1.5)
    # after set2 tied 1-1 cumul games 6-6 (state_diff=0.0)
    rows = _snaps("6-0 0-6 6-3", 1)
    assert rows[0]["state_diff"] == pytest.approx(1.5, abs=1e-4)
    assert rows[1]["state_diff"] == pytest.approx(0.0, abs=1e-4)
    assert "6-3" not in rows[1]["game_score"]  # set3 not visible at asof=1


def test_game_score_excludes_future_sets():
    rows = _snaps("6-3 4-6 6-4", 1)
    assert rows[0]["game_score"] == "6-3"
    assert rows[1]["game_score"] == "6-3,4-6"
    assert rows[2]["game_score"] == "6-3,4-6,6-4"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_sets_returns_empty():
    assert build_snapshots("x", [], 1, p0=0.5, surface="Hard") == []


def test_single_set_returns_empty():
    sets = parse_score("6-3")
    assert build_snapshots("x", sets, 1, p0=0.5, surface="Hard") == []


def test_invalid_winner_returns_empty():
    sets = parse_score("6-3 6-1")
    assert build_snapshots("x", sets, 0, p0=0.5, surface="Hard") == []
    assert build_snapshots("x", sets, 3, p0=0.5, surface="Hard") == []


# ---------------------------------------------------------------------------
# build_corpus DataFrame dtypes (stub Elo)
# ---------------------------------------------------------------------------

def test_dataframe_dtypes_after_build_corpus():
    """build_corpus with a fake Elo returns correct dtypes."""
    import domains.tennis.elo_walkforward as ewf
    from domains.tennis.ingest_ingame_states import build_corpus

    orig = ewf.walk_forward_elo

    def _fake(df):
        out = df.copy()
        for c in ("p1_elo", "p2_elo", "p1_surface_elo", "p2_surface_elo"):
            out[c] = 1500.0
        out["win_prob_p1"] = 0.55
        return out

    ewf.walk_forward_elo = _fake
    try:
        syn = pd.DataFrame([
            {"event_id": "m1", "date": "2022-01-10", "p1_id": 1, "p2_id": 2,
             "winner": 1, "surface": "Hard", "score": "6-3 6-1",
             "best_of": 3, "retirement": False},
            {"event_id": "m2", "date": "2022-01-11", "p1_id": 1, "p2_id": 3,
             "winner": 2, "surface": "Clay", "score": "6-4 6-3",
             "best_of": 3, "retirement": False},
        ])
        result = build_corpus(syn)
        assert not result.empty
        for col in REQUIRED_COLS:
            assert col in result.columns
        assert result["outcome"].dtype.name in ("int8", "int32", "int64")
        assert result["asof_idx"].dtype.name in ("int32", "int64")
        assert result["frac_elapsed"].between(0.0, 1.0).all()
        assert result["p0"].between(0.0, 1.0).all()
        # LIVE-ONLY: build_corpus feeds the in-game gate POOL.  It must NOT leak
        # the settled match-ending row (frac>=1.0) -- those decided rows have
        # sign(state_diff)==outcome ~100% and falsely inflate base BSS.
        assert (result["frac_elapsed"] < 1.0).all(), \
            "settled frac>=1.0 rows leaked into the gate pool"
    finally:
        ewf.walk_forward_elo = orig


# ---------------------------------------------------------------------------
# LIVE-ONLY gate pool -- terminal (settled) rows MUST be dropped by default.
# Regression guard for the 2026-06-18 HONESTY re-check: ~37.9% ATP / 43.1% WTA
# of states were SETTLED (frac==1.0, sign(state_diff)==outcome ~99.9%); those
# decided-match rows are NOT live in-game states and were propping up base BSS.
# ---------------------------------------------------------------------------

def test_live_default_drops_terminal_row():
    # "6-3 6-1": raw geometry has 2 rows; the 2nd (frac==1.0) is the match end.
    # Default (served) reconstruction keeps ONLY the genuinely-live first row.
    raw = _snaps("6-3 6-1", 1)
    live = _live_snaps("6-3 6-1", 1)
    assert len(raw) == 2
    assert len(live) == 1
    assert live[0]["frac_elapsed"] < 1.0


def test_live_no_frac_ge_1_any_match_length():
    for score, winner in [("6-3 6-1", 1), ("4-6 6-3 6-4", 1),
                          ("6-3 4-6 6-2 3-6 6-4", 1), ("6-3 6-4", 2)]:
        live = _live_snaps(score, winner)
        assert all(r["frac_elapsed"] < 1.0 for r in live), \
            f"settled frac>=1.0 row leaked for {score!r} w={winner}"


def test_live_drops_exactly_one_terminal_per_match():
    for score, winner in [("6-3 6-1", 1), ("4-6 6-3 6-4", 1),
                          ("6-3 4-6 6-2 3-6 6-4", 1)]:
        raw = _snaps(score, winner)
        live = _live_snaps(score, winner)
        assert len(live) == len(raw) - 1  # exactly the match-ending row removed


def test_live_two_set_match_keeps_one_live_row():
    # A straight-sets win still yields one genuinely-undecided live state
    # (after set 1, before the match-ending set 2).
    live = _live_snaps("6-3 6-1", 1)
    assert len(live) == 1
    assert live[0]["set_score"] == "1-0"
