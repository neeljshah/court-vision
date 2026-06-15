"""tests/platform/test_team_box_from_players.py

Per-file hermetic tests for domains.basketball_nba.team_box_from_players.
Injects a tiny synthetic player DataFrame; NO disk I/O, NO network.

Run: python -m pytest tests/platform/test_team_box_from_players.py -q
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

# Ensure repo root on path.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from domains.basketball_nba.team_box_from_players import (
    _SUM_STATS,
    aggregate_team_box,
)
from scripts.platformkit.brain_keystats import _stat_columns


# ---------------------------------------------------------------------------
# Synthetic fixture: 2 games, 3 players per side
# ---------------------------------------------------------------------------

def _make_players() -> pd.DataFrame:
    """Build a minimal synthetic player DataFrame."""
    rows = [
        # game G1 — home = LAL (is_home=1), away = BOS (is_home=0)
        dict(game_id="G1", date=pd.Timestamp("2024-01-01"), team="LAL", opp="BOS",
             is_home=1, player_id=1, player_name="P1", starter=True, min=30.0,
             pts=20, reb=5, oreb=2, dreb=3, ast=4, stl=1, blk=0,
             tov=2, fgm=8, fga=15, fg3m=2, fg3a=5, ftm=2, fta=3, pf=2, plus_minus=5),
        dict(game_id="G1", date=pd.Timestamp("2024-01-01"), team="LAL", opp="BOS",
             is_home=1, player_id=2, player_name="P2", starter=True, min=28.0,
             pts=15, reb=8, oreb=3, dreb=5, ast=2, stl=2, blk=1,
             tov=1, fgm=6, fga=12, fg3m=0, fg3a=0, ftm=3, fta=4, pf=3, plus_minus=3),
        dict(game_id="G1", date=pd.Timestamp("2024-01-01"), team="LAL", opp="BOS",
             is_home=1, player_id=3, player_name="P3", starter=False, min=18.0,
             pts=10, reb=3, oreb=1, dreb=2, ast=5, stl=0, blk=2,
             tov=3, fgm=4, fga=9, fg3m=2, fg3a=4, ftm=0, fta=0, pf=1, plus_minus=2),
        dict(game_id="G1", date=pd.Timestamp("2024-01-01"), team="BOS", opp="LAL",
             is_home=0, player_id=4, player_name="P4", starter=True, min=32.0,
             pts=25, reb=6, oreb=1, dreb=5, ast=7, stl=1, blk=0,
             tov=3, fgm=10, fga=18, fg3m=3, fg3a=7, ftm=2, fta=2, pf=4, plus_minus=-5),
        dict(game_id="G1", date=pd.Timestamp("2024-01-01"), team="BOS", opp="LAL",
             is_home=0, player_id=5, player_name="P5", starter=True, min=30.0,
             pts=12, reb=4, oreb=0, dreb=4, ast=3, stl=3, blk=1,
             tov=2, fgm=5, fga=11, fg3m=0, fg3a=2, ftm=2, fta=2, pf=2, plus_minus=-3),
        dict(game_id="G1", date=pd.Timestamp("2024-01-01"), team="BOS", opp="LAL",
             is_home=0, player_id=6, player_name="P6", starter=False, min=20.0,
             pts=8, reb=2, oreb=0, dreb=2, ast=1, stl=0, blk=0,
             tov=1, fgm=3, fga=8, fg3m=2, fg3a=5, ftm=0, fta=0, pf=1, plus_minus=-2),
        # game G2 — home = GSW, away = MIA
        dict(game_id="G2", date=pd.Timestamp("2024-01-02"), team="GSW", opp="MIA",
             is_home=1, player_id=7, player_name="P7", starter=True, min=36.0,
             pts=30, reb=5, oreb=0, dreb=5, ast=6, stl=2, blk=1,
             tov=4, fgm=11, fga=22, fg3m=5, fg3a=10, ftm=3, fta=4, pf=2, plus_minus=8),
        dict(game_id="G2", date=pd.Timestamp("2024-01-02"), team="MIA", opp="GSW",
             is_home=0, player_id=8, player_name="P8", starter=True, min=34.0,
             pts=22, reb=7, oreb=2, dreb=5, ast=5, stl=1, blk=2,
             tov=2, fgm=9, fga=17, fg3m=1, fg3a=4, ftm=3, fta=4, pf=3, plus_minus=-8),
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Expected aggregates for G1
# ---------------------------------------------------------------------------
_G1_HOME_PTS = 20 + 15 + 10   # 45
_G1_AWAY_PTS = 25 + 12 + 8    # 45  (tie, but still a valid row)
_G1_HOME_AST = 4 + 2 + 5       # 11
_G1_AWAY_AST = 7 + 3 + 1       # 11

_G2_HOME_PTS = 30
_G2_AWAY_PTS = 22


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def team_box():
    """Aggregate the synthetic players once."""
    players = _make_players()
    return aggregate_team_box(players)


def test_one_row_per_game(team_box):
    """Output must have exactly one row per game."""
    assert len(team_box) == 2, f"Expected 2 rows, got {len(team_box)}"


def test_home_score_equals_summed_pts(team_box):
    """home_score must equal the sum of pts for the home-side players."""
    g1 = team_box[team_box["event_id"] == "G1"].iloc[0]
    assert int(g1["home_score"]) == _G1_HOME_PTS, (
        f"G1 home_score {g1['home_score']} != expected {_G1_HOME_PTS}"
    )
    g2 = team_box[team_box["event_id"] == "G2"].iloc[0]
    assert int(g2["home_score"]) == _G2_HOME_PTS


def test_away_score_equals_summed_pts(team_box):
    """away_score must equal the sum of pts for the away-side players."""
    g1 = team_box[team_box["event_id"] == "G1"].iloc[0]
    assert int(g1["away_score"]) == _G1_AWAY_PTS
    g2 = team_box[team_box["event_id"] == "G2"].iloc[0]
    assert int(g2["away_score"]) == _G2_AWAY_PTS


def test_paired_stat_sums_correct(team_box):
    """home_ast / away_ast for G1 must equal the manual sums."""
    g1 = team_box[team_box["event_id"] == "G1"].iloc[0]
    assert int(g1["home_ast"]) == _G1_HOME_AST, (
        f"home_ast {g1['home_ast']} != {_G1_HOME_AST}"
    )
    assert int(g1["away_ast"]) == _G1_AWAY_AST, (
        f"away_ast {g1['away_ast']} != {_G1_AWAY_AST}"
    )


def test_home_away_abbr_correct(team_box):
    """home_abbr / away_abbr must reflect the is_home flag."""
    g1 = team_box[team_box["event_id"] == "G1"].iloc[0]
    assert g1["home_abbr"] == "LAL"
    assert g1["away_abbr"] == "BOS"
    g2 = team_box[team_box["event_id"] == "G2"].iloc[0]
    assert g2["home_abbr"] == "GSW"
    assert g2["away_abbr"] == "MIA"


def test_stat_columns_satisfy_keystats(team_box):
    """_stat_columns(output.columns) must return the expected paired stats.

    brain_keystats._stat_columns detects home_<stat>/away_<stat> pairs.
    Every stat in _SUM_STATS should appear because both sides were provided.
    """
    cols = list(team_box.columns)
    found = _stat_columns(cols)
    # All _SUM_STATS (except pts which becomes score) must be detected as pairs.
    # pts also appears as home_pts/away_pts in addition to home_score/away_score
    # so it should be in found too.
    for s in _SUM_STATS:
        assert s in found, (
            f"Stat '{s}' missing from _stat_columns result {found}"
        )


def test_output_has_required_identity_columns(team_box):
    """Output must carry event_id, date, home_abbr, away_abbr, home_score, away_score."""
    required = {"event_id", "date", "home_abbr", "away_abbr", "home_score", "away_score"}
    missing = required - set(team_box.columns)
    assert not missing, f"Missing required columns: {missing}"


def test_is_home_bool_input_works():
    """aggregate_team_box must handle boolean is_home values."""
    players = _make_players()
    players["is_home"] = players["is_home"].astype(bool)
    result = aggregate_team_box(players)
    assert len(result) == 2


def test_is_home_float_input_works():
    """aggregate_team_box must handle float is_home values (0.0/1.0)."""
    players = _make_players()
    players["is_home"] = players["is_home"].astype(float)
    result = aggregate_team_box(players)
    assert len(result) == 2
