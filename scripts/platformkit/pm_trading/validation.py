"""validation.py -- the GO-LIVE GATE: multi-week paper-validation harness.

Drives the PaperTrader over many simulated days against a deterministic
scenario, settles every market, and grades the REAL PnLBlotter:
  - net paper P&L (realized settlement P&L - fees), from blotter.summary(),
  - per-market P&L significance (normal-approx lower CI bound > 0?),
  - CLV (close - fill for BUY) in bps, and its positive rate,
  - the forward predictions logged to the REAL ledger (read_ledger reuse).

Verdict:
  PASS  -> net P&L > 0 AND mean CLV > 0 AND P&L lower-CI > 0 AND n >= min_n.
  FAIL  -> enough data but the bar is not cleared (an HONEST success: it means
           do NOT risk capital; nothing fabricated).
  INSUFFICIENT_DATA / NO_TRADES -> not enough to judge.

A PASS here is NECESSARY, NOT SUFFICIENT, for go-live: real capital also
requires the same verdict on the REAL-games forward ledger (run_live) over
multiple weeks, surviving the eval_gate, plus the human checklist. This harness
proves the machinery and the gate logic on a controlled world; it claims no
real edge.
"""
from __future__ import annotations

import math
import pathlib
import sys
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from pnl import PnLBlotter, log_prediction  # noqa: E402
from risk import RiskConfig, RiskManager  # noqa: E402
from run_trader import MarketState, PaperTrader, TraderConfig  # noqa: E402
from venues.base import Level, OrderBook, Side  # noqa: E402
from venues.paper import PaperVenue  # noqa: E402
from scripts.platformkit.execution.venue_fees import fee_polymarket  # noqa: E402

# Polymarket sports taker fee as bps of DOLLAR notional, per execution.venue_fees
# (docs.polymarket.com/trading/fees, retrieved 2026-09-01, Sports feeRate=0.05).
# UNITS: PaperVenue charges fee_bps/1e4 * (qty * price), i.e. bps of dollar
# notional, while fee_polymarket returns dollars for a SHARE count. Dividing by
# the reference price converts per-share dollars -> rate of dollar notional.
# Skipping that division reads 125 bps and undercharges fees by exactly 2x.
# PaperVenue takes only a flat scalar, but the true rate of notional is
# feeRate * (1 - P) -- so this is NOT a worst case: it understates fees below
# P=0.50 (-> 500 bps as P -> 0) and overstates them above it.
_PM_REF_PRICE = 0.50
_POLYMARKET_TAKER_BPS_AT_50 = round(
    fee_polymarket("taker", 1.0, _PM_REF_PRICE) / _PM_REF_PRICE * 1e4, 2)  # 250.0


@dataclass
class SimMarket:
    market_id: str
    true_prob: float
    market_price: float   # tradeable mid now
    close_price: float    # where the line settles (CLV reference)
    model_prob: float     # the model's calibrated number
    event_id: str = ""


@dataclass
class ValidationConfig:
    n_days: int = 20
    markets_per_day: int = 8
    seed: int = 2026
    bankroll: float = 10_000.0
    edge: float = 0.0            # 0 = efficient market (model==line); >0 = model+line informative
    min_edge_bps: float = 50.0
    fee_bps: float = _POLYMARKET_TAKER_BPS_AT_50  # Polymarket taker @ P=0.50, see above
    min_n: int = 30              # minimum traded markets to judge


def _clip(x: float) -> float:
    return float(min(max(x, 0.02), 0.98))


def make_scenario(cfg: ValidationConfig) -> List[List[SimMarket]]:
    rng = np.random.default_rng(cfg.seed)
    days: List[List[SimMarket]] = []
    for d in range(cfg.n_days):
        day: List[SimMarket] = []
        for i in range(cfg.markets_per_day):
            true_p = float(rng.uniform(0.25, 0.75))
            mkt = float(_clip(true_p + rng.normal(0.0, 0.06)))   # noisy line
            gap = true_p - mkt
            model_p = _clip(mkt + cfg.edge * gap)                 # model leans toward truth
            close_p = _clip(mkt + 0.8 * cfg.edge * gap)           # line drifts toward truth
            day.append(SimMarket("D%d-M%d" % (d, i), true_p, mkt, close_p, model_p,
                                 event_id="D%d" % d))
        days.append(day)
    return days


def _book(mid: float, depth: int = 10**6) -> OrderBook:
    return OrderBook("x", bids=(Level(round(mid - 0.005, 4), depth),),
                     asks=(Level(round(mid + 0.005, 4), depth),))


