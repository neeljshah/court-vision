"""DEEP GAME REPORT — the most in-depth single-game prediction the stack can produce.

Runs the full possession MC (anchored marginals, on-court defense, ft_force, tov_force, size-matchup,
assist network, recency, count-stat NB calibration, dispersion) at high N + the clock-aware engine for the
trajectory, and dumps EVERYTHING: full predicted box score (every rotation player, every stat, with
q10/q50/q90 ranges + minutes), team totals/spread/win-prob/projected final, milestone probabilities
(P(20/25/30+), double-double, triple-double), the quarter-by-quarter trajectory (lead changes, largest lead,
comeback, halftime), and the team-total uncertainty. One coherent sim prices the whole picture.

  python scripts/team_system/deep_game_report.py --home NYK --away SAS --nsims 40000
"""
from __future__ import annotations
import argparse, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import simulate_game_fast, device  # noqa: E402
from sim.game_clock_sim import simulate_clock  # noqa: E402

TS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "cache", "team_system")
ASC = lambda s: str(s).encode("ascii", "replace").decode()
import pandas as pd


def _mpg(home, away):
    m = {}
    try:
        rec = pd.read_parquet(os.path.join(TS, "recency_rates.parquet")).set_index("pid")["mpg_rec"].to_dict()
    except Exception:
        rec = {}
    for tm in (home, away):
        for p in tm.rate:
            m[p] = rec.get(p, tm.rate[p].get("mpg", 0) or 0)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default="NYK"); ap.add_argument("--away", default="SAS")
    ap.add_argument("--nsims", type=int, default=40000)
    a = ap.parse_args()
    home, away = TeamModel.from_cache(a.home), TeamModel.from_cache(a.away)
    print(f"=== DEEP GAME REPORT: {a.away} @ {a.home} | {a.nsims} sims on {device()} ===\n")
    res = simulate_game_fast(home, away, n_sims=a.nsims, seed=20260608, anchor=True, defense=True,
                             context={"neutral_site": False})
    mpg = _mpg(home, away)
    STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "ftm", "fga", "fgm", "oreb", "dreb", "pf"]

    ht, at = res.home_total, res.away_total
    margin = ht - at
    print(f"WIN PROBABILITY: {a.home} {res.home_win_prob*100:.1f}%  |  {a.away} {(1-res.home_win_prob)*100:.1f}%")
    print(f"PROJECTED FINAL: {a.home} {ht.mean():.1f}  {a.away} {at.mean():.1f}  "
          f"(spread {a.home} {margin.mean():+.1f}, total {(ht+at).mean():.1f})")
    print(f"  {a.home} total range q10-q90: {np.quantile(ht,.1):.0f}-{np.quantile(ht,.9):.0f}  |  "
          f"{a.away}: {np.quantile(at,.1):.0f}-{np.quantile(at,.9):.0f}")
    print(f"  margin range q10-q90: {np.quantile(margin,.1):+.0f} to {np.quantile(margin,.9):+.0f}  |  "
          f"total range: {np.quantile(ht+at,.1):.0f}-{np.quantile(ht+at,.9):.0f}")

    for tm, pids, tot, name in ((home, [p for p in res.players if res.players[p]['team']==a.home], ht, a.home),
                                (away, [p for p in res.players if res.players[p]['team']==a.away], at, a.away)):
        rows = sorted(pids, key=lambda p: -res.players[p]["mean"]["pts"])
        rows = [p for p in rows if (mpg.get(p,0) >= 8 or res.players[p]["mean"]["pts"] >= 5)]
        print(f"\n=== {name} BOX SCORE (proj mean | q10-q90 range) ===")
        print(f"{'player':20s} {'min':>3s} {'PTS':>11s} {'REB':>9s} {'AST':>9s} {'3PM':>7s} "
              f"{'STL':>5s} {'BLK':>5s} {'TOV':>5s} {'FT':>5s} {'FG':>9s}")
        for p in rows:
            d = res.players[p]; s = {k: np.asarray(d["samples"][k], float) for k in STATS if k in d["samples"]}
            s["reb"] = np.asarray(d["samples"]["reb"], float)
            def rng(k):
                return f"{s[k].mean():.1f}|{np.quantile(s[k],.1):.0f}-{np.quantile(s[k],.9):.0f}"
            fg = f"{s['fgm'].mean():.0f}/{s['fga'].mean():.0f}"
            print(f"{ASC(d['name']):20s} {mpg.get(p,0):3.0f} {rng('pts'):>11s} {rng('reb'):>9s} {rng('ast'):>9s} "
                  f"{s['fg3m'].mean():3.1f}@{np.quantile(s['fg3m'],.9):.0f} {s['stl'].mean():5.1f} {s['blk'].mean():5.1f} "
                  f"{s['tov'].mean():5.1f} {s['ftm'].mean():5.1f} {fg:>9s}")

    # milestones
    print("\n=== MILESTONES & EXOTICS (per-sim probabilities) ===")
    print(f"{'player':20s} {'20+':>5s} {'25+':>5s} {'30+':>5s} {'10reb':>6s} {'10ast':>6s} {'DD':>5s} {'TD':>5s} {'3+3pm':>6s}")
    allp = sorted(res.players, key=lambda p: -res.players[p]["mean"]["pts"])[:14]
    for p in allp:
        d = res.players[p]; pts = np.asarray(d["samples"]["pts"], float)
        reb = np.asarray(d["samples"]["reb"], float); ast = np.asarray(d["samples"]["ast"], float)
        fg3 = np.asarray(d["samples"]["fg3m"], float)
        dd = ((pts >= 10).astype(int) + (reb >= 10) + (ast >= 10) >= 2).mean()
        td = ((pts >= 10).astype(int) + (reb >= 10) + (ast >= 10) >= 3).mean()
        print(f"{ASC(d['name']):20s} {(pts>=20).mean()*100:4.0f}% {(pts>=25).mean()*100:4.0f}% "
              f"{(pts>=30).mean()*100:4.0f}% {(reb>=10).mean()*100:5.0f}% {(ast>=10).mean()*100:5.0f}% "
              f"{dd*100:4.0f}% {td*100:4.0f}% {(fg3>=3).mean()*100:5.0f}%")

    # trajectory (clock engine)
    print("\n=== TRAJECTORY (clock-aware engine, 4000 sims) ===")
    r = simulate_clock(home, away, n_sims=4000, seed=20260608)
    print(f"quarter scores: " + " ".join(f"Q{i+1} {a.home} {r['qh'][:,i].mean():.0f}-{r['qa'][:,i].mean():.0f} {a.away}" for i in range(4)))
    print(f"halftime margin {a.home} {r['half_margin'].mean():+.1f} | lead changes {r['lead_changes'].mean():.1f} | "
          f"largest lead {r['largest'].mean():.0f} | {a.home} leads {r['home_time_lead'].mean()*100:.0f}% of clock")
    print(f"comeback (down 10+ -> win): {a.home} {r['comeback_home']*100:.0f}%  {a.away} {r['comeback_away']*100:.0f}%")
    print(f"quarter-winner P({a.home}): " + " ".join(f"Q{i+1} {r['qwin_home'][i]*100:.0f}%" for i in range(4)))
    print(f"clock-engine final: {a.home} {r['finalh'].mean():.0f}-{r['finala'].mean():.0f} {a.away} (win {r['home_win']*100:.0f}%)")


if __name__ == "__main__":
    main()
