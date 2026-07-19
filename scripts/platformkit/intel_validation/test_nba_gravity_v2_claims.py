"""Per-file test for nba_gravity_v2_claims -- synthetic frames only.
Run: python -m pytest scripts/platformkit/intel_validation/test_nba_gravity_v2_claims.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import nba_gravity_v2_claims as m


def _raw():
    # G_high lifts on all three axes; G_fake has one big axis but the other
    # two flat (triangulation should rank G_high above G_fake); F fails floors.
    return pd.DataFrame({
        "player_id": [1, 2, 3, 4],
        "team_id": [10, 10, 11, 11],
        "player_name": ["G_high", "G_fake", "Mid", "F_floor"],
        "n_games": [70, 70, 70, 70],
        "min_on": [2000.0, 2000.0, 1500.0, 100.0],
        "teammate_efg_on": [.57, .54, .545, .55],
        "teammate_efg_off": [.52, .535, .54, .50],
        "teammate_fga_on": [3000, 3000, 2500, 150],
        "teammate_fga_off": [2000, 2000, 1800, 900],
        "net_rating_on_per48": [8.0, 2.0, 3.0, 1.0],
        "net_rating_off_per48": [1.0, 1.5, 2.5, 0.0],
        "teammate_efg_lift": [.05, .005, .005, .05],
        "net_rating_lift": [7.0, 0.5, 0.5, 1.0],
        "scoring_lift": [12.0, 15.0, 1.0, None],
    })


def test_triangulation_ranks_consistent_lift_first_and_floor_excludes():
    snap = m.compute_snapshot(_raw())
    # floor-failing rows STAY in the snapshot with NaN score (validator
    # re-derives the floor itself) -- never silently pre-filtered out
    f = snap[snap["player_name"] == "F_floor"].iloc[0]
    assert pd.isna(f["nba_gravity_v2"]) and f["n_present"] == 0
    top = snap.sort_values("nba_gravity_v2", ascending=False).iloc[0]
    assert top["player_name"] == "G_high"
    claim = m.build_claim(snap, 4)
    assert claim["claim_id"] == "nba_gravity_v2_triangulated_2025_26"
    assert claim["edge_claimed"] is False
    assert claim["criteria"]["entity_key"] == ["player_id", "team_id"]
    assert claim["ranking"][0]["player_name"] == "G_high"
