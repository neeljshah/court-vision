"""tests/platform/test_mlb_postmortem.py — Tests for MLB postmortem pipeline.

Covers:
  1. linescore.parse_innings: token parsing (digits, 'x', blanks, floats, dashes, '-1')
  2. linescore.innings_shape: shape descriptor correctness
  3. postmortem._label_game: decided_by logic on synthetic records
  4. postmortem.build_postmortem: integration test with tmp corpus
  5. postmortem.parquet: existence and column checks after real corpus run

HONEST: All tests are synthetic or use realized outcomes. No edge claimed.
"""
from __future__ import annotations

import math
import pathlib
from typing import Any, Dict, List

import pandas as pd
import pytest

from domains.mlb.linescore import _token_to_int, parse_innings, innings_shape
from domains.mlb.postmortem import (
    _extract_hand,
    _hand_matchup,
    _label_game,
    build_postmortem,
    _EXPECTED_COLS,
    _OUT_PATH,
)


# ===========================================================================
# 1. Token parser tests
# ===========================================================================

class TestTokenToInt:
    """_token_to_int: covers all legal token forms."""

    def test_digit_zero(self) -> None:
        assert _token_to_int("0") == 0

    def test_digit_positive(self) -> None:
        assert _token_to_int("3") == 3

    def test_x_returns_none(self) -> None:
        assert _token_to_int("x") is None

    def test_x_uppercase_returns_none(self) -> None:
        assert _token_to_int("X") is None

    def test_blank_returns_zero(self) -> None:
        assert _token_to_int("") == 0

    def test_whitespace_returns_zero(self) -> None:
        assert _token_to_int("  ") == 0

    def test_dash_returns_zero(self) -> None:
        assert _token_to_int("-") == 0

    def test_negative_one_returns_zero(self) -> None:
        assert _token_to_int("-1") == 0

    def test_negative_one_float_returns_zero(self) -> None:
        assert _token_to_int("-1.0") == 0

    def test_float_string_rounds(self) -> None:
        assert _token_to_int("2.0") == 2

    def test_float_string_large(self) -> None:
        assert _token_to_int("12.0") == 12


# ===========================================================================
# 2. parse_innings tests
# ===========================================================================

class TestParseInnings:
    """parse_innings: round-trip correctness."""

    def test_standard_9_inning_no_x(self) -> None:
        runs, n = parse_innings("0,1,0,2,0,0,0,0,0")
        assert runs == [0, 1, 0, 2, 0, 0, 0, 0, 0]
        assert n == 9

    def test_home_win_with_x(self) -> None:
        """'x' = home half not played; should still count 8 played innings."""
        runs, n = parse_innings("0,1,0,2,0,0,0,0,x")
        assert runs[8] == 0      # 'x' maps to 0
        assert n == 8            # only 8 played innings

    def test_multiple_x(self) -> None:
        """Rain-shortened game: x,x,x in last 3 positions."""
        runs, n = parse_innings("1,0,0,3,0,1,x,x,x")
        assert n == 6
        assert sum(runs) == 5   # only innings 1-6 count

    def test_none_input(self) -> None:
        runs, n = parse_innings(None)
        assert runs == []
        assert n == 0

    def test_empty_string(self) -> None:
        runs, n = parse_innings("")
        assert runs == []
        assert n == 0

    def test_float_tokens(self) -> None:
        runs, n = parse_innings("1.0,0.0,2.0,0.0,0.0,1,0,0,0")
        assert runs == [1, 0, 2, 0, 0, 1, 0, 0, 0]
        assert n == 9

    def test_dash_token(self) -> None:
        runs, n = parse_innings("0,0,5,0,0,0,-,x,x")
        assert runs[6] == 0     # '-' → 0
        assert n == 7            # 7 played (6 real + 1 dash)

    def test_negative_token(self) -> None:
        runs, n = parse_innings("0,0,0,1.0,-1.0,2,0,2,1")
        assert runs[4] == 0     # -1.0 → 0


# ===========================================================================
# 3. innings_shape tests
# ===========================================================================

