"""Full-sim ACCURACY scoreboard + anchor-strength sweep (player props AND team totals).

The sim's two endpoints disagree: the RAW engine is minutes-consistent but under-predicts team totals
(shared-pie), the season ANCHOR pins every star to his average but over-counts the team (8 star averages
can't all happen at once -- minutes are finite). The truth is a blend. This runs both per game and sweeps
the blend weight s (pred = (1-s)*raw + s*anchor) to find the s that minimizes BOTH player pts error and
team-total error -- the accuracy-optimal anchor strength.

Reports per blend: player pts MAE/bias (rotation, min>=12) and team-total MAE/bias, vs real outcomes.
reb/ast are reported at full anchor (they don't drive the team-total tension). Caveat: season rates are
in-sample (mild, ~1/100-game leak on the mean); the BIAS is what we act on.

  python scripts/team_system/backtest_sim_accuracy.py --nsims 2500
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
BLENDS = [0.0, 0.25, 0.5, 0.6, 0.75, 1.0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nsims", type=int, default=2500)
    a = ap.parse_args()
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

    # per blend: player pts errors, team errors; plus reb/ast at full anchor
    perr = {s: [] for s in BLENDS}; terr = {s: [] for s in BLENDS}
    reb_e, ast_e = [], []
    n = 0
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
            raw = simulate_game_fast(hm, am, n_sims=a.nsims, seed=99, anchor=False, defense=True, context=ctx, dispersion=False)
            anc = simulate_game_fast(hm, am, n_sims=a.nsims, seed=99, anchor=True, defense=True, context=ctx)
        except Exception:
            continue
        n += 1
        sides = {htri: bg["homeTeam"], atri: bg["awayTeam"]}
        for tri in (htri, atri):
            if tri not in MINE:
                continue
            raw_tot = float(np.mean(raw.home_total if tri == htri else raw.away_total))
            anc_tot = float(np.mean(anc.home_total if tri == htri else anc.away_total))
            act_tot = sum(_pstat(p)["pts"] for p in sides[tri].get("players", []))
            for s in BLENDS:
                terr[s].append((1 - s) * raw_tot + s * anc_tot - act_tot)
            for p in sides[tri].get("players", []):
                st = _pstat(p); pid = int(p["personId"])
                if st["min"] < 12 or pid not in raw.players or pid not in anc.players:
                    continue
                rp = raw.players[pid]["mean"]["pts"]; apr = anc.players[pid]["mean"]["pts"]
                for s in BLENDS:
                    perr[s].append((1 - s) * rp + s * apr - st["pts"])
                reb_e.append(anc.players[pid]["reb_mean"] - (st["oreb"] + st["dreb"]))
                ast_e.append(anc.players[pid]["mean"]["ast"] - st["ast"])

    print(f"=== FULL-SIM ACCURACY + ANCHOR SWEEP ===  {n} games, {a.nsims} sims each\n")
    print(f"  blend s = anchor strength (0 = raw/minutes-consistent, 1 = full season anchor)")
    print(f"  {'s':>5s} | {'PLAYER pts MAE/bias':>20s} | {'TEAM total MAE/bias':>20s}")
    for s in BLENDS:
        pe = np.array(perr[s]); te = np.array(terr[s])
        print(f"  {s:5.2f} | {np.abs(pe).mean():8.2f} {pe.mean():+7.2f}     | {np.abs(te).mean():8.2f} {te.mean():+7.2f}")
    # accuracy-optimal s for each
    bp = min(BLENDS, key=lambda s: np.abs(np.array(perr[s])).mean())
    bt = min(BLENDS, key=lambda s: np.abs(np.array(terr[s])).mean())
    btb = min(BLENDS, key=lambda s: abs(np.array(terr[s]).mean()))
    print(f"\n  -> player-MAE-optimal s={bp}  |  team-MAE-optimal s={bt}  |  team-UNBIASED s~={btb}")
    print(f"  reb (full anchor) MAE {np.abs(reb_e).mean():.2f} bias {np.mean(reb_e):+.2f}  |  "
          f"ast MAE {np.abs(ast_e).mean():.2f} bias {np.mean(ast_e):+.2f}  (n={len(reb_e)})")
    print("  current shipped anchor = s=1.0 (stars exact). caveat: in-sample season rates (mild mean leak).")


if __name__ == "__main__":
    main()
