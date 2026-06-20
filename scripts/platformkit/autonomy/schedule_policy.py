"""scripts.platformkit.autonomy.schedule_policy -- pure season-aware next-task chooser (A5/D3).

When the self-improve loop has no settled-game work pending, it asks this policy what to
work on next. The policy is PURE and DETERMINISTIC: it takes a durable-state dict and a
clock month, and returns a Decision -- either a measurement task to enqueue, or an honest
IDLE/OFFSEASON status when nothing is due. No I/O, no randomness.

HONESTY RAILS (gate-enforced):
  * The policy NEVER emits a ship / flag-flip / real-money kind. It only ever proposes a
    measurement kind from work_queue.ALLOWED_KINDS, and that verdict still flows through
    the unchanged 5-gate ratchet downstream. Self-scheduling changes *when* work runs,
    never *whether the gate decides*.
  * idle != fabricated work: an empty board returns a Decision with NO task.
  * idle != green-when-dead: an out-of-season sport returns a POSITIVE, distinct
    IDLE_OFFSEASON status (visibly different from a dead feed, which an in-season sport
    with no candidate surfaces as NO_CANDIDATE). The loop must render these distinctly;
    a dead in-season feed is NEVER laundered into "intentionally idle".

stdlib-only; ASCII; <=300 LOC.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# Decision statuses (positive, distinct -- the loop renders each differently).
TASK = "TASK"                  # a measurement task is due; .task is set
NO_CANDIDATE = "NO_CANDIDATE"  # in-season but nothing to do right now (honest idle)
IDLE_OFFSEASON = "IDLE_OFFSEASON"  # sport(s) out of season -> intentionally idle
IDLE_ALL = "IDLE_ALL"          # nothing due across ALL sports (honest global idle)

# Measurement-only kinds this policy may propose. Kept independent of work_queue's
# constant on purpose so a test can assert the two agree (no drift), and so importing
# this pure module never drags in queue I/O.
MEASUREMENT_KINDS = ("recalibrate", "regate_ingame", "refresh_corpora", "backfill_settled")

# Kinds that must NEVER be proposed (the honesty rail). Used only as a self-check.
FORBIDDEN_KINDS = frozenset(
    {"ship", "promote", "flag_on", "enable", "real_money", "bet", "place_bet", "stake"})

# Approximate in-season MONTH windows (1=Jan..12=Dec) per sport. Inclusive sets.
# Deterministic + injectable: pass season_windows= to override for tests / tuning.
# These are coarse calibration-cadence windows, NOT betting calendars.
DEFAULT_SEASON_WINDOWS: Dict[str, Tuple[int, ...]] = {
    "nba": (10, 11, 12, 1, 2, 3, 4, 5, 6),      # Oct-Jun
    "mlb": (3, 4, 5, 6, 7, 8, 9, 10),           # Mar-Oct
    "soccer": (8, 9, 10, 11, 12, 1, 2, 3, 4, 5),  # Aug-May
    "tennis": (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11),  # Jan-Nov
}


@dataclass(frozen=True)
class Task:
    """A proposed measurement task (mirrors work_queue.Task's enqueue inputs)."""
    kind: str
    sport: str
    args: Dict[str, Any]


@dataclass(frozen=True)
class Decision:
    """Result of policy.decide(): a status + optional task + per-sport reasons.

    status  : TASK | NO_CANDIDATE | IDLE_OFFSEASON | IDLE_ALL
    task    : the measurement task to enqueue (only when status == TASK)
    sports  : per-sport classification {sport: 'IN_SEASON'|'OFFSEASON'} for the readout
    reason  : short human-readable why-string (never a $ claim)
    """
    status: str
    task: Optional[Task]
    sports: Dict[str, str]
    reason: str


def is_in_season(sport: str, month: int,
                 season_windows: Optional[Dict[str, Tuple[int, ...]]] = None) -> bool:
    """True iff `sport` is in its calibration-cadence season in the given month."""
    windows = season_windows or DEFAULT_SEASON_WINDOWS
    return month in windows.get(sport, ())


def _month_now(now: Optional[_dt.datetime]) -> int:
    return (now or _dt.datetime.utcnow()).month


class SchedulePolicy:
    """Pure deterministic chooser. No I/O; all inputs are passed in.

    durable_state shape (all optional, all read-only here):
      {
        "<sport>": {
            "settled_pending": int,    # settled games awaiting recalibration
            "corpus_age_days": float,  # age of the oldest in-season corpus
            "ingame_pending": int,     # in-game candidates awaiting re-gate
        }, ...
      }
    """

    # Priority ladder for an in-season sport with work. Highest first.
    # (kind, durable-field that must be truthy, args-builder)
    def __init__(self,
                 sports: Optional[List[str]] = None,
                 season_windows: Optional[Dict[str, Tuple[int, ...]]] = None,
                 stale_corpus_days: float = 7.0):
        self.sports = (list(sports) if sports is not None
                       else list(DEFAULT_SEASON_WINDOWS.keys()))
        self.season_windows = season_windows or DEFAULT_SEASON_WINDOWS
        self.stale_corpus_days = float(stale_corpus_days)

    def _classify(self, month: int) -> Dict[str, str]:
        return {
            s: ("IN_SEASON" if is_in_season(s, month, self.season_windows)
                else "OFFSEASON")
            for s in self.sports
        }

    def _task_for_sport(self, sport: str, st: Dict[str, Any]) -> Optional[Task]:
        """Deterministic priority ladder for one in-season sport. None if no work."""
        if int(st.get("settled_pending", 0) or 0) > 0:
            return Task("recalibrate", sport, {"reason": "settled_pending"})
        if int(st.get("ingame_pending", 0) or 0) > 0:
            return Task("regate_ingame", sport, {"reason": "ingame_pending"})
        age = float(st.get("corpus_age_days", 0.0) or 0.0)
        if age >= self.stale_corpus_days:
            return Task("refresh_corpora", sport,
                        {"reason": "stale_corpus", "age_days": age})
        return None

    def decide(self, durable_state: Optional[Dict[str, Any]] = None,
               now: Optional[_dt.datetime] = None) -> Decision:
        """Choose the next measurement task, or an honest idle status.

        Order: among IN-SEASON sports (deterministic by self.sports order), pick the
        first with due work via the priority ladder. If every in-season sport is idle,
        return NO_CANDIDATE (in-season, honestly nothing to do). If NO sport is in
        season, return IDLE_OFFSEASON. If there are no sports at all, IDLE_ALL.
        """
        state = dict(durable_state or {})
        month = _month_now(now)
        classes = self._classify(month)

        if not self.sports:
            return Decision(IDLE_ALL, None, classes, "no sports configured")

        in_season = [s for s in self.sports if classes.get(s) == "IN_SEASON"]

        # Walk in-season sports in deterministic order; first due task wins.
        for sport in in_season:
            task = self._task_for_sport(sport, dict(state.get(sport, {})))
            if task is not None:
                # Defensive honesty self-check (should be impossible by construction).
                if task.kind in FORBIDDEN_KINDS or task.kind not in MEASUREMENT_KINDS:
                    raise AssertionError(
                        "policy produced a non-measurement kind: %r" % task.kind)
                return Decision(TASK, task, classes,
                                "due: %s %s" % (sport, task.kind))

        if not in_season:
            return Decision(IDLE_OFFSEASON, None, classes,
                            "all configured sports out of season")
        # In-season but nothing due. Honest idle -- NOT fabricated work, NOT green.
        return Decision(NO_CANDIDATE, None, classes,
                        "in-season, no settled/in-game/stale work pending")


__all__ = [
    "SchedulePolicy", "Decision", "Task", "is_in_season",
    "TASK", "NO_CANDIDATE", "IDLE_OFFSEASON", "IDLE_ALL",
    "MEASUREMENT_KINDS", "FORBIDDEN_KINDS", "DEFAULT_SEASON_WINDOWS",
]
