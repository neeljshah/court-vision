"""tests.platformkit.test_mlb_states -- offline synthetic tests for MLB in-game states.

Tests schema correctness, leak-freeness, and state invariants WITHOUT any network
calls.  All ESPN API calls are replaced by synthetic fixtures.

Run: cd /c/Users/neelj/nba-ai-system &&
     /c/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest
     tests/platformkit/test_mlb_states.py -v
"""
from __future__ import annotations

import datetime as dt
from typing import List, Optional
from unittest.mock import patch

import pandas as pd
import pytest

from domains.mlb.ingest_states import (
    _gc2espn,
    _scoreboard_map,
    fetch_game_states,
    ingest_season,
    parse_half_inning_states,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_end_inning_play(ptype: str, pnum: int, home: int, away: int) -> dict:
    """Synthetic ESPN end-inning play."""
    return {
        "type": {"type": "end-inning", "text": "End Inning"},
        "period": {"type": ptype, "number": pnum, "displayValue": f"{pnum}th Inning"},
        "homeScore": home,
        "awayScore": away,
        "scoringPlay": False,
    }


def _make_payload(half_inning_results: list, final_home: int, final_away: int) -> dict:
    """Build synthetic ESPN summary payload from list of (ptype, pnum, home, away).

    Includes a trailing non-scoring play that carries the final score.
    """
    plays: List[dict] = []
    for ptype, pnum, home, away in half_inning_results:
        plays.append(_make_end_inning_play(ptype, pnum, home, away))
    # Add a final non-end-inning play carrying final score
    plays.append({
        "type": {"type": "play-result", "text": "Final play"},
        "period": {"type": "End", "number": 9},
        "homeScore": final_home,
        "awayScore": final_away,
        "scoringPlay": False,
    })
    return {"plays": plays}


def _std_9inn_home_win() -> dict:
    """Standard 9-inning game where home team wins 5-3."""
    halves = [
        # (ptype, inning, home, away)
        ("Mid", 1, 0, 0),   # after top 1
        ("End", 1, 2, 0),   # after bot 1 (home scores 2)
        ("Mid", 2, 2, 1),   # after top 2 (away scores 1)
        ("End", 2, 2, 1),
        ("Mid", 3, 2, 1),
        ("End", 3, 3, 1),   # home scores 1
        ("Mid", 4, 3, 3),   # away scores 2
        ("End", 4, 3, 3),
        ("Mid", 5, 3, 3),
        ("End", 5, 4, 3),   # home scores 1
        ("Mid", 6, 4, 3),
        ("End", 6, 4, 3),
        ("Mid", 7, 4, 3),
        ("End", 7, 4, 3),
        ("Mid", 8, 4, 3),
        ("End", 8, 4, 3),
        ("Mid", 9, 4, 3),
        ("End", 9, 5, 3),   # walk-off run
    ]
    return _make_payload(halves, final_home=5, final_away=3)


def _std_9inn_away_win() -> dict:
    """Standard 9-inning game where away team wins 1-0."""
    halves = [
        ("Mid", 1, 0, 1),   # away scores in top 1
        ("End", 1, 0, 1),
        ("Mid", 2, 0, 1),
        ("End", 2, 0, 1),
        ("Mid", 3, 0, 1),
        ("End", 3, 0, 1),
        ("Mid", 4, 0, 1),
        ("End", 4, 0, 1),
        ("Mid", 5, 0, 1),
        ("End", 5, 0, 1),
        ("Mid", 6, 0, 1),
        ("End", 6, 0, 1),
        ("Mid", 7, 0, 1),
        ("End", 7, 0, 1),
        ("Mid", 8, 0, 1),
        ("End", 8, 0, 1),
        ("Mid", 9, 0, 1),
        # game ends after top 9 (walk-off game would end here) -- but away leads so no bot 9
    ]
    return _make_payload(halves, final_home=0, final_away=1)


def _extra_innings_home_win() -> dict:
    """10-inning extra-innings game where home wins 3-2."""
    halves = []
    for inn in range(1, 10):
        halves.append(("Mid", inn, 2, 2))
        halves.append(("End", inn, 2, 2))
    # Extra inning 10: away 0, home walk-off
    halves.append(("Mid", 10, 2, 2))
    halves.append(("End", 10, 3, 2))
    return _make_payload(halves, final_home=3, final_away=2)


# ---------------------------------------------------------------------------
# parse_half_inning_states tests
# ---------------------------------------------------------------------------

class TestParseHalfInningStates:
    def test_schema_cols_present(self):
        states = parse_half_inning_states(_std_9inn_home_win())
        assert states, "Expected non-empty states"
        required = {"asof_idx", "state_diff", "frac_elapsed", "half_inning_label"}
        for row in states:
            assert required <= set(row.keys()), f"Missing keys in {row}"

    def test_frac_elapsed_bounds(self):
        for payload in [_std_9inn_home_win(), _std_9inn_away_win(),
                        _extra_innings_home_win()]:
            states = parse_half_inning_states(payload)
            fracs = [s["frac_elapsed"] for s in states]
            assert all(0.0 < f <= 1.0 for f in fracs), f"frac out of (0,1]: {fracs}"

    def test_frac_elapsed_monotonic(self):
        states = parse_half_inning_states(_std_9inn_home_win())
        fracs = [s["frac_elapsed"] for s in states]
        assert fracs == sorted(fracs), "frac_elapsed not monotone"
        # Strictly increasing (no duplicate half-inning boundaries)
        assert len(fracs) == len(set(fracs)), "Duplicate frac_elapsed values"

    def test_standard_9inning_count(self):
        states = parse_half_inning_states(_std_9inn_home_win())
        assert len(states) == 18, f"Expected 18 half-inning states, got {len(states)}"

    def test_extra_innings_frac_at_most_1(self):
        states = parse_half_inning_states(_extra_innings_home_win())
        fracs = [s["frac_elapsed"] for s in states]
        last_frac = fracs[-1]
        assert last_frac == 1.0, (f"Extra-inning final state should have frac=1.0,"
                                  f" got {last_frac}")

    def test_state_diff_signed_home_perspective(self):
        """After bottom-1 with home=2 away=0, state_diff should be +2."""
        states = parse_half_inning_states(_std_9inn_home_win())
        # asof_idx=1 -> End inn 1 -> home=2 away=0 -> diff=+2
        bot1 = next((s for s in states if s["half_inning_label"] == "end1"), None)
        assert bot1 is not None, "end1 state missing"
        assert bot1["state_diff"] == 2.0, (f"Expected state_diff=+2 (home perspective) "
                                           f"at end1, got {bot1['state_diff']}")

    def test_asof_idx_sequential(self):
        states = parse_half_inning_states(_std_9inn_home_win())
        idxs = [s["asof_idx"] for s in states]
        assert idxs == list(range(len(states))), f"asof_idx not sequential: {idxs}"

    def test_empty_payload_returns_empty(self):
        assert parse_half_inning_states({}) == []
        assert parse_half_inning_states({"plays": []}) == []

    def test_no_end_inning_plays_returns_empty(self):
        payload = {"plays": [{"type": {"type": "ball"}, "period": {"type": "Top", "number": 1},
                               "homeScore": 0, "awayScore": 0}]}
        assert parse_half_inning_states(payload) == []


# ---------------------------------------------------------------------------
# fetch_game_states tests (no network)
# ---------------------------------------------------------------------------

class TestFetchGameStates:
    def _meta(self, p0: float = 0.53) -> dict:
        return {
            "game_id": "2023-04-01-HOU-CHW-1",
            "p0": p0,
            "home_team": "HOU",
            "away_team": "CWS",
            "date": "2023-04-01",
            "season": 2023,
        }

    def test_schema_required_cols(self):
        payload = _std_9inn_home_win()
        states = fetch_game_states("dummy_eid", self._meta(), lambda _: payload)
        assert states, "Expected states"
        required = {"sport", "game_id", "asof_idx", "state_diff", "frac_elapsed",
                    "p0", "outcome"}
        for row in states:
            missing = required - set(row.keys())
            assert not missing, f"Missing cols: {missing}"

    def test_sport_literal(self):
        states = fetch_game_states("e", self._meta(), lambda _: _std_9inn_home_win())
        assert all(row["sport"] == "mlb" for row in states)

    def test_outcome_matches_final_score_home_win(self):
        states = fetch_game_states("e", self._meta(), lambda _: _std_9inn_home_win())
        assert all(row["outcome"] == 1 for row in states)

    def test_outcome_matches_final_score_away_win(self):
        states = fetch_game_states("e", self._meta(), lambda _: _std_9inn_away_win())
        assert all(row["outcome"] == 0 for row in states)

    def test_p0_in_range(self):
        states = fetch_game_states("e", self._meta(p0=0.55),
                                   lambda _: _std_9inn_home_win())
        assert all(0.0 < row["p0"] < 1.0 for row in states)

    def test_p0_constant_across_states(self):
        """p0 is pregame -- same for every as-of state within a game."""
        states = fetch_game_states("e", self._meta(p0=0.61),
                                   lambda _: _std_9inn_home_win())
        p0s = [row["p0"] for row in states]
        assert len(set(p0s)) == 1 and abs(p0s[0] - 0.61) < 1e-9

    def test_frac_elapsed_monotone_within_game(self):
        states = fetch_game_states("e", self._meta(), lambda _: _std_9inn_home_win())
        fracs = [row["frac_elapsed"] for row in states]
        assert fracs == sorted(fracs)

    def test_empty_on_tied_final(self):
        """Tied-final games (rare rain-shortened) must be dropped."""
        halves = [("Mid", 1, 0, 0), ("End", 1, 0, 0)]
        payload = _make_payload(halves, final_home=0, final_away=0)
        states = fetch_game_states("e", self._meta(), lambda _: payload)
        assert states == [], "Tied final should produce no states"

    def test_empty_on_fetch_failure(self):
        states = fetch_game_states("e", self._meta(), lambda _: {})
        assert states == []

    def test_state_diff_is_home_minus_away(self):
        """At end1: home=2, away=0 -> state_diff=+2."""
        states = fetch_game_states("e", self._meta(), lambda _: _std_9inn_home_win())
        s = next((r for r in states if r["asof_idx"] == 1), None)  # End inn 1
        assert s is not None
        assert s["state_diff"] == 2.0, f"state_diff at end1 should be +2, got {s['state_diff']}"

    def test_asof_states_only_use_past_plays(self):
        """Leak check: at asof_idx=0 (end top 1), home and away still 0-0 in our fixture."""
        states = fetch_game_states("e", self._meta(), lambda _: _std_9inn_home_win())
        first = next(r for r in states if r["asof_idx"] == 0)  # Mid inn 1: after top 1, 0-0
        assert first["state_diff"] == 0.0, (f"After top1 both teams 0 runs, diff should=0,"
                                             f" got {first['state_diff']}")


# ---------------------------------------------------------------------------
# Leak-freeness: p0 uses only prior games
# ---------------------------------------------------------------------------

class TestLeakFreeP0:
    """Verify that the Elo p0 assigned to game G uses only games strictly before G's date."""

    def test_p0_constant_per_game_not_per_state(self):
        """Within a game all states share the same p0 (pregame).  No in-game leak."""
        payload = _std_9inn_home_win()
        meta = {"game_id": "test", "p0": 0.52, "home_team": "A", "away_team": "B",
                "date": "2023-05-01", "season": 2023}
        states = fetch_game_states("eid", meta, lambda _: payload)
        p0s = {r["p0"] for r in states}
        assert len(p0s) == 1, "p0 must be identical for all states of a game"

    def test_walk_forward_elo_uses_prior_games(self):
        """walk_forward_elo is called on the FULL corpus; the resulting p_home_elo for game G
        only incorporates games before G (guaranteed by the ratings.walk_forward_elo contract).
        Here we verify that the first game in the sequence gets the prior mean p0 (~0.5+HFA).
        """
        from domains.mlb.ratings import walk_forward_elo
        from domains.mlb.config import ELO_MEAN, ELO_HFA
        import math
        games = pd.DataFrame({
            "date": pd.to_datetime(["2023-04-01", "2023-04-02"]),
            "season": [2023, 2023],
            "home_team": ["A", "B"],
            "away_team": ["B", "A"],
            "home_runs": [3, 2],
            "away_runs": [1, 4],
            "game_seq": [1, 1],
        })
        wf = walk_forward_elo(games)
        # First game: both teams initialised to ELO_MEAN; expected p0 = f(HFA)
        expected_d = (ELO_MEAN + ELO_HFA) - ELO_MEAN  # = ELO_HFA
        expected_p = 1.0 / (1.0 + math.pow(10.0, -expected_d / 400.0))
        assert abs(wf.iloc[0]["p_home_elo"] - expected_p) < 1e-9, (
            f"First game p0 should be {expected_p:.4f} (HFA only), "
            f"got {wf.iloc[0]['p_home_elo']:.4f}")

    def test_second_game_p0_uses_first_result(self):
        """Second game's p0 must differ from the first (first result updated the Elo)."""
        from domains.mlb.ratings import walk_forward_elo
        games = pd.DataFrame({
            "date": pd.to_datetime(["2023-04-01", "2023-04-02"]),
            "season": [2023, 2023],
            "home_team": ["A", "B"],
            "away_team": ["B", "A"],
            "home_runs": [3, 1],  # A wins the first game decisively
            "away_runs": [1, 3],
            "game_seq": [1, 1],
        })
        wf = walk_forward_elo(games)
        p0_g1 = wf.iloc[0]["p_home_elo"]
        p0_g2 = wf.iloc[1]["p_home_elo"]
        assert abs(p0_g1 - p0_g2) > 1e-9, (
            "Second game p0 should reflect the first game result (Elo updated)")


# ---------------------------------------------------------------------------
# Team code normalisation
# ---------------------------------------------------------------------------

class TestTeamCodeNorm:
    @pytest.mark.parametrize("gc, espn", [
        ("CUB", "CHC"), ("CWS", "CHW"), ("KAN", "KC"),
        ("SDG", "SD"), ("SFO", "SF"), ("TAM", "TB"), ("WAS", "WSH"),
        ("HOU", "HOU"), ("NYY", "NYY"),  # passthrough cases
    ])
    def test_gc2espn_mapping(self, gc, espn):
        assert _gc2espn(gc) == espn


# ---------------------------------------------------------------------------
# Scoreboard map (offline mock)
# ---------------------------------------------------------------------------

class TestScoreboardMap:
    def _mock_scoreboard(self, url: str) -> dict:
        return {
            "events": [
                {
                    "id": "401471042",
                    "competitions": [{
                        "competitors": [
                            {"homeAway": "home", "team": {"abbreviation": "HOU"}},
                            {"homeAway": "away", "team": {"abbreviation": "CHW"}},
                        ]
                    }]
                },
                {
                    "id": "401471051",
                    "competitions": [{
                        "competitors": [
                            {"homeAway": "home", "team": {"abbreviation": "STL"}},
                            {"homeAway": "away", "team": {"abbreviation": "TOR"}},
                        ]
                    }]
                },
            ]
        }

    def test_returns_correct_event_ids(self):
        m = _scoreboard_map("20230401", self._mock_scoreboard)
        assert m[("HOU", "CHW")] == "401471042"
        assert m[("STL", "TOR")] == "401471051"

    def test_empty_events_returns_empty(self):
        m = _scoreboard_map("20230401", lambda _: {})
        assert m == {}
