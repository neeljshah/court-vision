"""scripts.platformkit.ingame.inplay_daytrader_gates -- late suppression-gate helpers for
inplay_daytrader.on_tick, split out under the <=300 LOC rail (pure move, zero behavior
change). Holds: the PAPER-DECISION venue allowlist (Kalshi-only for now) and the
event-reactive / venue / median-CLV-breaker suppression chain applied AFTER the edge +
segment-adverse gates already ran in inplay_daytrader.on_tick. Suppress-only: every check
here can only turn a would-be "bet" into "no_bet"; none can manufacture a bet. See
inplay_daytrader.py's module docstring for the full day-trader contract.

Per-file test (exercised via the parent's suite; this module has no separate test file):
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_inplay_daytrader.py -q
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.platformkit.ingame import inplay_breaker as _breaker
from scripts.platformkit.ingame import latency_scoreboard as _latsb

MARKET = "win_home"  # one anchor moneyline market per game (HOME side)

# PAPER-DECISION venue allowlist: Kalshi-only for now. Gates ENTER/RE-ENTER ONLY --
# capture_pair_once's grade series stays venue-agnostic (unaffected). Override via env
# CV_PAPER_VENUES (comma-separated) or on_tick(paper_venues=..., tests only). A tick
# with no "venue" field defaults to "kalshi" (today's only wired price source; see
# inplay_capture_loop._default_inplay_fetch), not to a silent block.
DEFAULT_PAPER_VENUES = ("kalshi",)


def _paper_venue_allowlist() -> frozenset:
    """DEFAULT_PAPER_VENUES, overridable via CV_PAPER_VENUES (comma-separated). Never raises."""
    raw = os.environ.get("CV_PAPER_VENUES", "")
    if not raw.strip():
        return frozenset(v.lower() for v in DEFAULT_PAPER_VENUES)
    return frozenset(v.strip().lower() for v in raw.split(",") if v.strip())


def _venue_allowed(tick: Dict[str, Any], paper_venues: Optional[Any]) -> bool:
    """True iff this tick's venue (default 'kalshi' -- see DEFAULT_PAPER_VENUES docstring)
    is in the effective allowlist (*paper_venues* override, else CV_PAPER_VENUES env,
    else DEFAULT_PAPER_VENUES)."""
    venue = str(tick.get("venue", "kalshi")).strip().lower()
    allowed = (frozenset(str(v).strip().lower() for v in paper_venues)
              if paper_venues is not None else _paper_venue_allowlist())
    return venue in allowed


def apply_late_gates(ev: Dict[str, Any], tick: Dict[str, Any], sport: str,
                      nowdt: datetime, paper_venues: Optional[Any],
                      ledger_path: Optional[Path], decision: Dict[str, Any]) -> bool:
    """Apply the event-reactive / venue-allowlist / median-CLV-breaker suppression chain
    (in order) to *decision* (mutated in place). Returns True iff on_tick should return
    *decision* immediately (a gate suppressed the would-be bet); False to fall through to
    enter/hold/exit. Runs only when ev["action"]=="bet" -- the edge + segment-adverse gates
    have already passed by the time on_tick calls this. Suppress-only: can only turn "bet"
    into "no_bet", never the reverse; the pair capture in on_tick already ran regardless.

    2b2. EVENT-REACTIVE ELIGIBILITY: an entry the caller declares event-reactive
    (tick["event_reactive"] truthy) is allowed only where the MEASURED venue latency
    supports it (latency_scoreboard: lag_p90<=5s AND src_ts coverage>=95% -- MLB yes,
    broadcast-tier NBA/soccer/tennis no). FAIL-CLOSED: an unmeasured/slow feed never
    supports it.

    2c. PAPER VENUE ALLOWLIST (binding: Kalshi-only paper decisions for now -- see
    DEFAULT_PAPER_VENUES).

    2d. MEDIAN-CLV BREAKER (pre-registered 2026-07-15): a negative rolling median CLV on
    graded paper_ingame rows CAPS placements per day (execution.circuit_breaker).
    """
    if (ev["action"] == "bet" and bool(tick.get("event_reactive"))
            and not _latsb.event_reactive_supported(sport)):
        decision["reason"] = "event_reactive_not_supported"
        return True

    if ev["action"] == "bet" and not _venue_allowed(tick, paper_venues):
        decision["reason"] = "venue_not_allowed:%s" % str(tick.get("venue", "kalshi")).strip().lower()
        return True

    if ev["action"] == "bet":
        br = _breaker.allow(MARKET, nowdt, ledger_path)
        decision["breaker"] = {k: br.get(k) for k in ("state", "placed_today", "reason")}
        if not br.get("allowed", True):
            decision["reason"] = "breaker_capped"
            return True

    return False


def grade(sport: Optional[str] = None, *,
          grade_dir: Optional[Path] = None,
          min_games: int = 5) -> Dict[str, Any]:
    """Grade the captured day-trader series via the EXISTING clustered aggregate grader.

    Pure pass-through to inplay_aggregate_grade.aggregate_grade -- the leak-free,
    two-arm, game-clustered CLV-vs-true-close pool (BEAT needs n>=5 games + >=40 ticks +
    BOTH arms). A single game/tick -> INSUFFICIENT_DATA. UNITS / probability only; never a
    $ figure; edge_claimed=False. Imported lazily so this module's import is network-free.
    """
    from scripts.platformkit.ingame import inplay_aggregate_grade as _agg
    return _agg.aggregate_grade(grade_dir, sport=sport, min_games=min_games)
