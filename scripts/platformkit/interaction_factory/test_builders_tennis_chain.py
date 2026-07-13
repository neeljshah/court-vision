"""Tests for the B9 tennis chain (rest/tournament-load) as-of attrs."""
from pathlib import Path

import pandas as pd

from scripts.platformkit.interaction_factory import builders_tennis_chain as tc
from scripts.platformkit.interaction_factory import generator as GEN


def _matches(rows):
    return pd.DataFrame(rows, columns=[
        "event_id", "date", "surface", "score", "tourney_id", "winner", "p1_id", "p2_id"])


def test_14d_window_math_and_transition():
    # Player 100 plays 3 matches: hard(d1), clay(d1+5, within 14d of the
    # d1+19 test row), hard(d1+19) -- e1 is 19 days prior, outside the window.
    m = _matches([
        ("e1", "2024-01-01", "Hard", "6-3 6-4", "t1", 1, 100, 200),
        ("e2", "2024-01-06", "Clay", "6-2 6-1", "t1", 1, 100, 201),
        ("e3", "2024-01-20", "Hard", "6-4 6-4", "t1", 1, 100, 202),
    ])
    chain = tc._player_chain_features(m)
    r = chain.loc[(chain["event_id"] == "e3") & (chain["player_id"] == 100)].iloc[0]
    # p1=100's trailing-14d window (2024-01-06..2024-01-20) contains only e2
    # (clay, 2024-01-06); e1 (2024-01-01) is 19 days prior -> outside window.
    assert r["matches_last_14d"] == 1
    assert r["sets_played_last_14d"] == 2  # e2 was 2 sets
    # today's match (e3) is Hard; the one match in the 14d window (e2) was
    # Clay -> a surface transition happened.
    assert r["surface_transition_flag"] == 1
    assert r["days_since_last_match"] == 14  # 2024-01-20 - 2024-01-06


def test_leak_trap_todays_match_never_in_own_attrs():
    # A player's FIRST match ever: no prior data at all -> zero load, NaN rest.
    m = _matches([("e1", "2024-03-01", "Hard", "6-3 6-4", "t1", 1, 300, 301)])
    frame = tc.build_tennis_chain_frame(m, tc.DIFF_ATTRS)
    row = frame.iloc[0]
    assert row["asof__matches_last_14d_diff"] == 0
    assert row["asof__sets_played_last_14d_diff"] == 0
    assert pd.isna(row["asof__days_since_last_match_diff"])
    # Two matches same calendar day for the same player: the second can never
    # see the first as "prior" (no intra-day ordering) -- both must show 0 load.
    m2 = _matches([
        ("e1", "2024-03-01", "Hard", "6-3 6-4", "t1", 1, 300, 301),
        ("e2", "2024-03-01", "Hard", "6-2 6-2", "t1", 1, 300, 302),
    ])
    frame2 = tc.build_tennis_chain_frame(m2, tc.DIFF_ATTRS)
    assert (frame2["asof__matches_last_14d_diff"] == 0).all()


def test_enumeration_non_empty():
    self_cross = GEN.enumerate_candidates("tennis_chain_asof_self_cross")
    cross = GEN.enumerate_candidates("tennis_chain_x_match_asof_cross")
    assert len(self_cross) == 6  # C(4,2) within the 4-attr chain pool
    assert len(cross) > 0


def test_missing_source_returns_none(monkeypatch):
    monkeypatch.setattr(tc, "_TENNIS_MATCHES", Path("does/not/exist.parquet"))
    assert tc._tennis_chain_builder(tc.DIFF_ATTRS, {}) is None
    assert tc._tennis_chain_x_match_cross_builder(tc.DIFF_ATTRS, {}) is None


def test_real_corpus_frame_row_count():
    if not tc._TENNIS_MATCHES.exists():
        return  # honest skip, no source on this box
    build = tc._tennis_chain_builder(tc.DIFF_ATTRS, GEN.TEMPLATES["tennis_chain_asof_self_cross"])
    assert build is not None
    assert len(build["frame"]) == 30616
    assert "date" in build["frame"].columns
