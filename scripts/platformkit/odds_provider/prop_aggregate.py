"""scripts.platformkit.odds_provider.prop_aggregate -- cross-source prop best-line.

Gathers PropLine rows from multiple providers for the same sport and de-duplicates
them by (player, stat, line) so the best two-sided price wins when multiple books
quote the same prop. Only sportsbook-priced rows (payout_type="sportsbook") enter
the best-price race; DFS pick'em rows (over_price=None) pass through unchanged as
context rows (a player on PrizePicks but with no real two-sided price still shows
up -- callers can display the line even if there is no exploitable price).

HONESTY: this module never fabricates a price. When no sportsbook quotes a side,
that side's price is None. A pick'em row from one source beats a missing sportsbook
price ONLY in the sense that it still carries the LINE -- it never inherits a fake
decimal_price. `is_pm` is False (these are DFS lines, not prediction-market lines).

UNAVAILABLE path: if all providers return empty / UNAVAILABLE for a sport, the
output list is [] and callers must degrade to status='UNAVAILABLE'. Never raises.

Per-file test: python -m pytest tests/platformkit/test_lines_matrix_routes.py -q
INVARIANTS: <=300 LOC; build under scripts/platformkit/; ASCII only; no $ field.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .prop_base import PropLine
from .base import is_unavailable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _key(row: PropLine) -> Tuple[str, str, str, float]:
    """De-dup key: (player, stat, event_id, line).

    Normalized to lowercase + stripped so minor label inconsistencies (casing,
    trailing spaces) across providers merge into one row.
    """
    return (
        str(row.player or "").strip().lower(),
        str(row.stat or "").strip().lower(),
        str(row.event_id or "").strip().lower(),
        float(row.line),
    )


def _better_price(current: Optional[float], candidate: Optional[float],
                  side: str) -> Optional[float]:
    """For OVER we want the HIGHEST decimal (more payout); same for UNDER.

    Returns *candidate* when it is a usable decimal (> 1.0) AND is better than
    (or replaces a missing) *current*. Never invents a price.
    """
    if candidate is None:
        return current
    try:
        c = float(candidate)
    except (TypeError, ValueError):
        return current
    if c <= 1.0:
        return current
    if current is None:
        return c
    try:
        cur = float(current)
    except (TypeError, ValueError):
        return c
    return c if c > cur else cur


def _merge_row(base: PropLine, other: PropLine) -> PropLine:
    """Merge *other* into *base*, keeping the best over_price/under_price.

    payout_type upgrades from "dfs_pickem" to "sportsbook" when the winning
    price comes from a sportsbook-priced source. source is kept as the original
    base source (first seen); as_of keeps the most-recent stamp.
    """
    new_over = _better_price(base.over_price, other.over_price, "over")
    new_under = _better_price(base.under_price, other.under_price, "under")
    # payout_type upgrades if either side now has a real decimal price.
    pt = base.payout_type
    if (new_over is not None or new_under is not None):
        pt = "sportsbook"
    # Freshest as_of wins.
    as_of = base.as_of
    if other.as_of and (not as_of or other.as_of > as_of):
        as_of = other.as_of
    return PropLine(
        sport=base.sport,
        event_id=base.event_id,
        match=base.match or other.match,
        player=base.player,
        team=base.team or other.team,
        stat=base.stat,
        line=base.line,
        over_price=new_over,
        under_price=new_under,
        payout_type=pt,
        source=base.source,
        as_of=as_of,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def gather_props(
    providers: Sequence[Any],
    sport: str,
) -> List[PropLine]:
    """Call each provider's fetch_props(sport) and return a flat list.

    This is a PASS-THROUGH gather (no dedup) matching prop_edge._gather.
    Providers that raise or return UNAVAILABLE are silently skipped (logged).
    NEVER raises; returns [] when all providers are down.
    """
    rows: List[PropLine] = []
    for prov in providers:
        try:
            result = prov.fetch_props(sport)
        except Exception as exc:  # noqa: BLE001
            logger.warning("prop_aggregate.gather_props: provider %s error: %s",
                           getattr(prov, "name", type(prov).__name__), exc)
            continue
        if is_unavailable(result):
            logger.debug("prop_aggregate: provider %s -> UNAVAILABLE for %s",
                         getattr(prov, "name", type(prov).__name__), sport)
            continue
        if isinstance(result, list):
            rows.extend(r for r in result if isinstance(r, PropLine))
    return rows


def best_line_props(
    providers: Sequence[Any],
    sport: str,
) -> List[PropLine]:
    """Gather props from all providers and de-duplicate by best over/under price.

    For each (player, stat, event_id, line) tuple:
    - When multiple providers quote the same prop, keep the HIGHEST decimal price
      per side (a bettor always prefers more payout).
    - DFS pick'em rows (over_price=None) survive as context rows but a sportsbook
      row for the same key REPLACES the pick'em row (real price wins).
    - When no sportsbook quotes a prop at all, the pick'em row is the only
      context available and is returned with over_price=None (honest).

    Returns: list of deduplicated PropLine, sorted by (player, stat, line).
    NEVER raises; returns [] when all providers are down.
    """
    raw = gather_props(providers, sport)
    if not raw:
        return []

    merged: Dict[Tuple[str, str, str, float], PropLine] = {}
    for row in raw:
        k = _key(row)
        if k not in merged:
            merged[k] = row
        else:
            merged[k] = _merge_row(merged[k], row)

    out = sorted(merged.values(), key=lambda r: (
        str(r.player or "").lower(),
        str(r.stat or "").lower(),
        float(r.line),
    ))
    return out


def prop_best_line_summary(row: PropLine) -> Dict[str, Any]:
    """Flat dict summary for one de-duplicated PropLine, shaped for the API.

    Fields: player, team, stat, line, over_price, under_price, payout_type,
    source, as_of, event_id, match, sport. No $ field. is_pm=False (DFS/sportsbook
    lines are NOT prediction-market contracts).
    """
    return {
        "player": row.player,
        "team": row.team,
        "stat": row.stat,
        "line": row.line,
        "over_price": row.over_price,
        "under_price": row.under_price,
        "payout_type": row.payout_type,
        "source": row.source,
        "as_of": row.as_of,
        "event_id": row.event_id,
        "match": row.match,
        "sport": row.sport,
        "is_pm": False,
    }


__all__ = [
    "gather_props",
    "best_line_props",
    "prop_best_line_summary",
]
