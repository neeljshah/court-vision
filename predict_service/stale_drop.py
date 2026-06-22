"""predict_service.stale_drop -- finished/past-tipoff record suppression.

STALE-NEVER-GREEN (BE-R3-2): a finished (game_state='post') game, or one whose
tipoff is in the past beyond a small grace window, must NOT be surfaced as a
current prediction. The producer calls drop_stale_records() so latest.json shows
ONLY the current/upcoming slate; on a UTC day rollover yesterday's games are
'post' (or past grace) and fall off on the next produce cycle (the scheduler
overwrites latest.json atomically each cadence -- no separate purge daemon).

Grace = typical game duration + a margin so a still-LIVE game is never dropped
while it is genuinely in progress; once a game is clearly over (post, or tipoff
older than the grace) it falls off. When every game on a slate has aged out the
producer degrades to status='unavailable' (honest empty, never stale-green).

Pure module: no network, no IO, no global state. *now* is injectable (UTC) for
deterministic day-rollover tests.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets;
no $ field; reuse contracts constants verbatim.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from predict_service.contracts import (
    GAME_STATE_LIVE,
    GAME_STATE_POST,
    GAME_STATE_PRE,
    _TYPICAL_GAME_DURATION_SECONDS,
    PredictionRecord,
)

# Past-tipoff grace: only ever consulted for games that are NOT explicitly live
# (a 'live' game keeps its record + prior no matter how long it has run -- see
# is_stale_record). It catches a game that should be over but never got an
# explicit 'post' signal. Kept generous (typical duration + a full extra duration)
# so an abandoned game is well beyond any real game length before it ages out --
# a long live game (extra innings, OT, a 3.5h MLB game) is never mistaken for
# stale on tipoff alone; the live game_state guard already protects it regardless.
PAST_TIPOFF_GRACE_SECONDS = 2 * _TYPICAL_GAME_DURATION_SECONDS


def _parse_tipoff(tipoff: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 tipoff (with or without trailing 'Z') to aware UTC."""
    if not tipoff:
        return None
    try:
        dt = datetime.fromisoformat(str(tipoff).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def tipoff_past_grace(tipoff: Optional[str], now: datetime) -> bool:
    """True when *tipoff* is older than the past-tipoff grace window vs *now* (UTC).

    A missing / unparseable tipoff is NOT stale on this signal alone (returns
    False) -- a no-tipoff game is kept and judged by game_state only.
    """
    tip_dt = _parse_tipoff(tipoff)
    if tip_dt is None:
        return False
    return (now - tip_dt).total_seconds() > PAST_TIPOFF_GRACE_SECONDS


def is_stale_record(rec: PredictionRecord, now: datetime) -> bool:
    """True when a record is finished/aged-out and must not be surfaced.

    A FINISHED game (producer-derived game_state == 'post'/final) is ALWAYS stale
    and is purged -- the regression fix that stops finished games showing as
    predictions holds.

    A LIVE game (game_state == 'live') is NEVER stale: it is actively in progress,
    not finished, so its record (and thus its leak-free pregame prior) MUST remain
    available for the in-game pregame_carry path to reprice it. A live game is kept
    no matter how long it has run -- the past-tipoff heuristic is NOT consulted for
    it (a long live game / extra innings is not "stale").

    For a non-live, non-post game (e.g. a 'pre' record that never got a live or
    post signal), tipoff past the (generous) grace window means it should be over
    but no explicit post arrived -> stale.  'pre' games before grace are kept.
    """
    state = getattr(rec, "game_state", GAME_STATE_PRE)
    if state == GAME_STATE_POST:
        return True
    if state == GAME_STATE_LIVE:
        # Actively live -> keep (prior must survive for in-game reprice/carry).
        return False
    return tipoff_past_grace(getattr(rec, "tipoff", None), now)


def drop_stale_records(
    records: List[PredictionRecord],
    all_markets: list,
    all_edges: list,
    now: Optional[datetime] = None,
) -> Tuple[List[PredictionRecord], list, list]:
    """Drop finished/past-tipoff records and their markets+edges (stale-never-green).

    Returns filtered (records, markets, edges). game_ids of surviving records gate
    which markets/edges remain so a dropped game leaves nothing behind on the
    surface. *now* is injectable (UTC) for deterministic day-rollover tests;
    defaults to the current wall clock.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    kept = [r for r in records if not is_stale_record(r, now)]
    keep_ids = {r.game_id for r in kept}
    markets = [m for m in all_markets if getattr(m, "game_id", None) in keep_ids]
    edges = [e for e in all_edges if getattr(e, "game_id", None) in keep_ids]
    return kept, markets, edges


__all__ = [
    "PAST_TIPOFF_GRACE_SECONDS",
    "tipoff_past_grace",
    "is_stale_record",
    "drop_stale_records",
]
