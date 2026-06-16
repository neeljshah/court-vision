"""pnl.py -- honest paper P&L + the CLV/calibration record.

Two append-only records, both local-only (gitignored), never a fabricated ROI:

1. PnLBlotter -- a trade blotter (fills + settlements) under data/pm_trading/.
   The prediction ledger has no $ columns, so paper money lives here. Every
   fill carries pred_ts (the decision vintage). Settlement P&L for one binary
   YES contract = net_qty * (resolution - avg_price). summary() reports net
   paper P&L = realized settlement P&L - fees. That is the bottom line that
   must go positive on FORWARD paper before any real-capital conversation.

2. log_prediction() -- forwards the calibrated fair_prob to the REAL prediction
   ledger (scripts/platformkit/ledger, read-only reuse) so the model's number
   is graded for CLV vs the devigged close. capture_forward() drives the
   forward_capture CLV clock. No edge is claimed; the gate + this record decide.
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Dict, List, Optional

_ROOT = pathlib.Path(__file__).resolve().parents[3]  # repo root
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from .venues.base import Fill, MarketVenue, Side
except ImportError:  # pragma: no cover  (flat import for hermetic tests)
    from venues.base import Fill, MarketVenue, Side  # type: ignore

_DEFAULT_DIR = _ROOT / "data" / "pm_trading"


class PnLBlotter:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self.path = pathlib.Path(base_dir) if base_dir else _DEFAULT_DIR
        self.path.mkdir(parents=True, exist_ok=True)
        self.file = self.path / "blotter.jsonl"

    def _append(self, record: dict) -> None:
        with open(self.file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")

    def record_fill(self, fill: Fill, pred_ts: str = "",
                    strategy: str = "") -> None:
        self._append({
            "kind": "fill", "ts": fill.ts, "pred_ts": pred_ts,
            "strategy": strategy, "market_id": fill.market_id,
            "side": fill.side.value, "qty": int(fill.qty),
            "price": float(fill.price), "fee": float(fill.fee),
        })

    def record_settlement(self, market_id: str, resolution: float,
                          net_qty: int, avg_price: float,
                          pred_ts: str = "") -> float:
        """resolution in {0.0, 1.0} (YES=1). Returns settlement P&L ($)."""
        pnl = round(net_qty * (resolution - avg_price), 6)
        self._append({
            "kind": "settlement", "pred_ts": pred_ts, "market_id": market_id,
            "resolution": float(resolution), "net_qty": int(net_qty),
            "avg_price": float(avg_price), "pnl": pnl,
        })
        return pnl

    def settle_from_venue(self, venue: MarketVenue, market_id: str,
                          resolution: float, pred_ts: str = "") -> float:
        pos = venue.get_positions().get(market_id)
        if pos is None or pos.net_qty == 0:
            return 0.0
        return self.record_settlement(market_id, resolution, pos.net_qty,
                                      pos.avg_price, pred_ts)

    def read(self) -> List[dict]:
        if not self.file.exists():
            return []
        with open(self.file, "r", encoding="utf-8") as fh:
            return [json.loads(ln) for ln in fh if ln.strip()]

    def summary(self) -> dict:
        recs = self.read()
        fills = [r for r in recs if r["kind"] == "fill"]
        setts = [r for r in recs if r["kind"] == "settlement"]
        fees = round(sum(r["fee"] for r in fills), 6)
        realized = round(sum(r["pnl"] for r in setts), 6)
        settled = {r["market_id"] for r in setts}
        open_markets = {r["market_id"] for r in fills} - settled
        return {
            "n_fills": len(fills),
            "gross_notional": round(sum(r["qty"] * r["price"] for r in fills), 6),
            "fees_paid": fees,
            "realized_settlement_pnl": realized,
            "net_paper_pnl": round(realized - fees, 6),
            "n_settled_markets": len(settled),
            "n_open_markets": len(open_markets),
        }


def log_prediction(sport: str, market: str, home: str, away: str,
                   fair_prob: float, pred_ts: str, layer: str = "pregame",
                   strategy: str = "", base_dir: Optional[str] = None,
                   **kw) -> str:
    """Forward the calibrated prob to the REAL prediction ledger for CLV
    grading (reuse). Returns the ledger pred_id."""
    from scripts.platformkit.ledger.ledger import append_prediction  # lazy reuse
    inputs = dict(kw.pop("inputs", {}))
    inputs.setdefault("strategy", strategy)
    return append_prediction(sport, layer, market, home, away, fair_prob,
                             inputs, pred_ts, base_dir=base_dir, **kw)


def capture_forward(predictions, quotes=None, **kw) -> dict:
    """Drive the forward_capture CLV clock (reuse). Returns its tick summary."""
    from scripts.platformkit.forward_capture.run_capture import run_tick  # lazy
    return run_tick(predictions=predictions, quotes=quotes, **kw)
