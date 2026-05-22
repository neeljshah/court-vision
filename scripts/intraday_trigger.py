"""
intraday_trigger.py — Continuous intraday trigger orchestrator (task 19.5-02).

On game days this runs as a continuous loop, polling the live trigger
models every 60 seconds:

  * foul_trouble_predictor  — star picks up 3 fouls in Q2
  * injury_monitor          — unexpected late scratch
  * garbage_time_detector   — blowout -> second-half prop bets

Every qualified event is tagged with its `source` and routed to
bet_selector.route_intraday_events().  Because the poll interval is 60 s, a
trigger event reaches bet_selector well within the 3-minute target.

Usage:
    python scripts/intraday_trigger.py [--poll-interval 60] [--season 2024-25]

All data providers are injectable so the loop can be driven by replayed
historical data in tests.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import Callable, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s [intraday_trigger] %(message)s")
log = logging.getLogger("intraday_trigger")

# Poll cadence: every 60 seconds while games are live.
POLL_INTERVAL_SECONDS = 60


def _tag(source: str, payload: dict) -> dict:
    """Stamp an event payload with its trigger source."""
    event = dict(payload)
    event["source"] = source
    return event


# ── default data providers (safe no-ops until live feeds are wired) ──────────

def _default_box_score() -> Tuple[list, int]:
    """Live box score for foul-trouble detection: (players, current_period)."""
    return [], 0


def _default_injuries() -> list:
    """Current ESPN injury records for late-scratch detection."""
    try:
        from src.data.injury_monitor import refresh
        return refresh(force=True).get("injuries", [])
    except Exception as exc:  # noqa: BLE001
        log.warning("injury feed unavailable: %s", exc)
        return []


def _default_game_states() -> list:
    """Live game states for blowout detection."""
    return []


def _default_roster() -> list:
    """Player roster (id, team, role) for second-half prop generation."""
    return []


# ── one poll cycle ────────────────────────────────────────────────────────────

def poll_triggers(
    *,
    box_score_fn: Callable[[], Tuple[list, int]],
    injury_fn: Callable[[], list],
    game_state_fn: Callable[[], list],
    roster_fn: Callable[[], list],
    prior_injuries: Optional[dict],
    season: str = "2024-25",
) -> Tuple[List[dict], Optional[dict]]:
    """Run one poll across all three trigger models.

    Returns ``(events, updated_prior_injuries)``.  Each event carries a
    ``source`` tag.  ``prior_injuries`` is None on the first poll (baseline),
    so late-scratch detection begins on the second poll.
    """
    events: List[dict] = []

    # 1. Foul trouble — star with 3 fouls in Q2.
    try:
        from src.prediction.foul_trouble_predictor import monitor_foul_trouble
        players, period = box_score_fn()
        for rec in monitor_foul_trouble(players, period):
            events.append(_tag("foul_trouble", rec))
    except Exception as exc:  # noqa: BLE001
        log.warning("foul-trouble poll failed: %s", exc)

    # 2. Late scratch — player flips to Out who was expected to play.
    updated_prior = prior_injuries
    try:
        from src.data.injury_monitor import detect_late_scratches, _snapshot_statuses
        current = injury_fn()
        if prior_injuries is not None:
            for scratch in detect_late_scratches(prior_injuries, current):
                events.append(_tag("late_scratch", scratch))
        updated_prior = _snapshot_statuses(current)
    except Exception as exc:  # noqa: BLE001
        log.warning("late-scratch poll failed: %s", exc)

    # 3. Garbage time — blowout routes to second-half prop bets.
    try:
        from src.prediction.garbage_time_detector import route_blowout_to_second_half
        roster = roster_fn()
        for game_state in game_state_fn():
            for bet in route_blowout_to_second_half(game_state, roster, season=season):
                events.append(_tag("garbage_time", bet))
    except Exception as exc:  # noqa: BLE001
        log.warning("garbage-time poll failed: %s", exc)

    return events, updated_prior


# ── continuous loop ───────────────────────────────────────────────────────────

def run_intraday_loop(
    *,
    poll_interval: int = POLL_INTERVAL_SECONDS,
    box_score_fn: Optional[Callable] = None,
    injury_fn: Optional[Callable] = None,
    game_state_fn: Optional[Callable] = None,
    roster_fn: Optional[Callable] = None,
    route_fn: Optional[Callable] = None,
    sleep_fn: Optional[Callable] = None,
    max_iterations: Optional[int] = None,
    stop_fn: Optional[Callable[[], bool]] = None,
    date_str: Optional[str] = None,
    season: str = "2024-25",
) -> dict:
    """Run the intraday trigger loop until stopped.

    Args:
        poll_interval:  Seconds between polls (default 60).
        *_fn providers: Injectable data sources / router / sleep for testing.
        max_iterations: Stop after N polls (None = until stop_fn).
        stop_fn:        Optional () -> bool; loop ends when it returns True.

    Returns:
        ``{"iterations": int, "events_routed": int}``.
    """
    box_score_fn  = box_score_fn  or _default_box_score
    injury_fn     = injury_fn     or _default_injuries
    game_state_fn = game_state_fn or _default_game_states
    roster_fn     = roster_fn     or _default_roster
    sleep_fn      = sleep_fn      or time.sleep
    if route_fn is None:
        from src.prediction.bet_selector import route_intraday_events
        route_fn = route_intraday_events

    prior_injuries: Optional[dict] = None
    iterations = 0
    events_routed = 0

    log.info("Intraday trigger loop started (poll every %ds)", poll_interval)
    while True:
        events, prior_injuries = poll_triggers(
            box_score_fn=box_score_fn, injury_fn=injury_fn,
            game_state_fn=game_state_fn, roster_fn=roster_fn,
            prior_injuries=prior_injuries, season=season,
        )
        if events:
            route_fn(events, date_str)
            events_routed += len(events)
            log.info("Routed %d trigger event(s) to bet_selector", len(events))

        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            break
        if stop_fn is not None and stop_fn():
            break
        sleep_fn(poll_interval)

    log.info("Intraday trigger loop finished: %d polls, %d events routed",
             iterations, events_routed)
    return {"iterations": iterations, "events_routed": events_routed}


def main() -> None:
    ap = argparse.ArgumentParser(description="Intraday trigger orchestrator")
    ap.add_argument("--poll-interval", type=int, default=POLL_INTERVAL_SECONDS)
    ap.add_argument("--season", default="2024-25")
    ap.add_argument("--max-iterations", type=int, default=None,
                    help="Stop after N polls (default: run until killed)")
    args = ap.parse_args()
    run_intraday_loop(
        poll_interval=args.poll_interval,
        season=args.season,
        max_iterations=args.max_iterations,
    )


if __name__ == "__main__":
    main()
