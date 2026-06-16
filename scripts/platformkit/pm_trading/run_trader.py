"""run_trader.py -- the PAPER trading daemon (the whole system, wired).

Each tick: poll venue books -> build edge signals -> run the enabled strategies
(model_vs_market gate-gated, market_maker, cross_market_arb) -> the RiskManager
sizes/approves -> BestExecution works the orders -> fills + the kill-switch are
logged to the PnLBlotter. Loops until the feed is exhausted, max_ticks is hit,
or the kill-switch halts it.

*** PAPER MODE. Default venue is PaperVenue; pm_trading.ENABLED is OFF, so even
    a real venue is blocked by risk.py. Going live requires wiring real keys AND
    a HUMAN-CONFIRM after a positive multi-week forward PAPER P&L + CLV record
    that survives the eval_gate. This daemon NEVER places a real order. ***
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional, Sequence

try:
    from .edge_signal import build_signal
    from .execution import BestExecution, ExecConfig
    from .pnl import PnLBlotter
    from .risk import RiskManager
    from .strategies import CrossMarketArb, MarketMaker, ModelVsMarket
    from .venues.base import MarketVenue, OrderType, Side
except ImportError:  # pragma: no cover  (flat import for hermetic tests)
    from edge_signal import build_signal  # type: ignore
    from execution import BestExecution, ExecConfig  # type: ignore
    from pnl import PnLBlotter  # type: ignore
    from risk import RiskManager  # type: ignore
    from strategies import CrossMarketArb, MarketMaker, ModelVsMarket  # type: ignore
    from venues.base import MarketVenue, OrderType, Side  # type: ignore

BANNER = (
    "=" * 70 + "\n"
    "  PM-TRADING DAEMON -- PAPER MODE\n"
    "  This is a SIMULATION. No real keys, no real orders, no real money.\n"
    "  WIRE KEYS + HUMAN-CONFIRM (after positive forward paper P&L + CLV\n"
    "  that survives the eval_gate) TO GO LIVE. ENABLED is OFF.\n"
    + "=" * 70
)


@dataclass
class MarketState:
    market_id: str
    fair_prob: float
    devig_prob: Optional[float] = None
    event_id: str = ""
    half_spread: float = 0.02


@dataclass
class TraderConfig:
    use_model_vs_market: bool = True
    use_market_maker: bool = False
    use_arb: bool = False
    gate_verdict: str = "MATCHES_CLOSE"   # model_vs_market trades ONLY on BEATS_CLOSE
    min_edge_bps: float = 50.0
    mm_base_qty: int = 100
    exec_config: ExecConfig = field(default_factory=ExecConfig)


class PaperTrader:
    def __init__(self, venue: MarketVenue, risk: RiskManager, blotter: PnLBlotter,
                 config: Optional[TraderConfig] = None,
                 venue_b: Optional[MarketVenue] = None,
                 risk_b: Optional[RiskManager] = None) -> None:
        self.venue = venue
        self.risk = risk
        self.blotter = blotter
        self.cfg = config or TraderConfig()
        self.venue_b = venue_b
        self.risk_b = risk_b
        self.execer = BestExecution(self.cfg.exec_config)
        self.halted = False
        self.tick_count = 0
        self.mvm = ModelVsMarket(risk, self.cfg.gate_verdict, self.cfg.min_edge_bps)
        self.mm = MarketMaker(risk, base_qty=self.cfg.mm_base_qty)
        self.arb = CrossMarketArb()

    def banner(self) -> str:
        return BANNER

    def _fill_intent(self, intent, pred_ts: str) -> list:
        order = intent.order
        if order.order_type == OrderType.MARKET:
            rep = self.execer.execute(intent.venue, order)
            fills = rep.fills
        else:
            placed = intent.venue.place_order(order)
            fills = [f for f in intent.venue.get_fills()
                     if f.order_id == placed.order_id]
        for f in fills:
            self.blotter.record_fill(f, pred_ts, intent.note)
        return fills

    def step(self, states: Sequence[MarketState], pred_ts: str = "") -> List:
        if self.halted or self.risk.check_kill_switch():
            self.halted = True
            return []
        fills: List = []
        if self.cfg.use_model_vs_market:
            sigs, evmap = [], {}
            for s in states:
                price = self.venue.get_price(s.market_id)
                if price is None:
                    continue
                sigs.append(build_signal(s.market_id, s.fair_prob, price, s.devig_prob))
                evmap[s.market_id] = s.event_id
            for intent in self.mvm.evaluate(sigs, evmap):
                fills += self._fill_intent(intent, pred_ts)
        if self.cfg.use_market_maker:
            for s in states:
                for intent in self.mm.evaluate(s.market_id, s.fair_prob,
                                               s.half_spread, s.event_id):
                    fills += self._fill_intent(intent, pred_ts)
        if self.cfg.use_arb and self.venue_b is not None and self.risk_b is not None:
            for s in states:
                for intent in self.arb.evaluate(self.venue, self.venue_b,
                                                s.market_id, self.risk, self.risk_b,
                                                s.event_id):
                    fills += self._fill_intent(intent, pred_ts)
        self.tick_count += 1
        if self.risk.check_kill_switch():
            self.halted = True
        return fills

    def run(self, feed: Iterable, max_ticks: int = 0, verbose: bool = True) -> dict:
        """feed yields (states, pred_ts). Stops on exhaustion / max_ticks / halt."""
        if verbose:
            print(self.banner())
        total = 0
        for i, (states, pred_ts) in enumerate(feed):
            if self.halted or (max_ticks and i >= max_ticks):
                break
            total += len(self.step(states, pred_ts))
            if self.halted:
                if verbose:
                    print("HALTED: %s" % self.risk.halt_reason)
                break
        summary = self.blotter.summary()
        summary["ticks"] = self.tick_count
        summary["total_fills_this_run"] = total
        summary["halted"] = self.halted
        return summary


def _demo() -> dict:
    """Deterministic end-to-end paper demo (no keys, no network)."""
    import tempfile
    try:
        from .pnl import PnLBlotter as _B
        from .risk import RiskConfig as _C, RiskManager as _RM
        from .venues.base import Level as _L, OrderBook as _OB
        from .venues.paper import PaperVenue as _PV
    except ImportError:
        from pnl import PnLBlotter as _B  # type: ignore
        from risk import RiskConfig as _C, RiskManager as _RM  # type: ignore
        from venues.base import Level as _L, OrderBook as _OB  # type: ignore
        from venues.paper import PaperVenue as _PV  # type: ignore

    venue = _PV(initial_cash=100_000.0)
    venue.set_book(_OB("NBA-BOS-YES", bids=((_L(0.495, 10**6)),),
                       asks=(_L(0.505, 10**6),)))
    risk = _RM(venue, _C(bankroll_start=100_000.0))
    blotter = _B(base_dir=tempfile.mkdtemp(prefix="pm_demo_"))
    # gate_verdict default MATCHES_CLOSE -> model_vs_market HONESTLY stands down;
    # flip to BEATS_CLOSE only to show the wiring fire on a synthetic edge.
    trader = PaperTrader(venue, risk, blotter,
                         TraderConfig(gate_verdict="BEATS_CLOSE", min_edge_bps=50.0))
    feed = [([MarketState("NBA-BOS-YES", 0.55, devig_prob=0.54)], "t%d" % i)
            for i in range(5)]
    return trader.run(feed, verbose=True)


if __name__ == "__main__":
    s = _demo()
    print("PAPER RUN SUMMARY (synthetic edge, demo only -- NOT a real result):")
    for k in ("ticks", "total_fills_this_run", "n_fills", "gross_notional",
              "fees_paid", "realized_settlement_pnl", "net_paper_pnl", "halted"):
        print("  %-24s %s" % (k, s.get(k)))
