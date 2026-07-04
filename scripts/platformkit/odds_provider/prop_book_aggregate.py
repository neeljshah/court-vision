"""scripts.platformkit.odds_provider.prop_book_aggregate -- FanDuel sportsbook wiring.

Wires two-sided SPORTSBOOK prop providers (payout_type="sportsbook") into the
prop best-line cross-source selection alongside DFS single-sided pick'em sources.

PROVIDER AUDIT (2026-07-03, prop close-capture root-cause): FanDuel's keyless NJ
API posts NO player-prop markets for MLB at all -- verified live (in-progress AND
pregame events both return only team/inning markets: Moneyline, Run Line, Total
Runs, "Nth Inning ..."). FanDuel-only left this module structurally silent for MLB.
DraftKingsV2Provider (prop_draftkings_v2, sportsbook-nash endpoint) is the provider
prop_edge_config actually wires for the REAL MLB pregame prop board and was live-
verified to return 100+ two-way rows same session -- added here so book_best_line_
props (and its caller, prop_close_capture_pregame) sees real MLB pregame closes.

CONTRACT (all upheld here):
  - Sportsbook two-sided price BEATS a DFS pick'em non-price on the same side:
    _better_price from prop_aggregate already handles this (any real decimal > None),
    so a FanDuel decimal beats a PrizePicks/Underdog None on the same (player, stat,
    line) key.
  - OVER-only sportsbook row (under_price=None): the UNDER stays absent; never
    guessed, never borrowed from another source for a different player/stat.
  - payout_type carried through: "sportsbook" when a real decimal price is present
    on at least one side; "dfs_pickem" when only a DFS context row survives.
  - Provider down -> UNAVAILABLE sentinel, not a synthetic empty list.
  - Offseason empty slate -> [] (no events) not a fabricated row list.
  - NEVER raises.

Build-on (READ-ONLY from this module):
  prop_fanduel.FanDuelProvider  -- two-sided American-odds sportsbook props (soccer;
    MLB currently posts no player props there -- kept as a provider for when it does)
  prop_draftkings_v2.DraftKingsV2Provider -- two-sided sportsbook-nash pregame props
    (the REAL live MLB pregame source; verified posting 100+ rows/session)
  prop_aggregate.gather_props, best_line_props, _better_price -- core merge logic
  prop_base.PropLine -- normalized row type
  base.is_unavailable, unavailable -- sentinel helpers

LOC discipline: <=300 LOC. ASCII only. No $ field. Per-file test:
  python -m pytest tests/platformkit/odds_provider/test_prop_book_aggregate.py -q
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Union

from .base import is_unavailable, unavailable
from .prop_aggregate import best_line_props, gather_props
from .prop_base import PropLine
from .prop_draftkings_v2 import DraftKingsV2Provider
from .prop_fanduel import FanDuelProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Book registry: providers yielding two-sided sportsbook props (payout_type=
# "sportsbook"). Additional DFS providers (PrizePicks, Underdog) are accepted
# as supplemental context sources in the optional dfs_providers argument.
#
# DraftKingsV2Provider listed first: it is the live-verified MLB pregame source
# (100+ rows/session, 2026-07-03 audit); FanDuel posts no MLB player props today
# but stays wired for soccer/WC and in case MLB props post there later. Both
# NEVER raise and degrade to UNAVAILABLE individually -- one dead provider never
# sinks the other (best_line_props merges whatever real prices come back).
# ---------------------------------------------------------------------------

_SPORTSBOOK_PROVIDERS = (DraftKingsV2Provider, FanDuelProvider)


def _default_book_providers() -> List[Any]:
    """Instantiate the default sportsbook provider set (keyless, no network at init)."""
    return [cls() for cls in _SPORTSBOOK_PROVIDERS]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def book_best_line_props(
    sport: str,
    *,
    book_providers: Optional[Sequence[Any]] = None,
    dfs_providers: Optional[Sequence[Any]] = None,
) -> List[PropLine]:
    """Return per-(player, stat, line) best OVER and best UNDER from sportsbook+DFS.

    Sportsbook two-sided prices (payout_type="sportsbook") beat any DFS pick'em
    context row on the same side because _better_price returns a real decimal over
    None. payout_type is "sportsbook" whenever at least one side has a real price;
    it is "dfs_pickem" for context-only rows where no sportsbook quoted the prop.

    Args:
        sport: e.g. "soccer_intl", "nba", "mlb".
        book_providers: sportsbook providers to query. Defaults to [FanDuelProvider].
            Injectable so tests can pass canned providers with no network calls.
        dfs_providers: optional DFS context providers (PrizePicks, Underdog, etc.).
            Default None means no DFS supplement -- DFS rows are context only and
            never inflate the price on a side already covered by a sportsbook.

    Returns:
        Sorted list[PropLine]. Empty list when all providers are down or no markets
        are posted (offseason) -- never a fabricated row. NEVER raises.
    """
    providers: List[Any] = list(book_providers if book_providers is not None
                                else _default_book_providers())
    if dfs_providers:
        providers.extend(dfs_providers)
    try:
        return best_line_props(providers, sport)
    except Exception as exc:  # noqa: BLE001 -- defensive: best_line_props never raises
        logger.warning("book_best_line_props unexpected error for %s: %s", sport, exc)
        return []


def book_gather_raw(
    sport: str,
    *,
    book_providers: Optional[Sequence[Any]] = None,
    dfs_providers: Optional[Sequence[Any]] = None,
) -> List[PropLine]:
    """Flat-gather (no dedup) from sportsbook+DFS providers for *sport*.

    Like gather_props but pre-wired to the sportsbook registry. Useful when a
    caller needs the raw multi-source rows before merging. NEVER raises.
    """
    providers: List[Any] = list(book_providers if book_providers is not None
                                else _default_book_providers())
    if dfs_providers:
        providers.extend(dfs_providers)
    try:
        return gather_props(providers, sport)
    except Exception as exc:  # noqa: BLE001
        logger.warning("book_gather_raw unexpected error for %s: %s", sport, exc)
        return []


def book_props_unavailable(
    sport: str,
    *,
    book_providers: Optional[Sequence[Any]] = None,
) -> Union[List[PropLine], Dict[str, str]]:
    """Try book providers and return UNAVAILABLE sentinel when nothing is posted.

    Returns:
        list[PropLine] (possibly empty for an empty offseason slate) on a normal run,
        or the UNAVAILABLE sentinel dict when every provider signals UNAVAILABLE.

    This is a thin helper for API callers that want to distinguish:
      - UNAVAILABLE  : providers are down / sport not supported (return sentinel)
      - []           : providers are up but no markets posted yet (return [])
      - [rows...]    : normal live data
    """
    providers: List[Any] = list(book_providers if book_providers is not None
                                else _default_book_providers())
    all_unavailable = True
    rows: List[PropLine] = []
    for prov in providers:
        try:
            result = prov.fetch_props(sport)
        except Exception as exc:  # noqa: BLE001
            logger.warning("book_props_unavailable: provider %s error: %s",
                           getattr(prov, "name", type(prov).__name__), exc)
            continue
        if is_unavailable(result):
            logger.debug("book_props_unavailable: provider %s UNAVAILABLE for %s",
                         getattr(prov, "name", type(prov).__name__), sport)
            continue
        all_unavailable = False
        if isinstance(result, list):
            rows.extend(r for r in result if isinstance(r, PropLine))
    if all_unavailable:
        return unavailable(
            "book_props: all providers unavailable for sport '%s'" % sport)
    return rows


__all__ = [
    "book_best_line_props",
    "book_gather_raw",
    "book_props_unavailable",
    "FanDuelProvider",
]
