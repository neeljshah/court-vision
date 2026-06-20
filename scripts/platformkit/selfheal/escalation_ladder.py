"""scripts.platformkit.selfheal.escalation_ladder -- streak accumulator + policy.

PURE ADVISORY logic.  This module:
  * reads autonomy_status.json services[] (read-only) to discover stale daemons
  * maintains a per-daemon consecutive-stale streak counter
  * applies a 3-level escalation policy based on streak depth
  * returns advice strings ONLY -- never an action/command field, never calls restart

ESCALATION LEVELS
-----------------
  OK                  -- streak == 0  (daemon is fresh / has recovered)
  WATCH               -- 1 <= streak < RESTART_THRESHOLD  (first stale tick; monitor)
  RESTART_RECOMMENDED -- streak >= RESTART_THRESHOLD       (3+ consecutive stale)

STREAK STATE (StreakStore)
--------------------------
  {daemon_name: {"streak": int>=0, "level": str, "first_stale_at": str|null}}

Input row shape (from autonomy_status.json services[]):
  {"name": str, "severity": "ok"|"degraded"|"down", ...}
  A row is considered STALE when severity != "ok".

INVARIANTS
----------
  * Pure functions -- no I/O, no side effects, no network, no subprocess.
  * No $ key in any returned dict.
  * No "action" or "command" key in escalation entries -- only "advice" (str).
  * streak never goes negative.
  * Recovery (fresh tick) resets streak to 0 and level to OK.
  * <=300 LOC; ASCII only; stdlib only; never raises.

Per-file test:
    python -m pytest tests/platformkit/selfheal/test_escalation_ladder.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LEVEL_OK = "OK"
LEVEL_WATCH = "WATCH"
LEVEL_RESTART_RECOMMENDED = "RESTART_RECOMMENDED"

RESTART_THRESHOLD = 3  # consecutive stale ticks -> RESTART_RECOMMENDED

_ADVICE_OK = "daemon is healthy; no action needed"
_ADVICE_WATCH = (
    "daemon reported stale/down for {streak} consecutive tick(s); "
    "monitor closely -- may self-recover"
)
_ADVICE_RESTART = (
    "daemon {name} has been stale/down for {streak} consecutive tick(s); "
    "a supervisor restart is recommended (human or orchestrator decision)"
)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# StreakStore: {daemon_name -> {"streak": int, "level": str, "first_stale_at": str|null}}
StreakStore = Dict[str, Dict[str, Any]]

# EscalationEntry (one per daemon in the feed):
# {"name": str, "streak": int, "level": str, "advice": str, "first_stale_at": str|null}
EscalationEntry = Dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_stale(row: Dict[str, Any]) -> bool:
    """A service row is considered stale when severity != 'ok' (degraded or down)."""
    sev = row.get("severity", "ok")
    return str(sev).lower() != "ok"


def _compute_level(streak: int) -> str:
    if streak <= 0:
        return LEVEL_OK
    if streak < RESTART_THRESHOLD:
        return LEVEL_WATCH
    return LEVEL_RESTART_RECOMMENDED


def _build_advice(name: str, streak: int, level: str) -> str:
    if level == LEVEL_OK:
        return _ADVICE_OK
    if level == LEVEL_WATCH:
        return _ADVICE_WATCH.format(streak=streak)
    # RESTART_RECOMMENDED
    return _ADVICE_RESTART.format(name=name, streak=streak)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def tick(
    services: Sequence[Dict[str, Any]],
    streaks: StreakStore,
    *,
    now_iso: Optional[str] = None,
) -> StreakStore:
    """Apply one tick of new service rows to the streak store.

    Parameters
    ----------
    services:  List of service rows from autonomy_status.json (read-only input).
    streaks:   Current streak store (will NOT be mutated -- a new dict is returned).
    now_iso:   Current UTC ISO timestamp (defaults to wall clock).

    Returns a NEW StreakStore with updated streaks.  Never raises.
    """
    now = now_iso or _utc_iso_now()
    new_store: StreakStore = {}

    for row in services:
        try:
            name = str(row.get("name", ""))
            if not name:
                continue
            prev = streaks.get(name, {})
            prev_streak = int(prev.get("streak", 0))

            if _is_stale(row):
                new_streak = prev_streak + 1
                first_stale = prev.get("first_stale_at") or now
            else:
                new_streak = 0
                first_stale = None

            level = _compute_level(new_streak)
            new_store[name] = {
                "streak": new_streak,
                "level": level,
                "first_stale_at": first_stale,
            }
        except Exception:  # noqa: BLE001 -- one bad row must not abort the tick
            continue

    return new_store


def build_feed(
    streaks: StreakStore,
    *,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the escalation_feed.json document from *streaks*.

    Shape:
    {
      "generated_at": "<ISO-UTC>",
      "honest_note": "...",
      "entries": [
        {"name": str, "streak": int, "level": str, "advice": str,
         "first_stale_at": str|null}
      ]
    }

    INVARIANTS: no "action"/"command" key; no "$" key; no $ P&L.
    Never raises.
    """
    entries: List[EscalationEntry] = []
    for name, state in sorted(streaks.items()):
        try:
            streak = int(state.get("streak", 0))
            level = _compute_level(streak)
            advice = _build_advice(name, streak, level)
            entries.append({
                "name": name,
                "streak": streak,
                "level": level,
                "advice": advice,
                "first_stale_at": state.get("first_stale_at"),
            })
        except Exception:  # noqa: BLE001
            continue

    return {
        "generated_at": generated_at or _utc_iso_now(),
        "honest_note": (
            "ADVISORY ONLY -- this feed recommends, never commands. "
            "No action/command field is emitted. Calibration not edge; no $ field."
        ),
        "entries": entries,
    }


__all__ = [
    "LEVEL_OK",
    "LEVEL_WATCH",
    "LEVEL_RESTART_RECOMMENDED",
    "RESTART_THRESHOLD",
    "tick",
    "build_feed",
]
