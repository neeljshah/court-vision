"""P0.4/P3.1 — event application for the typed GameState.

Split out of game_state.py to honour the repo's 300-LOC/file rule.  ``apply_event`` mutates a
GameState IN PLACE using ONLY the current event + current state (no lookahead), so the
truncation-invariance gate (tests/test_brain_game_state.py) holds BY CONSTRUCTION — the state after
events[0:k] is independent of whether events[k:] exist.

Normalized event schema (the feed adapter maps raw CDN PBP to this; P3.1):
    {type, team, pid, pts, fg3, assist_pid, sub_in, sub_out, period,
     clock_remaining_sec, home_score, away_score}
``type`` ∈ {made_fg, miss_fg, ft, reb, ast, stl, blk, tov, foul, sub, end_period}.

DEFAULT-OFF: imported only by GameState.apply_event, which is reached only under CV_INGAME_STATE.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ingame.game_state import STAT_IDX, BONUS_FOULS, REG_GAME_LEN_SEC

_COUNT_STATS = ("reb", "ast", "stl", "blk", "tov")


def _elapsed(period: int, clock_remaining_sec: float) -> float:
    """Absolute seconds elapsed at (period, clock_remaining). Reg periods 720s, OT 300s."""
    cr = float(clock_remaining_sec)
    if period <= 4:
        return max(0.0, (period - 1) * 720.0 + (720.0 - cr))
    return max(0.0, 2880.0 + (period - 5) * 300.0 + (300.0 - cr))


def _bump(gs, pid, stat: str, amt: float, changed: List[int]) -> None:
    """Additive increment of a player's stat in both the numpy board and PlayerSuff."""
    if pid is None:
        return
    idx = gs.pid_index.get(int(pid))
    if idx is None:
        return
    gs.cur[idx, STAT_IDX[stat]] += amt
    ps = gs.players.get(int(pid))
    if ps is not None:
        ps.suff[stat] = ps.suff.get(stat, 0.0) + amt
    if int(pid) not in changed:
        changed.append(int(pid))


def apply_event(gs, event: Dict[str, Any]) -> List[int]:
    """Apply one normalized PBP event to ``gs`` in place; return the changed player_ids.

    Leak-free: reads ONLY ``event`` + current ``gs``. O(changed) for stat rows; minutes accrual
    touches on-court players (bounded ~10). Clock scalars are SET from the echo, never accumulated.
    """
    et = event.get("type", "")
    team = event.get("team", "")
    is_home = (team == "home")
    pid = event.get("pid")
    changed: List[int] = []

    # --- clock: SET from echo; accrue minutes for on-court players over the positive delta ---
    if "period" in event:
        gs.period = int(event["period"])
    if "clock_remaining_sec" in event:
        new_elapsed = _elapsed(gs.period, event["clock_remaining_sec"])
        delta_min = max(0.0, new_elapsed - gs.game_elapsed_sec) / 60.0
        if delta_min > 0.0:
            oc = gs.on_court
            for p, i in gs.pid_index.items():
                if bool(oc[i]):
                    gs.min_so_far[i] += delta_min
                    ps = gs.players.get(p)
                    if ps is not None:
                        ps.min_so_far += delta_min
        gs.game_elapsed_sec = new_elapsed
        gs.clock_s = int(round(float(event["clock_remaining_sec"])))
        gs.game_remaining_sec = max(0.0, REG_GAME_LEN_SEC - new_elapsed)
        gs.remaining_frac = min(1.0, max(0.0, gs.game_remaining_sec / REG_GAME_LEN_SEC))

    pts = float(event.get("pts", 0) or 0)

    if et == "made_fg":
        _bump(gs, pid, "pts", pts, changed)
        if event.get("fg3"):
            _bump(gs, pid, "fg3m", 1.0, changed)
        _bump(gs, event.get("assist_pid"), "ast", 1.0, changed)
        if is_home:
            gs.home_fgm += 1; gs.home_fga += 1
            if event.get("fg3"): gs.home_fg3a += 1
        else:
            gs.away_fgm += 1; gs.away_fga += 1
            if event.get("fg3"): gs.away_fg3a += 1
    elif et == "miss_fg":
        if is_home:
            gs.home_fga += 1
            if event.get("fg3"): gs.home_fg3a += 1
        else:
            gs.away_fga += 1
            if event.get("fg3"): gs.away_fg3a += 1
    elif et == "ft":
        if pts > 0:
            _bump(gs, pid, "pts", pts, changed)
        if is_home:
            gs.home_ftm += int(pts > 0)
        else:
            gs.away_ftm += int(pts > 0)
    elif et in _COUNT_STATS:
        _bump(gs, pid, et, 1.0, changed)
    elif et == "foul":
        idx = gs.pid_index.get(int(pid)) if pid is not None else None
        if idx is not None:
            gs.pf[idx] += 1
            ps = gs.players.get(int(pid))
            if ps is not None:
                ps.pf += 1
                if ps.pf >= 6:
                    ps.available = False
            if int(pid) not in changed:
                changed.append(int(pid))
        if is_home:
            gs.home_team_fouls_period += 1
            gs.home_in_bonus = gs.home_team_fouls_period >= BONUS_FOULS
        else:
            gs.away_team_fouls_period += 1
            gs.away_in_bonus = gs.away_team_fouls_period >= BONUS_FOULS
    elif et == "sub":
        for p, on in ((event.get("sub_in"), True), (event.get("sub_out"), False)):
            if p is None:
                continue
            i = gs.pid_index.get(int(p))
            if i is None:
                continue
            gs.on_court[i] = on
            ps = gs.players.get(int(p))
            if ps is not None:
                ps.on_court = on
            if int(p) not in changed:
                changed.append(int(p))
    elif et == "end_period":
        gs.home_team_fouls_period = 0
        gs.away_team_fouls_period = 0
        gs.home_in_bonus = False
        gs.away_in_bonus = False
    # unknown types: no-op (return [])

    # --- score: authoritative echo wins; else derive from pts on scoring plays ---
    if "home_score" in event:
        gs.home_score = int(event["home_score"])
    elif et in ("made_fg", "ft") and is_home:
        gs.home_score += int(pts)
    if "away_score" in event:
        gs.away_score = int(event["away_score"])
    elif et in ("made_fg", "ft") and not is_home:
        gs.away_score += int(pts)
    gs.score_margin = gs.home_score - gs.away_score

    return changed
