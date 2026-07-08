"""Per-file test for claims_tournament_context.py -- synthetic frame,
hand-computed group math, edge_claimed=False, n-floor filtering.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_claims_tournament_context.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.soccer import claims_tournament_context as ctc


def _synthetic_results(n_competitive_neutral_post2000: int) -> pd.DataFrame:
    rows = []
    # competitive_neutral_post2000: n home wins evenly split with draws for hand-computed rates
    for i in range(n_competitive_neutral_post2000):
        home, away = (1, 0) if i % 2 == 0 else (1, 1)  # half home wins, half draws
        rows.append({"date": pd.Timestamp("2010-01-01"), "home_score": home, "away_score": away,
                     "tournament": "FIFA World Cup", "neutral": True})
    # friendly_home_venue_pre2000: all away wins (0 home wins, 0 draws)
    for _ in range(5):
        rows.append({"date": pd.Timestamp("1990-01-01"), "home_score": 0, "away_score": 1,
                     "tournament": "Friendly", "neutral": False})
    return pd.DataFrame(rows)


def test_group_label_hand_computed():
    df = _synthetic_results(n_competitive_neutral_post2000=4)
    source = ctc.build_source(df)
    assert set(source["group"]) == {"competitive_neutral_post2000", "friendly_home_venue_pre2000"}
    comp = source[source["group"] == "competitive_neutral_post2000"]
    assert comp["is_home_win"].sum() == 2
    assert comp["is_draw"].sum() == 2
    fr = source[source["group"] == "friendly_home_venue_pre2000"]
    assert fr["is_home_win"].sum() == 0
    assert fr["is_draw"].sum() == 0


def test_rank_hand_computed_rates(tmp_path):
    df = _synthetic_results(n_competitive_neutral_post2000=ctc.MIN_N)
    source = ctc.build_source(df)
    ranking, n_considered, n_excluded = ctc._rank(source, "is_home_win")
    ranked = {r["group"]: r for r in ranking}
    assert n_considered == 2
    assert n_excluded == 1  # friendly_home_venue_pre2000 has only 5 rows, below MIN_N
    assert len(ranking) == 1
    assert ranked["competitive_neutral_post2000"]["value"] == 0.5
    assert ranked["competitive_neutral_post2000"]["n"] == ctc.MIN_N


def test_n_floor_excludes_thin_group():
    df = _synthetic_results(n_competitive_neutral_post2000=ctc.MIN_N - 1)
    source = ctc.build_source(df)
    ranking, n_considered, n_excluded = ctc._rank(source, "is_draw")
    assert ranking == []  # both groups below floor (4/5 rows vs friendly's 5 rows)
    assert n_excluded == n_considered == 2


def test_edge_claimed_false_on_every_claim():
    df = _synthetic_results(n_competitive_neutral_post2000=ctc.MIN_N)
    source = ctc.build_source(df)
    for col in ("is_home_win", "is_draw"):
        ranking, n_considered, n_excluded = ctc._rank(source, col)
        claim = ctc._claim(f"test_{col}", "q", col, col, __import__("pathlib").Path("x.parquet"),
                            ranking, n_considered, n_excluded)
        assert claim["edge_claimed"] is False
