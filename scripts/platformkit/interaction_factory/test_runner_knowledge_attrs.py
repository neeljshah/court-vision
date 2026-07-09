"""Per-file test for the 3 fix-wave-alpha (2026-07-11) MLB knowledge-mapped
as-of attrs in scripts.platformkit.interaction_factory.runner.build_mlb_pa_frame:
edge_zone_rate (pitcher), chase_rate (batter), first_pitch_strike_rate
(pitcher) -- split out of test_runner.py to keep that file under its LOC
budget (see knowledge_intake.KNOWN_MAPPINGS for the mechanisms these back).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/interaction_factory/test_runner_knowledge_attrs.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.interaction_factory import runner as RUN


def _synthetic_pa_zone_df():
    """One batter/pitcher pair, 3 PAs (2 pitches each), zone/type populated for
    edge_zone_rate (pitcher), chase_rate (batter), first_pitch_strike_rate
    (pitcher) -- fix-wave-alpha's 3 newly-mapped MLB knowledge attrs."""
    rows = []
    for gp, ab, ev, p1, p2 in [
        (1, 1, "single", {"zone": 12.0, "description": "foul", "type": "S"},
                          {"zone": 5.0, "description": "hit_into_play", "type": "X"}),
        (2, 1, "single", {"zone": 5.0, "description": "ball", "type": "B"},
                          {"zone": 13.0, "description": "swinging_strike", "type": "S"}),
        (3, 1, "strikeout", {"zone": 1.0, "description": "ball", "type": "B"},
                             {"zone": 1.0, "description": "ball", "type": "B"}),
    ]:
        for pn, p in ((1, p1), (2, p2)):
            rows.append({"game_pk": gp, "game_date": "2025-0%d-01" % gp, "at_bat_number": ab,
                         "pitch_number": pn, "pitcher": 9, "batter": 1,
                         "events": ev if pn == 2 else None, "launch_speed": None, **p})
    return pd.DataFrame(rows)


def test_mlb_pa_edge_zone_chase_first_pitch_attrs_are_leak_free():
    frame = RUN.build_mlb_pa_frame(
        _synthetic_pa_zone_df(), ["edge_zone_rate", "chase_rate", "first_pitch_strike_rate"],
        min_prior_pa=1, min_prior_pitches=1)
    frame = frame.reset_index(drop=True)
    # PA1: no prior pitches/PAs for this pitcher/batter -> NaN.
    assert pd.isna(frame.loc[0, "asof__edge_zone_rate"])
    assert pd.isna(frame.loc[0, "asof__chase_rate"])
    assert pd.isna(frame.loc[0, "asof__first_pitch_strike_rate"])
    # PA2's as-of reflects ONLY PA1's 2 pitches: 1 edge-zone pitch (zone 12) -> 0.5;
    # 1 out-of-zone pitch that was also a swing (foul) -> chase_rate 1/1 = 1.0;
    # PA1's first pitch (zone 12, type S) was a strike -> first_pitch_strike_rate 1.0.
    assert abs(frame.loc[1, "asof__edge_zone_rate"] - 0.5) < 1e-9
    assert abs(frame.loc[1, "asof__chase_rate"] - 1.0) < 1e-9
    assert abs(frame.loc[1, "asof__first_pitch_strike_rate"] - 1.0) < 1e-9
    # PA3's as-of reflects PA1+PA2 (4 pitches): edges at PA1p1(zone12)+PA2p2(zone13) -> 2/4=0.5;
    # out-of-zone pitches PA1p1+PA2p2, both swings (foul, swinging_strike) -> chase_rate 2/2=1.0;
    # first pitches: PA1 strike(S) + PA2 ball(B) -> first_pitch_strike_rate (1+0)/2=0.5 --
    # excludes PA3's own first pitch (ball, type B) from its own as-of feature.
    assert abs(frame.loc[2, "asof__edge_zone_rate"] - 0.5) < 1e-9
    assert abs(frame.loc[2, "asof__chase_rate"] - 1.0) < 1e-9
    assert abs(frame.loc[2, "asof__first_pitch_strike_rate"] - 0.5) < 1e-9
