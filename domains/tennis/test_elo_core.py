"""Per-file tests for domains/tennis/elo_core.py.

Run with:
    python -m pytest domains/tennis/test_elo_core.py -q

Covers: _expected, _k, _is_walkover, prob, replay.
No network, no data files -- all inputs constructed in-memory.
ASCII-only identifiers and strings.
"""
from __future__ import annotations

import datetime as dt
import math

import pandas as pd
import pytest

from domains.tennis.elo_core import (
    BASE_RATING,
    K_EXPONENT,
    K_NUMERATOR,
    K_OFFSET,
    SURFACE_BLEND,
    EloState,
    _expected,
    _is_walkover,
    _k,
    prob,
    replay,
)


# ---------------------------------------------------------------------------
# _expected
# ---------------------------------------------------------------------------

class TestExpected:
    def test_equal_ratings_half(self):
        assert _expected(1500.0, 1500.0) == pytest.approx(0.5)

    def test_symmetry(self):
        for a, b in [(1500, 1600), (1200, 1800), (1000, 1000)]:
            assert _expected(float(a), float(b)) + _expected(float(b), float(a)) == pytest.approx(1.0)

    def test_monotone_in_gap(self):
        base = 1500.0
        probs = [_expected(base + g, base) for g in [0, 50, 100, 200, 400]]
        for i in range(len(probs) - 1):
            assert probs[i] < probs[i + 1]

    def test_bounded(self):
        for r1, r2 in [(500, 2500), (2500, 500), (1500, 1500)]:
            e = _expected(float(r1), float(r2))
            assert 0.0 < e < 1.0

    def test_known_400_gap(self):
        # 1 / (1 + 10^(-1)) = 10/11
        assert _expected(1900.0, 1500.0) == pytest.approx(10.0 / 11.0, rel=1e-6)


# ---------------------------------------------------------------------------
# _k
# ---------------------------------------------------------------------------

class TestK:
    def test_formula_at_zero(self):
        assert _k(0) == pytest.approx(K_NUMERATOR / (K_OFFSET ** K_EXPONENT))

    def test_formula_at_100(self):
        m = 100
        assert _k(m) == pytest.approx(K_NUMERATOR / ((m + K_OFFSET) ** K_EXPONENT))

    def test_decays_with_match_count(self):
        assert _k(0) > _k(10) > _k(100) > _k(500)

    def test_always_positive(self):
        for m in [0, 1, 10, 100, 1000]:
            assert _k(m) > 0.0


# ---------------------------------------------------------------------------
# _is_walkover
# ---------------------------------------------------------------------------

class TestIsWalkover:
    def test_wo_slash(self):
        assert _is_walkover("W/O") is True

    def test_wo_in_longer_string(self):
        assert _is_walkover("6-4 W/O") is True

    def test_walkover_word(self):
        assert _is_walkover("Walkover") is True

    def test_normal_score(self):
        assert _is_walkover("6-3 6-4") is False

    def test_non_string(self):
        assert _is_walkover(None) is False
        assert _is_walkover(float("nan")) is False

    def test_empty_string(self):
        assert _is_walkover("") is False


# ---------------------------------------------------------------------------
# prob
# ---------------------------------------------------------------------------

class TestProb:
    def _state2(self, r1: float, r2: float, p1: int = 1, p2: int = 2) -> EloState:
        s = EloState()
        s.ratings[p1] = r1
        s.ratings[p2] = r2
        return s

    def test_bounded(self):
        p = prob(self._state2(1500.0, 1500.0), 1, 2, "Hard")
        assert 0.0 < p < 1.0

    def test_equal_ratings_half(self):
        p = prob(self._state2(1500.0, 1500.0), 1, 2, "Clay")
        assert p == pytest.approx(0.5, abs=1e-9)

    def test_higher_rated_above_half(self):
        assert prob(self._state2(1800.0, 1400.0), 1, 2, "Grass") > 0.5

    def test_lower_rated_below_half(self):
        assert prob(self._state2(1300.0, 1700.0), 1, 2, "Hard") < 0.5

    def test_symmetry(self):
        s = self._state2(1620.0, 1480.0, p1=5, p2=6)
        assert prob(s, 5, 6, "Clay") + prob(s, 6, 5, "Clay") == pytest.approx(1.0)

    def test_unknown_players_half(self):
        p = prob(EloState(), 999, 1000, "Hard")
        assert p == pytest.approx(0.5, abs=1e-9)

    def test_surface_blend_shifts_prob(self):
        # Equal overall; p1 has +200 surface advantage on Clay
        s = EloState()
        s.ratings[1] = 1500.0
        s.ratings[2] = 1500.0
        s.surface[(1, "Clay")] = 1600.0
        s.surface[(2, "Clay")] = 1400.0
        # blended diff = (1-0.3)*0 + 0.3*200 = 60
        expected_p = 1.0 / (1.0 + 10.0 ** (-60.0 / 400.0))
        assert prob(s, 1, 2, "Clay") == pytest.approx(expected_p, rel=1e-9)


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------

def _make_matches() -> pd.DataFrame:
    """Three in-memory matches for replay tests."""
    return pd.DataFrame([
        {"date": dt.date(2024, 1, 1), "p1_id": 1, "p2_id": 2, "winner": 1,
         "surface": "Hard", "score": "6-3 6-4", "round": "R64"},
        {"date": dt.date(2024, 1, 2), "p1_id": 1, "p2_id": 2, "winner": 2,
         "surface": "Hard", "score": "4-6 6-3 7-5", "round": "R32"},
        {"date": dt.date(2024, 1, 3), "p1_id": 1, "p2_id": 2, "winner": 1,
         "surface": "Clay", "score": "6-1 6-2", "round": "QF"},
    ])


class TestReplay:
    def test_empty_returns_zero_state(self):
        df = pd.DataFrame(columns=["date", "p1_id", "p2_id", "winner", "surface", "score", "round"])
        state = replay(df)
        assert state.n_processed == 0 and state.ratings == {}

    def test_before_first_match_no_ratings(self):
        state = replay(_make_matches(), until=dt.date(2024, 1, 1))
        assert state.n_processed == 0
        assert state.ratings.get(1, BASE_RATING) == BASE_RATING

    def test_winner_rises_after_first_match(self):
        state = replay(_make_matches(), until=dt.date(2024, 1, 2))
        assert state.n_processed == 1
        assert state.ratings[1] > BASE_RATING
        assert state.ratings[2] < BASE_RATING

    def test_counts_equal_matches_processed(self):
        state = replay(_make_matches())
        assert state.counts[1] == 3 and state.counts[2] == 3
        assert state.n_processed == 3

    def test_until_excludes_cutoff_date(self):
        state = replay(_make_matches(), until=dt.date(2024, 1, 3))
        assert state.n_processed == 2

    def test_walkover_skips_rating_update(self):
        df = pd.DataFrame([
            {"date": dt.date(2024, 2, 1), "p1_id": 3, "p2_id": 4,
             "winner": 1, "surface": "Hard", "score": "W/O", "round": "R64"},
        ])
        state = replay(df)
        assert state.n_processed == 0
        assert 3 not in state.ratings and 4 not in state.ratings
        assert state.last_date == dt.date(2024, 2, 1)

    def test_surface_counts_per_surface(self):
        state = replay(_make_matches())
        assert state.surface_counts[(1, "Hard")] == 2
        assert state.surface_counts[(1, "Clay")] == 1

    def test_last_date_is_most_recent(self):
        state = replay(_make_matches())
        assert state.last_date == dt.date(2024, 1, 3)
