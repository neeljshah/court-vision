"""WALK-FORWARD (leak-free) backtest of the scoring baseline + defense adjustment.

The shipped backtest_defense.py predicts each player's points from his FULL-SEASON
scoring rate -- circular (the game being predicted is inside its own baseline). This rebuilds
the scoring baseline AS-OF each game (prior games only, empirical-Bayes shrinkage to a league
prior) and re-confirms the defense slopes with no scoring leakage.

Two defense variants, both tested leak-free on top of the as-of baseline:
  (1) TRAIT defense  -- the shipped mechanism: opponent rim_d/perim_d from individual
      INTERIOR_D/PERIMETER_D season ratings, weighted by who played (a slow talent trait).
  (2) EMPIRICAL defense -- fully as-of: opponent team's allowed efficiency from its OWN
      prior cached games (shrunk to league mean), mapped to a rim_d/perim_d-style drag.

Honest caveats (printed): defensive trait ratings + shot-zone style are season-fixed (slow
traits, not the circular pts leak); opponent rotation minutes are taken as actual (known
~pregame); the empirical opp-def is sparse (opponents appear only in cached NYK/SAS games).

  python scripts/team_system/walkforward_backtest.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from build_player_rates import _pstat  # noqa: E402
from sim.basketball_sim import PERIM_ANCHOR_SLOPE, REF_PERIM_D, REF_RIM_D, RIM_ANCHOR_SLOPE  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
BOX_DIR = os.path.join(TS, "box")
MINE = {"NYK", "SAS"}
PRIOR_K = 36.0       # shrinkage strength, in minutes (~1.5 games) for the as-of ppm
MIN_PRIOR_MIN = 60.0  # require >= this many prior minutes to score a player-game (real prediction)


def _opp_def_trait(players, rt):
    """Opponent rim_d / perim_d from individual season trait ratings, minute-weighted (shipped path)."""
    ints, perims, mins, prot = [], [], [], []
    for p in players:
        st = _pstat(p)
        if st["min"] < 4:
            continue
        r = rt.get(int(p["personId"]), {"INTERIOR_D": 50.0, "PERIMETER_D": 50.0})
        ints.append(r["INTERIOR_D"]); perims.append(r["PERIMETER_D"]); mins.append(st["min"])
        if st["min"] >= 10:
            prot.append(r["INTERIOR_D"])
    if not mins:
        return 50.0, 50.0
    mins = np.array(mins)
    rim_d = 0.5 * float(np.average(ints, weights=mins)) + 0.5 * (max(prot) if prot else float(np.average(ints, weights=mins)))
    return rim_d, float(np.average(perims, weights=mins))


def _matchup_drag(rr, rim_d, perim_d):
    """Base defense drag fraction (== shipped _matchup at mult=1, before the 1-x and clip)."""
    rim = rr["z_rim"] + rr["z_paint"]; per = rr["z_mid"] + rr["z_3"]; s = rim + per
    if s <= 0:
        return 0.0
    return float((rim * RIM_ANCHOR_SLOPE * (rim_d - REF_RIM_D) + per * PERIM_ANCHOR_SLOPE * (perim_d - REF_PERIM_D)) / s)


def main():
    rates = pd.read_parquet(os.path.join(TS, "player_rates.parquet")).set_index("pid")
    zcols = ["z_rim", "z_paint", "z_mid", "z_3"]
    zone = {pid: rates.loc[pid, zcols].to_dict() for pid in rates.index}  # season style (slow trait)
    rt = pd.read_parquet(os.path.join(TS, "player_ratings.parquet")).set_index("pid")[["INTERIOR_D", "PERIMETER_D"]].to_dict("index")
    games = sorted(json.load(open(os.path.join(TS, "nyk_sas_games.json"))), key=lambda g: (g["date"], g["gid"]))

    # league prior ppm for the as-of baseline shrinkage (global prior, allowed)
    M0 = float((rates["pts_pg"] / rates["mpg"].clip(lower=1)).clip(0.1, 1.2).median())

    psum = defaultdict(lambda: {"pts": 0.0, "min": 0.0})   # as-of player scoring
    team_def = defaultdict(lambda: {"opp_pts": 0.0, "opp_poss": 0.0})  # as-of empirical opp efficiency
    league_drtg = []  # for empirical-def league prior
    rec = []

    for gm in games:
        bf = os.path.join(BOX_DIR, f"{gm['gid']}.json")
        if not os.path.exists(bf):
            continue
        bg = json.load(open(bf))["game"]
        sides = {bg["homeTeam"]["teamTricode"]: bg["homeTeam"], bg["awayTeam"]["teamTricode"]: bg["awayTeam"]}
        tri_home, tri_away = bg["homeTeam"]["teamTricode"], bg["awayTeam"]["teamTricode"]

        # ---- score every NYK/SAS player-game with ONLY prior info ----
        for tri, tm in sides.items():
            if tri not in MINE:
                continue
            opp = sides[tri_away if tri == tri_home else tri_home]
            rim_d, perim_d = _opp_def_trait(opp.get("players", []), rt)
            # empirical as-of opp def: opponent's allowed pts/poss in ITS prior cached games
            otri = tri_away if tri == tri_home else tri_home
            ed = team_def[otri]
            emp_drtg = (100.0 * ed["opp_pts"] / ed["opp_poss"]) if ed["opp_poss"] > 200 else None
            lg_drtg = float(np.mean(league_drtg)) if league_drtg else 113.3
            for p in tm.get("players", []):
                st = _pstat(p); pid = int(p["personId"])
                if pid not in zone or st["min"] < 12:
                    continue
                ps = psum[pid]
                if ps["min"] < MIN_PRIOR_MIN:        # not enough history -> skip (no real prediction)
                    continue
                ppm = (ps["pts"] + PRIOR_K * M0) / (ps["min"] + PRIOR_K)   # shrunk as-of rate
                flat = ppm * st["min"]
                drag = _matchup_drag(zone[pid], rim_d, perim_d)            # trait-defense drag
                # empirical drag: strong opp D (LOW allowed drtg) -> positive drag -> lowers our pred
                if emp_drtg is not None:
                    emp_drag = 0.010 * (lg_drtg - emp_drtg)
                else:
                    emp_drag = 0.0
                rec.append({"gkey": f"{gm['gid']}-{tri}", "date": gm["date"], "actual": st["pts"],
                            "flat": flat, "drag": drag, "emp_drag": emp_drag, "rim_d": rim_d,
                            "has_emp": emp_drtg is not None})

        # ---- AFTER scoring, update as-of accumulators with THIS game (so it leaks into nothing prior) ----
        # possessions estimate per team from box player sums (leak-free, standard formula)
        tot = {}
        for tri, tm in sides.items():
            agg = defaultdict(float)
            for p in tm.get("players", []):
                st = _pstat(p)
                for k in ("pts", "fga", "fta", "oreb", "tov", "min"):
                    agg[k] += st[k]
            tot[tri] = agg
        for tri in (tri_home, tri_away):
            o = tot[tri_away if tri == tri_home else tri_home]
            poss = o["fga"] + 0.44 * o["fta"] - o["oreb"] + o["tov"]
            team_def[tri]["opp_pts"] += o["pts"]; team_def[tri]["opp_poss"] += poss
            if poss > 50:
                league_drtg.append(100.0 * o["pts"] / poss)
        for tri, tm in sides.items():
            for p in tm.get("players", []):
                st = _pstat(p)
                if st["min"] > 0:
                    psum[int(p["personId"])]["pts"] += st["pts"]; psum[int(p["personId"])]["min"] += st["min"]

    d = pd.DataFrame(rec)
    print("=== WALK-FORWARD (LEAK-FREE) BACKTEST ===")
    print(f"  {len(d)} scored player-games, {d.gkey.nunique()} team-games "
          f"(as-of ppm, shrink K={PRIOR_K:.0f}m to league prior {M0:.3f} ppm; >= {MIN_PRIOR_MIN:.0f} prior min)\n")

    def sweep(dragcol, label, sub=None):
        dd = d if sub is None else d[sub]
        print(f"  [{label}] n={len(dd)} player-games, {dd.gkey.nunique()} team-games")
        print(f"  {'mult':>5s} | {'PLAYER MAE/RMSE/bias':>24s} | {'TEAM MAE/RMSE/bias':>24s}")
        best, bestmae = 0.0, 1e9
        for m in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
            pred = dd.flat * np.clip(1 - m * dd[dragcol], 0.85, 1.12)
            pe = pred - dd.actual
            tg = pd.DataFrame({"a": dd.actual, "p": pred, "g": dd.gkey}).groupby("g").sum()
            te = tg.p - tg.a; tmae = te.abs().mean()
            if tmae < bestmae:
                best, bestmae = m, tmae
            print(f"  {m:5.1f} | {pe.abs().mean():6.2f} {np.sqrt((pe**2).mean()):6.2f} {pe.mean():+6.2f}    | "
                  f"{tmae:6.2f} {np.sqrt((te**2).mean()):6.2f} {te.mean():+6.2f}")
        print(f"   -> team-MAE-optimal mult: {best} (0.0 = no defense)\n")

    sweep("drag", "TRAIT defense (shipped mechanism), leak-free baseline")
    sweep("emp_drag", "EMPIRICAL as-of opp def (fully leak-free)", sub=d.has_emp)

    # paired bootstrap: is the TRAIT-defense team-MAE gain (no-def vs shipped mult=1.0) real?
    def team_abs_err(mult):
        pred = d.flat * np.clip(1 - mult * d.drag, 0.85, 1.12)
        tg = pd.DataFrame({"a": d.actual, "p": pred, "g": d.gkey}).groupby("g")
        return (tg.p.sum() - tg.a.sum()).abs()
    e0, e1 = team_abs_err(0.0).values, team_abs_err(1.0).values   # aligned by team-game
    diff = e0 - e1                                                 # >0 = defense helps that game
    n = len(diff); rng = np.random.default_rng(7)
    boots = np.array([diff[rng.integers(0, n, n)].mean() for _ in range(5000)])  # resample w/ replacement
    lo, hi = np.percentile(boots, [2.5, 97.5])
    print(f"\n  TRAIT-defense team-MAE gain (no-def -> shipped mult 1.0): {diff.mean():+.3f} pts/team-game")
    print(f"    95% bootstrap CI [{lo:+.3f}, {hi:+.3f}]  |  defense wins {100*(diff>0).mean():.0f}% of {n} team-games"
          f"  |  P(gain>0)={100*(boots>0).mean():.0f}%")

    # real bucketed gradient with leak-free baseline
    d["bucket"] = pd.qcut(d.rim_d, 3, labels=["weak-D", "avg-D", "strong-D"])
    print("  REAL effect (leak-free baseline) -- actual minus as-of prediction, by opp rim defense:")
    for b, g in d.groupby("bucket", observed=True):
        print(f"    {b:9s} (rim_d {g.rim_d.mean():.0f}): residual {(g.actual - g.flat).mean():+.2f} pts/player-game (n={len(g)})")
    print("\n  caveat: defensive trait ratings + shot-zone style are season-fixed (slow traits, not the")
    print("  circular pts leak); opp rotation minutes are actual (~known pregame); empirical opp-def is sparse.")


if __name__ == "__main__":
    main()
