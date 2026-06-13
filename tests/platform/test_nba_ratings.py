"""tests.platform.test_nba_ratings — leak-free + correctness tests for NBA Elo ratings.

All tests are pure-Python / pandas; no network, no torch, no FastAPI.
Run with:
    python -m pytest tests/platform/test_nba_ratings.py -q
"""
from __future__ import annotations

import ast
import datetime as dt
import math
import pathlib

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from domains.basketball_nba.elo_config import ELO_K, ELO_MEAN, ELO_HFA, SEASON_REGRESS
from domains.basketball_nba.ratings import EloState, elo_state_asof, replay, walk_forward_elo

# ---------------------------------------------------------------------------
# Synthetic fixture — 14 games, 4 teams, 2 seasons (NYK/BOS/LAL/GSW)
# ---------------------------------------------------------------------------

COLS = ["date", "season", "home_team", "away_team", "home_win"]

GAMES_DATA = [
    # Season 2023
    ("2023-11-01", 2023, "NYK", "BOS", 1.0),
    ("2023-11-01", 2023, "LAL", "GSW", 0.0),
    ("2023-11-15", 2023, "BOS", "NYK", 0.0),
    ("2023-12-01", 2023, "GSW", "LAL", 1.0),
    ("2023-12-15", 2023, "NYK", "LAL", 1.0),
    ("2024-01-05", 2023, "BOS", "GSW", 0.0),
    ("2024-01-20", 2023, "LAL", "NYK", 1.0),
    # Season 2024 — all 4 teams cross the season boundary
    ("2024-10-22", 2024, "NYK", "BOS", 1.0),
    ("2024-10-22", 2024, "LAL", "GSW", 0.0),
    ("2024-11-05", 2024, "GSW", "NYK", 0.0),
    ("2024-11-20", 2024, "BOS", "LAL", 1.0),
    ("2024-12-01", 2024, "NYK", "GSW", 0.0),
    ("2024-12-15", 2024, "LAL", "BOS", 1.0),
    ("2025-01-10", 2024, "GSW", "BOS", 0.0),
]


def _make_df(rows=None) -> pd.DataFrame:
    if rows is None:
        rows = GAMES_DATA
    return pd.DataFrame(rows, columns=COLS)


FULL_DF = _make_df()


# ---------------------------------------------------------------------------
# 1. Empty DataFrame — no crash, empty result with required columns
# ---------------------------------------------------------------------------

class TestEmptyDataFrame:
    def test_empty_no_crash_and_columns(self):
        out = walk_forward_elo(pd.DataFrame(columns=COLS))
        assert len(out) == 0
        for col in ("elo_home", "elo_away", "elo_diff_hfa", "p_home_elo"):
            assert col in out.columns

    def test_replay_empty_no_crash(self):
        state = replay(pd.DataFrame(columns=COLS))
        assert state.n_processed == 0 and state.elo == {}


# ---------------------------------------------------------------------------
# 2. Single row — both teams at ELO_MEAN, p_home_elo > 0.5 (HFA), exact value
# ---------------------------------------------------------------------------

class TestSingleRow:
    _single = _make_df([("2023-11-01", 2023, "NYK", "BOS", 1.0)])

    def test_single_row_no_crash_and_len(self):
        assert len(walk_forward_elo(self._single)) == 1

    def test_single_row_both_teams_at_mean(self):
        out = walk_forward_elo(self._single)
        assert out["elo_home"].iloc[0] == ELO_MEAN
        assert out["elo_away"].iloc[0] == ELO_MEAN

    def test_single_row_p_home_above_half_and_exact(self):
        out = walk_forward_elo(self._single)
        p = out["p_home_elo"].iloc[0]
        expected = 1.0 / (1.0 + math.pow(10.0, -ELO_HFA / 400.0))
        assert p > 0.5
        assert abs(p - expected) < 1e-12


# ---------------------------------------------------------------------------
# 3. Leak-free / determinism
# ---------------------------------------------------------------------------

class TestLeakFreeAndDeterminism:
    def test_two_runs_identical(self):
        assert_frame_equal(walk_forward_elo(FULL_DF), walk_forward_elo(FULL_DF))

    def test_flip_future_result_doesnt_change_past_elos(self):
        """Changing home_win on the last game must not alter any earlier snapshot."""
        out_orig = walk_forward_elo(FULL_DF)
        df_flipped = FULL_DF.copy()
        df_flipped.loc[df_flipped.index[-1], "home_win"] = (
            0.0 if FULL_DF["home_win"].iloc[-1] >= 0.5 else 1.0
        )
        out_flip = walk_forward_elo(df_flipped)
        for col in ("elo_home", "elo_away", "elo_diff_hfa", "p_home_elo"):
            for i in range(len(out_orig) - 1):
                assert out_orig[col].iloc[i] == out_flip[col].iloc[i], (
                    f"leak: row {i} col {col} changed when flipping last game"
                )

    def test_replay_deterministic(self):
        s1, s2 = replay(FULL_DF), replay(FULL_DF)
        assert s1.elo == s2.elo and s1.n_processed == s2.n_processed


# ---------------------------------------------------------------------------
# 4. p_home_elo in (0,1) and Elo finite for all rows
# ---------------------------------------------------------------------------

