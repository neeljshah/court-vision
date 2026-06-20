"""scripts.platformkit.odds_provider.market_join -- join predictor edges to quotes.

Joins a list of model-edge rows (EdgeRow dicts) to a list of captured MarketQuote
objects on the natural key (game_id, market_type, side).  This is the bridge
between the predict_service model output and the live book prices: every joined
row carries both the model's probability signal and the book's priced line so
downstream consumers (CLV ledger, paper engine, stake sizer) have what they need
in one flat record.

DESIGN DECISIONS (locked for M3):
  * Multiple books per side -- KEEP ALL.  A side may be priced by several venues
    (e.g. "espn:DraftKings" + "kalshi").  We emit ONE JoinedRow per (edge, quote)
    pair.  Callers that want only the best price can filter / sort by ``odds``;
    callers that want all prices (e.g. CLV vs each venue) keep them all.  Dropping
    to a single best-book row here would silently discard the closing-line context
    that CLV computation needs later.
  * Edges with NO matching quote are OMITTED (never fabricated).  A quote with no
    edge is ignored (we are an edge-first system; a book line alone has no model
    signal attached).
  * Pure function, no IO, no network.

JoinedRow field overview:
  From the edge (predict_service.contracts.EdgeRow):
    game_id       -- shared join key
    market_type   -- "moneyline" | "spread" | "total"
    side          -- "home"/"away" (ml/spread) | "over"/"under" (total)
    model_prob    -- model's calibrated probability for *side* winning
    market_prob   -- implied probability from the book price at bet time
    ev            -- EV per 1-unit stake (probability ratio, not dollars)
    tier          -- evidence tier "A"/"B"/"C" or None
    edge_book     -- book the edge was originally computed against (may differ
                     from quote_book when multiple venues price the same side)
    edge_line     -- line the edge was computed against (None for moneyline)
    edge_clv_is_proxy -- from the EdgeRow (was the close at edge-compute time a proxy?)
  From the quote (MarketQuote):
    quote_book      -- venue name for this specific price row
    quote_line      -- handicap/total for this venue's price (None for moneyline)
    quote_odds      -- decimal odds (> 1.0) as quoted by this venue
    quote_devigged_prob -- Shin no-vig fair prob for *side* from this venue (or None)
    quote_captured_at   -- ISO-8601 UTC timestamp the quote was captured

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; no IO.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Union

from scripts.platformkit.odds_provider.markets import MarketQuote

# --------------------------------------------------------------------------- #
# Output schema
# --------------------------------------------------------------------------- #

@dataclass
class JoinedRow:
    """One (edge, quote) pair for the same (game_id, market_type, side).

    When a side has N quotes (N books), N JoinedRows are emitted for that edge.
    This preserves all pricing context; the caller filters / picks best price.
    """
    # --- edge fields (from predict_service.contracts.EdgeRow) ---
    game_id: str
    market_type: str
    side: str
    model_prob: float
    market_prob: float
    ev: float
    tier: Optional[str]
    edge_book: str
    edge_line: Optional[float]
    edge_clv_is_proxy: bool

    # --- quote fields (from MarketQuote / MarketRow) ---
    quote_book: str
    quote_line: Optional[float]
    quote_odds: float
    quote_devigged_prob: Optional[float]
    quote_captured_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _edge_key(edge: Any) -> Optional[tuple]:
    """Extract the join key (game_id, market_type, side) from an EdgeRow-like obj.

    Accepts both EdgeRow instances (predict_service.contracts.EdgeRow) and plain
    dicts -- so callers can pass either form without a hard import of EdgeRow here.
    Returns None if the key is malformed (edge silently skipped, never fabricated).
    """
    try:
        if isinstance(edge, dict):
            gid = str(edge["game_id"]).strip()
            mt = str(edge["market_type"]).strip()
            sd = str(edge["side"]).strip()
        else:
            gid = str(edge.game_id).strip()
            mt = str(edge.market_type).strip()
            sd = str(edge.side).strip()
    except (KeyError, AttributeError, TypeError):
        return None
    if not gid or not mt or not sd:
        return None
    return (gid, mt, sd)


def _edge_field(edge: Any, name: str, default: Any = None) -> Any:
    """Read a field from EdgeRow-or-dict safely, returning *default* on miss."""
    try:
        if isinstance(edge, dict):
            return edge.get(name, default)
        return getattr(edge, name, default)
    except Exception:  # noqa: BLE001
        return default


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def join_quotes_to_edges(
    edges: Sequence[Any],
    quotes: Sequence[MarketQuote],
) -> List[JoinedRow]:
    """Join predictor edges to captured market quotes on (game_id, market_type, side).

    Parameters
    ----------
    edges:
        Iterable of predict_service.contracts.EdgeRow instances OR plain dicts
        with the same field names (game_id, market_type, side, model_prob,
        market_prob, ev, tier, book, line, clv_is_proxy).
    quotes:
        Iterable of MarketQuote objects produced by
        scripts.platformkit.odds_provider.markets.quotes_from_aggregate().

    Returns
    -------
    List[JoinedRow]
        One JoinedRow for each (edge, quote) pair that shares a key.
        Multiple books per side -> multiple rows (all retained).
        An edge with no matching quote is omitted entirely.
        A quote with no matching edge is ignored.
        Order: same as *edges*; within each edge, book order mirrors *quotes*.

    HONESTY: no line or price is invented; if an edge has no live quote the caller
    gets no row back (they cannot fabricate a close to compute CLV).
    """
    # Build a multimap: key -> list[MarketQuote].
    # We do this once up front so the join is O(E + Q) not O(E*Q).
    quote_map: Dict[tuple, List[MarketQuote]] = {}
    for q in quotes:
        key = (str(q.game_id).strip(), str(q.market_type).strip(),
               str(q.side).strip())
        if not all(key):
            continue  # malformed quote silently skipped
        quote_map.setdefault(key, []).append(q)

    out: List[JoinedRow] = []
    for edge in edges:
        key = _edge_key(edge)
        if key is None:
            continue  # malformed edge silently skipped
        matched = quote_map.get(key)
        if not matched:
            continue  # no quote for this edge -> omit (never fabricate)
        for q in matched:
            out.append(JoinedRow(
                # edge fields
                game_id=key[0],
                market_type=key[1],
                side=key[2],
                model_prob=float(_edge_field(edge, "model_prob", 0.0)),
                market_prob=float(_edge_field(edge, "market_prob", 0.0)),
                ev=float(_edge_field(edge, "ev", 0.0)),
                tier=_edge_field(edge, "tier", None),
                edge_book=str(_edge_field(edge, "book", "")),
                edge_line=_edge_field(edge, "line", None),
                edge_clv_is_proxy=bool(_edge_field(edge, "clv_is_proxy", True)),
                # quote fields
                quote_book=str(q.book),
                quote_line=q.line,
                quote_odds=float(q.odds),
                quote_devigged_prob=q.devigged_prob,
                quote_captured_at=str(q.captured_at),
            ))
    return out


__all__ = ["JoinedRow", "join_quotes_to_edges"]
