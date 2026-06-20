"""scripts.platformkit.odds_provider.markets -- typed team-market quote layer.

Turns the keyless multi-venue slate produced by `aggregate(sport)` into a flat,
typed list of `MarketQuote`s for the three team markets -- moneyline, spread,
total -- so a downstream consumer (predict_service) can map each quote cleanly
onto a `predict_service.contracts.MarketRow` (field names are mirrored).

What the aggregate carries (see odds_provider/base.OddsEvent.prices):
  {venue: {"home": dec, "away": dec, "draw": dec|None, ...}}
where dec is DECIMAL odds (> 1.0). The republished ESPN / Kalshi / Polymarket
slate is MONEYLINE today; this layer ALSO parses a forward-compatible extended
per-venue shape for spreads/totals when a venue quotes them:
  prices[venue]["spread"] = {"home": {"line": -3.5, "odds": 1.91},
                             "away": {"line":  3.5, "odds": 1.91}}
  prices[venue]["total"]  = {"over":  {"line": 44.5, "odds": 1.91},
                             "under": {"line": 44.5, "odds": 1.91}}
A side a venue does not quote is simply absent -- we NEVER fabricate a line or a
price. devigged_prob is the no-vig fair probability via the vetted Shin solver.

Three-way moneyline (soccer):
  When a venue quotes home + draw + away, all three legs are devigged jointly
  via the Shin N-outcome solver (shin_devig_decimal accepts any number of legs).
  This gives honest devigged_prob on every leg, summing to ~1. When the draw leg
  is genuinely absent (two-sided market), the legacy two-way Shin path is used
  instead -- we NEVER fabricate a draw price. The resulting MarketQuote for the
  draw leg has side='draw'.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only;
stdlib dataclasses; no network here (agg/now injectable for offline tests).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .aggregate import aggregate
from ..odds_shop import devig_twoway
from ..eval_gate.shin import shin_devig_decimal

# market_type values, matching predict_service.contracts.MarketRow.market_type.
MONEYLINE = "moneyline"
SPREAD = "spread"
TOTAL = "total"


@dataclass
class MarketQuote:
    """One venue's price for one side of one team market.

    Field names mirror predict_service.contracts.MarketRow where they overlap
    (sport, game_id, market_type, side, line, odds, book, devigged_prob,
    captured_at), so MarketQuote.to_market_row_dict() maps straight onto a
    MarketRow. home/away carry the game context the slate row belongs to.

    market_type: 'moneyline' | 'spread' | 'total'. side is 'home'/'away' for
    moneyline & spread, 'over'/'under' for total. line is the handicap/total
    (None for moneyline). odds is DECIMAL (> 1.0). devigged_prob is the no-vig
    fair probability for *side* (None until a two-way pair is devigged).
    captured_at is ISO-8601 UTC (the slate's as_of / now).
    """

    sport: str
    game_id: str
    home: str
    away: str
    market_type: str
    side: str
    line: Optional[float]
    odds: float
    book: str
    captured_at: str
    devigged_prob: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_market_row_dict(self) -> Dict[str, Any]:
        """The subset of fields a predict_service MarketRow consumes."""
        return {
            "sport": self.sport,
            "game_id": self.game_id,
            "market_type": self.market_type,
            "side": self.side,
            "line": self.line,
            "odds": self.odds,
            "book": self.book,
            "devigged_prob": self.devigged_prob,
            "captured_at": self.captured_at,
        }


def _now_iso(now: Optional[datetime]) -> str:
    dt = now if now is not None else datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _decimal(value: Any) -> Optional[float]:
    """A usable decimal price (> 1.0) or None. Never fabricates."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v > 1.0 else None


def _line(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _devig_pair(price_a: Optional[float], price_b: Optional[float],
                ) -> Tuple[Optional[float], Optional[float]]:
    """No-vig (fair_a, fair_b) via the vetted Shin solver, or (None, None).

    Only computes when BOTH sides have a usable decimal price; a one-sided
    market yields no devig (we never infer the missing side).
    """
    if price_a is None or price_b is None:
        return None, None
    try:
        fa, fb = devig_twoway(price_a, price_b)
    except Exception:  # noqa: BLE001 -- devig must never sink a row
        return None, None
    if not (0.0 < fa < 1.0 and 0.0 < fb < 1.0):
        return None, None
    return fa, fb


def _devig_threeway(
    price_h: Optional[float],
    price_d: Optional[float],
    price_a: Optional[float],
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """No-vig (fair_h, fair_d, fair_a) for a three-way market via Shin N-outcome.

    The Shin solver (shin_devig_decimal) accepts any number of legs, so passing
    all three together accounts for the draw's share of the overround correctly.
    Returns (None, None, None) if ANY leg is missing or the solver fails -- we
    never fabricate a fair probability for a partial market.
    """
    if price_h is None or price_d is None or price_a is None:
        return None, None, None
    try:
        probs, _z = shin_devig_decimal([price_h, price_d, price_a])
        fh, fd, fa = float(probs[0]), float(probs[1]), float(probs[2])
    except Exception:  # noqa: BLE001 -- devig must never sink a row
        return None, None, None
    if not all(0.0 < p < 1.0 for p in (fh, fd, fa)):
        return None, None, None
    return fh, fd, fa


def _moneyline_quotes(ctx: Dict[str, str], venue: str,
                      sides: Dict[str, Any]) -> List[MarketQuote]:
    """Moneyline quotes from a venue's flat side dict (home/draw/away or home/away).

    Soccer (3-way): when a draw price is present alongside home and away, the
    three legs are devigged jointly via the Shin N-outcome solver so each
    devigged_prob is honest and all three sum to ~1. The draw leg becomes a
    MarketQuote with side='draw'.

    All other markets (2-way): the legacy Shin two-way path is used. When the
    draw leg is genuinely missing we NEVER fabricate it -- devigged_prob is
    filled only where the full complement of legs is present.
    """
    h = _decimal(sides.get("home"))
    d = _decimal(sides.get("draw"))
    a = _decimal(sides.get("away"))
    out: List[MarketQuote] = []
    if d is not None:
        # Three-way market (soccer home/draw/away) -- devig all three jointly.
        fair_h, fair_d, fair_a = _devig_threeway(h, d, a)
        legs: List[Tuple[str, Optional[float], Optional[float]]] = [
            ("home", h, fair_h), ("draw", d, fair_d), ("away", a, fair_a),
        ]
    else:
        # Two-way market (NBA/MLB/tennis etc.) -- legacy Shin two-way path.
        fair_h, fair_a = _devig_pair(h, a)
        legs = [("home", h, fair_h), ("away", a, fair_a)]
    for side, odds, fair in legs:
        if odds is None:
            continue
        out.append(_quote(ctx, venue, MONEYLINE, side, None, odds, fair))
    return out


def _two_way_quotes(ctx: Dict[str, str], venue: str, market_type: str,
                    node: Any, side_a: str, side_b: str) -> List[MarketQuote]:
    """Parse a {side: {'line','odds'}} extended node into MarketQuotes.

    Used for spread (home/away) and total (over/under). A side missing a line OR
    a usable price is omitted -- never fabricated. devigged_prob is filled when
    both sides price.
    """
    if not isinstance(node, dict):
        return []
    parsed: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    for side in (side_a, side_b):
        leg = node.get(side)
        if not isinstance(leg, dict):
            parsed[side] = (None, None)
            continue
        parsed[side] = (_line(leg.get("line")), _decimal(leg.get("odds")))
    (la, oa), (lb, ob) = parsed[side_a], parsed[side_b]
    # Both legs must be fully formed (line AND price) for the market to be
    # two-way; only then is a devig honest -- otherwise one side gets dropped and
    # a lone devigged_prob would be misleading.
    a_ok = la is not None and oa is not None
    b_ok = lb is not None and ob is not None
    fair_a, fair_b = _devig_pair(oa, ob) if (a_ok and b_ok) else (None, None)
    out: List[MarketQuote] = []
    for side, line, odds, fair, ok in (
        (side_a, la, oa, fair_a, a_ok), (side_b, lb, ob, fair_b, b_ok),
    ):
        if not ok:  # need BOTH a line and a price
            continue
        out.append(_quote(ctx, venue, market_type, side, line, odds, fair))
    return out


def _quote(ctx: Dict[str, str], venue: str, market_type: str, side: str,
           line: Optional[float], odds: float,
           fair: Optional[float]) -> MarketQuote:
    return MarketQuote(
        sport=ctx["sport"], game_id=ctx["game_id"], home=ctx["home"],
        away=ctx["away"], market_type=market_type, side=side, line=line,
        odds=odds, book=venue, captured_at=ctx["captured_at"],
        devigged_prob=fair)


def _event_quotes(event: Dict[str, Any], sport: str,
                  captured_at: str) -> List[MarketQuote]:
    """All team-market quotes for one merged aggregate event (skips malformed)."""
    home = str(event.get("home") or "").strip()
    away = str(event.get("away") or "").strip()
    game_id = str(event.get("event_id") or "").strip()
    prices = event.get("prices")
    if not home or not away or not game_id or not isinstance(prices, dict):
        return []
    ctx = {"sport": sport, "game_id": game_id, "home": home, "away": away,
           "captured_at": captured_at}
    out: List[MarketQuote] = []
    for venue, sides in prices.items():
        if not venue or not isinstance(sides, dict):
            continue
        out.extend(_moneyline_quotes(ctx, str(venue), sides))
        out.extend(_two_way_quotes(ctx, str(venue), SPREAD,
                                   sides.get("spread"), "home", "away"))
        out.extend(_two_way_quotes(ctx, str(venue), TOTAL,
                                   sides.get("total"), "over", "under"))
    return out


def quotes_from_aggregate(sport: str, *, agg: Optional[Dict[str, Any]] = None,
                          now: Optional[datetime] = None) -> List[MarketQuote]:
    """Typed MarketQuotes for *sport* from the keyless consensus slate.

    *agg* (an aggregate() payload) and *now* are injectable so this is fully
    offline-testable; when *agg* is None we call aggregate(sport) ourselves.
    Parses each merged event's per-venue moneyline plus any extended spread /
    total nodes a venue quotes. Malformed entries are omitted; we NEVER
    fabricate a line or a price. Returns [] when the slate is unavailable.
    """
    payload = agg if agg is not None else aggregate(sport)
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return []
    captured_at = str(payload.get("as_of") or "").strip() or _now_iso(now)
    sport_key = str(payload.get("sport") or sport or "").lower()
    out: List[MarketQuote] = []
    for event in payload.get("events", []) or []:
        if isinstance(event, dict):
            out.extend(_event_quotes(event, sport_key, captured_at))
    return out


__all__ = [
    "MarketQuote", "quotes_from_aggregate",
    "MONEYLINE", "SPREAD", "TOTAL",
]
