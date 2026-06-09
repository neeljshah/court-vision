"""Full predicted BOX SCORE + game-scenario report for the next Finals game (default G3 SAS @ NYK).

Runs the GPU possession Monte Carlo (recency-weighted, defense-adjusted, dispersion-calibrated, anchored)
and prints a complete predicted box score for both teams -- per player MIN/PTS/REB/AST/STL/BLK/TO and
FG-3P-FT -- plus the game-outcome distribution: win prob, projected score, margin & total ranges, and
scenario probabilities. Box-score counting stats use the simulated MEAN; ranges use sim quantiles.

  python scripts/team_system/g3_boxscore.py --home NYK --away SAS --nsims 40000
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import device, simulate_game_fast  # noqa: E402

ASC = lambda s: str(s).encode("ascii", "replace").decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default="NYK"); ap.add_argument("--away", default="SAS")
    ap.add_argument("--nsims", type=int, default=40000)
    a = ap.parse_args()
    home, away = TeamModel.from_cache(a.home), TeamModel.from_cache(a.away)
    res = simulate_game_fast(home, away, n_sims=a.nsims, seed=2026, anchor=True, defense=True,
                             context={"neutral_site": False})
    hs, as_ = res.home_total, res.away_total
    wp = res.home_win_prob
    margin = hs - as_; total = hs + as_

    print(f"=== PREDICTED BOX SCORE: {a.away} @ {a.home}  ({a.nsims} sims, device {device()}) ===\n")

    def boxtable(tri):
        rows = [(p, d) for p, d in res.players.items() if d["team"] == tri]
        rows.sort(key=lambda x: -x[1]["mean"]["pts"])
        print(f"  {tri}")
        print(f"  {'player':20s} {'MIN':>4s} {'PTS':>4s} {'REB':>4s} {'AST':>4s} {'STL':>3s} {'BLK':>3s} "
              f"{'TO':>3s} {'FG':>9s} {'3P':>8s} {'FT':>8s}")
        tp = tr = ta = 0.0
        for p, d in rows:
            m = d["mean"]; rb = d["reb_mean"]
            if m["pts"] < 2 and rb < 2:
                continue
            mn = (home if tri == a.home else away).rate[p].get("mpg_rec") or (home if tri == a.home else away).rate[p].get("mpg", 0)
            tp += m["pts"]; tr += rb; ta += m["ast"]
            print(f"  {ASC(d['name']):20s} {mn:4.0f} {m['pts']:4.0f} {rb:4.1f} {m['ast']:4.1f} {m['stl']:3.1f} "
                  f"{m['blk']:3.1f} {m['tov']:3.1f} {m['fgm']:4.1f}-{m['fga']:<4.1f} {m['fg3m']:3.1f}-{m['fg3a']:<3.1f} "
                  f"{m['ftm']:3.1f}-{m['fta']:<3.1f}")
        print(f"  {'TEAM':20s} {'':>4s} {tp:4.0f} {tr:4.0f} {ta:4.0f}\n")

    boxtable(a.away); boxtable(a.home)

    print("=== GAME OUTCOME ===")
    print(f"  win prob:   {a.home} {wp:.0%}  /  {a.away} {1 - wp:.0%}")
    print(f"  projected:  {a.home} {np.median(hs):.0f}  {a.away} {np.median(as_):.0f}  "
          f"(median spread {a.home} {np.median(margin):+.1f})")
    print(f"  score range (q25-q75): {a.home} {np.quantile(hs,.25):.0f}-{np.quantile(hs,.75):.0f}  "
          f"{a.away} {np.quantile(as_,.25):.0f}-{np.quantile(as_,.75):.0f}")
    print(f"  margin     q10/q50/q90 ({a.home}): {np.quantile(margin,.1):+.0f} / {np.median(margin):+.0f} / {np.quantile(margin,.9):+.0f}")
    print(f"  total      q10/q50/q90: {np.quantile(total,.1):.0f} / {np.median(total):.0f} / {np.quantile(total,.9):.0f}  "
          f"(note: total runs ~high; trust spread/win-prob)")
    print(f"\n  scenarios:")
    print(f"    {a.home} wins by 10+: {np.mean(margin >= 10):.0%}   {a.away} wins by 10+: {np.mean(margin <= -10):.0%}")
    print(f"    game within 5 pts:   {np.mean(np.abs(margin) <= 5):.0%}   {a.home} wins close (1-5): {np.mean((margin>0)&(margin<=5)):.0%}")
    print(f"    if {a.home} wins, series 3-0 (sweep watch): {wp:.0%} this game")


if __name__ == "__main__":
    main()
