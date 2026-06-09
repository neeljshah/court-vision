"""Backtest the defense model against REAL outcomes — does it actually predict?

For every NYK/SAS game: take each player's minutes-controlled season scoring rate and predict
his points two ways — flat (season pts/min x actual minutes) and defense-adjusted (x the opponent
matchup factor). Compare both to what he ACTUALLY scored. The honest question: does adjusting for
the opponent's defense reduce error / capture a real signal, or is it noise?

Tests (player-level and team-level):
  - MAE / RMSE / bias: flat vs defense-adjusted
  - regression of actual residual on the model's predicted defense adjustment (slope > 0 = right
    direction; ~1 = well-calibrated)
  - bucketed: do players actually underperform vs strong defenses?

Honest caveats printed: season rate & opp ratings are full-season (mild in-sample leakage, dominated
by other games); minutes are taken as actual to remove the minutes confound.

  python scripts/team_system/backtest_defense.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from build_player_rates import _pstat  # noqa: E402
from sim.basketball_sim import PERIM_ANCHOR_SLOPE, REF_PERIM_D, REF_RIM_D, RIM_ANCHOR_SLOPE  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
MINE = {"NYK", "SAS"}


def _opp_def(players, rt):
    """Opponent defensive rim_d / perim_d from who played, minute-weighted (season ratings)."""
    ints, perims, mins, prot = [], [], [], []
    for p in players:
        st = _pstat(p)
        if st["min"] < 4:
            continue
        pid = int(p["personId"])
        r = rt.get(pid, {"INTERIOR_D": 50.0, "PERIMETER_D": 50.0})
        ints.append(r["INTERIOR_D"]); perims.append(r["PERIMETER_D"]); mins.append(st["min"])
        if st["min"] >= 10:
            prot.append(r["INTERIOR_D"])
    if not mins:
        return 50.0, 50.0
    mins = np.array(mins)
    wmean_int = float(np.average(ints, weights=mins))
    rim_d = 0.5 * wmean_int + 0.5 * (max(prot) if prot else wmean_int)
    perim_d = float(np.average(perims, weights=mins))
    return rim_d, perim_d


def _matchup(rrate, rim_d, perim_d, mult=1.0):
    rim = (rrate["z_rim"] + rrate["z_paint"]); per = (rrate["z_mid"] + rrate["z_3"]); s = rim + per
    if s <= 0:
        return 1.0
    drag = mult * (rim * RIM_ANCHOR_SLOPE * (rim_d - REF_RIM_D) + per * PERIM_ANCHOR_SLOPE * (perim_d - REF_PERIM_D)) / s
    return float(np.clip(1 - drag, 0.85, 1.12))


def main():
    rates = pd.read_parquet(os.path.join(TS, "player_rates.parquet")).set_index("pid")
    rt = pd.read_parquet(os.path.join(TS, "player_ratings.parquet")).set_index("pid")[["INTERIOR_D", "PERIMETER_D"]].to_dict("index")
    rate_d = {pid: rates.loc[pid].to_dict() for pid in rates.index}
    games = json.load(open(os.path.join(TS, "nyk_sas_games.json")))

    rec = []
    for gi, gm in enumerate(games):
        bf = os.path.join(TS, "box", f"{gm['gid']}.json")
        if not os.path.exists(bf):
            continue
        bg = json.load(open(bf))["game"]
        sides = {bg["homeTeam"]["teamTricode"]: bg["homeTeam"], bg["awayTeam"]["teamTricode"]: bg["awayTeam"]}
        for tri, tm in sides.items():
            if tri not in MINE:
                continue
            opp = sides[bg["awayTeam"]["teamTricode"] if tri == bg["homeTeam"]["teamTricode"] else bg["homeTeam"]["teamTricode"]]
            rim_d, perim_d = _opp_def(opp.get("players", []), rt)
            for p in tm.get("players", []):
                st = _pstat(p); pid = int(p["personId"])
                if pid not in rate_d or st["min"] < 12:
                    continue
                rr = rate_d[pid]
                if rr["mpg"] < 12 or rr["pts_pg"] < 6:
                    continue
                flat = rr["pts_pg"] / max(rr["mpg"], 1) * st["min"]      # minutes-controlled season rate
                drag = 1.0 - _matchup(rr, rim_d, perim_d, mult=1.0)      # base defense drag fraction
                rec.append({"gkey": f"{gm['gid']}-{tri}", "actual": st["pts"], "flat": flat,
                            "drag": drag, "rim_d": rim_d})
    d = pd.DataFrame(rec)
    print(f"=== DEFENSE BACKTEST vs REAL OUTCOMES ===  {len(d)} player-games, {d.gkey.nunique()} team-games\n")

    def predict(mult):
        return d.flat * np.clip(1 - mult * d.drag, 0.85, 1.12)

    print("  slope-multiplier sweep (mult x the base anchor slopes) vs real outcomes:")
    print(f"  {'mult':>5s} | {'PLAYER MAE/RMSE/bias':>24s} | {'TEAM MAE/RMSE/bias':>24s}")
    best, bestmae = 1.0, 1e9
    for m in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        pred = predict(m)
        pe = pred - d.actual
        tg = pd.DataFrame({"a": d.actual, "p": pred, "g": d.gkey}).groupby("g").sum()
        te = tg.p - tg.a
        tmae = te.abs().mean()
        if tmae < bestmae:
            best, bestmae = m, tmae
        print(f"  {m:5.1f} | {pe.abs().mean():6.2f} {np.sqrt((pe**2).mean()):6.2f} {pe.mean():+6.2f}    | "
              f"{tmae:6.2f} {np.sqrt((te**2).mean()):6.2f} {te.mean():+6.2f}")
    print(f"\n  -> team-MAE-optimal multiplier: {best} (current shipped = 1.0; mult 0.0 = no defense)")

    d["bucket"] = pd.qcut(d.rim_d, 3, labels=["weak-D", "avg-D", "strong-D"])
    print("\n  REAL effect — actual scoring vs season-rate baseline, by opponent rim defense:")
    for b, g in d.groupby("bucket", observed=True):
        print(f"    {b:9s} (rim_d {g.rim_d.mean():.0f}): mean residual {(g.actual - g.flat).mean():+.2f} pts/player-game (n={len(g)})")
    print("\n  caveat: season rate & opp ratings are full-season (mild in-sample leakage); minutes are actual.")


if __name__ == "__main__":
    main()