def run_validation(cfg: Optional[ValidationConfig] = None,
                   ledger_dir: Optional[str] = None) -> dict:
    cfg = cfg or ValidationConfig()
    rng = np.random.default_rng(cfg.seed + 1)
    blotter = PnLBlotter(base_dir=tempfile.mkdtemp(prefix="pm_val_"))
    ledger_dir = ledger_dir or tempfile.mkdtemp(prefix="pm_val_led_")
    clv_bps: List[float] = []
    scenario = make_scenario(cfg)
    pred_ts = "2026-06-16T00:00:00+00:00"

    for day in scenario:
        venue = PaperVenue(initial_cash=cfg.bankroll, fee_bps=cfg.fee_bps)
        risk = RiskManager(venue, RiskConfig(
            bankroll_start=cfg.bankroll, max_market_exposure=1e9,
            max_event_exposure=1e9, max_total_exposure=1e9, daily_loss_limit=1e9))
        trader = PaperTrader(venue, risk, blotter,
                             TraderConfig(gate_verdict="BEATS_CLOSE",
                                          min_edge_bps=cfg.min_edge_bps))
        for m in day:
            venue.set_book(OrderBook(m.market_id, bids=_book(m.market_price).bids,
                                     asks=_book(m.market_price).asks))
            log_prediction("sim", "ml", m.market_id, "FIELD", m.model_prob,
                           pred_ts, strategy="validation", base_dir=ledger_dir,
                           game_id=m.market_id)
            fills = trader.step([MarketState(m.market_id, m.model_prob,
                                             event_id=m.event_id)], pred_ts)
            for f in fills:
                cl = (m.close_price - f.price) if f.side == Side.BUY \
                    else (f.price - m.close_price)
                clv_bps.append(cl * 1e4)
            outcome = 1.0 if rng.random() < m.true_prob else 0.0
            blotter.settle_from_venue(venue, m.market_id, outcome, pred_ts)

    return grade(blotter, clv_bps, cfg, ledger_dir)


def grade(blotter: PnLBlotter, clv_bps: List[float], cfg: ValidationConfig,
          ledger_dir: Optional[str] = None) -> dict:
    recs = blotter.read()
    fills = [r for r in recs if r["kind"] == "fill"]
    setts = [r for r in recs if r["kind"] == "settlement"]
    fees_by_m: dict = {}
    for r in fills:
        fees_by_m[r["market_id"]] = fees_by_m.get(r["market_id"], 0.0) + r["fee"]
    per_market = [r["pnl"] - fees_by_m.get(r["market_id"], 0.0) for r in setts
                  if r["market_id"] in {f["market_id"] for f in fills}]
    summ = blotter.summary()
    n = len(per_market)
    arr = np.array(per_market) if n else np.array([0.0])
    mean_pnl = float(arr.mean()) if n else 0.0
    std_pnl = float(arr.std(ddof=1)) if n > 1 else 0.0
    ci_low = mean_pnl - 1.96 * std_pnl / math.sqrt(n) if n > 1 else 0.0
    mean_clv = float(np.mean(clv_bps)) if clv_bps else 0.0
    clv_pos = float(np.mean([1.0 if c > 0 else 0.0 for c in clv_bps])) if clv_bps else 0.0

    n_ledger = 0
    if ledger_dir:
        try:
            from scripts.platformkit.ledger.ledger import read_ledger
            n_ledger = len(read_ledger(base_dir=ledger_dir))
        except Exception:
            n_ledger = 0

    if n == 0:
        verdict = "NO_TRADES"
    elif n < cfg.min_n:
        verdict = "INSUFFICIENT_DATA"
    elif summ["net_paper_pnl"] > 0 and mean_clv > 0 and ci_low > 0:
        verdict = "PASS"
    else:
        verdict = "FAIL"

    return {
        "verdict": verdict,
        "net_paper_pnl": summ["net_paper_pnl"],
        "fees_paid": summ["fees_paid"],
        "n_traded_markets": n,
        "n_fills": summ["n_fills"],
        "pnl_per_market_mean": round(mean_pnl, 4),
        "pnl_ci95_low": round(ci_low, 4),
        "mean_clv_bps": round(mean_clv, 2),
        "clv_positive_rate": round(clv_pos, 4),
        "forward_predictions_logged": n_ledger,
        "note": "PASS is necessary, not sufficient: real go-live also needs the "
                "same verdict on the REAL-games forward ledger over weeks, "
                "surviving the eval_gate, plus HUMAN-CONFIRM. No edge is claimed.",
    }


if __name__ == "__main__":
    for e, label in ((0.0, "EFFICIENT (no edge)"), (0.6, "INFORMATIVE (synthetic edge)")):
        r = run_validation(ValidationConfig(edge=e))
        print("=== scenario: %s ===" % label)
        for k in ("verdict", "net_paper_pnl", "n_traded_markets", "pnl_ci95_low",
                  "mean_clv_bps", "clv_positive_rate", "forward_predictions_logged"):
            print("  %-26s %s" % (k, r[k]))
