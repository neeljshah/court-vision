"""domains.tennis.test_elo_walkforward -- hermetic tests for the walk-forward Elo layer.

Tests call the REAL functions from elo_walkforward and elo_core (no stubs).
All tests are deterministic and in-memory -- no network, no disk I/O.

Match DataFrame schema (required columns):
    date, p1_id, p2_id, winner (1=p1, 2=p2), surface, score, round
Optional tiebreak columns used by _sort_key: tour, tourney_id, match_num
NOTE: 'round' is required by _sort_key in elo_core.py (no fallback guard,
unlike tour/tourney_id/match_num which each have an explicit default).
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from domains.tennis.elo_core import BASE_RATING, replay
from domains.tennis.elo_walkforward import (
    elo_state_asof,
    replay_with_snapshots,
    walk_forward_elo,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

P1, P2, P3 = 101, 202, 303
D1 = dt.date(2024, 1, 10)
D2 = dt.date(2024, 1, 20)
D3 = dt.date(2024, 1, 30)


def _row(date, p1, p2, winner, surface="Hard", score="6-3 6-4", round="R32"):
    return {"date": str(date), "p1_id": p1, "p2_id": p2, "winner": winner,
            "surface": surface, "score": score, "round": round}


def _three_matches() -> pd.DataFrame:
    """Three matches across three dates: P1>P2 on D1, P2>P3 on D2, P1>P3 on D3."""
    return pd.DataFrame([
        _row(D1, P1, P2, winner=1),
        _row(D2, P2, P3, winner=1),
        _row(D3, P1, P3, winner=1),
    ])


def _asof_ratings(df, d, pid):
    """Helper: get rating for pid from elo_state_asof(df, d), defaulting to BASE."""
    return elo_state_asof(df, d).ratings.get(pid, BASE_RATING)


# ---------------------------------------------------------------------------
# walk_forward_elo
# ---------------------------------------------------------------------------

class TestWalkForwardElo:

    def test_first_match_pre_ratings_are_base(self):
        """First match must have BASE_RATING for both players (no prior matches)."""
        result = walk_forward_elo(_three_matches())
        first = result.iloc[0]
        assert first["p1_elo"] == pytest.approx(BASE_RATING)
        assert first["p2_elo"] == pytest.approx(BASE_RATING)
        assert first["p1_surface_elo"] == pytest.approx(BASE_RATING)
        assert first["p2_surface_elo"] == pytest.approx(BASE_RATING)

    def test_output_has_expected_columns(self):
        """Output must contain all five added pre-match columns plus original cols."""
        result = walk_forward_elo(_three_matches())
        for col in ("p1_elo", "p2_elo", "p1_surface_elo", "p2_surface_elo", "win_prob_p1",
                    "date", "p1_id", "p2_id", "winner", "surface", "score"):
            assert col in result.columns, f"Missing column: {col}"

    def test_row_count_unchanged(self):
        df = _three_matches()
        assert len(walk_forward_elo(df)) == len(df)

    def test_winner_elo_increases_for_next_appearance(self):
        """After P1 beats P2 on D1, P1's elo at D3 > P2's elo at D2 (P2 lost D1)."""
        result = walk_forward_elo(_three_matches())
        # D2 row: P2 is p1_id
        p2_elo_d2 = result[result["date"] == str(D2)].iloc[0]["p1_elo"]
        # D3 row: P1 is p1_id
        p1_elo_d3 = result[result["date"] == str(D3)].iloc[0]["p1_elo"]
        assert p1_elo_d3 > p2_elo_d2

    def test_leak_free_player_row_uses_only_prior_matches(self):
        """D1 row shows BASE_RATING for P2; D2 row shows updated rating for P2."""
        result = walk_forward_elo(_three_matches())
        # D1: P2 is p2_id, must be BASE_RATING (no prior match)
        assert result[result["date"] == str(D1)].iloc[0]["p2_elo"] == pytest.approx(BASE_RATING)
        # D2: P2 is p1_id, must differ from BASE_RATING (D1 updated P2)
        p2_at_d2 = result[result["date"] == str(D2)].iloc[0]["p1_elo"]
        assert p2_at_d2 != pytest.approx(BASE_RATING)

    def test_win_prob_half_for_equal_players(self):
        """Two fresh players at BASE_RATING must produce win_prob_p1 == 0.5."""
        result = walk_forward_elo(pd.DataFrame([_row(D1, P1, P2, 1)]))
        assert result.iloc[0]["win_prob_p1"] == pytest.approx(0.5, abs=1e-9)

    def test_win_prob_bounded(self):
        result = walk_forward_elo(_three_matches())
        assert (result["win_prob_p1"] > 0).all() and (result["win_prob_p1"] < 1).all()

    def test_walkover_does_not_update_ratings(self):
        """A walkover row is present in output but ratings must not change."""
        df = pd.DataFrame([
            _row(D1, P1, P2, 1, score="W/O"),
            _row(D2, P1, P2, 1),
        ])
        result = walk_forward_elo(df)
        assert len(result) == 2
        d2 = result[result["date"] == str(D2)].iloc[0]
        assert d2["p1_elo"] == pytest.approx(BASE_RATING)
        assert d2["p2_elo"] == pytest.approx(BASE_RATING)


# ---------------------------------------------------------------------------
# elo_state_asof
# ---------------------------------------------------------------------------

class TestEloStateAsof:

    def test_before_all_matches_empty_state(self):
        """Querying before any match must yield empty ratings dict."""
        state = elo_state_asof(_three_matches(), dt.date(2024, 1, 1))
        assert state.ratings == {}
        assert state.n_processed == 0

    def test_equals_replay_strict_before_at_d2(self):
        """asof(full, D2) must equal replay(rows < D2) for all players."""
        df = _three_matches()
        state_asof = elo_state_asof(df, D2)
        subset = df[pd.to_datetime(df["date"]).dt.date < D2]
        state_replay = replay(subset)
        for pid in (P1, P2):
            assert state_asof.ratings.get(pid, BASE_RATING) == pytest.approx(
                state_replay.ratings.get(pid, BASE_RATING), rel=1e-9
            )

    def test_equals_replay_strict_before_at_d3(self):
        """asof(full, D3) must equal replay(rows < D3) -- two prior matches."""
        df = _three_matches()
        state_asof = elo_state_asof(df, D3)
        subset = df[pd.to_datetime(df["date"]).dt.date < D3]
        state_replay = replay(subset)
        for pid in (P1, P2, P3):
            assert state_asof.ratings.get(pid, BASE_RATING) == pytest.approx(
                state_replay.ratings.get(pid, BASE_RATING), rel=1e-9
            )

    def test_excludes_match_on_exactly_d(self):
        """Match on exactly date D must be excluded (strict-before contract)."""
        state = elo_state_asof(_three_matches(), D1)
        assert state.ratings.get(P1, BASE_RATING) == pytest.approx(BASE_RATING)
        assert state.ratings.get(P2, BASE_RATING) == pytest.approx(BASE_RATING)

    def test_surface_ratings_equal_replay(self):
        """Surface ratings in asof must also match replay(strict-before)."""
        df = _three_matches()
        state_asof = elo_state_asof(df, D3)
        subset = df[pd.to_datetime(df["date"]).dt.date < D3]
        state_replay = replay(subset)
        for pid in (P1, P2):
            key = (pid, "Hard")
            assert state_asof.surface.get(key) == pytest.approx(
                state_replay.surface.get(key), rel=1e-9
            )

    def test_n_processed_matches_replay(self):
        """n_processed counter must match replay's count at D3."""
        df = _three_matches()
        assert elo_state_asof(df, D3).n_processed == replay(
            df[pd.to_datetime(df["date"]).dt.date < D3]
        ).n_processed


