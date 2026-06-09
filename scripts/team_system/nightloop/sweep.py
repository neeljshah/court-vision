"""Night-loop sweep harness: tune ANY sim constant fast on the GPU, scored walk-forward-ish.

Overrides a module constant across a grid of values (in BOTH basketball_sim and fast_sim, since fast_sim
binds some by import), runs the GPU sim over a fixed game SUBSAMPLE, and reports player-pts MAE/bias,
team-total bias, and pts interval coverage for each value -- so the night loop can find whether any value
beats the current default. Subsampled (default 60 games) so each value is ~1-2 min on the RTX 4060.

  python scripts/team_system/nightloop/sweep.py --const USAGE_CONCENTRATION --values 1.0,1.15,1.25,1.4
  python scripts/team_system/nightloop/sweep.py --const RECENCY_W --values 0.3,0.45,0.6,0.75,0.9 --stride 2

Leakage note: season-anchored (same ~1% in-sample lift for every value), so the RELATIVE ranking across
values is the clean signal; report the best value + whether it beats the default by a meaningful margin.
DOES NOT auto-apply anything -- it prints a verdict for the loop to record. ascii-only prints.
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
sys.path.insert(0, os.path.dirname(HERE))            # scripts/team_system (for build_player_rates)
sys.path.insert(0, os.path.join(ROOT, "src"))        # src (for sim.*)
from build_player_rates import _pstat  # noqa: E402
import sim.basketball_sim as B  # noqa: E402
import sim.fast_sim as F  # noqa: E402
TS = os.path.join(ROOT, "data", "cache", "team_system")
BOX = os.path.join(TS, "box")
MINE = {"NYK", "SAS"}


def setconst(name, val):
    n = 0
    for mod in (B, F):
        if hasattr(mod, name):
            setattr(mod, name, val); n += 1
    return n


def evaluate(games, rates_df, team_rates, nsims, minmin=25.0):
    """Run the sim over the game subsample; return player-pts MAE/bias, team-total bias, pts coverage."""
    models = {}
    def model(tri):
        if tri not in models:
            try:
                models[tri] = B.TeamModel.from_cache(tri, rates_df=rates_df, team_rates=team_rates)
            except Exception:
                models[tri] = None
        return models[tri]

    perr, pbias, terr, cov, n = [], [], [], [], 0
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
            res = F.simulate_game_fast(hm, am, n_sims=nsims, seed=2026, anchor=True, defense=True,
                                       context={"neutral_site": False})
        except Exception:
            continue
        n += 1
        sides = {htri: bg["homeTeam"], atri: bg["awayTeam"]}
        for tri in (htri, atri):
            if tri not in MINE:
                continue
            tot = res.home_total if tri == htri else res.away_total
            actual_tot = sum(_pstat(p)["pts"] for p in sides[tri].get("players", []))
            terr.append(float(np.median(tot)) - actual_tot)
            for p in sides[tri].get("players", []):
                st = _pstat(p); pid = int(p["personId"])
                if st["min"] < minmin or pid not in res.players:
                    continue
                sm = res.players[pid]["samples"]["pts"]
                perr.append(abs(float(sm.mean()) - st["pts"]))
                pbias.append(float(sm.mean()) - st["pts"])
                q10, q90 = np.quantile(sm, 0.1), np.quantile(sm, 0.9)
                cov.append(1.0 if q10 <= st["pts"] <= q90 else 0.0)
    return dict(n=n, pmae=np.mean(perr) if perr else float("nan"),
                pbias=np.mean(pbias) if pbias else float("nan"),
                tbias=np.mean(terr) if terr else float("nan"),
                cov=np.mean(cov) if cov else float("nan"), npg=len(perr))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--const", required=True)
    ap.add_argument("--values", required=True, help="comma-separated")
    ap.add_argument("--nsims", type=int, default=3000)
    ap.add_argument("--stride", type=int, default=6, help="use every Nth game (speed)")
    ap.add_argument("--minmin", type=float, default=25.0)
    a = ap.parse_args()

    if not (hasattr(B, a.const) or hasattr(F, a.const)):
        print(f"UNKNOWN const {a.const} (not in basketball_sim/fast_sim)"); return
    default = getattr(B, a.const, getattr(F, a.const, None))
    vals = [float(x) for x in a.values.split(",")]

    rates_df = pd.read_parquet(os.path.join(TS, "player_rates.parquet"))
    team_rates = json.load(open(os.path.join(TS, "team_rates.json")))
    allg = sorted(json.load(open(os.path.join(TS, "nyk_sas_games.json"))), key=lambda g: (g["date"], g["gid"]))
    games = allg[::a.stride]

    print(f"=== SWEEP {a.const} (default {default})  | {len(games)} games (stride {a.stride}), {a.nsims} sims ===")
    print(f"{'value':>8s} {'pts MAE':>8s} {'pts bias':>9s} {'tot bias':>9s} {'pts cov':>8s}  (npg)")
    rows = []
    for v in vals:
        setconst(a.const, v)
        r = evaluate(games, rates_df, team_rates, a.nsims, a.minmin)
        rows.append((v, r))
        mark = "  <-default" if abs(v - (default or 0)) < 1e-9 else ""
        print(f"{v:>8.3f} {r['pmae']:>8.3f} {r['pbias']:>+9.3f} {r['tbias']:>+9.2f} {r['cov']:>7.1%}  ({r['npg']}){mark}")
    setconst(a.const, default)  # restore

    # primary rank = pts MAE; ALSO surface min-|bias| and best-coverage on the verdict line (this is the
    # line run_next records) so the loop can apply the "judge on bias+coverage, not MAE-only" discipline.
    # Auto-CANDIDATE stays MAE-gated (conservative); the model eyeballs bias/cov candidates from these nums.
    best = min(rows, key=lambda x: x[1]["pmae"])
    dflt = min(rows, key=lambda x: abs(x[0] - (default or 0)))
    dmae = best[1]["pmae"] - dflt[1]["pmae"]
    bb = min(rows, key=lambda x: abs(x[1]["pbias"]))         # smallest |player-pts bias|
    cb = min(rows, key=lambda x: abs(x[1]["cov"] - 0.80))    # coverage closest to the 80% target
    verdict = ("KEEP default" if abs(best[0] - dflt[0]) < 1e-9 or dmae > -0.03
               else f"CANDIDATE {a.const}={best[0]} (pts MAE {dmae:+.3f} vs default)")
    print(f"VERDICT: best pts-MAE at {a.const}={best[0]} (MAE {best[1]['pmae']:.3f}); "
          f"default {dflt[0]} (MAE {dflt[1]['pmae']:.3f}) -> {verdict} "
          f"| minbias {a.const}={bb[0]} (pbias {bb[1]['pbias']:+.3f} vs dflt {dflt[1]['pbias']:+.3f}) "
          f"| bestcov {a.const}={cb[0]} (cov {cb[1]['cov']:.0%} vs dflt {dflt[1]['cov']:.0%})")


if __name__ == "__main__":
    main()
