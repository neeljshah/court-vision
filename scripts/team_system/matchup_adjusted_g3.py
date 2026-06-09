"""Matchup-adjusted G3 projection: blend the talent-neutral sim with the NYK-vs-SAS head-to-head.

The possession sim rates teams by SEASON-WIDE quality (SAS is the better defense vs the league). But the
realized NYK-vs-SAS matchup tells a different story: NYK is 3-1, +8.5 avg margin, 2-0 in the Finals
(both road wins), and won the one home meeting by 25. Styles make fights. This shrinks the H2H signal
toward the sim prior and applies it to the sim's margin distribution to get an honest win prob + score.

Method (transparent, small-sample-aware):
  1. take each H2H game's NYK margin, convert to a NYK-HOME basis (+2*HCA for road games, HCA=2.5).
  2. matchup margin = weighted mean of home-equiv margins (playoff games weighted 2x -- most relevant).
  3. shrink the gap (matchup margin - sim median margin) by w = n_eff/(n_eff + K), K=5 (4 games => modest).
  4. shift the sim's 40k-sample margin distribution by delta = w*gap; recompute win prob and score.

  python scripts/team_system/matchup_adjusted_g3.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import simulate_game_fast  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
HCA = 2.5     # home-court advantage in points (league ~2.5)
K = 5.0       # shrinkage strength (4 H2H games -> ~moderate weight)


def main():
    nyk, sas = TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS")
    res = simulate_game_fast(nyk, sas, n_sims=40000, seed=2026, anchor=True, defense=True,
                             context={"neutral_site": False})
    margin = res.home_total - res.away_total          # NYK - SAS, NYK home
    total = res.home_total + res.away_total
    sim_med = float(np.median(margin)); sim_wp = res.home_win_prob

    tg = pd.read_parquet(os.path.join(TS, "team_game.parquet"))
    h = tg[(tg.team == "NYK") & (tg.opp == "SAS")].sort_values("date")
    rows = []
    for r in h.itertuples():
        m = r.pts - r.opp_pts
        home_equiv = m + (2 * HCA if not r.is_home else 0.0)      # convert road -> home basis
        wt = 2.0 if r.kind == "playoff" else 1.0                  # weight the Finals games more
        rows.append((r.date, "HOME" if r.is_home else "AWAY", r.kind, m, home_equiv, wt))
    he = np.array([x[4] for x in rows]); wts = np.array([x[5] for x in rows])
    matchup_margin = float(np.sum(he * wts) / np.sum(wts))        # weighted home-equiv NYK margin
    n_eff = float(np.sum(wts))
    w = n_eff / (n_eff + K)
    gap = matchup_margin - sim_med
    delta = w * gap                                               # how much to shift toward NYK

    adj_margin = margin + delta
    adj_wp = float(np.mean(adj_margin > 0))
    adj_med = float(np.median(adj_margin))
    # split the (unchanged) total by the adjusted margin for a score read
    t_med = float(np.median(total))
    nyk_score = (t_med + adj_med) / 2; sas_score = (t_med - adj_med) / 2

    print("=== NYK-vs-SAS HEAD-TO-HEAD (NYK margin) ===")
    for d, site, kind, m, heq, wt in rows:
        print(f"  {d}  {site:4s} {kind:8s}  NYK {m:+3.0f}   home-equiv {heq:+5.1f}  (weight {wt:.0f})")
    print(f"\n  weighted home-equiv NYK matchup margin: {matchup_margin:+.1f}  (n_eff {n_eff:.0f})")

    print("\n=== TALENT-NEUTRAL SIM (season-wide quality) ===")
    print(f"  NYK win prob {sim_wp:.0%}  |  margin median NYK {sim_med:+.1f}")

    print("\n=== MATCHUP-ADJUSTED (sim + shrunk H2H) ===")
    print(f"  shrink weight on H2H: {w:.0%}  ->  shift {delta:+.1f} toward NYK")
    print(f"  NYK win prob {adj_wp:.0%}  |  margin median NYK {adj_med:+.1f}")
    print(f"  projected score: NYK {nyk_score:.0f}  SAS {sas_score:.0f}")
    print(f"  scenarios: NYK win {adj_wp:.0%} | within 5 {np.mean(np.abs(adj_margin)<=5):.0%} | "
          f"NYK by 10+ {np.mean(adj_margin>=10):.0%} | SAS by 10+ {np.mean(adj_margin<=-10):.0%}")
    lo = float(np.mean(adj_margin > 0))
    # sensitivity: how win prob moves with how much you trust the H2H
    print("\n  sensitivity (trust in H2H matchup):")
    for kk in (10.0, 5.0, 2.0):
        ww = n_eff / (n_eff + kk); dd = ww * gap
        print(f"    K={kk:>4.0f} (weight {ww:.0%}): NYK win {np.mean(margin+dd>0):.0%}  margin NYK {np.median(margin+dd):+.1f}")
    print("\n  read: the talent sim under-rates NYK because it ignores the matchup; NYK has beaten SAS")
    print("  3 of 4 (incl the only home game by 25, + both road Finals games). Honest call below.")


if __name__ == "__main__":
    main()
