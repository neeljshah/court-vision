"""Per-file test for the 07-08 WNBA zone-shooting expansion: zone-SCALE
validation (the load-bearing check that NBA's zone_geometry, reused
unmodified, classifies WNBA cdn x/y correctly with no transform), plus
hand-computed checks for the zone share/efg, assisted_share, def-zone-delta
sign convention, and last10 builders.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/profiles/test_zone_builders.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_nba.composition.zone_geometry import classify_zone, shot_geometry_ft
from domains.basketball_wnba.profiles.ingredients_defzone import BUILDERS as DEFZONE_BUILDERS
from domains.basketball_wnba.profiles.ingredients_zone import BUILDERS as ZONE_BUILDERS


def test_zone_scale_real_wnba_shots():
    """Real WNBA cdn x/y (game 1012600001) must classify_zone the same way
    the description labels them -- no coordinate transform needed, same
    percent/2-ended convention as the NBA cdn PBP."""
    # driving finger-roll layup, x=93.16,y=52.91 -> ~1.87ft -> rim
    dist, _ = shot_geometry_ft(93.15972222222221, 52.9081763424324)
    assert dist == pytest.approx(1.87, abs=0.05)
    assert classify_zone(93.15972222222221, 52.9081763424324, is_3=False) == "rim"

    # "9' driving floating" jump shot, x=14.99,y=49.98 -> ~8.84ft, matches the
    # description's own distance label within rounding -> not rim, not a 3.
    dist2, _ = shot_geometry_ft(14.989787581699346, 49.98237857234397)
    assert dist2 == pytest.approx(8.84, abs=0.1)
    zone2 = classify_zone(14.989787581699346, 49.98237857234397, is_3=False)
    assert zone2 in ("paint", "mid")  # never rim/corner3/above_break_3 at ~9ft 2pt

    # "25' 3PT" make, x=31.85,y=50.23 -> a 3pt attempt near center -> above_break_3
    assert classify_zone(31.85253267973856, 50.226195053184675, is_3=True) == "above_break_3"


def test_zone_share_and_efg_hand_computed():
    shots = pd.DataFrame([
        {"game_id": "g1", "team_id": 1, "person_id": 10, "zone": "rim", "fgm": 1, "fga": 1, "is_assisted": 0},
        {"game_id": "g1", "team_id": 1, "person_id": 10, "zone": "rim", "fgm": 0, "fga": 1, "is_assisted": 0},
        {"game_id": "g1", "team_id": 1, "person_id": 10, "zone": "mid", "fgm": 1, "fga": 1, "is_assisted": 1},
        {"game_id": "g1", "team_id": 1, "person_id": 10, "zone": "corner3", "fgm": 1, "fga": 1, "is_assisted": 1},
    ])
    rim_share = ZONE_BUILDERS["zone_rim_share"](shots).set_index("entity_id")
    assert rim_share.loc["10", "raw_value"] == pytest.approx(2 / 4)
    assert rim_share.loc["10", "n"] == 2

    rim_efg = ZONE_BUILDERS["zone_rim_efg"](shots).set_index("entity_id")
    assert rim_efg.loc["10", "raw_value"] == pytest.approx(0.5)  # 1 make / 2 fga, no 3pt bonus

    corner3_efg = ZONE_BUILDERS["zone_corner3_efg"](shots).set_index("entity_id")
    assert corner3_efg.loc["10", "raw_value"] == pytest.approx(1.5)  # 1.5*1/1


def test_assisted_share_hand_computed():
    shots = pd.DataFrame([
        {"game_id": "g1", "team_id": 1, "person_id": 10, "zone": "rim", "fgm": 1, "fga": 1, "is_assisted": 1},
        {"game_id": "g1", "team_id": 1, "person_id": 10, "zone": "mid", "fgm": 1, "fga": 1, "is_assisted": 0},
        {"game_id": "g1", "team_id": 1, "person_id": 10, "zone": "mid", "fgm": 0, "fga": 1, "is_assisted": 0},
    ])
    out = ZONE_BUILDERS["assisted_share"](shots).set_index("entity_id")
    assert out.loc["10", "raw_value"] == pytest.approx(0.5)  # 1 assisted / 2 makes
    assert out.loc["10", "n"] == 2


def test_defzone_delta_sign_and_floor():
    """A player who allows LESS while on-court (tighter defense) must get a
    POSITIVE raw_value -- this registry has no per-attribute direction flag,
    so sign must be off-minus-on, not on-minus-off."""
    df = pd.DataFrame({
        "player_id": [10, 20], "team_id": [1, 1], "player_name": ["A", "B"],
        "min_on": [400.0, 50.0], "min_off": [400.0, 400.0],
        "rim_share_allowed_on": [0.20, 0.20], "rim_share_allowed_off": [0.35, 0.35],
    })
    out = DEFZONE_BUILDERS["def_rim_share_allowed_delta"](df)
    assert set(out["entity_id"]) == {"10"}  # player 20 fails min_on>=300
    row = out.set_index("entity_id").loc["10"]
    assert row["raw_value"] == pytest.approx(0.35 - 0.20)  # off - on, positive = tighter D on-court


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
