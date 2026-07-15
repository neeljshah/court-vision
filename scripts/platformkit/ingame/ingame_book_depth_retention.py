"""scripts.platformkit.ingame.ingame_book_depth_retention -- date-aware sticky eviction.

Split out of ingame_book_depth_poller.py (already at the 300 LOC cap) so the FIX
for the live-day coverage gap has its own small, testable home. See
docs/research/execution-quality/book_depth_livegap_diagnosis.md for the full
diagnosis (measured ~44h gap, disk evidence).

THE GAP: poll_kalshi_depth's sticky active_by_sport list (added 2026-07-11 to
survive ordinary discovery-page churn) evicted the OLDEST-APPENDED ticker once a
sport's active count exceeded max_active_per_sport, with no regard for how close
that ticker's game actually is. Kalshi opens game markets DAYS ahead of first
pitch/tip, so "oldest appended" is systematically the ticker CLOSEST to going
live -- on a busy MLB day (4 series x ~15 games) this evicted a game's own
tickers hours to days before it ever went live, and discovery (itself
top-N-per-series, not exhaustive) never brought them back.

THE FIX: evict_over_cap() prefers to evict FUTURE-dated tickers
(kalshi_series_spec.is_future_game -- more than 1 day out) before ever touching
a today/tomorrow ticker, oldest-appended-first within each bucket. A ticker
whose game is imminent or already live is sacrificed only as a last resort, if
the "not future" bucket ALONE still exceeds the cap.

INVARIANTS: build only under scripts/platformkit/ingame/; <=300 LOC; ASCII only;
stdlib + repo-internal (kalshi_series_spec) only; pure (no I/O). Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_ingame_book_depth_retention.py -q
"""
from __future__ import annotations

from datetime import datetime
from typing import List

from scripts.platformkit.odds_provider.kalshi_series_spec import is_future_game


def evict_over_cap(active: List[str], max_active: int, now_dt: datetime) -> None:
    """Trim *active* (a per-sport sticky ticker list, in insertion/discovery
    order) down to *max_active*, IN PLACE.

    Evicts FUTURE-dated tickers first (oldest-appended among them); only
    reaches into the today/live bucket if the cap is still exceeded after every
    future ticker is gone -- i.e. an unprecedented same-day slate size, not the
    routine days-ahead-discovery churn this fix targets. Never raises: an
    unparseable ticker date makes is_future_game return False, so it lands in
    the "not future" (protected) bucket -- never evicted early on a parse miss.
    No-op if *active* is already at or under the cap.
    """
    n_over = len(active) - max_active
    if n_over <= 0:
        return
    future = [t for t in active if is_future_game(t, now_dt)]
    drop = set(future[:n_over])
    if len(drop) < n_over:
        not_future = [t for t in active if t not in future]
        drop.update(not_future[: n_over - len(drop)])
    active[:] = [t for t in active if t not in drop]


__all__ = ["evict_over_cap"]
