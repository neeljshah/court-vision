"""projection.py -- ASSUMPTION-DRIVEN summer P&L scenario tool (NOT measured).

*** THIS IS A SCENARIO PROJECTION, NOT A MEASURED OR CLAIMED EDGE. ***
No real money has been placed; no live exchange feed exists yet. This Monte
Carlo turns EXPLICIT, SOURCED assumptions into a P&L DISTRIBUTION for a
$100k bankroll over a ~12-week summer on Kalshi/Polymarket. Every input is
stated; change them and re-run. The honest result is near-flat with real
downside -- this file exists to show that quantitatively, not to promise ROI.

INPUT SOURCES (2026-06-16):
  - Model edge (measured, leak-free): summer sports (MLB/tennis/World-Cup
    soccer) MATCH the devigged close -> pregame edge ~0 to -5% after vig.
    The one durable edge (NBA AST +5%) is regular-season-only => NOT summer.
  - Venue research (see execution/venue_fees.py; both fees are PARABOLIC in
    price, quoted here at P=0.50): Kalshi taker 1.75c/contract = 3.5% of the
    $0.50 dollar notional; Polymarket sports 5% feeRate = 1.25c/share = 2.5%
    of dollar notional (July 2026 rate) / 0% maker. Per-contract cents and
    percent-of-notional differ by a factor of 1/P -- do not mix them.
    Capacity is the binding wall: ~1% of
    markets tradeable at size; arb captures ~$100-$2k/episode, seconds-long,
    ~6% of events co-listed; deep mainlines are efficient.
Fees are folded into the NET edge means below.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

WEEKS = 12
BANKROLL = 100_000.0
# risk-free benchmark: ~4.5%/yr T-bills over 12/52 of a year
RISK_FREE = BANKROLL * 0.045 * (WEEKS / 52.0)


@dataclass
class Scenario:
    name: str
    # cross-market arb (capital often locked to resolution)
    arb_opps_per_wk: float          # Poisson mean
    arb_cap_per_opp: float          # $ capturable before edge closes
    arb_edge_mean: float            # net of fees, per opp
    arb_edge_sd: float              # can go negative (one leg fills, other slips)
    # market making (capture half-spread minus adverse selection)
    mm_deployed: float              # $ inventory working
    mm_ret_mean: float              # weekly return on deployed
    mm_ret_sd: float
    # model-vs-market (summer sports: edge ~0/neg after vig)
    mvm_deployed: float             # $ at risk
    mvm_ret_mean: float             # weekly return on deployed
    mvm_ret_sd: float


SCENARIOS: List[Scenario] = [
    Scenario("BEAR  (realistic-pessimistic)",
             arb_opps_per_wk=1.0, arb_cap_per_opp=300.0,
             arb_edge_mean=0.008, arb_edge_sd=0.020,
             mm_deployed=2_000.0, mm_ret_mean=-0.001, mm_ret_sd=0.010,
             mvm_deployed=2_000.0, mvm_ret_mean=-0.004, mvm_ret_sd=0.030),
    Scenario("BASE  (most likely)",
             arb_opps_per_wk=2.5, arb_cap_per_opp=800.0,
             arb_edge_mean=0.012, arb_edge_sd=0.025,
             mm_deployed=6_000.0, mm_ret_mean=0.002, mm_ret_sd=0.012,
             mvm_deployed=5_000.0, mvm_ret_mean=-0.001, mvm_ret_sd=0.035),
    Scenario("BULL  (optimistic, everything works)",
             arb_opps_per_wk=6.0, arb_cap_per_opp=1_800.0,
             arb_edge_mean=0.015, arb_edge_sd=0.030,
             mm_deployed=15_000.0, mm_ret_mean=0.005, mm_ret_sd=0.015,
             mvm_deployed=12_000.0, mvm_ret_mean=0.003, mvm_ret_sd=0.040),
]


def simulate(sc: Scenario, n_sims: int, rng: np.random.Generator) -> np.ndarray:
    """Return array of total summer P&L ($) across n_sims paths."""
    pnl = np.zeros(n_sims)
    for _ in range(WEEKS):
        # arb: random # of opps each week, each with a noisy net edge
        opps = rng.poisson(sc.arb_opps_per_wk, n_sims)
        max_o = int(opps.max()) if opps.max() > 0 else 0
        arb_wk = np.zeros(n_sims)
        if max_o > 0:
            edges = rng.normal(sc.arb_edge_mean, sc.arb_edge_sd, (n_sims, max_o))
            mask = np.arange(max_o)[None, :] < opps[:, None]
            arb_wk = (edges * mask).sum(axis=1) * sc.arb_cap_per_opp
        mm_wk = rng.normal(sc.mm_ret_mean, sc.mm_ret_sd, n_sims) * sc.mm_deployed
        mvm_wk = rng.normal(sc.mvm_ret_mean, sc.mvm_ret_sd, n_sims) * sc.mvm_deployed
        pnl += arb_wk + mm_wk + mvm_wk
    return pnl


def _pct(a: np.ndarray, p: float) -> float:
    return float(np.percentile(a, p))


def run(n_sims: int = 200_000) -> Dict[str, dict]:
    rng = np.random.default_rng(2026)
    out: Dict[str, dict] = {}
    print("=" * 74)
    print("SUMMER P&L SCENARIO PROJECTION  (ASSUMPTION-DRIVEN, NOT MEASURED)")
    print("bankroll $%s | %d weeks | risk-free benchmark ~$%.0f (T-bills)"
          % (format(int(BANKROLL), ","), WEEKS, RISK_FREE))
    print("=" * 74)
    hdr = "%-38s %9s %9s %9s %9s" % ("scenario", "p5", "median", "mean", "p95")
    print(hdr)
    print("-" * 74)
    for sc in SCENARIOS:
        pnl = simulate(sc, n_sims, rng)
        d = {
            "p5": _pct(pnl, 5), "p25": _pct(pnl, 25), "median": _pct(pnl, 50),
            "mean": float(pnl.mean()), "p75": _pct(pnl, 75), "p95": _pct(pnl, 95),
            "p_profit": float((pnl > 0).mean()),
            "p_beat_rf": float((pnl > RISK_FREE).mean()),
            "p_lose_5pct": float((pnl < -0.05 * BANKROLL).mean()),
        }
        out[sc.name] = d
        print("%-38s %9.0f %9.0f %9.0f %9.0f"
              % (sc.name, d["p5"], d["median"], d["mean"], d["p95"]))
    print("-" * 74)
    print("%-38s %8s %8s %8s" % ("scenario", "P(gain)", "P(>RF)", "P(<-5%)"))
    for sc in SCENARIOS:
        d = out[sc.name]
        print("%-38s %7.0f%% %7.0f%% %7.0f%%"
              % (sc.name, 100 * d["p_profit"], 100 * d["p_beat_rf"],
                 100 * d["p_lose_5pct"]))
    print("=" * 74)
    print("Return % on $100k = P&L / 1000. Even BULL mean is a low-single-digit")
    print("% of bankroll: capacity caps absolute $, not the bankroll. Doing")
    print("nothing (T-bills) earns ~$%.0f risk-free over the same window." % RISK_FREE)
    print("All edges UNVALIDATED -- forward paper P&L + the gate decide reality.")
    return out


if __name__ == "__main__":
    run()
