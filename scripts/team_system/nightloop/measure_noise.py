"""Night-loop: quantify the MC NOISE FLOOR of the sweep harness (so 'within noise' verdicts are grounded).

Every nightloop sweep judged a param 'KEEP default' when its pts-MAE delta was tiny (~+/-0.008). But how
much of that is just Monte-Carlo seed noise? This re-runs the EXACT sweep evaluation (same games, same nsims,
default constants) across several seeds and reports the seed-to-seed std of each metric (pts MAE/bias, team
bias, coverage). A sweep delta is only a real signal if it exceeds ~2x this std -- this prints that detection
floor so the loop's KEEP/CANDIDATE calls are defensible. Pure validation, changes nothing. ascii-only.

  python scripts/team_system/nightloop/measure_noise.py --seeds 6 --stride 6
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "src"))
from build_player_rates import _pstat  # noqa: E402
import sim.basketball_sim as B  # noqa: E402
import sim.fast_sim as F  # noqa: E402

TS = os.path.join(ROOT, "data", "cache", "team_system")
BOX = os.path.join(TS, "box")
MINE = {"NYK", "SAS"}


def evaluate(games, rates_df, team_rates, nsims, seed, minmin=25.0):
    models = {}

    def model(tri):
        if tri not in models:
            try:
                models[tri] = B.TeamModel.from_cache(tri, rates_df=rates_df, team_rates=team_rates)
            except Exception:
                models[tri] = None
        return models[tri]

    perr, pbias, terr, cov = [], [], [], []
    for gm in games:
        bf = os.path.join(BOX, f"{gm['gid']}.json")
        if not os.path.exists(bf):
            continue
        bg = json.load(open(bf))["game"]
        htri, atri = bg["homeTeam"]["teamTricode"], bg["awayTeam"]["teamTricode"]
        if htri not in MINE and atri not in MINE:
            continue
        hm, am = model(htri), model(atri)
        if hm is None or am is None:
            continue
        try:
            res = F.simulate_game_fast(hm, am, n_sims=nsims, seed=seed, anchor=True, defense=True,
                                       context={"neutral_site": False})
        except Exception:
            continue
        sides = {htri: bg["homeTeam"], atri: bg["awayTeam"]}
        for tri in (htri, atri):
            if tri not in MINE:
                continue
            tot = res.home_total if tri == htri else res.away_total
            actual_tot = sum(_pstat(p)["pts"] for p in sides[tri].get("players", []))
            terr.append(float(np.median(tot)) - actual_tot)
            for p in sides[tri].get("players", []):
                st = _pstat(p)
                pid = int(p["personId"])
                if st["min"] < minmin or pid not in res.players:
                    continue
                sm = res.players[pid]["samples"]["pts"]
                perr.append(abs(float(sm.mean()) - st["pts"]))
                pbias.append(float(sm.mean()) - st["pts"])
                q10, q90 = np.quantile(sm, 0.1), np.quantile(sm, 0.9)
                cov.append(1.0 if q10 <= st["pts"] <= q90 else 0.0)
    return (float(np.mean(perr)), float(np.mean(pbias)), float(np.mean(terr)), float(np.mean(cov)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--nsims", type=int, default=3000)
    ap.add_argument("--stride", type=int, default=6)
    ap.add_argument("--minmin", type=float, default=25.0)
    a = ap.parse_args()

    rates_df = pd.read_parquet(os.path.join(TS, "player_rates.parquet"))
    team_rates = json.load(open(os.path.join(TS, "team_rates.json")))
    allg = sorted(json.load(open(os.path.join(TS, "nyk_sas_games.json"))), key=lambda g: (g["date"], g["gid"]))
    games = allg[::a.stride]
    seeds = [2026 + i * 101 for i in range(a.seeds)]   # spread-out fixed seeds (no Date.now / random)

    print(f"=== measure_noise ===  {len(games)} games (stride {a.stride}), {a.nsims} sims, {len(seeds)} seeds")
    print(f"  {'seed':>7s} {'pts MAE':>8s} {'pts bias':>9s} {'tot bias':>9s} {'pts cov':>8s}")
    rows = []
    for s in seeds:
        mae, pb, tb, cv = evaluate(games, rates_df, team_rates, a.nsims, s, a.minmin)
        rows.append((mae, pb, tb, cv))
        print(f"  {s:>7d} {mae:>8.3f} {pb:>+9.3f} {tb:>+9.2f} {cv:>7.1%}")
    arr = np.array(rows)
    mean = arr.mean(axis=0)
    std = arr.std(axis=0, ddof=1)
    labels = ["pts MAE", "pts bias", "tot bias", "pts cov"]
    print("  --- seed-to-seed noise floor (std across seeds) ---")
    for i, lab in enumerate(labels):
        print(f"  {lab:>9s}: mean {mean[i]:+.4f}  std {std[i]:.4f}  -> a real delta needs > ~{2*std[i]:.4f}")
    print(f"VERDICT: MC noise floor pts-MAE std={std[0]:.4f} (2-sigma {2*std[0]:.4f}); all S01-S19 sweep deltas "
          f"(|d| up to ~0.008) were {'WITHIN' if 0.008 < 2*std[0] else 'NEAR/ABOVE'} this floor -> KEEP-default calls "
          f"{'confirmed as noise' if 0.008 < 2*std[0] else 'warrant a closer look'}.")


if __name__ == "__main__":
    main()
