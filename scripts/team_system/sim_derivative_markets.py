"""sim_derivative_markets.py — price the OBSCURE / DERIVATIVE market menu from the sim's joint distribution.

The thesis (the open frontier): the point-prediction ceiling does NOT bind the full / JOINT distribution.
One 20k-sim possession run produces the entire joint outcome space, so it can price HUNDREDS of derivative
markets the book models thinly: player tails / alt-lines, double-doubles, triple-doubles, stat combos,
stocks, PRA, 3PM milestones, team derivatives. "What can happen and how often" across the whole menu.

DISCIPLINE / HONESTY (so this is a real frontier, not a fantasy edge):
  * This prints the SIM's probabilities + fair (no-vig) lines. The EDGE = sim_prob vs the book's de-vigged
    prob -- which needs CAPTURED book prices for these obscure markets (absent offline). No edge is claimed;
    first forward CLV Oct-2026.
  * The sim's TAILS are slightly UNDER-dispersed (cov80 ~74-78% raw, ~80% only after the dispersion layer),
    so extreme tail probs (40+, triple-double) are APPROXIMATE and likely CONSERVATIVE -> calibrate before
    pricing tails. Flagged per market.
  * The same-player CROSS-STAT joint is partially modeled (CV_MIN_VAR gap: pts-reb realized +0.2..0.35 vs
    sim ~independent), so COMBO/DD markets are the highest-value-but-needs-calibration cell. Flagged.
  * In-game, re-running this from the LIVE game state IS the in-play exotic pricer (the real-edge frontier).
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import simulate_game_fast  # noqa: E402

DD_STATS = ("pts", "reb", "ast", "stl", "blk")


def fair_odds(p: float) -> str:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return f"{-round(100*p/(1-p)):+d}" if p >= 0.5 else f"{round(100*(1-p)/p):+d}"


def _flag(market: str, p: float) -> str:
    if market.startswith("triple_double") or "40+" in market or "35+" in market:
        return "TAIL (under-dispersed -> approx, likely conservative)"
    if market.startswith("double_double") or "&" in market or market.startswith("pra"):
        return "JOINT (cross-stat corr partially modeled -> CV_MIN_VAR)"
    return "marginal (calibrated q50; tails approx)"


def price_player(name: str, s: dict) -> list:
    pts, reb, ast = s["pts"], s["reb"], s["ast"]
    fg3m = s.get("fg3m", np.zeros_like(pts)); stl = s.get("stl", np.zeros_like(pts)); blk = s.get("blk", np.zeros_like(pts))
    dd_count = sum((s.get(k, np.zeros_like(pts)) >= 10).astype(int) for k in DD_STATS)
    rows = []
    def add(m, mask):
        p = float(np.mean(mask)); rows.append((m, p, fair_odds(p), _flag(m, p)))
    for t in (20, 25, 30, 35, 40):
        add(f"pts {t}+", pts >= t)
    add("reb 10+", reb >= 10); add("reb 15+", reb >= 15)
    add("ast 8+", ast >= 8); add("ast 10+", ast >= 10)
    add("3PM 3+", fg3m >= 3); add("3PM 4+", fg3m >= 4); add("3PM 5+", fg3m >= 5)
    add("stocks 3+ (stl+blk)", (stl + blk) >= 3)
    add("pra 30+ (p+r+a)", (pts + reb + ast) >= 30); add("pra 40+", (pts + reb + ast) >= 40)
    add("pts25 & reb10", (pts >= 25) & (reb >= 10))
    add("20/10/5", (pts >= 20) & (reb >= 10) & (ast >= 5))
    add("double_double", dd_count >= 2)
    add("triple_double", dd_count >= 3)
    return rows


def main():
    ap = argparse.ArgumentParser(description="Sim derivative/obscure market pricer (joint distribution)")
    ap.add_argument("--home", default="NYK"); ap.add_argument("--away", default="SAS")
    ap.add_argument("--nsims", type=int, default=20000); ap.add_argument("--min-pts", type=float, default=10.0)
    a = ap.parse_args()
    h = TeamModel.from_cache(a.home); aw = TeamModel.from_cache(a.away)
    res = simulate_game_fast(h, aw, n_sims=a.nsims, seed=2026, anchor=True, defense=True)
    print("=" * 90)
    print(f"DERIVATIVE / OBSCURE MARKET MENU from the joint sim  ({a.away} @ {a.home}, {a.nsims} sims)")
    print("  sim PROBABILITY + fair no-vig line. EDGE needs book prices (absent offline). Tails approx (under-dispersed).")
    print("=" * 90)
    n_markets = 0
    rows = sorted(res.players.items(), key=lambda x: -x[1]["mean"]["pts"])
    for pid, d in rows:
        if d["mean"]["pts"] < a.min_pts:
            continue
        print(f"\n{d['name']} ({d['team']})  [mean {d['mean']['pts']:.0f} pts]")
        for m, p, odds, flag in price_player(d["name"], d["samples"]):
            if 0.02 < p < 0.985:  # only show markets with a real two-way price
                print(f"   {m:22s} {p*100:5.1f}%  ({odds:>6s})   {flag}")
                n_markets += 1
    # ---- team derivatives ----
    hs, as_ = res.home_total, res.away_total
    print(f"\nTEAM / GAME DERIVATIVES:")
    def team(m, mask):
        nonlocal n_markets
        p = float(np.mean(mask)); n_markets += 1
        print(f"   {m:28s} {p*100:5.1f}%  ({fair_odds(p):>6s})")
    for t in (210, 215, 220, 225):
        team(f"game total over {t}", (hs + as_) > t)
    team(f"{a.home} 110+", hs >= 110); team(f"{a.away} 110+", as_ >= 110)
    team("both teams 105+", (hs >= 105) & (as_ >= 105))
    team(f"{a.home} win by 6+", (hs - as_) >= 6); team(f"{a.away} win by 6+", (as_ - hs) >= 6)
    team("game within 3", np.abs(hs - as_) <= 3)
    print(f"\n  >>> {n_markets} derivative markets priced from ONE sim. "
          f"This is 'what can happen & how often' across the obscure menu.")
    print("  >>> EDGE = sim_prob vs book de-vigged prob (needs captured prices); JOINT/tail cells need calibration first.")
    print("  >>> IN-GAME: re-run this from the live game state = the in-play exotic pricer (the real-edge frontier).")


if __name__ == "__main__":
    main()
