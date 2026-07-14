"""Per-file test for scripts.platformkit.live_edge.player_attr.build_attr.

Proves the join rail on a REAL slice (30 games, 2024-25): scorer attribution
rate on scored possessions >=95%, and the possession KEY this module emits
(period, clock_start, off_is_home, points) matches sim2_possessions.parquet's
own rows for the same games at a high rate -- confirming this is the same
deterministic segmentation, not a fuzzy re-derivation.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_player_attr.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.live_edge.player_attr.build_attr import (
    PBP_DIRS, SIM2_POSSESSIONS_PATH, build_season,
)

SLICE_GAMES = 30


def test_attribution_rate_on_real_slice():
    df = build_season("2024-25", PBP_DIRS["2024-25"], max_games=SLICE_GAMES)
    assert len(df) > 0, "no possessions extracted from real slice"
    scored = df[df["points"] > 0]
    assert len(scored) > 0
    rate = scored["scorer_player_id"].notna().mean()
    assert rate >= 0.95, f"attribution rate {rate:.4f} below 0.95 rail on real slice"


def test_possession_key_matches_sim2_cache():
    """Same (game_id, period, clock_start, off_is_home, points) key sim2's
    own cached possessions carry, for the same real games -- proves this is
    the identical segmentation walk, not an independent/fuzzy re-derivation."""
    if not SIM2_POSSESSIONS_PATH.exists():
        return  # cache not materialized in this environment; rate test above still binds
    df = build_season("2024-25", PBP_DIRS["2024-25"], max_games=SLICE_GAMES)
    game_ids = set(df["game_id"].unique())
    sim2 = pd.read_parquet(SIM2_POSSESSIONS_PATH)
    sim2 = sim2[sim2["game_id"].isin(game_ids) & (sim2["season"] == "2024-25")]
    assert len(sim2) > 0, "sim2 cache has no rows for this real slice"

    key_cols = ["game_id", "period", "clock_start", "off_is_home", "points"]
    mine = set(map(tuple, df[key_cols].values.tolist()))
    theirs = set(map(tuple, sim2[key_cols].values.tolist()))
    match_rate = len(mine & theirs) / len(theirs)
    assert match_rate >= 0.95, f"possession-key match rate {match_rate:.4f} below 0.95 rail"
