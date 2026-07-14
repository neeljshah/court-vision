"""Per-file test: attach_terciles must never split the season column into
season_x/season_y (bdc6b03e suffix-collision bug class -- see corpus.py)."""
import pandas as pd

from domains.basketball_nba.sim2.corpus import attach_terciles


def _synthetic():
    poss = pd.DataFrame({
        "game_id": ["1", "1", "2", "2"],
        "off_is_home": [True, False, True, False],
        "season": ["2023-24", "2023-24", "2023-24", "2023-24"],
        "points": [2, 0, 2, 3],
    })
    wide = pd.DataFrame({
        "season": ["2023-24", "2023-24"],
        "home_off_t": [1, 2], "home_def_t": [0, 1],
        "away_off_t": [2, 0], "away_def_t": [1, 2],
        "pace_t": [1, 1],
    }, index=pd.Index(["1", "2"], name="game_id"))
    return poss, wide


def test_no_season_suffix_collision():
    poss, wide = _synthetic()
    m = attach_terciles(poss, wide)
    assert "season_x" not in m.columns
    assert "season_y" not in m.columns
    assert "season" in m.columns
    assert m["season"].tolist() == poss["season"].tolist()


def test_terciles_still_attached_correctly():
    poss, wide = _synthetic()
    m = attach_terciles(poss, wide).set_index(["game_id", "off_is_home"])
    # off_t/def_t pulled from the home/away side matching off_is_home
    assert m.loc[("1", True), "off_t"] == 1     # home_off_t for game 1
    assert m.loc[("1", False), "off_t"] == 2    # away_off_t for game 1
    assert m.loc[("1", True), "def_t"] == 1     # away_def_t (opponent) for home offense
    assert m.loc[("1", False), "def_t"] == 0    # home_def_t (opponent) for away offense