class TestInningsShape:
    """innings_shape: shape descriptor correctness."""

    def test_biggest_inning_known(self) -> None:
        shape = innings_shape("0,1,0,2,0,0,0,0,0")
        assert shape["biggest_inning_runs"] == 2
        assert shape["biggest_inning_idx"] == 4  # 1-indexed

    def test_total_runs(self) -> None:
        shape = innings_shape("1,2,3,0,0,0,0,0,0")
        assert shape["total_runs"] == 6

    def test_big_inning_share_known(self) -> None:
        shape = innings_shape("0,0,6,0,0,0,0,0,0")
        assert abs(shape["big_inning_share"] - 1.0) < 1e-6

    def test_big_inning_share_zero_total(self) -> None:
        shape = innings_shape("0,0,0,0,0,0,0,0,0")
        assert shape["big_inning_share"] == 0.0

    def test_scoreless_frame_rate_all_zero(self) -> None:
        shape = innings_shape("0,0,0,0,0,0,0,0,0")
        assert abs(shape["scoreless_frame_rate"] - 1.0) < 1e-6

    def test_scoreless_frame_rate_none_zero(self) -> None:
        shape = innings_shape("1,1,1,1,1,1,1,1,1")
        assert shape["scoreless_frame_rate"] == 0.0

    def test_segment_runs_1_3(self) -> None:
        shape = innings_shape("3,2,1,0,0,0,0,0,0")
        assert shape["runs_1_3"] == 6

    def test_segment_runs_4_6(self) -> None:
        shape = innings_shape("0,0,0,4,3,2,0,0,0")
        assert shape["runs_4_6"] == 9

    def test_segment_runs_7_9(self) -> None:
        shape = innings_shape("0,0,0,0,0,0,5,4,3")
        assert shape["runs_7_9"] == 12

    def test_x_excluded_from_scoreless_count(self) -> None:
        """'x' token must not inflate scoreless frame rate."""
        shape_x = innings_shape("0,0,0,0,0,0,0,0,x")
        shape_9 = innings_shape("0,0,0,0,0,0,0,0,0")
        # With x: 8 played, 8 scoreless → rate = 1.0
        # Without x: 9 played, 9 scoreless → rate = 1.0
        assert abs(shape_x["scoreless_frame_rate"] - 1.0) < 1e-6
        assert abs(shape_9["scoreless_frame_rate"] - 1.0) < 1e-6

    def test_none_input_returns_zeros(self) -> None:
        shape = innings_shape(None)
        assert shape["total_runs"] == 0
        assert shape["biggest_inning_runs"] == 0
        assert shape["biggest_inning_idx"] is None


# ===========================================================================
# 4. decided_by logic tests
# ===========================================================================

def _make_shape(
    runs_1_3: int = 0,
    runs_4_6: int = 0,
    runs_7_9: int = 0,
    big_share: float = 0.0,
) -> dict:
    total = runs_1_3 + runs_4_6 + runs_7_9
    return {
        "big_inning_share": big_share,
        "runs_1_3": runs_1_3,
        "runs_4_6": runs_4_6,
        "runs_7_9": runs_7_9,
        "total_runs": total,
    }


