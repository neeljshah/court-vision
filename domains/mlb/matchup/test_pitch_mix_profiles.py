"""Per-file tests for pitch_mix_profiles. Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    domains/mlb/matchup/test_pitch_mix_profiles.py -q

Acceptance criteria:
  1. classify_terminal_k splits K rows into swinging/looking from `des` text
     only (never touches non-K rows).
  2. build_pitcher_profile's usage_share sums to 1 per pitcher-season and
     putaway_swinging_share is a valid rate.
  3. build_batter_profile's slug_proxy/k_rate/on_base_rate match a hand-
     computed fixture.
  4. Real on-disk corpus smoke test (2022 only, for speed).
"""
from __future__ import annotations

import pandas as pd

from domains.mlb.matchup import pitch_mix_profiles as pmp


def _fixture_rows() -> pd.DataFrame:
    return pd.DataFrame({
        "pitcher": [1, 1, 1, 1, 2, 2],
        "batter": [10, 10, 11, 11, 10, 11],
        "pitch_type": ["FF", "FF", "SL", "SL", "FF", "SL"],
        "zone": [5, 12, 3, 11, 5, 4],
        "type": ["S", "B", "S", "S", "S", "X"],
        "des": [
            None, None,
            "b strikes out swinging.",  # SL, batter 11, swinging K
            "b called out on strikes.",  # SL, batter 11, looking K (2nd PA)
            "a strikes out swinging.",  # pitcher 2, FF, batter 10, swinging K
            None,
        ],
        "events": [None, None, "strikeout", "strikeout", "strikeout", "field_out"],
    })


def test_classify_terminal_k_only_touches_k_rows():
    df = _fixture_rows()
    out = pmp.classify_terminal_k(df["des"], df["events"])
    assert list(out) == [None, None, "swinging", "looking", "swinging", None]


def test_build_pitcher_profile_usage_shares_and_putaway():
    rows = _fixture_rows()
    rows["season"] = 2022
    profile = pmp.build_pitcher_profile(rows)
    p1 = profile[profile["pitcher"] == 1].set_index("pitch_type")
    assert abs(p1["usage_share"].sum() - 1.0) < 1e-9
    assert p1.loc["FF", "usage_share"] == 0.5
    assert p1.loc["SL", "usage_share"] == 0.5
    # pitcher 1 SL: 1 swinging K + 1 looking K -> putaway_swinging_share = 0.5
    assert p1.loc["SL", "n_k"] == 2
    assert p1.loc["SL", "putaway_swinging_share"] == 0.5
    # pitcher 2 FF: 1 pitch, type=='S' -> strike_rate 1.0, 1 swinging K
    p2 = profile[profile["pitcher"] == 2].set_index("pitch_type")
    assert p2.loc["FF", "strike_rate"] == 1.0
    assert p2.loc["FF", "putaway_swinging_share"] == 1.0


def test_build_batter_profile_rates():
    rows = _fixture_rows()
    rows["season"] = 2022
    profile = pmp.build_batter_profile(rows)
    b11 = profile[(profile["batter"] == 11) & (profile["pitch_type"] == "SL")].iloc[0]
    # batter 11 vs SL: 3 PAs (2 K vs pitcher 1: swinging+looking, 1 field_out
    # vs pitcher 2) -> k_rate=2/3
    assert b11["n_pa"] == 3
    assert abs(b11["k_rate"] - 2 / 3) < 1e-9
    assert b11["putaway_swinging_share"] == 0.5
    assert b11["slug_proxy"] == 0.0  # no hits among these 3 PAs -> 0 total bases


def test_real_corpus_profiles_build_and_are_valid_rates():
    """Smoke test against the REAL on-disk statcast_fuller corpus (2022 only,
    for speed) -- proves the pipeline builds end-to-end on real data."""
    rows = pmp.load_pitch_rows(seasons=(2022,))
    assert len(rows) > 0
    pitcher_profile = pmp.build_pitcher_profile(rows)
    batter_profile = pmp.build_batter_profile(rows)
    assert len(pitcher_profile) > 0
    assert len(batter_profile) > 0
    assert pitcher_profile["strike_rate"].between(0, 1).all()
    assert pitcher_profile["in_zone_rate"].dropna().between(0, 1).all()
    assert batter_profile["k_rate"].between(0, 1).all()
    assert batter_profile["on_base_rate"].between(0, 1).all()
    usage_sums = pitcher_profile.groupby("pitcher")["usage_share"].sum()
    assert (usage_sums.round(6) == 1.0).all()
