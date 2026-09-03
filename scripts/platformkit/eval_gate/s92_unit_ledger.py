"""scripts.platformkit.eval_gate.s92_unit_ledger -- the S92 five-man UNIT ON/OFF ledger.

Split out of `s92_nba_lineup_dynamic` only to keep that module inside the 300-LOC bar; it
has no other caller. From the same `team_system/pbp*/<nba_game_id>.json` action stream S84
already parses, it walks each game substitution-boundary to substitution-boundary and books,
for BOTH five-man units on the floor, the seconds of that stint and the score delta over it
(the actions carry cumulative `scoreHome` / `scoreAway`, so no shot arithmetic is needed).
`unit_history` then accumulates those stints per season and hands each target game the value
of a unit over its STRICTLY EARLIER games only -- a date's targets are snapshotted before any
game of that same date is booked, so a game can never enter its own or a sibling's history.
Possessions are a pace-100 time proxy (the feed carries no possession field); the value is
the n/(n+200)-shrunk net rating, which collapses to 100*points/(possessions+200).
Calibration language only; ASCII only.
Test: python -m pytest tests/platformkit/ingame/test_s92_nba_lineup_dynamic.py -q
"""
from __future__ import annotations

import json
from collections import defaultdict
from itertools import groupby
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from scripts.platformkit.eval_gate.s84_nba_lineup_at_tick import (elapsed_of, game_events,
                                                                  parse_clock)

REPO = Path(__file__).resolve().parents[3]
GAMES = REPO / "data" / "domains" / "basketball_nba" / "games.parquet"
POSS_PER_SEC = 100.0 / 2880.0   # ponytail: pace-100 proxy; the feed carries no possession field
SHRINK_POSS = 200.0             # the row's shrinkage n/(n+200)


def unit_stints(path: str, home: str, away: str) -> List[Tuple[frozenset, float, int]]:
    """Per five-man stint of BOTH sides: (unit, seconds, that unit's own point differential)."""
    subs, starters = game_events(path)
    with open(path, encoding="utf-8") as handle:
        acts = json.load(handle)["game"]["actions"]
    line = sorted((elapsed_of(a["period"], parse_clock(a.get("clock"))), i,
                   int(a.get("scoreHome") or 0), int(a.get("scoreAway") or 0))
                  for i, a in enumerate(acts) if parse_clock(a.get("clock")) >= 0.0)
    if (not line or sorted(starters) != sorted([home, away])
            or any(len(v) != 5 for v in starters.values())):
        return []
    floor = {team: set(five) for team, five in starters.items()}
    out: List[Tuple[frozenset, float, int]] = []
    start, prev, idx = 0.0, 0, 0
    bounds = [(b, list(g)) for b, g in groupby(subs, key=lambda e: float(e["elapsed"]))]
    for at, group in bounds + [(line[-1][0], [])]:
        while idx + 1 < len(line) and line[idx + 1][0] <= at:
            idx += 1
        margin = line[idx][2] - line[idx][3]
        if at > start and all(len(v) == 5 for v in floor.values()):
            out.append((frozenset(floor[home]), at - start, margin - prev))
            out.append((frozenset(floor[away]), at - start, prev - margin))
        for ev in group:
            side = floor.get(ev["team"])
            if side is not None:
                (side.add if ev["sub"] == "in" else side.discard)(int(ev["player"]))
        start, prev = at, margin
    return out


def unit_value(seconds: float, points: float) -> float:
    """Shrunk per-100-possession net rating: 100 * points / (possessions + 200); 0.0 unseen."""
    return 100.0 * float(points) / (float(seconds) * POSS_PER_SEC + SHRINK_POSS)


def unit_history(need: Dict[str, set], pbp: Dict[str, str]) -> Dict[str, Dict[frozenset, float]]:
    """{nba_game_id: {unit: shrunk net rating}} from STRICTLY EARLIER same-season games only."""
    meta = pd.read_parquet(GAMES, columns=["game_id", "date", "home_team", "away_team"])
    meta["game_id"], meta["date"] = meta["game_id"].astype(str), meta["date"].astype(str)
    meta = meta[meta["game_id"].isin(pbp)].copy()
    meta["season"] = meta["game_id"].str[3:5]
    out: Dict[str, Dict[frozenset, float]] = {}
    for _s, block in meta[meta["season"].isin({str(g)[3:5] for g in need})].groupby("season"):
        acc: Dict[frozenset, List[float]] = defaultdict(lambda: [0.0, 0.0])
        for _day, day_block in block.sort_values("game_id").groupby("date", sort=True):
            for gid in day_block["game_id"]:
                if gid in need:
                    out[gid] = {u: unit_value(*acc[u]) for u in need[gid] if u in acc}
            for rec in day_block.itertuples(index=False):
                for unit, sec, pts in unit_stints(pbp[rec.game_id], rec.home_team, rec.away_team):
                    acc[unit][0] += float(sec)
                    acc[unit][1] += float(pts)
    return out
