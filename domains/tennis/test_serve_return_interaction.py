"""Smoke test for domains/tennis/serve_return_interaction.py -- tiny
synthetic profiles frame, asserts tiering + pairing-tally shape.

Run: python -m pytest domains/tennis/test_serve_return_interaction.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.tennis.serve_return_interaction import _tally_cells, _tier_lookup


def _profiles():
    # 4 player-season-tour rows, same tour+season, 2 above/below median each dim.
    return pd.DataFrame({
        "player_id": [1, 2, 3, 4], "season": [2020] * 4, "tour": ["ATP"] * 4,
        "serve_strength": [0.70, 0.60, 0.68, 0.58],
        "return_strength": [0.40, 0.30, 0.38, 0.28],
    })


def test_tier_lookup_big_elite():
    tiers = _tier_lookup(_profiles())
    assert set(tiers["serve_tier"]) == {"Big", "Normal"}
    assert set(tiers["return_tier"]) == {"Elite", "Normal"}
    assert tiers.loc[tiers["player_id"] == 1, "serve_tier"].item() == "Big"
    assert tiers.loc[tiers["player_id"] == 2, "serve_tier"].item() == "Normal"


def test_tally_cells_shape():
    rows = pd.DataFrame({
        "self_serve_tier": ["Big", "Big", "Normal", "Normal"],
        "opp_return_tier": ["Elite", "Normal", "Elite", "Normal"],
        "self_won": [1, 1, 0, 1],
    })
    table = _tally_cells(rows)
    assert table["n"].sum() == 4
    assert table["self_win_rate"].between(0, 1).all()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
