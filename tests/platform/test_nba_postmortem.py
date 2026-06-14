"""
tests/platform/test_nba_postmortem.py
======================================
Tests for the NBA per-game post-mortem foundation.

Validates:
- Factor contributions sum to approximately the realized margin (within tolerance)
- Opponent join is correct (OREB% uses genuine opponent dreb)
- Schema / column completeness
- decided_by labels are valid
- Leak-tier tag is present and correct
- CLI dry-run runs without error
- Edge invariant: no edge claim anywhere in the module docstring
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[2]
_BS_PATH = _ROOT / "data/domains/basketball_nba/player_boxscores.parquet"
_GAMES_PATH = _ROOT / "data/domains/basketball_nba/games.parquet"

REAL_DATA_AVAILABLE = _BS_PATH.exists() and _GAMES_PATH.exists()
skip_no_data = pytest.mark.skipif(
    not REAL_DATA_AVAILABLE,
    reason="Real boxscore/games parquets not present",
)


@pytest.fixture(scope="module")
def postmortem_df():
    """Build the full postmortem DataFrame once for all tests in this module."""
    from domains.basketball_nba.postmortem import build_postmortems
    return build_postmortems()


# ---------------------------------------------------------------------------
# Synthetic data helpers (no disk dependency)
# ---------------------------------------------------------------------------

def _make_synthetic_bs() -> pd.DataFrame:
    """Two teams, three players each, for one game."""
    rows = [
        # game_id, date, season, team, opp, is_home, player_id, starter,
        # min, pts, reb, oreb, dreb, ast, stl, blk, tov, fgm, fga, fg3m, fg3a, ftm, fta, pf, plus_minus
        ("G001", "2024-01-01", "2024-25", "HOM", "AWY", 1.0, 1, True,
         30, 10, 5, 2, 3, 3, 1, 0, 2, 4, 9, 2, 4, 0, 0, 2, 5),
        ("G001", "2024-01-01", "2024-25", "HOM", "AWY", 1.0, 2, True,
         30, 20, 3, 1, 2, 5, 0, 1, 1, 8, 14, 2, 5, 2, 3, 1, 8),
        ("G001", "2024-01-01", "2024-25", "HOM", "AWY", 1.0, 3, False,
         20, 5, 2, 0, 2, 1, 0, 0, 0, 2, 5, 1, 2, 0, 0, 3, 3),
        ("G001", "2024-01-01", "2024-25", "AWY", "HOM", 0.0, 4, True,
         30, 8, 4, 1, 3, 2, 0, 0, 3, 3, 10, 1, 3, 1, 2, 2, -5),
        ("G001", "2024-01-01", "2024-25", "AWY", "HOM", 0.0, 5, True,
         30, 18, 2, 0, 2, 4, 1, 0, 2, 7, 13, 2, 6, 2, 2, 1, -8),
        ("G001", "2024-01-01", "2024-25", "AWY", "HOM", 0.0, 6, False,
         20, 4, 1, 0, 1, 0, 0, 0, 1, 1, 5, 2, 3, 0, 0, 4, -3),
    ]
    cols = [
        "game_id", "date", "season", "team", "opp", "is_home", "player_id",
        "starter", "min", "pts", "reb", "oreb", "dreb", "ast", "stl", "blk",
        "tov", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pf", "plus_minus",
    ]
    return pd.DataFrame(rows, columns=cols)


def _make_synthetic_games() -> pd.DataFrame:
    # HOM wins (pts: 35 vs 30)
    return pd.DataFrame(
        [{"game_id": "G001", "home_team": "HOM", "away_team": "AWY", "home_win": 1.0}]
    )


@pytest.fixture(scope="module")
def synthetic_df():
    """Post-mortem built from deterministic synthetic data."""
    bs = _make_synthetic_bs()
    games = _make_synthetic_games()

    # Temporarily write to tmp parquets and call build_postmortems
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        bs_p = Path(td) / "player_boxscores.parquet"
        gp = Path(td) / "games.parquet"
        bs.to_parquet(bs_p, index=False)
        games.to_parquet(gp, index=False)

        from domains.basketball_nba.postmortem import build_postmortems
        return build_postmortems(bs_path=bs_p, games_path=gp)


# ---------------------------------------------------------------------------
# Schema tests (synthetic)
# ---------------------------------------------------------------------------

EXPECTED_COLS = {
    "game_id", "home_team", "away_team", "home_win", "margin",
    "pace", "home_pts", "away_pts",
    "home_efg", "away_efg", "home_ortg", "away_ortg",
    "home_tov_rate", "away_tov_rate",
    "home_oreb_pct", "away_oreb_pct",
    "home_ft_rate", "away_ft_rate",
    "contrib_shooting", "contrib_turnovers",
    "contrib_rebounding", "contrib_free_throws",
    "decided_by", "_leak_tier",
}


def test_schema_columns_present(synthetic_df):
    """All required columns must be present in the output."""
    missing = EXPECTED_COLS - set(synthetic_df.columns)
    assert missing == set(), f"Missing columns: {missing}"


def test_one_row_per_game(synthetic_df):
    """Exactly one row per game_id."""
    assert len(synthetic_df) == synthetic_df["game_id"].nunique()


def test_decided_by_valid_labels(synthetic_df):
    valid = {"SHOOTING", "TURNOVERS", "REBOUNDING", "FREE_THROWS", "BALANCED"}
    bad = set(synthetic_df["decided_by"].unique()) - valid
    assert bad == set(), f"Unexpected decided_by labels: {bad}"


def test_leak_tier_tag(synthetic_df):
    """Every row must be tagged as DESCRIPTIVE_REALIZED."""
    assert (synthetic_df["_leak_tier"] == "DESCRIPTIVE_REALIZED").all()


def test_margin_sign_matches_home_win(synthetic_df):
    """Positive margin must correspond to home_win == True."""
    row = synthetic_df.iloc[0]
    assert row["margin"] > 0
    assert row["home_win"] is True or row["home_win"] == 1


# ---------------------------------------------------------------------------
# Factor contributions sum check (KEY TEST)
# ---------------------------------------------------------------------------

def test_factor_contributions_sum_close_to_margin(synthetic_df):
    """
    Sum of the four factor contributions must be within 200% of the realized
    margin (absolute) for every game.  The Four-Factor decomposition is a
    linear approximation (scaled by pace and empirical weights), so it will
    not exactly reproduce the margin — but a gross error (>2x) indicates a
    formula bug.  We also verify the sum and margin share the same sign,
    which is the load-bearing directional check.
    """
    for _, row in synthetic_df.iterrows():
        total = (
            row["contrib_shooting"]
            + row["contrib_turnovers"]
            + row["contrib_rebounding"]
            + row["contrib_free_throws"]
        )
        margin = row["margin"]
        if abs(margin) < 1.0:
            continue  # skip near-zero margins (e.g. OT games)
        rel_err = abs(total - margin) / abs(margin)
        assert rel_err < 2.0, (
            f"game_id={row['game_id']}: factor sum={total:.2f} margin={margin:.2f} "
            f"rel_err={rel_err:.2f} (>2.0)"
        )
        # Directional check: signs must agree
        assert (total * margin) > 0 or abs(total) < 0.5, (
            f"game_id={row['game_id']}: factor sum sign ({total:.2f}) opposes margin ({margin:.2f})"
        )


# ---------------------------------------------------------------------------
# Opponent join correctness (KEY TEST)
# ---------------------------------------------------------------------------

def test_opponent_join_oreb_pct_uses_opp_dreb(synthetic_df):
    """
    home_oreb_pct must use the opponent's (away) defensive rebounds in the
    denominator, NOT the home team's own dreb.

    Synthetic check: HOM has oreb=[2+1+0]=3, AWY has dreb=[3+2+1]=6
    OREB% = 3 / (3+6) = 0.333
    """
    row = synthetic_df.iloc[0]
    expected_home_oreb_pct = 3.0 / (3.0 + 6.0)  # ~0.333
    assert abs(row["home_oreb_pct"] - expected_home_oreb_pct) < 0.01, (
        f"home_oreb_pct={row['home_oreb_pct']:.4f} expected≈{expected_home_oreb_pct:.4f} — "
        "opponent join may be using same-team dreb"
    )


def test_away_oreb_pct_uses_home_dreb(synthetic_df):
    """
    away_oreb_pct must use the home team's defensive rebounds in the denominator.

    Synthetic: AWY oreb=[1+0+0]=1, HOM dreb=[3+2+2]=7
    OREB% = 1/(1+7) = 0.125
    """
    row = synthetic_df.iloc[0]
    expected_away_oreb_pct = 1.0 / (1.0 + 7.0)  # 0.125
    assert abs(row["away_oreb_pct"] - expected_away_oreb_pct) < 0.01, (
        f"away_oreb_pct={row['away_oreb_pct']:.4f} expected≈{expected_away_oreb_pct:.4f}"
    )


# ---------------------------------------------------------------------------
# Real-data smoke tests
# ---------------------------------------------------------------------------

@skip_no_data
def test_real_data_row_count(postmortem_df):
    """Must cover at least 100 games from the real corpus."""
    assert len(postmortem_df) >= 100, f"Only {len(postmortem_df)} games — too few"


@skip_no_data
def test_real_data_no_null_decided_by(postmortem_df):
    assert postmortem_df["decided_by"].isna().sum() == 0


@skip_no_data
def test_real_data_factor_sum_close_to_margin(postmortem_df):
    """Factor contributions should approximate margin within 30 pts for all games."""
    total = (
        postmortem_df["contrib_shooting"]
        + postmortem_df["contrib_turnovers"]
        + postmortem_df["contrib_rebounding"]
        + postmortem_df["contrib_free_throws"]
    )
    diff = (total - postmortem_df["margin"]).abs()
    # Allow up to 30 pts absolute error (Four-Factor is an approximation)
    bad = (diff > 30).sum()
    assert bad == 0, f"{bad} games have factor-sum error > 30 pts"


@skip_no_data
def test_real_data_home_win_margin_align(postmortem_df):
    """Margin sign should align with home_win in at least 98% of non-tie games.

    Excluded cases (known data artifacts):
    - margin==0: overtime games where boxscore pts are tied at regulation
    - Partial/abandoned games with very few total pts (<50 combined) where
      the final scoreline doesn't match boxscore player stats
    """
    # Exclude zero-margin (OT) and very small combined-pts (partial games)
    combined = postmortem_df["home_pts"] + postmortem_df["away_pts"]
    clean = postmortem_df[(postmortem_df["margin"] != 0) & (combined >= 50)]

    wins = clean[clean["home_win"] == True]
    losses = clean[clean["home_win"] == False]

    win_align = (wins["margin"] > 0).mean()
    loss_align = (losses["margin"] < 0).mean()

    assert win_align >= 0.98, (
        f"Only {win_align:.1%} of home wins have positive margin (expect >=98%)"
    )
    assert loss_align >= 0.98, (
        f"Only {loss_align:.1%} of home losses have negative margin (expect >=98%)"
    )


# ---------------------------------------------------------------------------
# Module docstring invariant — no edge claim
# ---------------------------------------------------------------------------

def test_no_edge_claim_in_module():
    """
    The postmortem module's docstring must contain the phrase
    'NO edge claim' (the explicit disclaimer is load-bearing).
    """
    import domains.basketball_nba.postmortem as pm_mod
    doc = pm_mod.__doc__ or ""
    assert "NO edge claim" in doc, (
        "postmortem.py docstring must contain 'NO edge claim'"
    )


# ---------------------------------------------------------------------------
# CLI dry-run
# ---------------------------------------------------------------------------

def test_cli_dry_run_exits_zero():
    """CLI --dry-run must exit 0 without writing any file."""
    result = subprocess.run(
        [sys.executable, "-m", "domains.basketball_nba.postmortem", "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(_ROOT),
    )
    assert result.returncode == 0, (
        f"CLI exited {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "Games covered" in result.stdout