# ---------------------------------------------------------------------------
# replay_with_snapshots
# ---------------------------------------------------------------------------

class TestReplayWithSnapshots:

    def test_snapshots_equal_asof_at_two_dates(self):
        """Snapshot at D2 and D3 must equal elo_state_asof at each date."""
        df = _three_matches()
        snaps = replay_with_snapshots(df, [D2, D3])
        for d in (D2, D3):
            expected = elo_state_asof(df, d)
            actual = snaps[d]
            for pid in (P1, P2, P3):
                assert actual.ratings.get(pid, BASE_RATING) == pytest.approx(
                    expected.ratings.get(pid, BASE_RATING), rel=1e-9
                ), f"snapshots[{d}] pid={pid}"

    def test_snapshot_before_all_matches_empty(self):
        before = dt.date(2024, 1, 1)
        snaps = replay_with_snapshots(_three_matches(), [before])
        assert snaps[before].ratings == {}
        assert snaps[before].n_processed == 0

    def test_snapshot_after_all_matches_equals_full_replay(self):
        """Snapshot at a date after all matches must equal replay of full dataset."""
        df = _three_matches()
        after = dt.date(2024, 12, 31)
        snaps = replay_with_snapshots(df, [after])
        state_full = replay(df)
        for pid in (P1, P2, P3):
            assert snaps[after].ratings.get(pid, BASE_RATING) == pytest.approx(
                state_full.ratings.get(pid, BASE_RATING), rel=1e-9
            )

    def test_all_requested_dates_present(self):
        snaps = replay_with_snapshots(_three_matches(), [D1, D2, D3])
        for d in (D1, D2, D3):
            assert d in snaps

    def test_n_processed_matches_asof(self):
        df = _three_matches()
        snaps = replay_with_snapshots(df, [D2, D3])
        for d in (D2, D3):
            expected = elo_state_asof(df, d)
            assert snaps[d].n_processed == expected.n_processed

    def test_surface_ratings_match_asof(self):
        df = _three_matches()
        snaps = replay_with_snapshots(df, [D3])
        expected = elo_state_asof(df, D3)
        for pid in (P1, P2):
            key = (pid, "Hard")
            assert snaps[D3].surface.get(key) == pytest.approx(
                expected.surface.get(key), rel=1e-9
            )
