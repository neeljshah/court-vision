"""Per-file test for the pitch-class-grid explosion (ingredients_pitcher_grid
/ ingredients_batter_grid): pitch-class classification, hand-computed
mix-by-count cell, floor enforcement on a grid attribute, and batter
class-grid NaN safety (a class an entity never faced must be ABSENT, never
a fabricated 0.0 -- the nansum-on-empty-slice landmine named in the brief).
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/profiles/test_ingredients_grid.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.mlb.profiles.attribute_registry import ATTRIBUTES
from domains.mlb.profiles.build_profiles import _BUILDERS, build_attribute_window
from domains.mlb.profiles.ingredients_batter_grid import BUILDERS as BATTER_GRID_BUILDERS
from domains.mlb.profiles.ingredients_batter_grid import build_hard_contact_share
from domains.mlb.profiles.ingredients_pitcher_grid import BUILDERS as PITCHER_GRID_BUILDERS
from domains.mlb.profiles.ingredients_pitcher_grid import MIX_BUILDERS, classify_pitch_class


def test_classify_pitch_class():
    types = pd.Series(["FF", "SI", "SL", "CU", "CH", "FS", "PO", "UN", "None"])
    out = classify_pitch_class(types)
    assert list(out[:6]) == ["fastball", "fastball", "breaking", "breaking", "offspeed", "offspeed"]
    assert out[6] is None and out[7] is None and out[8] is None


def test_registry_grid_count_and_parity():
    # 14 original + 29 pitcher-grid + 20 batter-grid + 30 pitcher-zone + 17 batter-zone = 110
    assert len(ATTRIBUTES) == 110
    assert set(ATTRIBUTES) == set(_BUILDERS)
    assert len(PITCHER_GRID_BUILDERS) == 29
    assert len(BATTER_GRID_BUILDERS) == 20


def test_hand_computed_mix_ahead_fastball():
    """pitcher 1: 4 pitches while ahead (2 fastball, 1 breaking, 1 offspeed)
    -> mix_fastball_ahead raw_value = 2/4 = 0.5, n = 4 (total pitches ahead)."""
    frame = pd.DataFrame({
        "pitcher": [1] * 4,
        "pitch_type": ["FF", "SI", "SL", "CH"],
        "balls": [0, 0, 0, 0],
        "strikes": [1, 2, 1, 2],  # strikes > balls -> ahead, all 4 rows
    })
    build = MIX_BUILDERS["mix_fastball_ahead"]
    out = build(frame).set_index("entity_id")
    assert out.loc[1, "raw_value"] == pytest.approx(0.5)
    assert out.loc[1, "n"] == 4
    breaking = MIX_BUILDERS["mix_breaking_ahead"](frame).set_index("entity_id")
    assert breaking.loc[1, "raw_value"] == pytest.approx(0.25)


def test_floor_enforcement_on_grid_attribute():
    """command_edge_share_behind floor=50. One pitcher clears it, one doesn't."""
    rows = []
    for i in range(60):  # pitcher 1: 60 taken pitches while behind, clears floor=50
        rows.append({"pitcher": 1, "description": "ball", "balls": 2, "strikes": 0,
                      "plate_x": 0.0, "plate_z": 2.5, "sz_top": 3.5, "sz_bot": 1.5})
    for i in range(10):  # pitcher 2: 10 taken pitches while behind, below floor=50
        rows.append({"pitcher": 2, "description": "ball", "balls": 2, "strikes": 0,
                      "plate_x": 0.0, "plate_z": 2.5, "sz_top": 3.5, "sz_bot": 1.5})
    frame = pd.DataFrame(rows)
    scored, coverage = build_attribute_window("command_edge_share_behind", "2023", frame, {})
    assert coverage["n_considered"] == 2
    assert coverage["n_excluded_below_floor"] == 1
    assert set(scored["entity_id"]) == {1}


def test_batter_class_grid_nan_safety():
    """batter 1 faces ONLY fastballs and swings/misses at all of them -- the
    breaking-class and offspeed-class whiff builders must simply OMIT batter
    1 (never fabricate a 0.0 or a NaN raw_value for a class never faced)."""
    frame = pd.DataFrame({
        "batter": [1] * 5,
        "pitch_type": ["FF"] * 5,
        "description": ["swinging_strike"] * 5,
    })
    fb = BATTER_GRID_BUILDERS["whiff_vs_fastball"](frame)
    assert set(fb["entity_id"]) == {1}
    assert fb.set_index("entity_id").loc[1, "raw_value"] == pytest.approx(1.0)

    breaking = BATTER_GRID_BUILDERS["whiff_vs_breaking"](frame)
    assert len(breaking) == 0  # absent, not a fabricated 0.0/NaN row


def test_hard_contact_share_handles_all_nan_launch_speed_angle():
    """LANDMINE guard: an entity whose every batted ball has NaN
    launch_speed_angle must be dropped entirely (dropna upstream), not
    silently scored 0.0 via a nansum over the all-NaN slice."""
    frame = pd.DataFrame({
        "batter": [1, 1, 1],
        "launch_speed_angle": [float("nan"), float("nan"), float("nan")],
    })
    out = build_hard_contact_share(frame)
    assert len(out) == 0


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
