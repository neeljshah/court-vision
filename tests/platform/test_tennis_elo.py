"""tests/platform/test_tennis_elo.py — hermetic offline tests for domains/tennis/elo.py.

Assertions:
 1. Pre-match ratings use only prior matches (first match for a player == BASE_RATING).
 2. Win probability in (0, 1) and favors the higher-rated player.
 3. TRUNCATION-INVARIANCE: elo_state_asof(full_df, D) == replay(full_df[:before_D]).
 4. Determinism: same input → same output.
 5. Walkovers do not update ratings.
 6. Surface-blend: a clay specialist's clay prob > hard prob against the same opponent.
 7. prob() symmetry: prob(a,b) + prob(b,a) == 1.0 exactly.
 8. Three-match hand-computed Elo values verified to 1e-12.

No network access, no file I/O, no external fixtures required.
"""
from __future__ import annotations

import datetime as dt
import math

import pandas as pd
import pytest

from domains.tennis.elo import (
    BASE_RATING,
    EloState,
    elo_state_asof,
    prob,
    replay,
    walk_forward_elo,
    _k,
    _expected,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a match DataFrame from a list of row dicts.

    Minimal required keys: date (dt.date), p1_id, p2_id, winner (1|2), surface, score.
    Optional keys used for sort tiebreaking are supplied where relevant.
    """
    df = pd.DataFrame(rows)
    return df


def _base_row(
    date: dt.date,
    p1_id: int,
    p2_id: int,
    winner: int,
    surface: str = "Hard",
    score: str = "6-3 6-4",
    tour: str = "atp",
    tourney_id: str = "100",
    round_: str = "R32",
    match_num: int = 1,
) -> dict:
    return {
        "date": date,
        "p1_id": p1_id,
        "p2_id": p2_id,
        "winner": winner,
        "surface": surface,
        "score": score,
        "tour": tour,
        "tourney_id": tourney_id,
        "round": round_,
        "match_num": match_num,
    }


# ---------------------------------------------------------------------------
# Synthetic match sequence — 20 matches, 6 players, 2 "seasons"
# Player IDs: 100..105  (all fictional; >= 900000 reserved for ingest fixtures)
# ---------------------------------------------------------------------------

P = {i: 100 + i for i in range(6)}   # P[0]=100, P[1]=101, ...

SEASON1_START = dt.date(2023, 1, 15)
SEASON2_START = dt.date(2024, 3, 10)


def _build_synthetic_20() -> pd.DataFrame:
    rows = [
        # Season 1 — Hard courts
        _base_row(SEASON1_START,                     P[0], P[1], 1, "Hard", match_num=1),
        _base_row(SEASON1_START,                     P[2], P[3], 2, "Hard", match_num=2),
        _base_row(dt.date(2023, 1, 20),              P[0], P[2], 1, "Hard"),
        _base_row(dt.date(2023, 1, 22),              P[1], P[3], 1, "Hard"),
        _base_row(dt.date(2023, 2, 5),               P[4], P[5], 2, "Hard"),
        _base_row(dt.date(2023, 2, 7),               P[0], P[4], 1, "Hard"),
        # Clay swing
        _base_row(dt.date(2023, 4, 10),              P[1], P[2], 1, "Clay"),
        _base_row(dt.date(2023, 4, 12),              P[3], P[5], 2, "Clay"),
        _base_row(dt.date(2023, 5,  1),              P[0], P[3], 2, "Clay"),
        _base_row(dt.date(2023, 5,  3),              P[4], P[1], 1, "Clay"),
        # Walkover — should NOT update ratings
        _base_row(dt.date(2023, 6, 15),              P[2], P[5], 1, "Grass", score="W/O"),
        # Grass
        _base_row(dt.date(2023, 6, 20),              P[0], P[5], 1, "Grass"),
        _base_row(dt.date(2023, 7,  1),              P[1], P[4], 2, "Grass"),
        # Season 2 — Hard
        _base_row(SEASON2_START,                     P[2], P[0], 1, "Hard"),
        _base_row(dt.date(2024, 3, 12),              P[3], P[1], 2, "Hard"),
        _base_row(dt.date(2024, 4,  5),              P[5], P[4], 1, "Hard"),
        # Clay
        _base_row(dt.date(2024, 5, 20),              P[0], P[1], 2, "Clay"),
        _base_row(dt.date(2024, 5, 22),              P[2], P[4], 1, "Clay"),
        _base_row(dt.date(2024, 6,  8),              P[3], P[5], 1, "Clay"),
        _base_row(dt.date(2024, 7, 10),              P[0], P[5], 1, "Hard"),
    ]
    return _make_df(rows)


FULL_DF = _build_synthetic_20()
# Mid-point cut: after season 1, before season 2 — 13 matches qualify
MID_DATE = dt.date(2024, 1, 1)


# ---------------------------------------------------------------------------
# 1. Pre-match ratings for first appearances == BASE_RATING
# ---------------------------------------------------------------------------

class TestFirstMatchBaseRating:
    def test_first_match_p1_base(self) -> None:
        result = walk_forward_elo(FULL_DF)
        # First match in sorted order involves P[0] and P[1].
        # Both appear for the first time → both pre-match Elos == BASE_RATING.
        first = result.iloc[0]
        assert first["p1_elo"] == BASE_RATING, (
            f"First-match p1_elo should be {BASE_RATING}, got {first['p1_elo']}"
        )
        assert first["p2_elo"] == BASE_RATING, (
            f"First-match p2_elo should be {BASE_RATING}, got {first['p2_elo']}"
        )

    def test_first_match_surface_elos_base(self) -> None:
        result = walk_forward_elo(FULL_DF)
        first = result.iloc[0]
        # Surface Elo for a player with no prior surface matches == their overall Elo
        # which is also BASE_RATING at that point.
        assert first["p1_surface_elo"] == BASE_RATING
        assert first["p2_surface_elo"] == BASE_RATING

    def test_new_player_mid_sequence(self) -> None:
        """P[4] and P[5] debut at row index 4 — their first Elos must be BASE_RATING."""
        result = walk_forward_elo(FULL_DF)
        p4_debut = result[result["p1_id"] == P[4]].iloc[0]
        assert p4_debut["p1_elo"] == BASE_RATING, (
            "P[4] first pre-match Elo must be BASE_RATING"
        )


# ---------------------------------------------------------------------------
# 2. Win probability in (0, 1) and favors higher-rated player
# ---------------------------------------------------------------------------

class TestWinProbability:
    def test_win_prob_in_open_interval(self) -> None:
        result = walk_forward_elo(FULL_DF)
        wp = result["win_prob_p1"]
        assert (wp > 0.0).all(), "win_prob_p1 must be > 0 for every match"
        assert (wp < 1.0).all(), "win_prob_p1 must be < 1 for every match"

    def test_higher_elo_favored(self) -> None:
        """After several matches some players will diverge from 1500.
        Build a state where P[0] is known to have won more matches, then
        confirm the win probability is correct in direction."""
        # Build a tiny frame where P[0] wins 5 straight against fresh opponents
        rows = [
            _base_row(dt.date(2022, 1, i + 1), P[0], 200 + i, 1)
            for i in range(5)
        ]
        small_df = _make_df(rows)
        result = walk_forward_elo(small_df)
        # After 5 wins P[0]'s Elo > 1500; the 6th match's pre-match Elo will show this.
        # Let's check the last row: p1 = P[0] after 4 wins (5th match pre-match)
        last = result.iloc[-1]
        # P[0] has won 4 prior matches → rating > BASE_RATING
        assert last["p1_elo"] > BASE_RATING, "Winner's Elo must rise above BASE_RATING"
        assert last["win_prob_p1"] > 0.5, "Higher-rated player must be favored"

    def test_prob_symmetry_via_state(self) -> None:
        """prob(state, a, b, s) + prob(state, b, a, s) must equal exactly 1.0."""
        state = EloState(
            ratings={P[0]: 1600.0, P[1]: 1450.0},
            surface={(P[0], "Clay"): 1620.0, (P[1], "Clay"): 1430.0},
        )
        p_ab = prob(state, P[0], P[1], "Clay")
        p_ba = prob(state, P[1], P[0], "Clay")
        assert p_ab + p_ba == 1.0, (
            f"prob(a,b)+prob(b,a) must be exactly 1.0; got {p_ab + p_ba}"
        )


# ---------------------------------------------------------------------------
# 3. TRUNCATION-INVARIANCE (the binding leak-free check)
# ---------------------------------------------------------------------------

class TestTruncationInvariance:
    def _states_equal(self, a: EloState, b: EloState) -> None:
        assert a.ratings == b.ratings, (
            f"ratings differ:\n  a={a.ratings}\n  b={b.ratings}"
        )
        assert a.surface == b.surface, "surface ratings differ"
        assert a.counts == b.counts, "counts differ"
        assert a.surface_counts == b.surface_counts, "surface_counts differ"
        assert a.n_processed == b.n_processed, (
            f"n_processed differs: {a.n_processed} vs {b.n_processed}"
        )
        assert a.last_date == b.last_date, (
            f"last_date differs: {a.last_date} vs {b.last_date}"
        )

    def test_truncation_invariance_mid_history(self) -> None:
        """Core invariant: elo_state_asof(full_df, D) == replay(truncated_df).

        Both paths must produce EXACTLY equal EloState (same float bits).
        """
        # Path A: replay full corpus filtered to before MID_DATE
        state_a = elo_state_asof(FULL_DF, MID_DATE)

        # Path B: physically filter the DataFrame first, then replay with no cutoff
        dates = pd.to_datetime(FULL_DF["date"]).dt.date
        truncated = FULL_DF[dates < MID_DATE].copy()
        state_b = replay(truncated)

        self._states_equal(state_a, state_b)

    def test_truncation_invariance_early_date(self) -> None:
        """Invariant holds at an early cutoff (few matches processed)."""
        early = dt.date(2023, 2, 1)
        state_a = elo_state_asof(FULL_DF, early)
        dates = pd.to_datetime(FULL_DF["date"]).dt.date
        truncated = FULL_DF[dates < early].copy()
        state_b = replay(truncated)
        self._states_equal(state_a, state_b)

    def test_truncation_invariance_late_date(self) -> None:
        """Invariant holds near the end of the corpus."""
        late = dt.date(2024, 6, 1)
        state_a = elo_state_asof(FULL_DF, late)
        dates = pd.to_datetime(FULL_DF["date"]).dt.date
        truncated = FULL_DF[dates < late].copy()
        state_b = replay(truncated)
        self._states_equal(state_a, state_b)

    def test_truncation_before_first_match(self) -> None:
        """Cutoff before any match → empty state."""
        before_all = dt.date(2020, 1, 1)
        state = elo_state_asof(FULL_DF, before_all)
        assert state.ratings == {}, "No ratings before any match"
        assert state.n_processed == 0

    def test_truncation_after_last_match(self) -> None:
        """Cutoff after all matches → same as full replay."""
        after_all = dt.date(2030, 1, 1)
        state_a = elo_state_asof(FULL_DF, after_all)
        state_b = replay(FULL_DF)
        assert state_a.ratings == state_b.ratings
        assert state_a.n_processed == state_b.n_processed


# ---------------------------------------------------------------------------
# 4. Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_walk_forward_deterministic(self) -> None:
        result1 = walk_forward_elo(FULL_DF)
        result2 = walk_forward_elo(FULL_DF)
        pd.testing.assert_frame_equal(result1, result2)

    def test_replay_deterministic(self) -> None:
        s1 = replay(FULL_DF)
        s2 = replay(FULL_DF)
        assert s1.ratings == s2.ratings
        assert s1.surface == s2.surface
        assert s1.counts == s2.counts
        assert s1.n_processed == s2.n_processed

    def test_unsorted_input_deterministic(self) -> None:
        """Shuffled input must produce the same result as sorted input."""
        shuffled = FULL_DF.sample(frac=1, random_state=42).reset_index(drop=True)
        r1 = walk_forward_elo(FULL_DF)
        r2 = walk_forward_elo(shuffled)
        # Both outputs are sorted chronologically — compare sorted by index key
        pd.testing.assert_frame_equal(
            r1.reset_index(drop=True),
            r2.reset_index(drop=True),
        )


# ---------------------------------------------------------------------------
# 5. Walkovers do not update ratings
# ---------------------------------------------------------------------------

class TestWalkoverSkip:
    def test_walkover_does_not_change_ratings(self) -> None:
        """Build a sequence: match, walkover, match.
        The state after match+walkover must equal replay(just_the_first_match)."""
        rows = [
            _base_row(dt.date(2023, 1, 1), P[0], P[1], 1, "Hard"),
            _base_row(dt.date(2023, 1, 5), P[0], P[2], 1, "Hard", score="W/O"),
            _base_row(dt.date(2023, 1, 9), P[1], P[2], 2, "Hard"),
        ]
        df3 = _make_df(rows)

        # State just before the third match (after match + walkover)
        state_with_wo = elo_state_asof(df3, dt.date(2023, 1, 9))
        # State from just the first match
        state_one = replay(_make_df([rows[0]]))

        assert state_with_wo.ratings.get(P[0]) == state_one.ratings.get(P[0]), (
            "P[0]'s rating must be unchanged by the walkover"
        )
        assert state_with_wo.ratings.get(P[1]) == state_one.ratings.get(P[1]), (
            "P[1]'s rating must be unchanged by the walkover"
        )
        # P[2] was involved in the walkover but ratings not updated
        assert state_with_wo.ratings.get(P[2]) is None, (
            "P[2] should have no overall rating after only a W/O"
        )

    def test_walkover_counted_in_walk_forward_output(self) -> None:
        """walk_forward_elo must include the walkover row in output (row count matches)."""
        rows = [
            _base_row(dt.date(2023, 1, 1), P[0], P[1], 1),
            _base_row(dt.date(2023, 1, 2), P[2], P[3], 2, score="W/O"),
        ]
        df = _make_df(rows)
        result = walk_forward_elo(df)
        assert len(result) == 2, "Both rows (including walkover) must appear in output"
        # The walkover row's Elo values should both be BASE_RATING (first appearances)
        wo_row = result[result["score"] == "W/O"].iloc[0]
        assert wo_row["p1_elo"] == BASE_RATING
        assert wo_row["p2_elo"] == BASE_RATING


# ---------------------------------------------------------------------------
# 6. Surface-blend: clay specialist test
# ---------------------------------------------------------------------------

class TestSurfaceBlend:
    def test_clay_specialist_has_higher_clay_prob(self) -> None:
        """Construct an EloState directly where P[0]'s clay Elo >> hard Elo.

        The blended prob on clay must exceed the blended prob on hard against
        the same opponent, because the surface component of the blend is higher.
        """
        from domains.tennis.elo import SURFACE_BLEND, BASE_RATING as BR

        # P[0] overall 1600, clay 1800, hard 1400.  P[2] overall 1500 (no surface history).
        state = EloState(
            ratings={P[0]: 1600.0, P[2]: 1500.0},
            surface={(P[0], "Clay"): 1800.0, (P[0], "Hard"): 1400.0},
        )

        # When P[2] has no surface entry it defaults to their overall (1500).
        # Clay blend diff = (1-SB)*(1600-1500) + SB*(1800-1500) = (1-SB)*100 + SB*300
        # Hard blend diff = (1-SB)*(1600-1500) + SB*(1400-1500) = (1-SB)*100 + SB*(-100)
        # Clay diff > Hard diff → clay prob > hard prob.

        p_clay = prob(state, P[0], P[2], "Clay")
        p_hard = prob(state, P[0], P[2], "Hard")
        assert p_clay > p_hard, (
            f"Clay specialist should have higher win prob on clay ({p_clay:.4f}) "
            f"than on hard ({p_hard:.4f})"
        )
        assert p_clay > 0.5, "Clay specialist should be favored on clay"
        assert p_hard > 0.5, "Overall-stronger player still favored on hard"

    def test_surface_elo_rises_with_wins(self) -> None:
        """Verify that replaying clay wins raises the clay surface Elo."""
        clay_rows = [
            _base_row(dt.date(2022, 5, i + 1), P[0], 500 + i, 1, "Clay")
            for i in range(8)
        ]
        df_clay = _make_df(clay_rows)
        state = replay(df_clay)

        clay_surface_elo = state.surface.get((P[0], "Clay"), BASE_RATING)
        assert clay_surface_elo > BASE_RATING + 50, (
            "Clay specialist's clay Elo should be significantly above base"
        )
        assert state.ratings[P[0]] > BASE_RATING, "Overall Elo also rises with wins"


# ---------------------------------------------------------------------------
# 7. Three-match hand-computed Elo values (closed-form arithmetic)
# ---------------------------------------------------------------------------

class TestHandComputedValues:
    """Verify Elo arithmetic against manually calculated expected values.

    Three players: A(200), B(201), C(202).  All start at 1500.0.
    Match 1: A vs B, A wins.  Match 2: B vs C, B wins.  Match 3: A vs C, C wins.
    """

    A, B, C = 200, 201, 202

    def _expected_ratings(self) -> tuple[float, float, float]:
        """Return (rA, rB, rC) after 3 matches via manual Elo computation."""
        r = {self.A: 1500.0, self.B: 1500.0, self.C: 1500.0}
        c = {self.A: 0, self.B: 0, self.C: 0}

        def _update(p1: int, p2: int, winner: int) -> None:
            exp1 = _expected(r[p1], r[p2])
            exp2 = 1.0 - exp1
            k1 = _k(c[p1])
            k2 = _k(c[p2])
            actual1 = 1.0 if winner == p1 else 0.0
            actual2 = 1.0 - actual1
            r[p1] += k1 * (actual1 - exp1)
            r[p2] += k2 * (actual2 - exp2)
            c[p1] += 1
            c[p2] += 1

        _update(self.A, self.B, self.A)
        _update(self.B, self.C, self.B)
        _update(self.A, self.C, self.C)
        return r[self.A], r[self.B], r[self.C]

    def test_hand_computed_overall_ratings(self) -> None:
        rows = [
            _base_row(dt.date(2023, 3, 1), self.A, self.B, 1, "Hard"),
            _base_row(dt.date(2023, 3, 2), self.B, self.C, 1, "Hard"),
            _base_row(dt.date(2023, 3, 3), self.A, self.C, 2, "Hard"),
        ]
        df = _make_df(rows)
        state = replay(df)

        exp_a, exp_b, exp_c = self._expected_ratings()

        assert abs(state.ratings[self.A] - exp_a) < 1e-12, (
            f"rA: expected {exp_a}, got {state.ratings[self.A]}"
        )
        assert abs(state.ratings[self.B] - exp_b) < 1e-12, (
            f"rB: expected {exp_b}, got {state.ratings[self.B]}"
        )
        assert abs(state.ratings[self.C] - exp_c) < 1e-12, (
            f"rC: expected {exp_c}, got {state.ratings[self.C]}"
        )

    def test_pre_match_elo_is_prior_state(self) -> None:
        """The pre-match p1_elo/p2_elo columns must match the state BEFORE each match."""
        rows = [
            _base_row(dt.date(2023, 3, 1), self.A, self.B, 1, "Hard"),
            _base_row(dt.date(2023, 3, 2), self.B, self.C, 1, "Hard"),
            _base_row(dt.date(2023, 3, 3), self.A, self.C, 2, "Hard"),
        ]
        df = _make_df(rows)
        result = walk_forward_elo(df)

        # Match 1: both at base
        m1 = result.iloc[0]
        assert m1["p1_elo"] == BASE_RATING
        assert m1["p2_elo"] == BASE_RATING

        # Match 2: B's pre-match Elo = B's Elo after match 1; C still at base
        state_after_m1 = replay(df.iloc[:1])
        m2 = result.iloc[1]
        assert abs(m2["p1_elo"] - state_after_m1.ratings[self.B]) < 1e-12, (
            "Match 2 p1_elo must equal B's Elo after match 1"
        )
        assert m2["p2_elo"] == BASE_RATING, "C has no prior matches before match 2"

        # Match 3: A's pre-match Elo = Elo after match 1; C = Elo after match 2
        state_after_m2 = replay(df.iloc[:2])
        m3 = result.iloc[2]
        assert abs(m3["p1_elo"] - state_after_m2.ratings[self.A]) < 1e-12, (
            "Match 3 p1_elo must equal A's Elo after matches 1+2"
        )
        assert abs(m3["p2_elo"] - state_after_m2.ratings[self.C]) < 1e-12, (
            "Match 3 p2_elo must equal C's Elo after matches 1+2"
        )


# ---------------------------------------------------------------------------
# 8. Edge-case / robustness
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_dataframe(self) -> None:
        """replay on empty frame returns empty EloState."""
        cols = ["date", "p1_id", "p2_id", "winner", "surface", "score", "round", "match_num"]
        empty = pd.DataFrame(columns=cols)
        state = replay(empty)
        assert state.ratings == {}
        assert state.n_processed == 0

    def test_single_match(self) -> None:
        rows = [_base_row(dt.date(2023, 1, 1), P[0], P[1], 1)]
        df = _make_df(rows)
        state = replay(df)
        assert state.n_processed == 1
        assert P[0] in state.ratings
        assert P[1] in state.ratings
        # Winner's Elo > BASE; loser's Elo < BASE (symmetric update from same base)
        assert state.ratings[P[0]] > BASE_RATING
        assert state.ratings[P[1]] < BASE_RATING

    def test_win_prob_equal_ratings(self) -> None:
        """Equal ratings → win prob == 0.5 exactly."""
        state = EloState(
            ratings={P[0]: 1600.0, P[1]: 1600.0},
            surface={(P[0], "Hard"): 1600.0, (P[1], "Hard"): 1600.0},
        )
        p = prob(state, P[0], P[1], "Hard")
        assert p == 0.5, f"Equal ratings must give exactly 0.5, got {p}"

    def test_win_prob_unknown_surface_falls_back_to_overall(self) -> None:
        """When a player has no surface entry, surface Elo defaults to overall."""
        state = EloState(ratings={P[0]: 1600.0, P[1]: 1500.0})
        # No surface entries → surface defaults to overall → blended = overall
        p = prob(state, P[0], P[1], "Clay")
        exp_p = 1.0 / (1.0 + 10.0 ** (-(1600.0 - 1500.0) / 400.0))
        assert abs(p - exp_p) < 1e-12

    def test_large_rating_difference_prob_close_to_1(self) -> None:
        """A massive Elo gap should give a win probability very close to 1."""
        state = EloState(ratings={P[0]: 3000.0, P[1]: 1000.0})
        p = prob(state, P[0], P[1], "Hard")
        assert p > 0.9999, f"Expected near-certain win, got {p}"
        assert p < 1.0

    def test_n_processed_excludes_walkovers(self) -> None:
        """n_processed must not count walkover rows."""
        rows = [
            _base_row(dt.date(2023, 1, 1), P[0], P[1], 1),
            _base_row(dt.date(2023, 1, 2), P[0], P[2], 1, score="W/O"),
            _base_row(dt.date(2023, 1, 3), P[1], P[2], 2),
        ]
        df = _make_df(rows)
        state = replay(df)
        assert state.n_processed == 2, (
            f"n_processed should be 2 (walkovers excluded), got {state.n_processed}"
        )


# ---------------------------------------------------------------------------
# 9. win_prob column in walk_forward output matches prob() function
# ---------------------------------------------------------------------------

class TestWinProbColumnConsistency:
    def test_win_prob_matches_prob_function(self) -> None:
        """win_prob_p1 in walk_forward output must match prob() on the pre-match state."""
        rows = [
            _base_row(dt.date(2023, 1, d + 1), P[d % 3], P[(d + 1) % 3], (d % 2) + 1)
            for d in range(6)
        ]
        df = _make_df(rows)
        result = walk_forward_elo(df)
        dates = pd.to_datetime(df["date"]).dt.date.sort_values().unique()

        for i, row in result.iterrows():
            asof_state = elo_state_asof(df, pd.to_datetime(row["date"]).date())
            surface = row["surface"]
            expected_wp = prob(asof_state, int(row["p1_id"]), int(row["p2_id"]), surface)
            assert abs(row["win_prob_p1"] - expected_wp) < 1e-12, (
                f"Row {i}: walk_forward win_prob_p1={row['win_prob_p1']:.10f} "
                f"vs prob()={expected_wp:.10f}"
            )
