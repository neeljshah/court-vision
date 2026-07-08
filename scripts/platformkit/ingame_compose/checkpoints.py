"""checkpoints -- game state at fixed IN-GAME checkpoints, leak-free BY
CONSTRUCTION.

The whole leak defence lives in ONE function (_before): a feature at checkpoint
t is computed from actions with global elapsed time <= t and NOTHING else. Any
event after t (a late basket that flips the score, garbage-time free throws) is
excluded here, so a checkpoint feature literally cannot see the future -- this is
what makes the retracted endQ3 Q4-leak impossible to reproduce (see leak test).

Checkpoints (regulation clock; 12min/period, 48min=2880s game):
  endQ1   -> 720s elapsed  (time-remaining frac 0.75)
  half    -> 1440s         (0.50)
  endQ3   -> 2160s         (0.25)
  q4_6min -> 2520s (6:00 left in Q4)  (0.125)

Per checkpoint we extract, from that game's action stream only:
  score_diff  = home minus away score at t (feed scoreHome/scoreAway; verified
                scoreHome == games.parquet home_team on the corpus).
  event_count = number of actions with elapsed <= t (an elapsed-possessions
                proxy -- raw event tempo, not a possession parse).

Clock helpers (_elapsed_s / _period_length_s / _CLOCK_RE) are reused from
domains.basketball_nba.lineups.pbp_lineups -- one clock parser for the repo.
Games missing a checkpoint (stream never reaches t) return None for it and the
caller skips+counts them; a gap is NEVER imputed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from domains.basketball_nba.lineups.pbp_lineups import (
    _CLOCK_RE,
    _elapsed_s,
    _period_length_s,
)

# (id, elapsed-seconds threshold, time-remaining fraction) -- all regulation.
CHECKPOINTS: List[Tuple[str, float, float]] = [
    ("endQ1", 720.0, 0.75),
    ("half", 1440.0, 0.50),
    ("endQ3", 2160.0, 0.25),
    ("q4_6min", 2520.0, 0.125),
]
_GAME_S = 2880.0


@dataclass(frozen=True)
class CheckpointState:
    score_diff: float      # home - away at t
    event_count: int       # actions with elapsed <= t (possessions proxy)


def _global_elapsed(period: int, clock: str) -> Optional[float]:
    """Seconds elapsed since tip-off, or None if the clock won't parse.

    Prior full periods (720s regulation, 300s OT) plus elapsed within `period`.
    None -> the action is dropped from every checkpoint (conservative: a state we
    cannot time cannot bound a <=t window)."""
    if not isinstance(clock, str) or not _CLOCK_RE.match(clock):
        return None
    prior = sum(_period_length_s(p) for p in range(1, period))
    return prior + _elapsed_s(period, clock)


def _timed_actions(actions: List[Dict[str, Any]]) -> List[Tuple[float, int, Any]]:
    """(elapsed, actionNumber, score_tuple_or_None) for every timeable action,
    ascending by actionNumber. score_tuple is (home, away) ints or None."""
    out: List[Tuple[float, int, Any]] = []
    for a in actions:
        e = _global_elapsed(a.get("period"), a.get("clock"))
        if e is None:
            continue
        sh, sa = a.get("scoreHome"), a.get("scoreAway")
        score = (int(sh), int(sa)) if sh is not None and sa is not None else None
        out.append((e, int(a["actionNumber"]), score))
    out.sort(key=lambda t: t[1])
    return out


def _before(timed: List[Tuple[float, int, Any]], t: float
            ) -> Optional[CheckpointState]:
    """THE leak boundary: state from actions with elapsed <= t only.

    Returns None when the stream never reaches t (max elapsed < t) -> checkpoint
    absent, caller skips+counts. Score at t = last scored action with elapsed<=t
    (0-0 tip-off default); event_count = all actions with elapsed<=t."""
    if not timed or max(e for e, _, _ in timed) < t:
        return None
    kept = [(e, n, s) for e, n, s in timed if e <= t]
    if not kept:
        return None
    scored = [s for _, _, s in kept if s is not None]
    home, away = scored[-1] if scored else (0, 0)
    return CheckpointState(float(home - away), len(kept))


def extract_checkpoints(game_json: Dict[str, Any]
                        ) -> Dict[str, Optional[CheckpointState]]:
    """{checkpoint_id -> CheckpointState or None} for one game's PBP json."""
    timed = _timed_actions(game_json["game"]["actions"])
    return {cid: _before(timed, t) for cid, t, _ in CHECKPOINTS}


def final_home_margin(game_json: Dict[str, Any]) -> Optional[float]:
    """Final home-away margin (last scored action) -- used only to sanity-check
    that the feed's scoreHome truly is games.parquet's home_team."""
    scored = [s for _, _, s in _timed_actions(game_json["game"]["actions"])
              if s is not None]
    if not scored:
        return None
    h, a = scored[-1]
    return float(h - a)