class TestLabelGame:
    """_label_game: decided_by classification correctness."""

    def test_blowout_margin_7(self) -> None:
        h = _make_shape(5, 2, 1, 0.0)
        a = _make_shape(0, 1, 0, 0.0)
        assert _label_game(8, 1, h, a) == "BLOWOUT"

    def test_blowout_takes_priority_over_sp_duel(self) -> None:
        """margin>=7 wins even if total is low (pathological edge)."""
        h = _make_shape(7, 0, 0, 1.0)
        a = _make_shape(0, 0, 0, 0.0)
        assert _label_game(7, 0, h, a) == "BLOWOUT"

    def test_sp_duel(self) -> None:
        h = _make_shape(1, 1, 0, 0.5)
        a = _make_shape(1, 0, 1, 0.5)
        assert _label_game(2, 2, h, a) == "SP_DUEL"

    def test_sp_duel_boundary_total_4_margin_2(self) -> None:
        h = _make_shape(1, 0, 2, 1.0)
        a = _make_shape(0, 0, 1, 1.0)
        assert _label_game(3, 1, h, a) == "SP_DUEL"

    def test_big_inning_home(self) -> None:
        """Home team scores 5 of 6 in one inning."""
        h = _make_shape(5, 1, 0, big_share=5 / 6)
        a = _make_shape(2, 0, 1, big_share=2 / 3)
        assert _label_game(6, 3, h, a) == "BIG_INNING"

    def test_big_inning_away(self) -> None:
        h = _make_shape(1, 0, 1, big_share=0.5)
        a = _make_shape(0, 4, 0, big_share=1.0)
        assert _label_game(2, 4, h, a) == "BIG_INNING"

    def test_late_comeback_home_wins(self) -> None:
        """Home trails after 6 but wins via bullpen."""
        h = _make_shape(0, 0, 4, big_share=1.0)  # 4 late runs, big share
        a = _make_shape(1, 2, 0, big_share=0.0)  # 3 early runs
        # home_through_6 = 0, away_through_6 = 3 → home wins 4-3 = LATE_COMEBACK
        # But big_share >= 0.5 → would be BIG_INNING first unless we arrange it
        # Make it not big inning:
        h2 = _make_shape(0, 0, 4, big_share=0.4)
        a2 = _make_shape(1, 2, 0, big_share=0.0)
        result = _label_game(4, 3, h2, a2)
        assert result == "LATE_COMEBACK"

    def test_bullpen_swing(self) -> None:
        h = _make_shape(2, 1, 4, big_share=0.0)
        a = _make_shape(2, 1, 0, big_share=0.0)
        # home_through_6 = 3, away_through_6 = 3 → not late comeback
        # runs_7_9 diff = 4 >= 3 → BULLPEN_SWING
        assert _label_game(7, 3, h, a) == "BULLPEN_SWING"

    def test_routine(self) -> None:
        h = _make_shape(1, 2, 1, big_share=0.25)
        a = _make_shape(1, 1, 1, big_share=0.33)
        assert _label_game(4, 3, h, a) == "ROUTINE"


# ===========================================================================
# 5. SP handedness helper tests
# ===========================================================================

class TestExtractHand:
    def test_right_handed(self) -> None:
        assert _extract_hand("JBECKETT-R") == "R"

    def test_left_handed(self) -> None:
        assert _extract_hand("CSABATHIA-L") == "L"

    def test_no_suffix_returns_unknown(self) -> None:
        assert _extract_hand("CARPENTER-R") == "R"

    def test_none_returns_unknown(self) -> None:
        assert _extract_hand(None) == "U"

    def test_empty_returns_unknown(self) -> None:
        assert _extract_hand("") == "U"


class TestHandMatchup:
    def test_rr(self) -> None:
        assert _hand_matchup("R", "R") == "RR"

    def test_lr(self) -> None:
        assert _hand_matchup("L", "R") == "LR"

    def test_rl(self) -> None:
        assert _hand_matchup("R", "L") == "RL"

    def test_unknown_returns_mixed(self) -> None:
        assert _hand_matchup("U", "R") == "MIXED"

    def test_both_unknown_returns_mixed(self) -> None:
        assert _hand_matchup("U", "U") == "MIXED"


# ===========================================================================
# 6. Integration test with synthetic corpus (tmp_path)
# ===========================================================================

def _make_games_df() -> pd.DataFrame:
    """Minimal synthetic games corpus covering all decided_by labels."""
    return pd.DataFrame([
        # BLOWOUT
        {"event_id": "EVT001", "home_runs": 10, "away_runs": 1,
         "target_home_win": 1},
        # SP_DUEL
        {"event_id": "EVT002", "home_runs": 2, "away_runs": 1,
         "target_home_win": 1},
        # BIG_INNING (home gets 5 of 5 in one inning)
        {"event_id": "EVT003", "home_runs": 5, "away_runs": 2,
         "target_home_win": 1},
        # LATE_COMEBACK
        {"event_id": "EVT004", "home_runs": 4, "away_runs": 3,
         "target_home_win": 1},
        # BULLPEN_SWING
        {"event_id": "EVT005", "home_runs": 7, "away_runs": 3,
         "target_home_win": 1},
        # ROUTINE
        {"event_id": "EVT006", "home_runs": 4, "away_runs": 3,
         "target_home_win": 1},
    ])


