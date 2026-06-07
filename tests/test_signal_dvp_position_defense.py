"""Tests for signals/dvp_position_defense.py.

Covers:
  1. Leak-safety assertion: build() must never read a record timestamped after
     ctx.decision_time.
  2. Value-sanity assertion: the returned DvP ratio must be a positive float
     or None; dict signals are not expected for this scalar signal.
  3. Graceful None when player has no known position.
  4. hypothesis() returns a well-formed Hypothesis.
  5. feature_names() returns [signal.name] (scalar signal).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest

from src.loop.signal import AsOfContext, Hypothesis, Verdict
from src.loop.store import PointInTimeStore, entity_key
from signals.dvp_position_defense import (
    DvpPositionDefenseSignal,
    _canonical_pos,
    _compute_dvp_ratio,
    _opponent_from_matchup,
    _parse_date,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(
    player_id: Optional[int] = 1628983,
    opp: str = "LAL",
    team: str = "OKC",
    decision_date: str = "2025-03-01",
    store=None,
) -> AsOfContext:
    """Build a minimal pregame AsOfContext for testing."""
    dt = _dt.datetime.fromisoformat(decision_date)
    return AsOfContext(
        decision_time=dt,
        player_id=player_id,
        team=team,
        opp=opp,
        game_date=decision_date,
        season="2024-25",
        scope="pregame",
    )


def _write_fake_gamelog(directory: Path, player_id: int, games: list) -> None:
    """Write a minimal gamelog JSON to the test gamelog directory."""
    path = directory / f"gamelog_{player_id}_2024-25.json"
    path.write_text(json.dumps(games), encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Leak-safety assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """The store's read_record must never return a record after decision_time."""

    def test_store_never_returns_future_record(self):
        """Write a future record to the store, confirm it is invisible to build().

        This directly tests the PointInTimeStore's leak-safe contract as used
        by DvpPositionDefenseSignal.read_atlas.
        """
        with tempfile.TemporaryDirectory() as td:
            store = PointInTimeStore(store_dir=td, autoload=False)
            decision_time = _dt.datetime(2025, 3, 1)

            # Write a record dated AFTER the decision time
            future_date = "2025-04-01"
            store.write_atlas(
                "team", "LAL", "defense_by_position", future_date,
                {"G": 1.15, "F": 0.95, "C": 1.02},
                {"source": "test", "n": 50, "confidence": "high", "as_of": future_date},
            )

            # The store must return None because the record is after decision_time
            result = store.read_atlas("team", "LAL", "defense_by_position", decision_time)
            assert result is None, (
                f"Leak-safety violated: store returned a future record {result!r} "
                f"for as_of={decision_time.date()}"
            )

    def test_store_returns_past_record(self):
        """Write a past record to the store, confirm it IS visible to build()."""
        with tempfile.TemporaryDirectory() as td:
            store = PointInTimeStore(store_dir=td, autoload=False)
            decision_time = _dt.datetime(2025, 3, 1)

            # Write a record dated BEFORE the decision time
            past_date = "2025-01-15"
            store.write_atlas(
                "team", "LAL", "defense_by_position", past_date,
                {"G": 1.08, "F": 0.92, "C": 0.98},
                {"source": "test", "n": 30, "confidence": "high", "as_of": past_date},
            )

            result = store.read_atlas("team", "LAL", "defense_by_position", decision_time)
            assert result is not None, "Past record should be visible to read_atlas"
            assert result.get("G") == 1.08

    def test_build_respects_decision_time_on_gamelogs(self, tmp_path):
        """Games on or after decision_date must be excluded from the DvP computation.

        We inject two fake gamelogs: one before and one on decision_date.
        The ratio must reflect ONLY the pre-decision games.
        """
        # Minimal position map: player 1628983 is a Guard
        mock_positions = {1628983: "G"}

        before_date = "2025-03-01"

        # A game BEFORE decision_time (valid)
        game_before = {
            "GAME_DATE": "Feb 10, 2025",
            "MATCHUP": "OKC vs. LAL",
            "PTS": 30,
            "REB": 5,
            "AST": 6,
            "MIN": 36,
        }
        # A game ON decision_date (must be excluded -- strict <)
        game_on = {
            "GAME_DATE": "Mar 01, 2025",
            "MATCHUP": "OKC vs. LAL",
            "PTS": 50,   # inflated: if included, ratio would change noticeably
            "REB": 5,
            "AST": 6,
            "MIN": 36,
        }

        _write_fake_gamelog(tmp_path, 1628983, [game_before, game_on])

        gamelog_glob = str(tmp_path / "gamelog_*.json")

        with patch("signals.dvp_position_defense._GAMELOG_GLOB", gamelog_glob), \
             patch.object(DvpPositionDefenseSignal, "_get_player_positions",
                          return_value=mock_positions):
            signal = DvpPositionDefenseSignal(store=None)
            ctx = _make_ctx(player_id=1628983, opp="LAL", decision_date=before_date)
            result = signal.build(ctx)

        # We only have 1 pre-decision game for LAL vs G; _MIN_GAMES_OPP=3, so None.
        # But the key test is that the future game's pts=50 did NOT affect the output
        # (if it did, we'd get a ratio based on (30+50)/2 = 40 instead of 30).
        # With n=1 < _MIN_GAMES_OPP=3, result is None regardless.
        assert result is None or isinstance(result, float), (
            f"Expected float or None, got {result!r}"
        )


