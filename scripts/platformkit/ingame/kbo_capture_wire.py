"""scripts.platformkit.ingame.kbo_capture_wire -- KBO Kalshi-ticker -> relay state-row
wiring (kbo-alias-wire-soak lane, capture-only).

Closes the seam wave-55 deferred: inplay_capture_loop.py keys KBO games by their KALSHI
ticker; kbo_relay_state_provider needs the NAVER gameId. This module builds the LAZY
per-tick (kalshi_ticker) -> state-row closure the capture loop's deep_state_fn slot
expects, chaining:　ticker -> kbo_game_matcher.parse+teams_for_kalshi_blob -> EN teams ->
kbo_game_matcher.naver_game_id_for(today, ..) -> kbo_relay_state_provider.
relay_state_for_game -> as-of state row (also appended to disk as a side effect, mirroring
make_kbo_state_fn's own capture=True default).

FAIL-OPEN AT EVERY HOP (binding): a non-KBO/unparseable ticker, an unmapped team code, a
slate miss, or a relay-fetch failure ALL degrade to {} (never None -- the capture loop's
merge treats {} identically to no enrichment: `if isinstance(deep, dict) and deep`), so a
zero-content dict is indistinguishable from "nothing to add" and the tick is captured
exactly as it always was. NOTHING here can raise past this module's own boundary.

SCOPE (unchanged from kbo_relay_state_provider): NO model probability, NO dispatch
branch, NO bet decision. This is descriptive state only, same class as the MLB deep
enricher (ingame_id_resolver_mlb.make_tick_deep_fn) this module mirrors.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_kbo_capture_wire.py -q
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from scripts.platformkit.ingame import kbo_game_matcher as _matcher
from scripts.platformkit.ingame import kbo_relay_state_provider as _relay_state

logger = logging.getLogger(__name__)


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def kbo_deep_state_for_ticker(ticker: str, *,
                              date: Optional[str] = None,
                              slate_dir: Optional[Path] = None,
                              http_get: Optional[Callable] = None,
                              relay_http_get: Optional[Callable] = None
                              ) -> Dict[str, Any]:
    """Resolve one Kalshi KBO ticker -> its as-of relay state row (a plain dict,
    matching kbo_relay_state_provider's row shape), or {} on ANY miss/failure at any
    hop. *date* defaults to today (UTC) -- injectable so the tested path is
    deterministic. Never raises."""
    try:
        parsed = _matcher.parse_kalshi_kbo_ticker(ticker)
        if parsed is None:
            return {}
        pair = _matcher.teams_for_kalshi_blob(parsed["blob"])
        if pair is None:
            return {}
        en1, en2 = pair
        the_date = date if date is not None else _today_utc()
        # Order is unspecified from the blob split (kbo_team_alias's alphabets do not
        # encode home/away) -- try both (home,away) assignments against the slate; at
        # most one can be an exact match (naver_game_id_for's home/away fields are
        # never swapped/fuzzy), so trying both here is safe, not a guess.
        gid = _matcher.naver_game_id_for(the_date, en1, en2, slate_dir=slate_dir,
                                         http_get=http_get)
        if gid is None:
            gid = _matcher.naver_game_id_for(the_date, en2, en1, slate_dir=slate_dir,
                                             http_get=http_get)
        if gid is None:
            return {}
        row = _relay_state.relay_state_for_game(gid, http_get=relay_http_get)
        return row if isinstance(row, dict) else {}
    except Exception as exc:  # noqa: BLE001 -- capture-only enrichment must never raise
        logger.debug("kbo_capture_wire kbo_deep_state_for_ticker(%s) failed: %s", ticker, exc)
        return {}


def make_kbo_deep_fn(*, date: Optional[str] = None,
                     slate_dir: Optional[Path] = None,
                     http_get: Optional[Callable] = None,
                     relay_http_get: Optional[Callable] = None
                     ) -> Callable[[str], Dict[str, Any]]:
    """Build the (kalshi_ticker) -> dict closure for inplay_capture_loop's
    deep_state_fn slot, mirroring ingame_id_resolver_mlb.make_tick_deep_fn's shape
    (a bare callable, no lazy candidate cache needed here since every lookup is
    already cheap/cached via the slate file). Never raises -- degrades to {}."""
    def _deep(ticker: str) -> Dict[str, Any]:
        return kbo_deep_state_for_ticker(
            ticker, date=date, slate_dir=slate_dir,
            http_get=http_get, relay_http_get=relay_http_get)
    return _deep


__all__ = ["kbo_deep_state_for_ticker", "make_kbo_deep_fn"]
