"""risk.py -- the gate EVERY strategy order must pass through.

Nothing reaches a venue except via RiskManager.approve(). It enforces, in
order: global live-trading flag (ENABLED, default OFF -> live venues blocked,
paper always allowed), halt state, fractional-Kelly sizing (<= 1/4), a
correlation haircut, and per-market / per-event / total max-loss exposure
caps. A drawdown OR daily-loss breach trips the kill-switch: flatten every
position and halt all new entries until manually reset.

Single source of truth: the drawdown threshold, the quarter-Kelly fraction,
and the absolute Kelly cap are IMPORTED from src/prediction/betting_portfolio
(read-only) -- never re-implemented here, so they cannot drift.

Binary-contract Kelly (price m in [0,1], payoff $1):
  BUY  YES: f* = (p - m) / (1 - m), risk/contract = m
  SELL YES: f* = (m - p) / m,       risk/contract = (1 - m)
Applied fraction = clamp(f* * KELLY_FRACTION * (1 - corr), 0, KELLY_PCT_MAX).
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

_ROOT = pathlib.Path(__file__).resolve().parents[3]  # repo root
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from src.prediction.betting_portfolio import (  # noqa: E402  (real guard, not a stub)
    KELLY_FRACTION,
    KELLY_PCT_MAX,
    check_drawdown_ok,
)

try:
    from .venues.base import MarketVenue, Order, OrderType, Side
except ImportError:  # pragma: no cover  (flat sibling import for hermetic tests)
    from venues.base import MarketVenue, Order, OrderType, Side  # type: ignore


@dataclass
class RiskConfig:
    bankroll_start: float
    kelly_fraction: float = KELLY_FRACTION         # quarter-Kelly (0.25)
    max_market_exposure: float = 2_000.0           # $ max-loss per market
    max_event_exposure: float = 5_000.0            # $ max-loss per event
    max_total_exposure: float = 20_000.0           # $ max-loss across book
    daily_loss_limit: float = 2_000.0              # halt if day P&L <= -this
    enabled: bool = False                          # LIVE flag; paper ignores it


def kelly_fraction_binary(fair_prob: float, price: float, side: Side,
                          corr: float = 0.0,
                          kelly_fraction: float = KELLY_FRACTION) -> float:
    """Fractional-Kelly fraction-of-bankroll-at-risk for one binary contract.

    Returns 0.0 when there is no positive edge on the requested side. The
    result is correlation-haircut and hard-clamped to KELLY_PCT_MAX (0.25).
    """
    if not (0.0 < price < 1.0) or not (0.0 <= fair_prob <= 1.0):
        return 0.0
    if side == Side.BUY:
        f_full = (fair_prob - price) / (1.0 - price)
    else:
        f_full = (price - fair_prob) / price
    if f_full <= 0.0:
        return 0.0
    corr = min(max(corr, 0.0), 1.0)
    frac = f_full * kelly_fraction * (1.0 - corr)
    return float(min(max(frac, 0.0), KELLY_PCT_MAX))


def _risk_per_contract(price: float, side: Side) -> float:
    return price if side == Side.BUY else (1.0 - price)


class RiskManager:
    def __init__(self, venue: MarketVenue, config: RiskConfig) -> None:
        self.venue = venue
        self.cfg = config
        self.halted = False
        self.halt_reason = ""
        self._day_start_equity = config.bankroll_start
        self._market_event: Dict[str, str] = {}  # market_id -> event_id

    # -- equity / exposure ----------------------------------------------
    def equity(self) -> float:
        eq = self.venue.get_balance().cash
        for m, pos in self.venue.get_positions().items():
            mark = self.venue.get_price(m)
            if mark is None:
                mark = pos.avg_price
            eq += pos.net_qty * mark
        return round(eq, 6)

    def market_exposure(self, market_id: str) -> float:
        pos = self.venue.get_positions().get(market_id)
        if pos is None or pos.net_qty == 0:
            return 0.0
        side = Side.BUY if pos.net_qty > 0 else Side.SELL
        return abs(pos.net_qty) * _risk_per_contract(pos.avg_price, side)

    def event_exposure(self, event_id: str) -> float:
        return sum(self.market_exposure(m) for m, e in self._market_event.items()
                   if e == event_id)

    def total_exposure(self) -> float:
        return sum(self.market_exposure(m) for m in self.venue.get_positions())

    # -- kill switch -----------------------------------------------------
    def start_day(self) -> None:
        """Reset the daily P&L reference (call at the start of each session)."""
        self._day_start_equity = self.equity()

    def check_kill_switch(self) -> bool:
        """Return True if the kill-switch is (or just became) tripped."""
        if self.halted:
            return True
        eq = self.equity()
        if not check_drawdown_ok(self.cfg.bankroll_start, eq):
            self._trip("drawdown > MAX_DRAWDOWN_PCT")
            return True
        if eq <= self._day_start_equity - self.cfg.daily_loss_limit:
            self._trip("daily loss limit hit")
            return True
        return False

    def _trip(self, reason: str) -> None:
        self.halted = True
        self.halt_reason = reason
        self.flatten()

    def flatten(self) -> int:
        """Close every open position with MARKET orders. Returns # flattened."""
        n = 0
        for m, pos in list(self.venue.get_positions().items()):
            if pos.net_qty == 0:
                continue
            side = Side.SELL if pos.net_qty > 0 else Side.BUY
            self.venue.place_order(
                Order(market_id=m, side=side, qty=abs(pos.net_qty),
                      order_type=OrderType.MARKET))
            n += 1
        return n

    def reset(self) -> None:
        self.halted = False
        self.halt_reason = ""

    # -- the approval gate ----------------------------------------------
    def _enter_ok(self) -> bool:
        """Halt + global-ENABLED + live-venue checks shared by every entry."""
        if self.check_kill_switch():
            self.last_block_reason = "halted: " + self.halt_reason
            return False
        if self.venue.is_live() and not (self.cfg.enabled and _global_enabled()):
            self.last_block_reason = "live trading disabled (ENABLED OFF)"
            return False
        return True

    def _apply_caps(self, market_id: str, side: Side, price: float,
                    want: int, event_id: str) -> int:
        """Trim a desired qty to per-market/event/total max-loss headroom."""
        rpc = _risk_per_contract(price, side)
        if rpc <= 0.0:
            self.last_block_reason = "degenerate price"
            return 0
        if event_id:
            self._market_event[market_id] = event_id
        caps = [
            (self.cfg.max_market_exposure - self.market_exposure(market_id), "market"),
            (self.cfg.max_total_exposure - self.total_exposure(), "total"),
        ]
        if event_id:
            caps.append((self.cfg.max_event_exposure - self.event_exposure(event_id),
                         "event"))
        for headroom, label in caps:
            allowed = int(max(headroom, 0.0) / rpc + 1e-9)
            if allowed < want:
                want = allowed
                self.last_block_reason = "capped by %s exposure" % label
        return max(want, 0)

    def cap_quantity(self, market_id: str, side: Side, price: float,
                     want: int, event_id: str = "") -> int:
        """Risk-check a NON-Kelly desired size (arb / market-making quotes):
        applies halt/ENABLED/exposure caps only. Returns approved int >= 0."""
        self.last_block_reason = ""
        if want <= 0:
            return 0
        if not self._enter_ok():
            return 0
        return self._apply_caps(market_id, side, price, int(want), event_id)

    def approve(self, market_id: str, side: Side, fair_prob: float, price: float,
                event_id: str = "", corr: float = 0.0,
                limit_price: Optional[float] = None) -> Optional[Order]:
        """Kelly-size + risk-check a desired trade. Returns a risk-checked
        Order or None when blocked (reason via last_block_reason)."""
        self.last_block_reason = ""
        if not self._enter_ok():
            return None
        frac = kelly_fraction_binary(fair_prob, price, side, corr,
                                     self.cfg.kelly_fraction)
        if frac <= 0.0:
            self.last_block_reason = "no positive edge / zero Kelly"
            return None
        rpc = _risk_per_contract(price, side)
        if rpc <= 0.0:
            self.last_block_reason = "degenerate price"
            return None
        # +eps absorbs float noise (e.g. 0.05*10000 == 499.999...) so a clean
        # integer count doesn't round down to N-1.
        want = int((frac * self.cfg.bankroll_start) / rpc + 1e-9)
        want = self._apply_caps(market_id, side, price, want, event_id)
        if want <= 0:
            if not self.last_block_reason:
                self.last_block_reason = "exposure cap leaves no room"
            return None
        return Order(market_id=market_id, side=side, qty=want,
                     order_type=OrderType.LIMIT if limit_price is not None
                     else OrderType.MARKET, limit_price=limit_price)


def _global_enabled() -> bool:
    """Read the package-level live kill flag at call time (default OFF)."""
    try:
        from . import ENABLED  # type: ignore
    except ImportError:  # pragma: no cover
        try:
            import __init__ as pkg  # type: ignore
            return bool(getattr(pkg, "ENABLED", False))
        except Exception:
            return False
    return bool(ENABLED)