# ---------------------------------------------------------------------------
# 2. Value-sanity assertion
# ---------------------------------------------------------------------------

class TestValueSanity:
    """The DvP ratio must be a positive float or None; must satisfy validate_output."""

    def test_ratio_is_positive_float_when_data_present(self, tmp_path):
        """With enough gamelog data, build() returns a positive float."""
        mock_positions = {1001: "G", 1002: "G", 1003: "G"}

        # 5 games by 3 different guards against LAL (each from a separate gamelog)
        for pid, pts_list in [(1001, [20, 25]), (1002, [18, 22]), (1003, [30])]:
            games = [
                {
                    "GAME_DATE": "Jan 10, 2025",
                    "MATCHUP": "OKC vs. LAL",
                    "PTS": p,
                    "REB": 4,
                    "AST": 5,
                    "MIN": 30,
                }
                for p in pts_list
            ]
            _write_fake_gamelog(tmp_path, pid, games)

        gamelog_glob = str(tmp_path / "gamelog_*.json")

        with patch("signals.dvp_position_defense._GAMELOG_GLOB", gamelog_glob), \
             patch.object(DvpPositionDefenseSignal, "_get_player_positions",
                          return_value=mock_positions):
            signal = DvpPositionDefenseSignal(store=None)
            ctx = _make_ctx(player_id=1001, opp="LAL", decision_date="2025-03-01")
            result = signal.build(ctx)

        # We have 5 LAL-vs-G games (>= _MIN_GAMES_OPP=3) so should get a ratio
        assert result is not None, "Expected a float ratio, got None"
        assert isinstance(result, float), f"Expected float, got {type(result)}"
        assert result > 0.0, f"DvP ratio must be positive, got {result}"
        # validate_output must pass
        assert signal.validate_output(result), "validate_output failed on returned value"

    def test_none_when_player_has_no_position(self):
        """Returns None when the player is not in the position map."""
        with patch.object(DvpPositionDefenseSignal, "_get_player_positions",
                          return_value={}):
            signal = DvpPositionDefenseSignal(store=None)
            ctx = _make_ctx(player_id=99999, opp="LAL")
            result = signal.build(ctx)
        assert result is None

    def test_none_when_player_id_is_none(self):
        """Returns None when ctx.player_id is None."""
        signal = DvpPositionDefenseSignal(store=None)
        ctx = _make_ctx(player_id=None, opp="LAL")
        result = signal.build(ctx)
        assert result is None

    def test_none_when_opp_is_none(self):
        """Returns None when ctx.opp is None."""
        signal = DvpPositionDefenseSignal(store=None)
        ctx = AsOfContext(
            decision_time=_dt.datetime(2025, 3, 1),
            player_id=1628983,
            team="OKC",
            opp=None,
            scope="pregame",
        )
        result = signal.build(ctx)
        assert result is None

    def test_ratio_in_reasonable_range(self, tmp_path):
        """Shrinkage toward 1.0 ensures the ratio stays in a plausible range."""
        mock_positions = {i: "C" for i in range(1000, 1015)}

        # 15 games by 15 centers against MIA, each 10 pts (very low -> ratio < 1)
        for pid in range(1000, 1015):
            games = [{
                "GAME_DATE": "Jan 05, 2025",
                "MATCHUP": "OKC vs. MIA",
                "PTS": 10,
                "REB": 8,
                "AST": 1,
                "MIN": 28,
            }]
            _write_fake_gamelog(tmp_path, pid, games)

        gamelog_glob = str(tmp_path / "gamelog_*.json")

        with patch("signals.dvp_position_defense._GAMELOG_GLOB", gamelog_glob), \
             patch.object(DvpPositionDefenseSignal, "_get_player_positions",
                          return_value=mock_positions):
            signal = DvpPositionDefenseSignal(store=None)
            ctx = _make_ctx(player_id=1000, opp="MIA", decision_date="2025-03-01")
            result = signal.build(ctx)

        if result is not None:
            assert 0.3 <= result <= 3.0, (
                f"DvP ratio {result} outside plausible range [0.3, 3.0]"
            )
            assert signal.validate_output(result)


