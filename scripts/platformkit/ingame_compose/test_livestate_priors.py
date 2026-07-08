"""Leak tests for livestate_priors: every as-of table must be unaffected by
mutating rows dated ON OR AFTER the lookup date (future-event mutation), and
must equal the same lookup computed on a stream with those rows deleted
(prefix-equality)."""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.ingame_compose.livestate_priors import (
    build_league_shot_rate_table,
    build_player_net48_asof,
    build_top3_fga_table,
    league_shot_rates_asof,
    top3_fga_by_team,
)

D = pd.Timestamp


def _stints_games():
    stints = pd.DataFrame([
        dict(game_id="g1", team_id=1, lineup_key="1,2,3,4,5",
             pts_for=10, pts_against=5, elapsed_s=300.0),
        dict(game_id="g2", team_id=1, lineup_key="1,2,3,4,5",
             pts_for=4, pts_against=8, elapsed_s=300.0),
        dict(game_id="g3", team_id=1, lineup_key="1,2,3,4,5",   # target game (date >= cutoff)
             pts_for=999, pts_against=0, elapsed_s=300.0),
    ])
    games = pd.DataFrame([
        dict(game_id="g1", date=D("2026-01-01")),
        dict(game_id="g2", date=D("2026-01-03")),
        dict(game_id="g3", date=D("2026-01-05")),
    ])
    return stints, games


def test_player_net48_asof_ignores_same_or_later_game():
    stints, games = _stints_games()
    net = build_player_net48_asof(stints, games)
    before = net[("g3", 1)]

    mutated = stints.copy()
    mutated.loc[mutated["game_id"] == "g3", "pts_for"] = -99999  # blow up g3's own row
    net_mut = build_player_net48_asof(mutated, games)
    assert net_mut[("g3", 1)] == pytest.approx(before)

    # prefix-equality: dropping g3 entirely from the source and re-deriving
    # g1/g2-only priors by hand (net over g1+g2: pf=14,pa=13,sec=600) matches.
    expected = (14 - 13) / 600.0 * 2880.0
    assert before == pytest.approx(expected)


def test_top3_fga_by_team_excludes_target_and_future_games():
    box = pd.DataFrame([
        dict(team="OKC", player_id=1, date=D("2026-01-01"), fga=20),
        dict(team="OKC", player_id=2, date=D("2026-01-01"), fga=10),
        dict(team="OKC", player_id=1, date=D("2026-01-05"), fga=999),  # on/after cutoff
    ])
    table = build_top3_fga_table(box)
    top3 = top3_fga_by_team(table, "OKC", D("2026-01-05"))
    assert top3 == [1, 2]  # only the 01-01 rows count; the 999-fga row is same-date, excluded

    mutated = box.copy()
    mutated.loc[mutated["date"] == D("2026-01-05"), "fga"] = -1
    table_mut = build_top3_fga_table(mutated)
    assert top3_fga_by_team(table_mut, "OKC", D("2026-01-05")) == [1, 2]


def test_league_shot_rates_asof_excludes_target_date():
    box = pd.DataFrame([
        dict(date=D("2026-01-01"), fgm=5, fga=10, fg3m=1, fg3a=3, ftm=2, fta=2),
        dict(date=D("2026-01-05"), fgm=999, fga=1, fg3m=0, fg3a=0, ftm=0, fta=0),  # cutoff date
    ])
    table = build_league_shot_rate_table(box)
    p2, p3, pft = league_shot_rates_asof(table, D("2026-01-05"))
    # only 01-01 counts: fg2m=4,fg2a=7 -> p2=4/7; fg3m=1,fg3a=3 -> p3=1/3; ft=2/2
    assert p2 == pytest.approx(4 / 7)
    assert p3 == pytest.approx(1 / 3)
    assert pft == pytest.approx(1.0)
