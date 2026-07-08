"""Per-file test on two real fixture games that exercise BOTH description
formats this corpus mixes (0022500003.json = abbreviated "K. Towns 1 AST",
0022500001.json = full-name "Luguentz Dort assists") -- checks every parsed
row is a made shot (fgm==fga==1), name resolution match rate is near-total
on both formats (the specific bug class this module guards against: an
early version only handled the full-name format and silently dropped every
assist in the abbreviated-format games, ~16% of the corpus), and eFG values
fall in the documented [1.0, 1.5] range for made-only shots.

Run: python -m pytest domains/basketball_nba/interactions/test_assist_network.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from domains.basketball_nba.interactions.assist_network import (
    _abbrev_map_by_game,
    _name_to_id_by_game,
    build_edges,
    load_assisted_makes,
    resolve_assister_ids,
)
from domains.basketball_nba.lineups.pbp_lineups import _BOX_SRC, _PBP_DIR

_FIXTURE_ABBREV = _PBP_DIR / "0022500003.json"
_FIXTURE_FULL = _PBP_DIR / "0022500001.json"


@pytest.mark.skipif(
    not _FIXTURE_ABBREV.exists() or not _FIXTURE_FULL.exists() or not _BOX_SRC.exists(),
    reason="local-only data not present",
)
def test_assist_parsing_and_name_resolution_both_formats() -> None:
    box_df = pd.read_parquet(_BOX_SRC)
    name_map = _name_to_id_by_game(box_df)
    abbrev_map = _abbrev_map_by_game(box_df)

    all_resolved = []
    for fixture in (_FIXTURE_ABBREV, _FIXTURE_FULL):
        game_json = json.loads(fixture.read_text(encoding="utf-8"))
        rows = load_assisted_makes(game_json)
        assert len(rows) > 0
        for r in rows:
            assert r["fgm"] == 1 and r["fga"] == 1
            assert r["fg3m"] in (0, 1)
            assert r["assister_name"]  # non-empty parsed name

        resolved, n_unmatched = resolve_assister_ids(rows, name_map, abbrev_map)
        assert n_unmatched <= 1  # near-total match rate on this fixture, either format
        assert len(resolved) == len(rows) - n_unmatched
        all_resolved.extend(resolved)

    # confirm both formats actually got exercised (not both silently falling to one path)
    assert any(r["abbrev"] for r in all_resolved)
    assert any(not r["abbrev"] for r in all_resolved)

    # one game rarely clears MIN_ASSISTS_PER_EDGE=10 on any single pair -- lower it
    # to 1 here so the eFG-range check below actually exercises real rows.
    import domains.basketball_nba.interactions.assist_network as mod
    orig_floor = mod.MIN_ASSISTS_PER_EDGE
    mod.MIN_ASSISTS_PER_EDGE = 1
    try:
        edges = build_edges(all_resolved)
    finally:
        mod.MIN_ASSISTS_PER_EDGE = orig_floor

    assert len(edges) > 0
    vals = edges["efg_by_assister"].dropna()
    assert (vals >= 1.0).all() and (vals <= 1.5).all()
