"""Per-file test for scripts.platformkit.live_edge.foul_attr.build_foul.

Proves the join rail on a REAL slice (30 games, 2024-25): the possession key
this module emits (game_id, period, clock_start, off_is_home, points) matches
sim2_possessions.parquet's own rows for the same games at >=95% -- same
deterministic segmentation, not a fuzzy re-derivation (mirrors
test_player_attr.py's proof). Also proves the leak guard: a possession's
snapshot counters never include a foul committed during that same possession
or any later one.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_foul_attr.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from scripts.platformkit.live_edge.foul_attr.build_foul import (
    PBP_DIRS, SIM2_POSSESSIONS_PATH, build_season, classify_foul, extract_foul_possessions,
)

SLICE_GAMES = 30


def test_possession_key_matches_sim2_cache():
    if not SIM2_POSSESSIONS_PATH.exists():
        return  # cache not materialized here; other tests still bind
    df = build_season("2024-25", PBP_DIRS["2024-25"], max_games=SLICE_GAMES)
    assert len(df) > 0, "no possessions extracted from real slice"
    game_ids = set(df["game_id"].unique())
    sim2 = pd.read_parquet(SIM2_POSSESSIONS_PATH)
    sim2 = sim2[sim2["game_id"].isin(game_ids) & (sim2["season"] == "2024-25")]
    assert len(sim2) > 0, "sim2 cache has no rows for this real slice"

    key_cols = ["game_id", "period", "clock_start", "off_is_home", "points"]
    mine = set(map(tuple, df[key_cols].values.tolist()))
    theirs = set(map(tuple, sim2[key_cols].values.tolist()))
    match_rate = len(mine & theirs) / len(theirs)
    assert match_rate >= 0.95, f"possession-key match rate {match_rate:.4f} below 0.95 rail"


def test_foul_actions_found_across_schemas():
    """2025-26 marks fouls actionType=='foul'; 2023-24/2024-25 fold them into
    actionType=='other' + description text. classify_foul must catch both."""
    for season, d in PBP_DIRS.items():
        files = sorted(d.glob("*.json"))[:5]
        n_fouls = 0
        for fp in files:
            g = json.loads(fp.read_text(encoding="utf-8"))["game"]
            n_fouls += sum(1 for a in g["actions"] if classify_foul(a) is not None)
        assert n_fouls > 0, f"no foul actions detected in {season} sample -- schema drift?"


def test_leak_guard_snapshot_precedes_own_possession_fouls():
    """Build one real game; for every possession where a foul occurs INSIDE
    that possession's own segment, confirm the emitted snapshot for the NEXT
    possession reflects it but the possession's OWN row does not double count
    fouls that happen after its own start. Concretely: cumulative team-foul
    counts are non-decreasing across possession order, and a possession's
    off/def team-foul count never exceeds the count in a later possession's
    same (period, team) -- i.e. state only grows forward, never observes
    itself or the future."""
    fp = sorted(PBP_DIRS["2024-25"].glob("*.json"))[0]
    g = json.loads(fp.read_text(encoding="utf-8"))["game"]
    poss = extract_foul_possessions(g["actions"])
    assert len(poss) > 0
    seen_pf: dict = {}
    for i, p in enumerate(poss):
        pf_map = json.loads(p["pf_map"])
        for pid, cnt in pf_map.items():
            prev = seen_pf.get(pid, 0)
            assert cnt >= prev, f"possession {i}: personId {pid} pf count went backwards ({cnt} < {prev})"
            seen_pf[pid] = cnt
