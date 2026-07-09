"""scripts.platformkit.ingame.ingame_book_depth -- VENUE DEPTH-OF-BOOK snapshot builder (LANE 3).

STANDALONE, ADDITIVE module: builds one depth snapshot per in-play market on Kalshi
and Polymarket. Does NOT touch inplay_capture_loop.py or any shared runner -- this
is a measurement-only sidecar with its own poller entrypoint and its own JSONL
artifact tree (data/cache/book_depth/<venue>/<date>.jsonl).

VENUES (both KEYLESS -- verified live 2026-07-04; no stealth needed):

  Kalshi (see ingame_book_depth_kalshi.py for the orderbook/trades reader):
    GET {KALSHI_BASE}/markets/{ticker}/orderbook -> orderbook_fp {yes_dollars,
      no_dollars} price/size ladders (ASC by price; best = LAST entry each side).
    GET {KALSHI_BASE}/markets/trades?ticker=&limit= -> ms-precision tape.

  Polymarket: resolve clob_token_id ONCE per market (gamma events slug lookup),
    then GET https://clob.polymarket.com/book?token_id=
      -> {"bids":[{"price","size"}...] ASC, "asks":[{"price","size"}...] DESC --
          in BOTH arrays the LAST entry is the best (highest bid / lowest ask),
          verified live 2026-07-04}. /midpoint -> {"mid"}, /spread -> {"spread"}
          are cross-check reads only (not required for the canonical row).
    TRAP (binding): gamma's `outcomePrices` on /events or /markets is a LAGGED
    CACHE, updated on its own slow schedule -- NEVER read here as a live price.
    Only the CLOB /book (+/midpoint,/spread) endpoints are live.

CANONICAL SNAPSHOT ROW:
  {ts, venue, ticker|slug (the market ref), best_bid, best_ask, spread_bp,
   book_thinness (sum of size across the top-3 levels per side), n_levels,
   last_trade_ts, trades_last_5m, stale_quote_flag}

STALE_QUOTE_FLAG (derived, documented threshold): True iff BOTH (a) best_bid AND
best_ask are byte-identical to the immediately PRIOR snapshot for this exact
market (top-of-book literally unchanged) AND (b) spread_bp > STALE_SPREAD_BP_MIN
(50 bp = 0.5c on a $1 contract). Rationale: a market that is both quote-frozen AND
wide is a stronger staleness signal than either alone -- a narrow-spread liquid
market can legitimately sit unchanged for a few seconds between trades (that is
a healthy resting book, not staleness); a wide AND frozen quote is the classic
"nobody is making this market right now" shape. The threshold is a documented
judgment call, not tuned against any label.

WIRE SPEC (future integration lane -- NOT wired here, additive-only tick fields):
  1. inplay_capture_loop's _build_tick() currently sets "is_fresh": True
     unconditionally (see its docstring: "in-play ticks are fresh by
     construction; stale feeds emit []"). A future wire would instead compute
     is_fresh = not stale_quote_flag for the tick's matched (venue, ticker)
     depth row (joined by game_id -> ticker via the same team-name bridge
     _scan_live_by_legs already does), REPLACING the current always-True
     assumption with a REAL top-of-book-derived signal instead of inplay_
     capture_loop's coarser "a fetch returned rows at all" proxy.
  2. quote_freshness.py's existing heuristic (is a tick's market_prob != the
     PREVIOUS tick's market_prob for the same game) is SYNTACTIC on the derived
     probability only; stale_quote_flag is a STRICTLY STRONGER signal because it
     also requires a WIDE spread, so it catches genuinely stale-AND-illiquid
     quotes that quote_freshness's raw price-changed check cannot distinguish
     from a healthy-but-momentarily-unchanged tight market. A future wire would
     OR the two: mark_stale = quote_freshness_stale OR stale_quote_flag, so
     either signal alone is sufficient to exclude a tick from the "fresh-only"
     verdict arm in ingame_outcome_verdict_freshness.py.
  3. ingame_tail_gate.py's H1/H2 price bands currently score EVERY captured
     tick in their forward corpus regardless of quote freshness. A future wire
     would add a fresh-only sub-arm (mirroring the raw/fresh split
     ingame_outcome_verdict_freshness.py already does for the outcome verdict)
     by filtering out ticks whose depth row has stale_quote_flag=True before
     computing each band's CI -- this could only ever TIGHTEN or CONFIRM a
     verdict (removing stale-quote noise), never manufacture a new edge.
  Exact additive line for step 1 (illustrative, not applied):
     tick["is_fresh"] = not depth_row.get("stale_quote_flag", False) if depth_row else True

This file owns the two per-venue SNAPSHOT BUILDERS (snapshot_kalshi_market /
snapshot_polymarket_token) + the shared stale_quote_flag. The discover+poll
loop, sidecar writer, bounded serve loop and CLI live in
ingame_book_depth_poller.py (split out to stay under the 300 LOC cap).

INVARIANTS: build only under scripts/platformkit/ingame/; <=300 LOC; ASCII only;
stdlib + repo-internal only (http_cache, transport, kalshi_series_spec -- ALL
READ-ONLY imports, no shared runner edited). No pip installs. Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_ingame_book_depth.py -q
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from scripts.platformkit.ingame import ingame_book_depth_kalshi as _kd
from scripts.platformkit.ingame import ingame_book_depth_poly as _pd
from scripts.platformkit.odds_provider.http_cache import http_get_json
from scripts.platformkit.odds_provider.transport import resilient_get_json

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SIDECAR_DIR = _REPO_ROOT / "data" / "cache" / "book_depth"

KALSHI_BASE = _kd.KALSHI_BASE
POLY_GAMMA_BASE = _pd.GAMMA_BASE
POLY_CLOB_BASE = _pd.CLOB_BASE

# stale_quote_flag threshold: a wide (>50bp) AND top-of-book-frozen quote. See
# the module docstring for the judgment-call rationale.
STALE_SPREAD_BP_MIN = 50.0

HttpGet = Callable[[str], Any]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def stale_quote_flag(prev: Optional[Dict[str, Any]], cur: Dict[str, Any]) -> bool:
    """True iff top-of-book is BYTE-IDENTICAL to *prev* for this market AND the
    current spread_bp exceeds STALE_SPREAD_BP_MIN. None-safe: prev=None -> False
    (no history yet -- cannot claim staleness on the first snapshot)."""
    if not isinstance(prev, dict):
        return False
    if prev.get("best_bid") != cur.get("best_bid") or prev.get("best_ask") != cur.get("best_ask"):
        return False
    sbp = cur.get("spread_bp")
    return sbp is not None and sbp > STALE_SPREAD_BP_MIN


def snapshot_kalshi_market(ticker: str, *, http: HttpGet = resilient_get_json,
                           now_dt: Optional[datetime] = None,
                           prev: Optional[Dict[str, Any]] = None,
                           trade_watermark: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """One full depth snapshot for a Kalshi *ticker* (delegates the fetch/parse to
    ingame_book_depth_kalshi, then applies the shared stale_quote_flag). Passes
    *trade_watermark* straight through to _kd.snapshot_market -- see that
    docstring for the transient "_new_trades"/"_trade_watermark" row keys the
    poller pops off before persisting the depth row."""
    row = _kd.snapshot_market(ticker, http=http, now_dt=now_dt or datetime.now(timezone.utc),
                              now_iso_fn=_now_iso, trade_watermark=trade_watermark)
    if row is None:
        return None
    row["stale_quote_flag"] = stale_quote_flag(prev, row)
    return row


def resolve_polymarket_token(slug: str, *, http: HttpGet = http_get_json,
                             outcome_index: int = 0) -> Optional[str]:
    """Resolve a Polymarket gamma EVENT slug -> ONE clob_token_id. Thin delegate
    to ingame_book_depth_poly.resolve_token (see there for the full contract)."""
    return _pd.resolve_token(slug, http=http, outcome_index=outcome_index)


def snapshot_polymarket_token(token_id: str, *, http: HttpGet = http_get_json,
                              now_dt: Optional[datetime] = None,
                              prev: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """One full depth snapshot for a Polymarket *token_id* (delegates the fetch/
    parse to ingame_book_depth_poly, then applies the shared stale_quote_flag)."""
    row = _pd.fetch_book_row(token_id, http=http, ts=_now_iso())
    if row is None:
        return None
    row["stale_quote_flag"] = stale_quote_flag(prev, row)
    return row


__all__ = [
    "DEFAULT_SIDECAR_DIR", "STALE_SPREAD_BP_MIN", "KALSHI_BASE",
    "POLY_GAMMA_BASE", "POLY_CLOB_BASE",
    "stale_quote_flag", "resolve_polymarket_token",
    "snapshot_kalshi_market", "snapshot_polymarket_token",
]