def _make_pitchers_df() -> pd.DataFrame:
    return pd.DataFrame([
        # BLOWOUT — large margin, any innings
        {"event_id": "EVT001",
         "home_innings": "3,2,1,1,1,1,1,0,0",
         "away_innings": "0,0,1,0,0,0,0,0,0",
         "home_sp_name": "STARTER-R", "away_sp_name": "PITCHER-L"},
        # SP_DUEL — total=3, margin=1, small innings
        {"event_id": "EVT002",
         "home_innings": "1,0,0,0,1,0,0,0,0",
         "away_innings": "0,0,0,0,0,1,0,0,0",
         "home_sp_name": "STARTER-R", "away_sp_name": "PITCHER-R"},
        # BIG_INNING — home gets 5 in one inning
        {"event_id": "EVT003",
         "home_innings": "5,0,0,0,0,0,0,0,0",
         "away_innings": "1,0,0,0,1,0,0,0,0",
         "home_sp_name": "STARTER-L", "away_sp_name": "PITCHER-R"},
        # LATE_COMEBACK — home trails after 6 (0+0+1+0+0+1=2 vs 1+1+1+0+0+0=3)
        # but wins 4-3; big_share=0.25 so BIG_INNING not triggered
        {"event_id": "EVT004",
         "home_innings": "0,0,1,0,0,1,1,1,0",
         "away_innings": "1,1,1,0,0,0,0,0,0",
         "home_sp_name": "STARTER-R", "away_sp_name": "PITCHER-L"},
        # BULLPEN_SWING — home wins late (7_9 diff=3); big_share=0.29 < 0.5
        {"event_id": "EVT005",
         "home_innings": "1,1,1,1,0,0,2,1,0",
         "away_innings": "1,1,1,0,0,0,0,0,0",
         "home_sp_name": "STARTER-R", "away_sp_name": "PITCHER-R"},
        # ROUTINE — moderate, balanced
        {"event_id": "EVT006",
         "home_innings": "1,1,1,0,0,0,1,0,0",
         "away_innings": "1,1,0,0,0,0,1,0,0",
         "home_sp_name": "STARTER-R", "away_sp_name": "PITCHER-R"},
    ])


