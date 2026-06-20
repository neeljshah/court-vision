"""scripts.platformkit.prop_edge_bestline -- cross-source prop best-line selection.

Wraps prop_aggregate.best_line_props so that when two (or more) providers quote
the SAME (player, stat, line) for the same event, the single row that survives has
the HIGHEST decimal over_price AND the HIGHEST decimal under_price -- one row per
key, never a duplicate.

This is the integration point between the multi-provider gather layer
(prop_aggregate) and the edge board (prop_edge._gather / build_prop_board): callers
that previously collected a flat, undeduped list of PropLine rows from _gather
should call gather_best_lines instead to guarantee exactly one row per key before
the pricing engine runs.

KEY INVARIANTS:
  - No $ P&L field (units / calibration / CLV only).
  - UNAVAILABLE is returned honestly as {"status": "unavailable", "reason": ...}
    when all providers are down OR when the deduped list is empty.
  - Never raises -- all errors degrade to UNAVAILABLE or empty list with a log.
  - Per-side semantics: over_price and under_price are selected INDEPENDENTLY so
    we keep the best over from provider A and the best under from provider B if
    that combination is most favorable.
  - Single provider -> passthrough (no dedup mutation; idempotent).

Per-file test:
    cd /c/Users/neelj/nba-ai-system && \\
    python -m pytest scripts/platformkit/test_prop_edge_bestline.py -q
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.odds_provider.prop_base import PropLine
from scripts.platformkit.odds_provider.prop_aggregate import best_line_props
from scripts.platformkit.odds_provider.base import is_unavailable, UNAVAILABLE

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------

class BestLineResult:
    """Return value from gather_best_lines.

    Attributes
    ----------
    rows : list[PropLine]
        Deduplicated rows, one per (player, stat, event_id, line) key, with the
        best (highest decimal) over_price and under_price from all providers.
        Empty when all providers are down or no rows were posted.
    sources : dict[str, str]
        Per-provider health summary: "ok (N rows)" or "unavailable: <reason>".
    is_available : bool
        True when at least one row was returned; False when the result is empty
        (callers should surface "UNAVAILABLE" in that case).
    unavailable_reason : str | None
        Human-readable reason string when is_available is False.
    """

    __slots__ = ("rows", "sources", "is_available", "unavailable_reason")

    def __init__(
        self,
        rows: List[PropLine],
        sources: Dict[str, str],
        is_available: bool,
        unavailable_reason: Optional[str] = None,
    ) -> None:
        self.rows = rows
        self.sources = sources
        self.is_available = is_available
        self.unavailable_reason = unavailable_reason

    def to_unavailable_dict(self) -> Dict[str, Any]:
        """Return the UNAVAILABLE sentinel dict shaped for API / board callers."""
        return {
            "status": "unavailable",
            "reason": self.unavailable_reason or "no prop lines returned",
            "sources": self.sources,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _probe_providers(
    providers: Sequence[Any],
    sport: str,
) -> Dict[str, str]:
    """Dry-run each provider to build a source-health summary without gathering rows.

    Returns {provider_name: status_string} for reporting. The actual row gather
    is done by best_line_props (which also suppresses provider errors).
    """
    health: Dict[str, str] = {}
    for prov in providers:
        name = getattr(prov, "name", type(prov).__name__)
        try:
            res = prov.fetch_props(sport)
        except Exception as exc:  # noqa: BLE001
            health[name] = "error: %s" % type(exc).__name__
            continue
        if is_unavailable(res):
            reason = res.get("reason", "unavailable") if isinstance(res, dict) else "unavailable"
            health[name] = "unavailable: %s" % reason
        elif isinstance(res, list):
            health[name] = "ok (%d rows)" % len(res)
        else:
            health[name] = "unexpected shape: %s" % type(res).__name__
    return health


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def gather_best_lines(
    providers: Sequence[Any],
    sport: str,
) -> BestLineResult:
    """Gather props from all providers; return one row per (player,stat,line) key.

    For each unique (player, stat, event_id, line) tuple, when multiple providers
    quote the same prop the row that survives has:
      - over_price  = max(all quoted over_prices)   # highest payout for the over
      - under_price = max(all quoted under_prices)  # highest payout for the under

    A DFS pick'em row (over_price=None) survives when it is the only source; a
    sportsbook row for the same key replaces it (real price wins).

    Returns a BestLineResult with is_available=False and an honest reason string
    when all providers are down or no rows were returned.

    NEVER raises.
    """
    if not providers:
        logger.debug("gather_best_lines: no providers for sport=%s", sport)
        return BestLineResult(
            rows=[],
            sources={},
            is_available=False,
            unavailable_reason="no providers configured",
        )

    # Build health summary (one extra round-trip per provider; accepted for
    # observability -- the data is already being fetched inside best_line_props).
    sources = _probe_providers(providers, sport)

    try:
        rows = best_line_props(providers, sport)
    except Exception as exc:  # noqa: BLE001
        logger.warning("gather_best_lines: best_line_props failed: %s", exc)
        return BestLineResult(
            rows=[],
            sources=sources,
            is_available=False,
            unavailable_reason="aggregation error: %s" % type(exc).__name__,
        )

    if not rows:
        reason = "no prop lines returned by any provider for sport=%s" % sport
        logger.debug("gather_best_lines: %s", reason)
        return BestLineResult(
            rows=[],
            sources=sources,
            is_available=False,
            unavailable_reason=reason,
        )

    return BestLineResult(
        rows=rows,
        sources=sources,
        is_available=True,
    )


def select_best_line(
    rows: Sequence[PropLine],
    player: str,
    stat: str,
    line: float,
) -> Optional[PropLine]:
    """Find the single best row for a given (player, stat, line) triple.

    Scans *rows* (assumed to already be deduped via gather_best_lines) and
    returns the matching row or None when not found. Case/whitespace insensitive
    on player and stat so minor label differences across providers do not miss.

    Useful for callers that want to look up a specific prop without re-running
    the full gather.
    """
    p_norm = str(player or "").strip().lower()
    s_norm = str(stat or "").strip().lower()
    try:
        l_float = float(line)
    except (TypeError, ValueError):
        return None
    for row in rows:
        if (str(row.player or "").strip().lower() == p_norm
                and str(row.stat or "").strip().lower() == s_norm
                and float(row.line) == l_float):
            return row
    return None


def best_line_summary(result: BestLineResult) -> Dict[str, Any]:
    """Flat summary dict for API / logging.

    Returns {"available": bool, "count": int, "sources": dict,
    "reason": str|None}. No $ field. is_pm always False (DFS/sportsbook lines
    are not prediction-market contracts).
    """
    return {
        "available": result.is_available,
        "count": len(result.rows),
        "sources": result.sources,
        "reason": result.unavailable_reason,
        "is_pm": False,
    }


__all__ = [
    "BestLineResult",
    "gather_best_lines",
    "select_best_line",
    "best_line_summary",
]
