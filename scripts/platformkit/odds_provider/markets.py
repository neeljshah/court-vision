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

CLOCK-TRUST GUARD (captured_at_suspect): captured_at is stamped from the
poller box's OWN wall-clock (http_cache._fetched_at / aggregate.as_of), then
later compared by line_store against the provider's ABSOLUTE commence_time to
decide a TRUE close. Those are two uses of the SAME box clock with no
external reconciliation. If that clock steps between the as_of stamp (taken
during the fetch) and *now* (read moments later, at the top of the same poll
tick -- see line_snapshot_daemon.poll_once), the two readings diverge and the
close classification silently corrupts. When |now - as_of| exceeds
CAPTURED_AT_SUSPECT_WINDOW_SEC we stamp every quote from this tick
captured_at_suspect=True; line_store's _within_lock() treats a suspect row as
PROXY-only (never a TRUE close). KNOWN LIMIT: this only catches a clock STEP
*within* one poll tick. A UNIFORM box-clock drift (as_of and now drift
together, e.g. the box is always +N minutes off true time) is invisible to
this in-process check -- that is an OPS guarantee (bounded-step NTP /
chrony + drift alerting on the poller host), not something this module can
detect from inside a single process. We do not build that ops system here.

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

# |now - as_of| beyond this many seconds -> captured_at_suspect=True (see the
# CLOCK-TRUST GUARD module docstring section above).
CAPTURED_AT_SUSPECT_WINDOW_SEC = 300  # 5 min


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
    captured_at is ISO-8601 UTC (the slate's as_of / now). captured_at_suspect
    is True when this tick's as_of disagreed with the poller's own clock by
    more than CAPTURED_AT_SUSPECT_WINDOW_SEC (see the CLOCK-TRUST GUARD module
    docstring section) -- line_store never treats a suspect row as a TRUE close.
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
    captured_at_suspect: bool = False

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


def _now_dt(now: Optional[datetime]) -> datetime:
    dt = now if now is not None else datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _now_iso(now: Optional[datetime]) -> str:
    return _now_dt(now).isoformat(timespec="seconds")


def _parse_iso(value: str) -> Optional[datetime]:
    """Best-effort ISO-8601 -> aware UTC datetime, or None. Never raises."""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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


def _quote(ctx: Dict[str, Any], venue: str, market_type: str, side: str,
           line: Optional[float], odds: float,
           fair: Optional[float]) -> MarketQuote:
    return MarketQuote(
        sport=ctx["sport"], game_id=ctx["game_id"], home=ctx["home"],
        away=ctx["away"], market_type=market_type, side=side, line=line,
        odds=odds, book=venue, captured_at=ctx["captured_at"],
        devigged_prob=fair,
        captured_at_suspect=bool(ctx.get("captured_at_suspect", False)))


def _event_quotes(event: Dict[str, Any], sport: str, captured_at: str,
                  captured_at_suspect: bool = False) -> List[MarketQuote]:
    """All team-market quotes for one merged aggregate event (skips malformed)."""
    home = str(event.get("home") or "").strip()
    away = str(event.get("away") or "").strip()
    game_id = str(event.get("event_id") or "").strip()
    prices = event.get("prices")
    if not home or not away or not game_id or not isinstance(prices, dict):
        return []
    ctx: Dict[str, Any] = {"sport": sport, "game_id": game_id, "home": home,
                           "away": away, "captured_at": captured_at,
                           "captured_at_suspect": captured_at_suspect}
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

    CLOCK-TRUST GUARD: when the slate carries a real as_of, every quote is
    stamped captured_at_suspect=True if as_of disagrees with *now* (or the
    live wall-clock when *now* is None) by more than
    CAPTURED_AT_SUSPECT_WINDOW_SEC, or if as_of does not parse -- see the
    module docstring. The *now*-absent fallback path (no as_of at all) always
    stamps captured_at=now and is never suspect (there is nothing to disagree
    with).
    """
    payload = agg if agg is not None else aggregate(sport)
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return []
    as_of_raw = str(payload.get("as_of") or "").strip()
    suspect = False
    if as_of_raw:
        captured_at = as_of_raw
        as_of_dt = _parse_iso(as_of_raw)
        if as_of_dt is None:
            suspect = True  # unverifiable clock claim -- never trust it as TRUE-close-eligible
        else:
            drift = abs((_now_dt(now) - as_of_dt).total_seconds())
            suspect = drift > CAPTURED_AT_SUSPECT_WINDOW_SEC
    else:
        captured_at = _now_iso(now)
    sport_key = str(payload.get("sport") or sport or "").lower()
    out: List[MarketQuote] = []
    for event in payload.get("events", []) or []:
        if isinstance(event, dict):
            out.extend(_event_quotes(event, sport_key, captured_at, suspect))
    return out


__all__ = [
    "MarketQuote", "quotes_from_aggregate",
    "MONEYLINE", "SPREAD", "TOTAL", "CAPTURED_AT_SUSPECT_WINDOW_SEC",
]