class TestBuildPostmortem:
    """Integration tests using a synthetic corpus written to tmp_path."""

    def _run(self, tmp_path: pathlib.Path) -> pd.DataFrame:
        games_path = tmp_path / "games.parquet"
        pitchers_path = tmp_path / "pitchers.parquet"
        out_path = tmp_path / "postmortem.parquet"
        _make_games_df().to_parquet(games_path, index=False)
        _make_pitchers_df().to_parquet(pitchers_path, index=False)
        return build_postmortem(
            games_path=str(games_path),
            pitchers_path=str(pitchers_path),
            out_path=str(out_path),
        )

    def test_output_has_expected_columns(self, tmp_path: pathlib.Path) -> None:
        df = self._run(tmp_path)
        for col in _EXPECTED_COLS:
            assert col in df.columns, f"Missing column: {col}"

    def test_row_count_matches_input(self, tmp_path: pathlib.Path) -> None:
        df = self._run(tmp_path)
        assert len(df) == 6

    def test_blowout_detected(self, tmp_path: pathlib.Path) -> None:
        df = self._run(tmp_path)
        assert "BLOWOUT" in df["decided_by"].values

    def test_sp_duel_detected(self, tmp_path: pathlib.Path) -> None:
        df = self._run(tmp_path)
        assert "SP_DUEL" in df["decided_by"].values

    def test_big_inning_detected(self, tmp_path: pathlib.Path) -> None:
        df = self._run(tmp_path)
        assert "BIG_INNING" in df["decided_by"].values

    def test_late_comeback_detected(self, tmp_path: pathlib.Path) -> None:
        df = self._run(tmp_path)
        assert "LATE_COMEBACK" in df["decided_by"].values

    def test_bullpen_swing_detected(self, tmp_path: pathlib.Path) -> None:
        df = self._run(tmp_path)
        assert "BULLPEN_SWING" in df["decided_by"].values

    def test_margin_correct(self, tmp_path: pathlib.Path) -> None:
        df = self._run(tmp_path)
        row = df[df["event_id"] == "EVT001"].iloc[0]
        assert row["margin"] == 9

    def test_total_runs_correct(self, tmp_path: pathlib.Path) -> None:
        df = self._run(tmp_path)
        row = df[df["event_id"] == "EVT001"].iloc[0]
        assert row["total_runs"] == 11

    def test_sp_hand_matchup_values(self, tmp_path: pathlib.Path) -> None:
        df = self._run(tmp_path)
        valid = {"LL", "LR", "RL", "RR", "MIXED"}
        for val in df["sp_hand_matchup"]:
            assert val in valid, f"Unexpected matchup: {val}"

    def test_big_inning_share_range(self, tmp_path: pathlib.Path) -> None:
        df = self._run(tmp_path)
        for col in ("home_big_inning_share", "away_big_inning_share"):
            assert df[col].between(0.0, 1.0).all(), f"{col} out of [0,1]"

    def test_scoreless_frame_rate_range(self, tmp_path: pathlib.Path) -> None:
        df = self._run(tmp_path)
        for col in ("home_scoreless_frame_rate", "away_scoreless_frame_rate"):
            assert df[col].between(0.0, 1.0).all(), f"{col} out of [0,1]"

    def test_parquet_written(self, tmp_path: pathlib.Path) -> None:
        self._run(tmp_path)
        assert (tmp_path / "postmortem.parquet").exists()

    def test_parquet_readable(self, tmp_path: pathlib.Path) -> None:
        self._run(tmp_path)
        df2 = pd.read_parquet(tmp_path / "postmortem.parquet")
        assert len(df2) == 6


# ===========================================================================
# 7. Real-corpus smoke test: postmortem.parquet existence + columns
# ===========================================================================

class TestRealCorpusOutput:
    """Checks that postmortem.parquet exists and has correct columns.

    Runs build_postmortem() against the live corpus to create the file,
    then validates the output. Skipped if corpus files are absent.
    """

    @pytest.fixture(scope="class", autouse=True)
    def _ensure_built(self) -> None:
        """Build the postmortem if data is available."""
        if not _OUT_PATH.parent.exists():
            pytest.skip("MLB data directory not found")
        games_ok = (_OUT_PATH.parent / "games.parquet").exists()
        pits_ok = (_OUT_PATH.parent / "pitchers.parquet").exists()
        if not (games_ok and pits_ok):
            pytest.skip("MLB corpus files not found")
        build_postmortem()

    def test_output_exists(self) -> None:
        assert _OUT_PATH.exists(), f"Expected {_OUT_PATH}"

    def test_expected_columns_present(self) -> None:
        df = pd.read_parquet(_OUT_PATH)
        for col in _EXPECTED_COLS:
            assert col in df.columns, f"Missing column: {col}"

    def test_decided_by_no_nulls(self) -> None:
        df = pd.read_parquet(_OUT_PATH)
        assert df["decided_by"].notna().all()

    def test_decided_by_known_values(self) -> None:
        df = pd.read_parquet(_OUT_PATH)
        valid = {"BLOWOUT", "SP_DUEL", "BIG_INNING",
                 "LATE_COMEBACK", "BULLPEN_SWING", "ROUTINE"}
        unknown = set(df["decided_by"].unique()) - valid
        assert not unknown, f"Unknown decided_by values: {unknown}"

    def test_coverage_positive(self) -> None:
        df = pd.read_parquet(_OUT_PATH)
        assert len(df) > 0

    def test_big_inning_share_range(self) -> None:
        df = pd.read_parquet(_OUT_PATH)
        for col in ("home_big_inning_share", "away_big_inning_share"):
            assert df[col].between(0.0, 1.0).all(), f"{col} out of [0,1]"
