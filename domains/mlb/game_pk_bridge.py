"""domains.mlb.game_pk_bridge -- verified game_pk <-> event_id resolver (provable).

TASK-4b JOIN VERIFICATION ARTIFACT.

The MLB corpora use two disjoint identifier schemes that NO column directly bridges:

  * player_gamelogs.parquet  keys on  game_pk  (int64 MLB Stats API id, e.g. 822974),
                             covers the CURRENT season only (2026-04 .. 2026-06).
  * pitchers.parquet / games.parquet  key on  event_id  (str 'YYYYMMDD-HOME-AWAY-N'),
                             cover 2010..2021 -- ZERO date overlap with player_gamelogs.
  * games_current.parquet    keys on  event_id, covers 2022-04 .. present and DOES
                             overlap player_gamelogs (77/78 days).

So the ONLY provable bridge for the player_gamelogs era is
  game_pk  --(date, unordered-team-pair)-->  games_current.event_id
after normalising the two team-code dialects (player_gamelogs uses 'AZ'/'SD'/'TB'/...,
games_current uses 'ARI'/'SDG'/'TAM'/...). This resolver builds and verifies exactly
that map. On the real corpus it resolves 1030/1031 game_pks; the only ambiguity is
same-day doubleheaders (same date + team-pair, two events), which are flagged, NOT
guessed -- an ambiguous game_pk maps to event_id=None so no caller can silently pick
the wrong half of a doubleheader.

This module bridges GAME identity only. It deliberately does NOT recover starting-
pitcher identity: pitchers.parquet (the documented SP source) is era-disjoint from
player_gamelogs, and row-order within player_gamelogs is NOT start order (only 25%%
of the time is the first pitcher row the game's max-innings pitcher). See
asof_bullpen_DEFER.md for why the bullpen ERA-proxy feature is DEFERRED, not faked.

PURE pandas/numpy. No src/kernel/api imports. ASCII only.
ACCURACY/COVERAGE ONLY -- NO MARKET EDGE CLAIMED.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLAYER_GAMELOGS = _REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"
_GAMES_CURRENT = _REPO_ROOT / "data" / "domains" / "mlb" / "games_current.parquet"

# games_current team-code dialect -> player_gamelogs team-code dialect.
# Derived by diffing the two `home_team` value sets on overlapping dates.
GC_TO_PG_TEAM: Dict[str, str] = {
    "ARI": "AZ", "SDG": "SD", "TAM": "TB", "KAN": "KC",
    "SFO": "SF", "WAS": "WSH", "OAK": "ATH", "CUB": "CHC",
}


def _norm_team(code: object) -> str:
    s = str(code).strip().upper()
    return GC_TO_PG_TEAM.get(s, s)


def _pair_key(date_val: object, a: str, b: str) -> str:
    """Date + unordered team-pair key (both team codes normalised to pg dialect)."""
    d = str(pd.to_datetime(date_val).date())
    x, y = sorted((_norm_team(a), _norm_team(b)))
    return f"{d}|{x}|{y}"


@dataclass(frozen=True)
class BridgeResult:
    """Outcome of build_game_pk_bridge.

    mapping       : game_pk -> event_id (only UNAMBIGUOUS resolutions).
    n_game_pks    : distinct 2-team game_pks seen in player_gamelogs.
    n_resolved    : how many got a unique event_id.
    n_ambiguous   : how many fell on a doubleheader key (>1 event) -> left unmapped.
    n_unmatched   : how many found no games_current key at all.
    """

    mapping: Dict[int, str]
    n_game_pks: int
    n_resolved: int
    n_ambiguous: int
    n_unmatched: int

    @property
    def resolved_frac(self) -> float:
        return self.n_resolved / self.n_game_pks if self.n_game_pks else 0.0


def build_game_pk_bridge(
    player_gamelogs: Optional[pd.DataFrame] = None,
    games_current: Optional[pd.DataFrame] = None,
) -> BridgeResult:
    """Build the verified game_pk -> event_id map for the player_gamelogs era.

    Doubleheaders (a date+team-pair carrying >1 games_current event) are AMBIGUOUS and
    are intentionally left OUT of `mapping` (never guessed). Unmatched game_pks (no key
    in games_current) are likewise omitted. Both counts are returned for the caller.
    """
    pg = (player_gamelogs.copy() if isinstance(player_gamelogs, pd.DataFrame)
          else pd.read_parquet(str(_PLAYER_GAMELOGS)))
    gc = (games_current.copy() if isinstance(games_current, pd.DataFrame)
          else pd.read_parquet(str(_GAMES_CURRENT)))

    for col in ("game_pk", "date", "team"):
        if col not in pg.columns:
            raise KeyError(f"player_gamelogs missing column: {col!r}")
    for col in ("event_id", "date", "home_team", "away_team"):
        if col not in gc.columns:
            raise KeyError(f"games_current missing column: {col!r}")

    # games_current: pair_key -> list of event_ids (a list so doubleheaders are visible).
    gc_keys: Dict[str, list] = {}
    for _, r in gc.iterrows():
        k = _pair_key(r["date"], r["home_team"], r["away_team"])
        gc_keys.setdefault(k, []).append(str(r["event_id"]))

    # player_gamelogs: one (date, team-set) per game_pk.
    grp = pg.groupby("game_pk").agg(
        date=("date", "first"),
        teams=("team", lambda s: sorted(set(str(x) for x in s))),
    )

    mapping: Dict[int, str] = {}
    n_game_pks = n_resolved = n_ambiguous = n_unmatched = 0
    for game_pk, row in grp.iterrows():
        teams = row["teams"]
        if len(teams) != 2:
            continue  # not a clean 2-team game row; skip (cannot key)
        n_game_pks += 1
        k = _pair_key(row["date"], teams[0], teams[1])
        events = gc_keys.get(k)
        if not events:
            n_unmatched += 1
        elif len(events) > 1:
            n_ambiguous += 1  # doubleheader -- never guess which half
        else:
            mapping[int(game_pk)] = events[0]
            n_resolved += 1

    return BridgeResult(mapping, n_game_pks, n_resolved, n_ambiguous, n_unmatched)


def resolve_event_id(game_pk: int, bridge: BridgeResult) -> Optional[str]:
    """Return the event_id for a game_pk, or None if ambiguous/unmatched."""
    return bridge.mapping.get(int(game_pk))


__all__ = [
    "GC_TO_PG_TEAM", "BridgeResult", "build_game_pk_bridge", "resolve_event_id",
]
