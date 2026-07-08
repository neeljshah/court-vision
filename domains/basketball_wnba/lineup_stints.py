"""domains.basketball_wnba.lineup_stints -- full-game 5-player lineup stint
reconstruction from the CDN backfill playbyplay log (data/domains/wnba/
cdn_backfill/<gameId>/{boxscore,playbyplay}.json, see cdn_backfill.py).

WHY A NEW MODULE (vs. reusing cdn_states_extract.py): that module only
reconstructs lineups at THREE checkpoints (end_q1/half/end_q3) for the
in-game-conditioning gate. This module walks the FULL substitution timeline
end-to-end (period-1 opening tip -> final game-end action) to produce
CONTIGUOUS 5-man stints with elapsed minutes + points-for/against -- the
SAME "period starters + chronological substitution replay" inference
cdn_states_extract._lineup_at_checkpoint already uses, extended across the
whole game instead of stopping at 3 snapshots (reuse over reinvent: this
module imports clock_to_sec/_game_elapsed_sec from ingame_live_cdn.py, the
SAME clock parser + elapsed-time formula the CDN family already
ground-truthed -- cdn_states_extract.py itself already imports a private
helper, _run_last_3min, from that same module, so cross-module private
reuse within this domain is an established pattern, not a new one).

SCORE ATTRIBUTION: every playbyplay action (not just scoring ones) carries
its own scoreHome/scoreAway as a CUMULATIVE running total (ground-truthed
against game 1012600001: the period-1-start action reports '0'/'0', the
game-end action reports the final score) -- so a stint's points-for/against
is simply the score delta between the action that OPENED the stint and the
action that CLOSED it (a substitution batch, or game-end). No shot-by-shot
point-value bookkeeping needed here, unlike atlas_extract_pbp's per-action
point-value derivation (that module needs the POINT VALUE of one shot; this
module only needs two score snapshots' delta).

MULTI-PLAYER SUBSTITUTIONS: several 'in'/'out' actions can share the exact
same (period, clock) timestamp (a double/triple sub). All subs sharing one
timestamp are batched and applied together before the stint is closed/
reopened ONCE per batch -- never once per individual player swap (which
would fabricate spurious near-zero-length stints).

HONEST GAP: if a substitution replay ever yields an oncourt set != 5 players
for a side (malformed/partial feed, or missing starters), that stint (and
any stint built from that side for that game once the mismatch occurs) is
DROPPED -- not fabricated with a padded/truncated 5th player -- same
"honest None over fake 5th player" contract as
cdn_states_extract._lineup_at_checkpoint.

INVARIANTS: standalone; <=300 LOC; ASCII only; no pip installs; pure
functions (no network I/O; only iter_backfilled_games touches disk, reused
from atlas_extract_common); never raises (a malformed game degrades to zero
stints for that game/side, not an aborted run).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_lineup_stints.py -q
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from domains.basketball_wnba.atlas_extract_common import iter_backfilled_games
from domains.basketball_wnba.ingame_live_cdn import _game_elapsed_sec, clock_to_sec

SIDES = ("home", "away")


@dataclass
class Stint:
    game_id: str
    team_id: Any
    side: str
    lineup: Tuple[str, ...]  # sorted personId strings, always length 5
    elapsed_start_sec: float
    elapsed_end_sec: float
    pts_for: float
    pts_against: float

    @property
    def minutes(self) -> float:
        return max(0.0, self.elapsed_end_sec - self.elapsed_start_sec) / 60.0


def _starters(team: dict) -> Optional[List[str]]:
    ids = [str(p.get("personId")) for p in (team.get("players") or [])
           if isinstance(p, dict) and str(p.get("starter")) == "1"]
    return ids if len(ids) == 5 else None


def _score_of(action: dict) -> Optional[Tuple[float, float]]:
    try:
        return float(action.get("scoreHome")), float(action.get("scoreAway"))
    except (TypeError, ValueError):
        return None


def _side_score(score: Tuple[float, float], side: str) -> Tuple[float, float]:
    home, away = score
    return (home, away) if side == "home" else (away, home)


def _elapsed(action: dict) -> Optional[float]:
    period = action.get("period")
    if period is None:
        return None
    try:
        period = int(period)
    except (TypeError, ValueError):
        return None
    return _game_elapsed_sec(period, clock_to_sec(action.get("clock")))


def reconstruct_game_stints(game_id: str, box_game: dict, pbp_game: dict) -> List[Stint]:
    """Full-game 5-man stints for BOTH sides of one game. Empty list if
    starters/actions are missing or malformed (never raises)."""
    actions = pbp_game.get("actions") or []
    if not actions:
        return []

    out: List[Stint] = []
    for side in SIDES:
        team = box_game.get(f"{side}Team") or {}
        team_id = team.get("teamId")
        starters = _starters(team)
        if starters is None:
            continue
        oncourt = set(starters)

        stint_start_elapsed = 0.0
        first_score = _score_of(actions[0]) or (0.0, 0.0)
        stint_start_score = _side_score(first_score, side)

        i, n = 0, len(actions)
        while i < n:
            a = actions[i]
            if not isinstance(a, dict) or a.get("actionType") != "substitution" \
               or a.get("teamId") != team_id:
                i += 1
                continue

            ts_period, ts_clock = a.get("period"), a.get("clock")
            batch, j = [], i
            while j < n:
                b = actions[j]
                if not isinstance(b, dict) or b.get("actionType") != "substitution" \
                   or b.get("teamId") != team_id or b.get("period") != ts_period \
                   or b.get("clock") != ts_clock:
                    break
                batch.append(b)
                j += 1

            close_elapsed = _elapsed(a)
            close_score = _score_of(a)
            if close_elapsed is not None and close_score is not None and len(oncourt) == 5:
                pf, pa = _side_score(close_score, side)
                sf, sa = stint_start_score
                out.append(Stint(
                    game_id=str(game_id), team_id=team_id, side=side,
                    lineup=tuple(sorted(oncourt)),
                    elapsed_start_sec=stint_start_elapsed, elapsed_end_sec=close_elapsed,
                    pts_for=pf - sf, pts_against=pa - sa,
                ))

            for b in batch:
                pid = str(b.get("personId"))
                if b.get("subType") == "out":
                    oncourt.discard(pid)
                elif b.get("subType") == "in":
                    oncourt.add(pid)

            if close_elapsed is not None:
                stint_start_elapsed = close_elapsed
            if close_score is not None:
                stint_start_score = _side_score(close_score, side)
            i = j

        last = actions[-1]
        final_elapsed = _elapsed(last)
        final_score = _score_of(last)
        if final_elapsed is not None and final_score is not None and len(oncourt) == 5 \
           and final_elapsed > stint_start_elapsed:
            pf, pa = _side_score(final_score, side)
            sf, sa = stint_start_score
            out.append(Stint(
                game_id=str(game_id), team_id=team_id, side=side,
                lineup=tuple(sorted(oncourt)),
                elapsed_start_sec=stint_start_elapsed, elapsed_end_sec=final_elapsed,
                pts_for=pf - sf, pts_against=pa - sa,
            ))
    return out


def build_all_stints() -> List[Stint]:
    """Walk every backfilled game and reconstruct both sides' stints."""
    all_stints: List[Stint] = []
    for gid, pair in iter_backfilled_games():
        all_stints.extend(reconstruct_game_stints(gid, pair["boxscore"], pair["playbyplay"]))
    return all_stints


__all__ = ["Stint", "reconstruct_game_stints", "build_all_stints", "SIDES"]
