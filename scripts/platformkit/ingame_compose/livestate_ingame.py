"""livestate_ingame -- the 4 v2 features AT a checkpoint t, computed ONLY from
this game's own events/stints with elapsed <= t (score/luck/bench) or start <
t (minutes/lineup identity). Same leak boundary discipline as checkpoints.py's
`_before`, extended to lineup stints:

  floor_lineup_at(t)      : identity of the 5-man unit on the floor AT t = the
                             most-recently-STARTED stint with start_g <= t. No
                             end_g is used to pick it -- "this lineup is still
                             out there" is exactly "no substitution happened
                             between start_g and t", knowable from t alone; end_g
                             is a FUTURE event relative to a mid-stint t and is
                             never read for this purpose.
  truncated_minutes_at(t) : per-player seconds actually played before t. A
                             stint spanning t contributes min(end_g, t)-start_g,
                             i.e. its TRUE end (which may be > t) is discarded
                             and replaced by the cap -- this is the literal
                             "truncate at t" leak guard the stint features need.
  distinct_players_at(t)  : players in any stint with start_g < t (bench depth
                             so far) -- identity only, no duration/end_g.
  shot_tally_before(t)    : made/attempted by shot type (2pt/3pt/freethrow)
                             for actions with elapsed <= t, reusing
                             checkpoints._global_elapsed verbatim (one clock
                             parser, same as the score/event_count checkpoint).

Feature diffs (home - away), returned together so a ladder rung either has
all 4 or the game/checkpoint is skipped whole (comparable sample across
rungs -- see conditional_gate_v2):
  1. floor_quality_now    : mean prior net48 (livestate_priors) of the players
                            floor_lineup_at(t) returns.
  2. star_minutes_load    : sum truncated_minutes_at(t) over each team's
                            preregistered top-3-FGA roster, / (3*t) [share of
                            available minutes].
  3. shooting_luck_so_far : actual - (league-rate) expected points from
                            shot_tally_before(t) -- see livestate_priors'
                            docstring for why this is shot-TYPE not shot-ZONE.
  4. bench_depth_used     : len(distinct_players_at(t)), home - away.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from domains.basketball_nba.lineups.pbp_lineups import _period_length_s
from scripts.platformkit.ingame_compose.checkpoints import _global_elapsed

FEATURE_NAMES = ["floor_quality_now", "star_minutes_load",
                  "shooting_luck_so_far", "bench_depth_used"]


@lru_cache(maxsize=16)
def _period_offset(period: int) -> float:
    return sum(_period_length_s(p) for p in range(1, period))


def add_global_times(stints: pd.DataFrame) -> pd.DataFrame:
    """+start_g/+end_g: global elapsed seconds (period-local start_s/end_s ->
    tip-off-relative), same convention as checkpoints._global_elapsed."""
    off = stints["period"].map(_period_offset)
    out = stints.copy()
    out["start_g"] = off + out["start_s"]
    out["end_g"] = off + out["end_s"]
    return out


def _lineup_ids(lineup_key: str) -> List[int]:
    return [int(x) for x in lineup_key.split(",") if x]


def floor_lineup_at(game_stints: pd.DataFrame, team_id: int, t: float) -> Optional[List[int]]:
    sub = game_stints[(game_stints["team_id"] == team_id) & (game_stints["start_g"] <= t)]
    if sub.empty:
        return None
    row = sub.loc[sub["start_g"].idxmax()]
    return _lineup_ids(row["lineup_key"])


def truncated_minutes_at(game_stints: pd.DataFrame, team_id: int, t: float) -> Dict[int, float]:
    sub = game_stints[(game_stints["team_id"] == team_id) & (game_stints["start_g"] < t)]
    out: Dict[int, float] = {}
    for row in sub.itertuples():
        dur = min(row.end_g, t) - row.start_g   # NEVER row.end_g alone -- truncate at t
        if dur <= 0:
            continue
        for pid in _lineup_ids(row.lineup_key):
            out[pid] = out.get(pid, 0.0) + dur
    return out


def distinct_players_at(game_stints: pd.DataFrame, team_id: int, t: float) -> set:
    sub = game_stints[(game_stints["team_id"] == team_id) & (game_stints["start_g"] < t)]
    players: set = set()
    for lk in sub["lineup_key"]:
        players.update(_lineup_ids(lk))
    return players


_SHOT_TYPES = {"2pt": (0, 1, 2), "3pt": (2, 3, 3), "freethrow": (4, 5, 1)}


def shot_tally_before(actions: List[Dict[str, Any]], t: float) -> Dict[int, List[int]]:
    """teamId -> [made2, att2, made3, att3, madeFT, attFT] for elapsed <= t."""
    tally: Dict[int, List[int]] = {}
    for a in actions:
        spec = _SHOT_TYPES.get(a.get("actionType"))
        tid = a.get("teamId")
        if spec is None or tid is None:
            continue
        e = _global_elapsed(a.get("period"), a.get("clock"))
        if e is None or e > t:
            continue
        made_i, att_i, _pts = spec
        d = tally.setdefault(int(tid), [0, 0, 0, 0, 0, 0])
        d[att_i] += 1
        if a.get("shotResult") == "Made":
            d[made_i] += 1
    return tally


def _luck_for_team(tally: Dict[int, List[int]], team_id: int,
                   rates: Tuple[float, float, float]) -> float:
    p2, p3, pft = rates
    made2, att2, made3, att3, madeft, attft = tally.get(team_id, [0, 0, 0, 0, 0, 0])
    actual = 2 * made2 + 3 * made3 + 1 * madeft
    expected = 2 * p2 * att2 + 3 * p3 * att3 + 1 * pft * attft
    return float(actual - expected)


def _mean_net(players: List[int], net48_asof: Dict[int, float]) -> Optional[float]:
    vals = [net48_asof[p] for p in players
            if p in net48_asof and not np.isnan(net48_asof[p])]
    return float(np.mean(vals)) if vals else None


def compute_v2_features(game_json: Dict[str, Any], game_stints: pd.DataFrame, t: float,
                        home_id: int, away_id: int, net48_asof: Dict[int, float],
                        top3_home: List[int], top3_away: List[int],
                        shot_rates: Tuple[float, float, float]
                        ) -> Optional[Tuple[float, float, float, float]]:
    """The 4 preregistered home-minus-away diffs at checkpoint t, or None if
    any is undefined (no floor lineup yet / no top-3 roster history) -- the
    whole game/checkpoint is skipped rather than partially imputed."""
    home_floor = floor_lineup_at(game_stints, home_id, t)
    away_floor = floor_lineup_at(game_stints, away_id, t)
    if not home_floor or not away_floor:
        return None
    h_net, a_net = _mean_net(home_floor, net48_asof), _mean_net(away_floor, net48_asof)
    if h_net is None or a_net is None:
        return None
    floor_quality_now = h_net - a_net

    if not top3_home or not top3_away:
        return None
    tm_h, tm_a = truncated_minutes_at(game_stints, home_id, t), truncated_minutes_at(game_stints, away_id, t)
    avail = 3.0 * t
    if avail <= 0:
        return None
    share_h = sum(tm_h.get(p, 0.0) for p in top3_home) / avail
    share_a = sum(tm_a.get(p, 0.0) for p in top3_away) / avail
    star_minutes_load = share_h - share_a

    tally = shot_tally_before(game_json["game"]["actions"], t)
    shooting_luck_so_far = (_luck_for_team(tally, home_id, shot_rates)
                            - _luck_for_team(tally, away_id, shot_rates))

    bench_depth_used = float(len(distinct_players_at(game_stints, home_id, t))
                             - len(distinct_players_at(game_stints, away_id, t)))

    return floor_quality_now, star_minutes_load, shooting_luck_so_far, bench_depth_used
