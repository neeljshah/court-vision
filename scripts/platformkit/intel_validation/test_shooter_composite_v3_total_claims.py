"""Per-file test for shooter_composite_v3_total_claims -- pure-transform
checks on synthetic frames, no parquet/network.
Run: python -m pytest scripts/platformkit/intel_validation/test_shooter_composite_v3_total_claims.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import shooter_composite_v3_total_claims as m


def _raw(n=6):
    # player 0 elite everywhere; player 5 missing 3 profile ingredients (below 4/6)
    return pd.DataFrame({
        "player_id": range(n),
        "player_name": [f"P{i}" for i in range(n)],
        "games": [70] * n,
        "fg3a_per_game": [10, 8, 6, 4, 2, 1],
        "fg3_pct": [.45, .40, .38, .36, .34, .30],
        "ft_pct": [.95, .90, .85, .80, .75, .70],
        "clutch_efg": [.60, .55, .50, .45, .40, None],
        "gravity": [.9, .8, .7, .6, .5, None],
        "self_created_3_share": [.7, .6, .5, .4, .3, None],
    })


def test_elite_everywhere_ranks_first_and_score_is_100():
    snap = m.compute_snapshot(_raw())
    top = snap.sort_values("shooter_composite_v3_total", ascending=False).iloc[0]
    assert top["player_name"] == "P0"
    assert top["shooter_composite_v3_total"] == 100.0  # top percentile on all 6


def test_below_min_ingredients_excluded():
    snap = m.compute_snapshot(_raw())
    p5 = snap[snap["player_name"] == "P5"].iloc[0]
    assert p5["n_present"] == 3  # 3 boxscore only -> below the 4/6 floor
    assert pd.isna(p5["shooter_composite_v3_total"])
    claim = m.build_claim(snap, "2025-26")
    assert claim["n_excluded_below_floor"] == 1
    assert all(r["player_name"] != "P5" for r in claim["ranking"])


def test_claim_contract_fields():
    claim = m.build_claim(m.compute_snapshot(_raw()), "2025-26")
    assert claim["claim_id"] == "shooter_composite_v3_total_full_season_2025_26"
    assert claim["edge_claimed"] is False
    assert claim["criteria"]["entity_key"] == "player_id"
    assert claim["criteria"]["min_sample"] == {"n_present": 4}
    assert "DESCRIPTIVE" in claim["caveats"][0]
    assert claim["ranking"][0]["rank"] == 1