class TestOutputRange:
    def test_p_home_in_unit_interval_and_elo_finite(self):
        out = walk_forward_elo(FULL_DF)
        for i in range(len(out)):
            p = out["p_home_elo"].iloc[i]
            assert 0.0 < p < 1.0, f"row {i}: p_home_elo={p}"
            assert math.isfinite(out["elo_home"].iloc[i])
            assert math.isfinite(out["elo_away"].iloc[i])


# ---------------------------------------------------------------------------
# 5. A team that wins repeatedly gains Elo; a loser loses it
# ---------------------------------------------------------------------------

class TestEloGainsFromWins:
    def test_repeated_winner_gains_elo(self):
        rows = [
            ("2023-11-01", 2023, "NYK", "BOS", 1.0),
            ("2023-11-10", 2023, "NYK", "LAL", 1.0),
            ("2023-11-20", 2023, "NYK", "GSW", 1.0),
        ]
        out = walk_forward_elo(_make_df(rows))
        # Row 2's pre-game elo_home already reflects wins 1+2 → must exceed MEAN.
        assert out["elo_home"].iloc[2] > ELO_MEAN

    def test_repeated_loser_loses_elo(self):
        rows = [
            ("2023-11-01", 2023, "NYK", "BOS", 1.0),
            ("2023-11-10", 2023, "LAL", "BOS", 1.0),
            ("2023-11-20", 2023, "GSW", "BOS", 1.0),
        ]
        out = walk_forward_elo(_make_df(rows))
        assert out["elo_away"].iloc[2] < ELO_MEAN


# ---------------------------------------------------------------------------
# 6. elo_diff_hfa = (elo_home + ELO_HFA) - elo_away exactly
# ---------------------------------------------------------------------------

class TestEloDiffFormula:
    def test_elo_diff_hfa_exact(self):
        out = walk_forward_elo(FULL_DF)
        for i in range(len(out)):
            expected = (out["elo_home"].iloc[i] + ELO_HFA) - out["elo_away"].iloc[i]
            assert abs(out["elo_diff_hfa"].iloc[i] - expected) < 1e-12, f"row {i}"

    def test_p_home_consistent_with_diff(self):
        out = walk_forward_elo(FULL_DF)
        for i in range(len(out)):
            d = out["elo_diff_hfa"].iloc[i]
            ep = 1.0 / (1.0 + math.pow(10.0, -d / 400.0))
            assert abs(out["p_home_elo"].iloc[i] - ep) < 1e-12, f"row {i}"


# ---------------------------------------------------------------------------
# 7. Season regression: fires on season transition, absent in mid-offseason cut
# ---------------------------------------------------------------------------

class TestSeasonRegression:
    def test_regression_fires_on_first_season2024_game(self):
        out = walk_forward_elo(FULL_DF)
        s2023 = replay(FULL_DF[FULL_DF["season"] == 2023].copy())
        expected = s2023.elo["NYK"] + SEASON_REGRESS * (ELO_MEAN - s2023.elo["NYK"])
        first_s24_nyk = out[
            (pd.to_datetime(out["date"]).dt.year == 2024)
            & (out["home_team"] == "NYK") & (out["season"] == 2024)
        ].iloc[0]
        assert abs(first_s24_nyk["elo_home"] - expected) < 1e-9

    def test_mid_offseason_cut_no_regression(self):
        # Sep 2024 is between last 2023 game (Jan 2024) and first 2024 game (Oct 2024).
        state = elo_state_asof(FULL_DF, dt.date(2024, 9, 1))
        for team in ["NYK", "BOS", "LAL", "GSW"]:
            assert state.last_season.get(team) == 2023, f"{team} regressed early"


# ---------------------------------------------------------------------------
# 8. Output schema + row count
# ---------------------------------------------------------------------------

class TestOutputSchema:
    def test_required_columns_and_row_count(self):
        out = walk_forward_elo(FULL_DF)
        assert len(out) == len(FULL_DF)
        for col in ("elo_home", "elo_away", "elo_diff_hfa", "p_home_elo"):
            assert col in out.columns

    def test_n_processed_equals_len(self):
        assert replay(FULL_DF).n_processed == len(FULL_DF)


# ---------------------------------------------------------------------------
# 9. F5 forbidden-import check (AST)
# ---------------------------------------------------------------------------

class TestForbiddenImports:
    _path = (
        pathlib.Path(__file__).parent.parent.parent
        / "domains" / "basketball_nba" / "ratings.py"
    )

    def _imports(self) -> list[str]:
        tree = ast.parse(self._path.read_text(encoding="utf-8"))
        out: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                out.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                out.append(node.module)
        return out

    def test_no_src_or_kernel_imports(self):
        for imp in self._imports():
            assert not imp.startswith("src."), f"forbidden: {imp}"
            assert not imp.startswith("kernel."), f"forbidden: {imp}"

    def test_no_other_domain_strings(self):
        src = self._path.read_text(encoding="utf-8")
        for bad in ("domains.mlb", "domains.tennis", "domains.soccer"):
            assert bad not in src, f"forbidden string {bad!r} in ratings.py"

    def test_allowed_imports_only(self):
        allowed = ("math", "datetime", "dataclasses", "typing", "pandas",
                   "numpy", "domains.basketball_nba", "__future__")
        for imp in self._imports():
            assert any(imp.startswith(p) for p in allowed), (
                f"non-allowlisted import: {imp}"
            )
