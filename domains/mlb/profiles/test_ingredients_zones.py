"""Per-file test for the attack-zone grid (ingredients_pitcher_zones /
ingredients_batter_zones): region classification on hand-placed pitches,
floor enforcement on a zone attribute, and one hand-computed batter
shadow-take rate.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/profiles/test_ingredients_zones.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.mlb.profiles.attribute_registry import ATTRIBUTES
from domains.mlb.profiles.build_profiles import LEADERBOARD_BUILDERS, _BUILDERS, build_attribute_window
from domains.mlb.profiles.ingredients_batter_zones import BUILDERS as BATTER_ZONE_BUILDERS
from domains.mlb.profiles.ingredients_batter_zones import build_shadow_take_rate
from domains.mlb.profiles.ingredients_pitcher_zones import BUILDERS as PITCHER_ZONE_BUILDERS
from domains.mlb.profiles.ingredients_pitcher_zones import classify_attack_zone

_ZONE_GEOM = {"sz_top": 3.5, "sz_bot": 1.5}  # zone center=2.5, half-height=1.0


def test_registry_zone_count_and_parity():
    # 63 (grid total) + 30 pitcher-zone + 17 batter-zone = 110
    # + 6 leaderboard (bat-tracking/OAA/catch-probability, see ingredients_leaderboard.py) = 116
    assert len(ATTRIBUTES) == 116
    assert set(ATTRIBUTES) == set(_BUILDERS) | set(LEADERBOARD_BUILDERS)
    assert len(PITCHER_ZONE_BUILDERS) == 30
    assert len(BATTER_ZONE_BUILDERS) == 17


def test_classify_attack_zone_hand_placed():
    """center of zone -> HEART; both horizontal edges (plate_x=+-0.83, on
    the true zone boundary) -> SHADOW; far outside -> WASTE; a near-miss
    beyond the shadow band but inside CHASE_FT -> CHASE."""
    rows = pd.DataFrame([
        {"plate_x": 0.0, "plate_z": 2.5, **_ZONE_GEOM},   # dead center -> HEART
        {"plate_x": 0.83, "plate_z": 2.5, **_ZONE_GEOM},  # right on the horizontal edge -> SHADOW
        {"plate_x": -0.83, "plate_z": 2.5, **_ZONE_GEOM}, # left on the horizontal edge -> SHADOW
        {"plate_x": 1.33, "plate_z": 2.5, **_ZONE_GEOM},  # 0.5ft beyond the edge -> CHASE
        {"plate_x": 3.0, "plate_z": 2.5, **_ZONE_GEOM},   # 2.17ft beyond the edge -> WASTE
    ])
    out = classify_attack_zone(rows)
    assert list(out) == ["heart", "shadow", "shadow", "chase", "waste"]


def test_floor_enforcement_on_zone_attribute():
    """region_pitch_share_heart floor=100 (n=total pitches, all zones).
    One pitcher clears it, one doesn't."""
    rows = []
    for _ in range(110):  # pitcher 1: 110 pitches, clears floor=100
        rows.append({"pitcher": 1, "plate_x": 0.0, "plate_z": 2.5, **_ZONE_GEOM})
    for _ in range(20):  # pitcher 2: 20 pitches, below floor=100
        rows.append({"pitcher": 2, "plate_x": 0.0, "plate_z": 2.5, **_ZONE_GEOM})
    frame = pd.DataFrame(rows)
    scored, coverage = build_attribute_window("region_pitch_share_heart", "2023", frame, {})
    assert coverage["n_considered"] == 2
    assert coverage["n_excluded_below_floor"] == 1
    assert set(scored["entity_id"]) == {1}


def test_hand_computed_shadow_take_rate():
    """batter 1: 4 pitches on the SHADOW edge, 2 swings (swinging_strike,
    foul) + 2 takes (ball) -> swing_rate=0.5 -> shadow_take_rate=0.5."""
    frame = pd.DataFrame({
        "batter": [1] * 4,
        "plate_x": [0.83] * 4, "plate_z": [2.5] * 4,
        "sz_top": [3.5] * 4, "sz_bot": [1.5] * 4,
        "description": ["swinging_strike", "ball", "ball", "foul"],
    })
    out = build_shadow_take_rate(frame).set_index("entity_id")
    assert out.loc[1, "raw_value"] == pytest.approx(0.5)
    assert out.loc[1, "n"] == 4


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
