"""scripts.platformkit.clv.kx_close_fallback -- ticker-keyed CLOSE fallback (Lane 5).

Bridges clv_ledger_enrich's close-lookup to kx_ticker_close's derived Kalshi-
ticker close-proxies. ADDITIVE ONLY: this is consulted strictly AFTER the
existing ESPN-numeric-game_id path (clv_close_lookup.lookup_close_legs) returns
None, so byte-identical existing behavior for every ESPN-keyed row is
unaffected -- see clv_ledger_enrich._compute_clv_fields for the call order.

CONVENTION (matches kx_ticker_close.derive_close, never re-derives it here):
  close_prob is the HOME side's last-tick venue-implied win probability.
  Two-way decimal odds for compute_clv are the NAIVE complement pair
  (1/p, 1/(1-p)) -- NOT devigged/two-book, because a Kalshi single-market YES
  price already IS the venue's one number for that side; the away leg is
  simply its complement (Kalshi binaries have no separate away contract quote
  in this capture). This is explicitly a PROXY, stamped close_kind='last_tick'
  and clv_is_proxy=True always -- never promoted to a "true" close.

HONESTY (binding): a close_prob of exactly 0.0 or 1.0 (or missing/NaN) yields
None -- we never divide by zero or fabricate an odds pair. This module reads
data/cache/kx_closes/ ONLY (via kx_ticker_close.get_close_prob); it never
derives (writes) closes itself and never touches the ESPN line_history corpus
or the canonical ledger.

INVARIANTS: scripts/platformkit/clv/ only; <=300 LOC; ASCII only; no network;
never raises.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/clv/test_kx_close_fallback.py -q
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from scripts.platformkit.clv import kx_ticker_close as _kx

logger = logging.getLogger(__name__)


def _is_kx_ticker(game_id: str) -> bool:
    """Same convention as kx_ticker_close._is_kx_ticker: a non-numeric venue id."""
    s = str(game_id or "").strip()
    return bool(s) and not s.isdigit()


def _join_id(row: Dict[str, Any]) -> Optional[str]:
    """Same preference order as clv_close_lookup._join_id: game_id, then event_id."""
    for k in ("game_id", "event_id"):
        v = row.get(k)
        if v not in (None, ""):
            return str(v)
    return None


def lookup_close_legs_kx(row: Dict[str, Any]) -> Optional[Tuple[float, float, bool]]:
    """``(close_home_decimal, close_away_decimal, is_true_close)`` for a Kalshi-
    ticker-keyed in-game bet, derived from the captured tick series' last price.

    Returns None when: the row's join id is not a KX-style ticker (ESPN-numeric
    rows are OUT OF SCOPE here -- they use the existing line_store path), no
    close was ever derived for that ticker (kx_ticker_close.write_closes has not
    run, or the tick file was empty), or close_prob is degenerate (<=0 or >=1,
    cannot invert to odds). is_true_close is ALWAYS False -- a last-tick proxy
    is by definition never an at-lock true close. Never raises.
    """
    jid = _join_id(row)
    if jid is None or not _is_kx_ticker(jid):
        return None
    sport = str(row.get("sport") or "").lower()
    if not sport:
        return None
    try:
        rec = _kx.get_close_prob(jid, sport)
    except Exception as exc:  # noqa: BLE001 -- a lookup failure is an honest miss
        logger.debug("kx_close_fallback lookup failed for %s/%s: %s", sport, jid, exc)
        return None
    if rec is None:
        return None
    try:
        p_home = float(rec.get("close_prob"))
    except (TypeError, ValueError):
        return None
    if not (0.0 < p_home < 1.0):
        return None
    close_home_decimal = 1.0 / p_home
    close_away_decimal = 1.0 / (1.0 - p_home)
    return (close_home_decimal, close_away_decimal, False)


def close_kind_for_row(row: Dict[str, Any]) -> Optional[str]:
    """The close_kind label ('last_tick') for a KX-ticker row with a derived
    close, or None if lookup_close_legs_kx(row) would return None. Lets a
    caller stamp clv rows with close_kind WITHOUT re-deriving the odds pair."""
    if lookup_close_legs_kx(row) is None:
        return None
    return _kx.CLOSE_KIND


__all__ = ["lookup_close_legs_kx", "close_kind_for_row"]
