"""Per-file test for ingredients_batted_ball.py (mlb_batted_ball_quality,
Family 1): hand-computed exit velocity / hard-hit / barrel / BABIP / chase
rate on a tiny synthetic frame, plus a floor-exclusion check and a registry
wiring check (every BUILDERS key has a matching attribute_registry entry).
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/profiles/test_ingredients_batted_ball.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.mlb.profiles.attribute_registry import ATTRIBUTES
from domains.mlb.profiles.ingredients_batted_ball import (
    BUILDERS,
    build_avg_exit_velocity,
    build_babip,
    build_barrel_rate,
    build_chase_rate,
    build_hard_hit_rate,
)


def test_builders_registered_in_attribute_registry():
    for attr in BUILDERS:
        assert attr in ATTRIBUTES, f"{attr} builder has no registry entry"
        assert ATTRIBUTES[attr]["entity"] == "batter"


def test_avg_exit_velocity_and_hard_hit_rate():
    # batter 1: 3 BIP at 90/96/100 mph -> avg 95.33, hard_hit_rate=2/3
    # batter 2: 1 BIP at 80 mph, plus a non-BIP row (type != 'X') ignored
    frame = pd.DataFrame({
        "batter": [1, 1, 1, 2, 2],
        "type": ["X", "X", "X", "X", "B"],
        "launch_speed": [90.0, 96.0, 100.0, 80.0, None],
    })
    ev = build_avg_exit_velocity(frame).set_index("entity_id")
    assert ev.loc[1, "raw_value"] == pytest.approx((90 + 96 + 100) / 3)
    assert ev.loc[1, "n"] == 3
    assert ev.loc[2, "n"] == 1  # the type=='B' row never counted

    hh = build_hard_hit_rate(frame).set_index("entity_id")
    assert hh.loc[1, "raw_value"] == pytest.approx(2 / 3)
    assert hh.loc[2, "raw_value"] == pytest.approx(0.0)


def test_barrel_rate_matches_launch_speed_angle_code():
    frame = pd.DataFrame({
        "batter": [1, 1, 1, 1],
        "launch_speed_angle": [6, 6, 5, 1],
    })
    out = build_barrel_rate(frame).set_index("entity_id")
    assert out.loc[1, "raw_value"] == pytest.approx(0.5)
    assert out.loc[1, "n"] == 4


def test_babip_hand_computed():
    # batter 1: events = single, home_run, strikeout, field_out, walk (not AB)
    # H=2 (single+HR), HR=1, K=1, SF=0, AB = all non-walk events = 4 (single,HR,K,field_out)
    # babip = (2-1)/(4-1-1+0) = 1/2 = 0.5
    frame = pd.DataFrame({
        "batter": [1, 1, 1, 1, 1],
        "events": ["single", "home_run", "strikeout", "field_out", "walk"],
    })
    out = build_babip(frame).set_index("entity_id")
    assert out.loc[1, "raw_value"] == pytest.approx(0.5)
    assert out.loc[1, "n"] == 4  # n_ab


def test_babip_zero_denominator_excluded_not_fabricated():
    # every event is a walk -> AB denominator is 0 -> ab_denom <= 0 -> dropped, not inf/NaN
    frame = pd.DataFrame({"batter": [9, 9], "events": ["walk", "walk"]})
    out = build_babip(frame)
    assert out.empty


def test_chase_rate_hand_computed():
    # batter 1: 4 out-of-zone pitches (zone>=11), 2 swung on (foul, hit_into_play), 2 taken (ball)
    frame = pd.DataFrame({
        "batter": [1, 1, 1, 1],
        "zone": [11, 12, 13, 14],
        "description": ["foul", "hit_into_play", "ball", "ball"],
    })
    out = build_chase_rate(frame).set_index("entity_id")
    assert out.loc[1, "raw_value"] == pytest.approx(0.5)
    assert out.loc[1, "n"] == 4


def test_chase_rate_in_zone_pitches_excluded():
    frame = pd.DataFrame({
        "batter": [1, 1],
        "zone": [5, 5],  # in-zone -- never counted as an out-of-zone chase opportunity
        "description": ["swinging_strike", "ball"],
    })
    out = build_chase_rate(frame)
    assert out.empty
