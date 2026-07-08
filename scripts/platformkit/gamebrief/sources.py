"""Read-only, premise-checked loaders for every store the brief cites.

Every loader degrades to None / [] on a missing file -- never raises -- so
assemble.py can render an honest "not available" line per section instead of
crashing. Parquet reads are lru_cache'd (module-level, process-lifetime) since
one CLI run touches several of these from multiple sections.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _pq(rel: str) -> Optional[pd.DataFrame]:
    p = _REPO_ROOT / rel
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception:  # noqa: BLE001 - degrade, never crash the brief
        return None


def _jsonl(rel: str) -> List[Dict[str, Any]]:
    p = _REPO_ROOT / rel
    if not p.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


@functools.lru_cache(maxsize=1)
def games() -> Optional[pd.DataFrame]:
    return _pq("data/domains/basketball_nba/games.parquet")


@functools.lru_cache(maxsize=1)
def player_boxscores() -> Optional[pd.DataFrame]:
    return _pq("data/domains/basketball_nba/player_boxscores.parquet")


@functools.lru_cache(maxsize=1)
def gravity_proxy() -> Optional[pd.DataFrame]:
    return _pq("data/cache/team_system/lineups/gravity_proxy_2025_26.parquet")


@functools.lru_cache(maxsize=1)
def lineup_synergy() -> Optional[pd.DataFrame]:
    return _pq("data/cache/team_system/interactions/lineup_synergy_2025_26.parquet")


@functools.lru_cache(maxsize=1)
def on_off() -> Optional[pd.DataFrame]:
    return _pq("data/cache/team_system/lineups/on_off_2025_26.parquet")


@functools.lru_cache(maxsize=1)
def usage_redistribution() -> Optional[pd.DataFrame]:
    return _pq("data/cache/team_system/interactions/usage_redistribution_2025_26.parquet")


@functools.lru_cache(maxsize=1)
def concession() -> Optional[pd.DataFrame]:
    return _pq("data/cache/team_system/composition/concession_2025_26.parquet")


@functools.lru_cache(maxsize=1)
def shot_xpts() -> Optional[pd.DataFrame]:
    return _pq("data/cache/team_system/composition/shot_xpts_2025_26.parquet")


@functools.lru_cache(maxsize=1)
def team_game_zone_sample() -> Optional[pd.DataFrame]:
    """Team-game shot-zone attempt counts (rim/mid/paint/fg3a). Narrow coverage
    (verified: only NYK/SAS, a finals-study sample) -- callers must premise-
    check the team is present before using it, never assume league-wide."""
    return _pq("data/cache/team_system/team_game.parquet")


@functools.lru_cache(maxsize=1)
def injury_rows() -> List[Dict[str, Any]]:
    return _jsonl("data/cache/edge_engine/injury_facts_nba.jsonl")


@functools.lru_cache(maxsize=1)
def news_rows() -> List[Dict[str, Any]]:
    return _jsonl("data/cache/edge_engine/news_facts_nba.jsonl")
