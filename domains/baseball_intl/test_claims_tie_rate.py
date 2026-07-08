"""Per-file test for claims_tie_rate.py -- synthetic npb/kbo frames,
hand-computed tie/run-diff/home-win math, edge_claimed=False, n-floor.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_intl/test_claims_tie_rate.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.baseball_intl import claims_tie_rate as ctr


def _league_frame(n_games: int, n_tied: int, n_rundiff1: int) -> pd.DataFrame:
    """n_games rows: first n_tied are ties (home=away=1, diff=0), next
    n_rundiff1 are 1-run decided games (home=2, away=1), rest are 3-run
    decided games (home=4, away=1, diff=3, not counted as rundiff1)."""
    rows = []
    for i in range(n_games):
        if i < n_tied:
            home, away, tied, home_win = 1, 1, True, False
        elif i < n_tied + n_rundiff1:
            home, away, tied, home_win = 2, 1, False, True
        else:
            home, away, tied, home_win = 4, 1, False, True
        rows.append({"date": pd.Timestamp("2023-01-01"), "home_score": home, "away_score": away,
                     "home_win": home_win, "tied": tied})
    return pd.DataFrame(rows)


def test_tie_rate_hand_computed():
    npb = _league_frame(n_games=100, n_tied=10, n_rundiff1=30)
    kbo = _league_frame(n_games=100, n_tied=5, n_rundiff1=20)
    source = ctr.build_all_games_source(npb, kbo)
    ranking, n_considered, n_excluded = ctr._rank(source, "is_tied")
    ranked = {r["league"]: r for r in ranking}
    assert n_considered == 2 and n_excluded == 0
    assert ranked["npb"]["value"] == 0.10
    assert ranked["kbo"]["value"] == 0.05
    assert ranked["npb"]["n"] == 100


def test_run_diff1_share_hand_computed():
    npb = _league_frame(n_games=100, n_tied=10, n_rundiff1=30)
    kbo = _league_frame(n_games=100, n_tied=5, n_rundiff1=20)
    source = ctr.build_all_games_source(npb, kbo)
    ranking, _, _ = ctr._rank(source, "is_rundiff1")
    ranked = {r["league"]: r for r in ranking}
    assert ranked["npb"]["value"] == 0.30
    assert ranked["kbo"]["value"] == 0.20


def test_home_win_share_decided_excludes_ties():
    npb = _league_frame(n_games=120, n_tied=10, n_rundiff1=110)  # 110 decided, all home wins, clears MIN_N
    kbo = _league_frame(n_games=110, n_tied=5, n_rundiff1=105)  # 105 decided, clears MIN_N
    decided = ctr.build_decided_source(npb, kbo)
    assert len(decided) == 110 + 105  # ties dropped entirely
    ranking, n_considered, n_excluded = ctr._rank(decided, "is_home_win")
    ranked = {r["league"]: r for r in ranking}
    assert ranked["npb"]["value"] == 1.0  # every decided row in the fixture is a home win
    assert ranked["npb"]["n"] == 110


def test_n_floor_excludes_thin_league():
    npb = _league_frame(n_games=ctr.MIN_N, n_tied=1, n_rundiff1=1)
    kbo = _league_frame(n_games=ctr.MIN_N - 1, n_tied=1, n_rundiff1=1)  # below floor
    source = ctr.build_all_games_source(npb, kbo)
    ranking, n_considered, n_excluded = ctr._rank(source, "is_tied")
    assert n_considered == 2
    assert n_excluded == 1
    assert len(ranking) == 1
    assert ranking[0]["league"] == "npb"


def test_edge_claimed_false_on_every_claim():
    npb = _league_frame(n_games=ctr.MIN_N, n_tied=5, n_rundiff1=10)
    kbo = _league_frame(n_games=ctr.MIN_N, n_tied=3, n_rundiff1=8)
    source = ctr.build_all_games_source(npb, kbo)
    for col in ("is_tied", "is_rundiff1"):
        ranking, n_considered, n_excluded = ctr._rank(source, col)
        claim = ctr._claim(f"test_{col}", "q", col, col, __import__("pathlib").Path("x.parquet"),
                            ranking, n_considered, n_excluded, "caveat")
        assert claim["edge_claimed"] is False
