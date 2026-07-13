"""Per-file test for scripts.platformkit.interaction_factory.reserve.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/interaction_factory/test_reserve.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.interaction_factory import reserve as RES


def test_season_axis_reserves_most_recent_complete_season():
    frame = pd.DataFrame({
        "entity_id": [1, 2, 3, 4, 5],
        "season": [2022, 2022, 2023, 2023, 2024],
        "y": [0.1, 0.2, 0.3, 0.4, 0.5],
    })
    discovery, name = RES.reserve_mask(frame)
    # 2024 is the current/incomplete season (no LATER season exists) so it's
    # not "complete" either -- only 2023 (2024 exists after it) qualifies as
    # "most recent complete" and gets reserved. 2022 and 2024 stay in discovery.
    assert name == "2023"
    assert sorted(discovery["season"].unique().tolist()) == [2022, 2024]
    assert 2023 not in discovery["season"].values


def test_season_axis_with_one_distinct_value_is_r5_no_split():
    frame = pd.DataFrame({"entity_id": [1, 2], "season": [2024, 2024], "y": [0.1, 0.2]})
    discovery, name = RES.reserve_mask(frame)
    assert name is None
    assert len(discovery) == 2


def test_date_axis_reserves_trailing_25pct():
    frame = pd.DataFrame({
        "game_id": list(range(8)),
        "game_date": pd.to_datetime(["2025-01-0%d" % (i + 1) for i in range(8)]),
        "y": [float(i) for i in range(8)],
    })
    discovery, name = RES.reserve_mask(frame)
    assert name == "trailing_25pct_by_game_date"
    assert len(discovery) == 6  # 75% of 8
    # the 2 latest dates are excluded from discovery.
    assert discovery["game_date"].max() < frame["game_date"].max()


def test_no_time_axis_is_unchanged_r5():
    frame = pd.DataFrame({"player_id": [1, 2, 3], "y": [1.0, 2.0, 3.0]})
    discovery, name = RES.reserve_mask(frame)
    assert name is None
    pd.testing.assert_frame_equal(discovery, frame)
