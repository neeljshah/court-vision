"""Is the possession Monte Carlo's UNCERTAINTY calibrated? (PIT + interval coverage + Brier)

The sim emits a full distribution per player (q10/q50/q90) and a win prob. The anchor pins each
player's MEAN to his season level; the INTERVAL WIDTH is whatever the possession MC produces. Nobody
has checked whether that width matches real game-to-game variance. This runs the GPU sim for every
NYK/SAS game and compares the simulated distributions to what actually happened.

Metrics (pooled over all NYK/SAS player-games and team-games):
  - PIT (probability integral transform): rank of the actual value in the sim distribution. If the
    sim is calibrated, pooled PITs ~ Uniform(0,1) -> mean ~0.50, and the central 80% interval
    [q10,q90] covers ~80% of outcomes. < 80% => intervals too tight (under-dispersed).
  - directional: fraction below q10 / above q90 (each should be ~0.10).
  - team total: actual team points vs the simulated team-total distribution.
  - win prob Brier: on the well-modeled NYK-vs-SAS games only (both rosters full); small-n, flagged.

Leakage note: the anchor mean uses the season average, which contains this game -- but over ~100
games per team that shifts the mean ~1%, so coverage (a test of the MC VARIANCE, not the mean) is
effectively leak-free. Minutes are NOT conditioned on (a true pregame MC), so minute-surprise games
legitimately widen the realized spread -- that is part of honest pregame uncertainty.

  python scripts/team_system/calibration_sim.py --nsims 4000
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from build_player_rates import _pstat  # noqa: E402
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import simulate_game_fast  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
BOX_DIR = os.path.join(TS, "box")
MINE = {"NYK", "SAS"}


def mid_pit(samples, actual):
    """Randomized-PIT expectation for a discrete sim distribution (handles ties)."""
    lt = float((samples < actual).mean()); le = float((samples <= actual).mean())
    return 0.5 * (lt + le)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nsims", type=int, default=4000)
    ap.add_argument("--minmin", type=float, default=12.0)
    ap.add_argument("--nodisp", action="store_true", help="disable dispersion calibration (raw MC spread)")
    a = ap.parse_args()
    disp = not a.nodisp

    rates_df = pd.read_parquet(os.path.join(TS, "player_rates.parquet"))
    team_rates = json.load(open(os.path.join(TS, "team_rates.json")))
    games = sorted(json.load(open(os.path.join(TS, "nyk_sas_games.json"))), key=lambda g: (g["date"], g["gid"]))

    models = {}
    def model(tri):
        if tri not in models:
            try:
                models[tri] = TeamModel.from_cache(tri, rates_df=rates_df, team_rates=team_rates)
            except Exception:
                models[tri] = None
        return models[tri]

    pit = {"pts": [], "reb": [], "ast": []}
    cov80 = {"pts": [], "reb": [], "ast": []}
    below = {"pts": [], "reb": [], "ast": []}
    above = {"pts": [], "reb": [], "ast": []}
    team_pit, team_cov, team_err = [], [], []
    brier, n_h2h = [], 0
    nseen = 0

    for gm in games:
        bf = os.path.join(BOX_DIR, f"{gm['gid']}.json")
        if not os.path.exists(bf):
            continue
        bg = json.load(open(bf))["game"]
        htri, atri = bg["homeTeam"]["teamTricode"], bg["awayTeam"]["teamTricode"]
        if htri not in MINE and atri not in MINE:
            continue
        hm, am = model(htri), model(atri)
        if hm is None or am is None:
            continue
        ctx = {"neutral_site": False}
        try:
            res = simulate_game_fast(hm, am, n_sims=a.nsims, seed=2026, anchor=True, defense=True,
                                     context=ctx, dispersion=disp)
        except Exception:
            continue
        nseen += 1
        sides = {htri: bg["homeTeam"], atri: bg["awayTeam"]}
        actual_tot = {tri: sum((_pstat(p)["pts"]) for p in sides[tri].get("players", [])) for tri in (htri, atri)}

        # H2H win-prob Brier (both teams well modeled)
        if htri in MINE and atri in MINE:
            n_h2h += 1
            home_win = 1.0 if actual_tot[htri] > actual_tot[atri] else 0.0
            brier.append((res.home_win_prob - home_win) ** 2)

        for tri in (htri, atri):
            if tri not in MINE:
                continue
            tot_samp = res.home_total if tri == htri else res.away_total
            at = actual_tot[tri]
            team_pit.append(mid_pit(tot_samp, at))
            team_cov.append(1.0 if np.quantile(tot_samp, 0.1) <= at <= np.quantile(tot_samp, 0.9) else 0.0)
            team_err.append(float(np.median(tot_samp)) - at)   # projected (median) - actual
            for p in sides[tri].get("players", []):
                st = _pstat(p); pid = int(p["personId"])
                if st["min"] < a.minmin or pid not in res.players:
                    continue
                d = res.players[pid]["samples"]
                for stat, act in (("pts", st["pts"]), ("reb", st["oreb"] + st["dreb"]), ("ast", st["ast"])):
                    sm = d[stat]
                    pit[stat].append(mid_pit(sm, act))
                    q10, q90 = np.quantile(sm, 0.1), np.quantile(sm, 0.9)
                    cov80[stat].append(1.0 if q10 <= act <= q90 else 0.0)
                    below[stat].append(1.0 if act < q10 else 0.0)
                    above[stat].append(1.0 if act > q90 else 0.0)

    print(f"=== SIM CALIBRATION vs REAL OUTCOMES ===  {nseen} games simulated, {a.nsims} sims each "
          f"(dispersion={'ON' if disp else 'OFF'})\n")
    print("  PLAYER distributions (pooled player-games, actual min >= %.0f):" % a.minmin)
    print(f"  {'stat':>4s} | {'n':>5s} | {'mean PIT':>9s} | {'cov[q10,q90]':>13s} | {'<q10':>6s} | {'>q90':>6s}")
    for s in ("pts", "reb", "ast"):
        n = len(pit[s])
        print(f"  {s:>4s} | {n:5d} | {np.mean(pit[s]):9.3f} | {np.mean(cov80[s]):13.1%} | "
              f"{np.mean(below[s]):6.1%} | {np.mean(above[s]):6.1%}")
    print("   (calibrated target: mean PIT 0.50, coverage 80.0%, tails 10% each)\n")

    print("  TEAM total distributions (NYK/SAS team-games):")
    te = np.array(team_err)
    print(f"    n={len(team_pit)}  mean PIT {np.mean(team_pit):.3f}  cov[q10,q90] {np.mean(team_cov):.1%}  "
          f"| projected-total MAE {np.abs(te).mean():.2f}  bias {te.mean():+.2f}")
    if brier:
        base = 0.25
        print(f"\n  WIN-PROB Brier (NYK-vs-SAS only, n={n_h2h}): {np.mean(brier):.4f}  (coin-flip 0.25)  [small-n]")
    print("\n  note: anchor mean ~leak-free over ~100 games; minutes not conditioned (pregame MC),")
    print("  so minute-surprise legitimately widens realized spread. PIT<0.5 => sim over-predicts.")


if __name__ == "__main__":
    main()
