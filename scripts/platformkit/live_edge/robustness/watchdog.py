"""scripts.platformkit.live_edge.robustness.watchdog -- check-and-restart
INTENT for A3 scraper robustness (LIVE-EDGE program item A3).

NOT a running loop. check_and_restart() takes SLA rows (freshness_sla.py) and
returns restart-intent dicts for every DOWN source, naming which capture proc
owns it (bus_ingest.py's INGESTERS map / news/fetch.capture_once -- there is
no supervisor ProcSpec for any of these today, confirmed by grepping
supervisor/stack_specs for bus_ingest/news.fetch: zero hits). This module
never kills or restarts anything -- actually bouncing a shared daemon is the
fleet-restart human/Fable path (see .claude/skills/fleet-restart). A future
daemon wrapping this in a loop is what would act on the intent.

Also provides the polite-cadence helpers a future daemon needs: jittered
delay, exponential backoff schedule, and 429/ban detection reusing the SAME
blocked-code tuple odds_provider/transport.py already defines (import, not a
second copy) so a ban is never mistaken for "just slow" and retried into a
storm.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_freshness_sla.py -q
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from scripts.platformkit.live_edge.robustness.freshness_sla import DOWN

# reused, not reinvented: the same set of HTTP codes odds_provider/transport.py
# already treats as "bot-walled", so 429/ban detection here matches production.
from scripts.platformkit.odds_provider.transport import _BLOCKED_HTTP_CODES as BLOCKED_HTTP_CODES

# source prefix -> the capture proc that owns it (bus_ingest.INGESTERS keys +
# the standalone news module). "prefix" because odds:/injury: fan out per sport.
_CAPTURE_PROC_BY_PREFIX: Dict[str, str] = {
    "odds:": "scripts.platformkit.live_edge.bus_ingest.ingest_odds",
    "injury:": "scripts.platformkit.live_edge.bus_ingest.ingest_injury",
    "gumbo:": "scripts.platformkit.live_edge.bus_ingest.ingest_gumbo",
    "fotmob:": "scripts.platformkit.live_edge.bus_ingest.ingest_fotmob",
    "news:": "scripts.platformkit.live_edge.news.fetch.capture_once",
}


def capture_proc_for(source: str) -> str:
    """The capture proc that owns *source*, or 'unknown' if no prefix matches
    (an honest gap, never guessed)."""
    for prefix, proc in _CAPTURE_PROC_BY_PREFIX.items():
        if source.startswith(prefix):
            return proc
    return "unknown"


def check_and_restart(sla_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """For every DOWN row, emit a restart-intent dict. Does NOT restart
    anything -- shared-daemon restart is the fleet-restart human path. Never
    raises; a malformed row is skipped, not fatal."""
    intents: List[Dict[str, Any]] = []
    for row in sla_rows or []:
        try:
            if row.get("status") != DOWN:
                continue
            source = row.get("source", "")
            intents.append({
                "source": source,
                "capture_proc": capture_proc_for(source),
                "action": "restart_intent",
                "staleness_sec": row.get("staleness_sec"),
                "sla_sec": row.get("sla_sec"),
                "note": "intent only -- actual restart is the fleet-restart human/Fable path",
            })
        except Exception:  # noqa: BLE001 -- one bad row must not sink the batch
            continue
    return intents


def jittered_delay(base_sec: float, *, jitter_frac: float = 0.2,
                    rng: Optional[random.Random] = None) -> float:
    """base_sec +/- jitter_frac*base_sec, so N future daemons polling the same
    source don't all wake on the exact same tick (thundering-herd avoidance)."""
    r = rng or random
    spread = base_sec * jitter_frac
    return max(0.0, base_sec + r.uniform(-spread, spread))


def backoff_schedule(attempt: int, *, base_sec: float = 5.0, max_sec: float = 900.0) -> float:
    """Exponential backoff wait for retry *attempt* (0-indexed), capped at
    max_sec so a persistent ban still yields a bounded, polite retry cadence
    instead of retrying forever at max frequency."""
    return min(max_sec, base_sec * (2 ** max(0, attempt)))


def is_ban_shaped(http_status: Optional[int]) -> bool:
    """True if *http_status* looks like a block/ban (429 or the other codes
    transport.py already treats as bot-walled) -- the signal that must trigger
    backoff, never a retry-storm."""
    return http_status in BLOCKED_HTTP_CODES


def conditional_get_headers(*, etag: Optional[str] = None,
                             last_modified: Optional[str] = None) -> Dict[str, str]:
    """If-None-Match / If-Modified-Since headers for a polite conditional GET
    (a future daemon avoids paying full-body cost on an unchanged source)."""
    headers: Dict[str, str] = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


__all__ = [
    "capture_proc_for", "check_and_restart", "jittered_delay",
    "backoff_schedule", "is_ban_shaped", "conditional_get_headers",
    "BLOCKED_HTTP_CODES",
]
