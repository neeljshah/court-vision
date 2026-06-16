"""model_vs_market -- trade our calibrated prob vs the exchange price.

GATE-GATED, honestly: this strategy emits orders ONLY when the eval_gate
verdict for the relevant corpus is BEATS_CLOSE. If the gate says MATCHES_CLOSE
or BEHIND (which is the measured truth on every summer-sport slice today), it
emits NOTHING -- we do not trade a model that has not been proven to beat the
close. This is the no-edge-claims rail expressed as code.

When it does fire, each contract is sized by RiskManager.approve (fractional
Kelly + exposure caps), using the Signal's calibrated fair_prob vs price.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

try:
    from ..risk import RiskManager
    from ..edge_signal import Signal
    from .base import Strategy, TradeIntent
except ImportError:  # pragma: no cover
    from risk import RiskManager  # type: ignore
    from edge_signal import Signal  # type: ignore
    from base import Strategy, TradeIntent  # type: ignore

# Only this gate verdict authorizes model-vs-market trading.
GATE_TRADE_VERDICTS = frozenset({"BEATS_CLOSE"})


class ModelVsMarket(Strategy):
    def __init__(self, risk: RiskManager, gate_verdict: str,
                 min_edge_bps: float = 0.0,
                 require_consensus: bool = True) -> None:
        self.risk = risk
        self.gate_verdict = str(gate_verdict)
        self.min_edge_bps = float(min_edge_bps)
        self.require_consensus = require_consensus
        self.last_skip_reason = ""

    @property
    def name(self) -> str:
        return "model_vs_market"

    def gate_open(self) -> bool:
        return self.gate_verdict in GATE_TRADE_VERDICTS

    def evaluate(self, signals: Sequence[Signal],
                 event_ids: Optional[Dict[str, str]] = None) -> List[TradeIntent]:
        if not self.gate_open():
            self.last_skip_reason = "gate verdict %r != BEATS_CLOSE" % self.gate_verdict
            return []
        event_ids = event_ids or {}
        out: List[TradeIntent] = []
        for s in signals:
            if abs(s.edge_bps) < self.min_edge_bps:
                continue
            if self.require_consensus and not s.agrees_with_consensus():
                continue  # model fights the devigged book -> skip (yellow flag)
            order = self.risk.approve(s.market_id, s.side, s.fair_prob,
                                      s.market_price,
                                      event_id=event_ids.get(s.market_id, ""))
            if order is not None:
                out.append(TradeIntent(self.risk.venue, order,
                                       "edge_bps=%.0f" % s.edge_bps))
        return out