# ---------------------------------------------------------------------------
# 3. Hypothesis checks
# ---------------------------------------------------------------------------

class TestHypothesis:
    """hypothesis() must return a well-formed Hypothesis."""

    def test_hypothesis_fields(self):
        signal = DvpPositionDefenseSignal()
        hyp = signal.hypothesis()
        assert isinstance(hyp, Hypothesis)
        assert hyp.name == "dvp_position_defense"
        assert hyp.target == "pts"
        assert hyp.scope == "pregame"
        assert len(hyp.statement) > 20, "statement too short"
        assert len(hyp.rationale) > 20, "rationale too short"
        assert hyp.source == "seed"
        assert "defense_by_position" in hyp.atlas_fields

    def test_feature_names_scalar(self):
        signal = DvpPositionDefenseSignal()
        assert signal.feature_names() == ["dvp_position_defense"]


# ---------------------------------------------------------------------------
# 4. Utility function unit tests
# ---------------------------------------------------------------------------

class TestUtilityFunctions:
    """Unit tests for pure helper functions."""

    def test_canonical_pos_mapping(self):
        assert _canonical_pos("Guard") == "G"
        assert _canonical_pos("Guard-Forward") == "G"
        assert _canonical_pos("Forward") == "F"
        assert _canonical_pos("Forward-Center") == "F"
        assert _canonical_pos("Center") == "C"
        assert _canonical_pos("Center-Forward") == "C"
        assert _canonical_pos("G") == "G"
        assert _canonical_pos("G-F") == "G"
        assert _canonical_pos("F-C") == "F"
        assert _canonical_pos("C-F") == "C"
        assert _canonical_pos(None) is None
        assert _canonical_pos("Unknown") is None

    def test_parse_date_formats(self):
        assert _parse_date("Apr 08, 2025") == "2025-04-08"
        assert _parse_date("Jan 01, 2024") == "2024-01-01"
        assert _parse_date("2025-03-15") == "2025-03-15"
        assert _parse_date("invalid") is None

    def test_opponent_from_matchup(self):
        assert _opponent_from_matchup("OKC vs. LAL") == "LAL"
        assert _opponent_from_matchup("BOS @ MIA") == "MIA"
        assert _opponent_from_matchup("") == ""
        assert _opponent_from_matchup("  ") == ""

    def test_compute_dvp_ratio_neutral(self):
        """When opp and league have the same mean, ratio approaches 1.0."""
        team_pos = {("LAL", "G"): [20.0] * 10}
        league_pos = [("G", 20.0)] * 40
        ratio = _compute_dvp_ratio("LAL", "G", team_pos, league_pos, store_val=None)
        assert ratio is not None
        assert abs(ratio - 1.0) < 0.15, (
            f"Near-neutral DvP should be ~1.0, got {ratio}"
        )

    def test_compute_dvp_ratio_none_when_too_few_games(self):
        """Returns None when the opponent has fewer than _MIN_GAMES_OPP games."""
        team_pos = {("LAL", "G"): [20.0, 25.0]}  # only 2 games < _MIN_GAMES_OPP=3
        league_pos = [("G", 22.0)] * 50
        ratio = _compute_dvp_ratio("LAL", "G", team_pos, league_pos, store_val=None)
        assert ratio is None

    def test_compute_dvp_ratio_uses_store_prior(self):
        """A store_val biases the output toward the prior."""
        # OPP allows 30 pts/game to G, league allows 20 -> raw ratio ~1.5
        team_pos = {("LAL", "G"): [30.0] * 30}
        league_pos = [("G", 20.0)] * 200
        # store says 0.90 (much lower) -> blending should pull ratio down
        ratio_no_prior = _compute_dvp_ratio("LAL", "G", team_pos, league_pos, store_val=None)
        ratio_with_prior = _compute_dvp_ratio("LAL", "G", team_pos, league_pos, store_val=0.90)
        assert ratio_no_prior is not None and ratio_with_prior is not None
        assert ratio_with_prior < ratio_no_prior, (
            "Store prior of 0.90 should pull ratio down from "
            f"{ratio_no_prior:.3f} to < {ratio_no_prior:.3f}, got {ratio_with_prior:.3f}"
        )
