"""g4_ingame_validate.py — does the G4 in-game driver predict ACCURATELY THROUGHOUT the game?

Grades the EXACT projection logic of g4_ingame.py (model B team + sqrt(frac) dispersion + foul-out per-player +
win-prob from the corrected samples) across EVERY distinct state of the 3 played Finals games, vs the ACTUAL final.
Unlike pbp_replay (which validated the bare model-B mean), this validates the DRIVER's full output: win prob,
projected score, per-player props, AND two throughout-game properties the user cares about:

  1. CALIBRATION  — win-prob Brier + reliability by game-time (a 70% call should win ~70%; the sqrt(frac)
                    dispersion should beat the old fixed-sigma heuristic).
  2. CONVERGENCE  — as the clock runs out the projection must collapse onto the realized final (team-score RMSE
                    -> ~0 in the last minutes; per-player RMSE shrinks monotonically by quarter).

RMSE + signed BIAS, NEVER MAE. Reuses pbp_replay (state loading) + g4_ingame (the validated projector logic).

  python scripts/team_system/g4_ingame_validate.py
"""
from __future__ import annotations

import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import simulate_game_fast  # noqa: E402
import pbp_replay as R  # noqa: E402  (load_states, actual_final, elapsed_min, GAMES, HOMEAWAY, STATS)
from g4_ingame import foulout_mult  # noqa: E402  (the validated lever)

GAME_MIN = 48.0


def rmse_bias(errs):
    e = np.asarray(errs, dtype=float)
    return (math.sqrt(float(np.mean(e ** 2))), float(np.mean(e))) if len(e) else (float("nan"), float("nan"))


def run_game(game_key, nsims=10000, min_final_min=10.0):
    gid = R.GAMES[game_key]
    home_m, away_m = R.HOMEAWAY[game_key]
    states = R.load_states(gid)
    fin_pl, fin_h, fin_a, ht, at_ = R.actual_final(states)
    home_won = 1 if fin_h > fin_a else 0
    h, a = TeamModel.from_cache(home_m), TeamModel.from_cache(away_m)
    res = simulate_game_fast(h, a, n_sims=nsims, seed=2026, anchor=True, defense=True)
    home_arr, away_arr = np.asarray(res.home_total), np.asarray(res.away_total)
    muH, muA = home_arr.mean(), away_arr.mean()
    psamp = {pid: {s: np.asarray(d["samples"][s]) for s in R.STATS} for pid, d in res.players.items()}
    pmu = {pid: {s: psamp[pid][s].mean() for s in R.STATS} for pid in psamp}
    pname = {pid: d["name"] for pid, d in res.players.items()}
    rotation = {pid for pid, v in fin_pl.items() if v["min"] >= min_final_min and pid in psamp}

    team_err, wp_brier = defaultdict(list), defaultdict(list)
    pp_err = {s: defaultdict(list) for s in R.STATS}
    calib = []          # (p_home, home_won) pooled
    conv = []           # (frac_rem, |team_score_err|) for convergence
    prop_calib = []     # (pred_prob, hit, bucket) for the LIVE BOARD's per-player prop calibration
    PROP_THR = {"pts": (10, 15, 20, 25), "reb": (6, 8, 10), "ast": (5, 8)}
    checkpoints, ck_targets = {}, [(12, "endQ1"), (24, "half"), (36, "endQ3"), (42, "Q4 6:00"), (46, "Q4 2:00")]

    for st in states:
        el = R.elapsed_min(st["period"], st["clock_s"])
        if el < 0.5 or el > 53.0:
            continue
        rem_min = (GAME_MIN - el) if st["period"] <= 4 else (st["clock_s"] / 60.0)   # OT-aware (mirror driver)
        frac = max(0.0, rem_min) / GAME_MIN
        frac_el = el / GAME_MIN
        sqf = math.sqrt(frac)
        bucket = f"Q{min(int(st['period']), 4)}" if st["period"] <= 4 else "OT"
        # team (model B + sqrt-frac dispersion, TRUNCATED at the realized score -- mirror driver)
        hf = np.maximum(st["home_score"] + (muH * frac + (home_arr - muH) * sqf), st["home_score"])
        af = np.maximum(st["away_score"] + (muA * frac + (away_arr - muA) * sqf), st["away_score"])
        p_home = float(np.mean(hf > af))
        proj_h, proj_a = float(np.median(hf)), float(np.median(af))
        for b in (bucket, "ALL"):
            team_err[b].append(proj_h - fin_h); team_err[b].append(proj_a - fin_a)
            wp_brier[b].append((p_home - home_won) ** 2)
        calib.append((p_home, home_won))
        conv.append((frac, abs(proj_h - fin_h), abs(proj_a - fin_a)))
        # per-player (baseline + foul-out)
        margin_abs = abs(st["home_score"] - st["away_score"])  # noqa: F841 (kept for parity; garbage-time off)
        for pid in rotation:
            stp = st["players"].get(pid)
            if not stp:
                continue
            mult = foulout_mult(float(stp.get("pf") or 0), float(stp.get("min") or 0), frac, frac_el)
            for s in R.STATS:
                floor = float(stp.get(s) or 0.0)
                proj = np.maximum(floor + (pmu[pid][s] * frac + (psamp[pid][s] - pmu[pid][s]) * sqf) * mult, floor)
                pj = float(np.mean(proj))   # MEAN = RMSE-optimal point estimate (median under-projects skewed counts)
                pp_err[s][bucket].append(pj - fin_pl[pid][s]); pp_err[s]["ALL"].append(pj - fin_pl[pid][s])
                for thr in PROP_THR.get(s, ()):                     # LIVE BOARD prop calibration (the real test)
                    pred = float(np.mean(proj >= thr))
                    if 0.02 < pred < 0.98:                          # ignore near-locks (uninformative)
                        prop_calib.append((pred, 1 if fin_pl[pid][s] >= thr else 0, bucket))
        # checkpoints (closest state to each target elapsed)
        for tgt, lab in ck_targets:
            if abs(el - tgt) < 0.6 and lab not in checkpoints:
                checkpoints[lab] = dict(elapsed=round(el, 1), score=f"{st['home_score']}-{st['away_score']}",
                                        p_home=round(p_home, 3), proj=f"{proj_h:.0f}-{proj_a:.0f}")
    return dict(game=game_key, gid=gid, home=ht, away=at_, final=(fin_h, fin_a), home_won=home_won,
                team_err=team_err, wp_brier=wp_brier, pp_err=pp_err, calib=calib, conv=conv,
                prop_calib=prop_calib, checkpoints=checkpoints, n_rotation=len(rotation))


def main():
    games = [run_game(g) for g in ("G1", "G2", "G3")]
    BUCKETS = ("Q1", "Q2", "Q3", "Q4", "OT", "ALL")
    pool_team, pool_brier = defaultdict(list), defaultdict(list)
    pool_pp = {s: defaultdict(list) for s in R.STATS}
    pool_calib, pool_conv, pool_prop = [], [], []
    for G in games:
        print("=" * 92)
        print(f"{G['game']} ({G['gid']})  {G['away']} @ {G['home']}  actual {G['final'][0]}-{G['final'][1]} "
              f"({'home' if G['home_won'] else 'away'} won)  | rotation {G['n_rotation']}")
        print("  CHECKPOINT TRACE (projection vs actual final — does it track + converge?):")
        for lab in ("endQ1", "half", "endQ3", "Q4 6:00", "Q4 2:00"):
            c = G["checkpoints"].get(lab)
            if c:
                print(f"    {lab:9s} @{c['elapsed']:>4}min  score {c['score']:>9s}  ->  proj {c['proj']:>9s}  "
                      f"| P(home win) {c['p_home']*100:4.0f}%")
        print(f"    FINAL                                  ->  {G['final'][0]}-{G['final'][1]}      "
              f"| home {'WON' if G['home_won'] else 'lost'}")
        for b in BUCKETS:
            if b in G["team_err"]:
                pool_team[b] += G["team_err"][b]; pool_brier[b] += G["wp_brier"][b]
        for s in R.STATS:
            for b in G["pp_err"][s]:
                pool_pp[s][b] += G["pp_err"][s][b]
        pool_calib += G["calib"]; pool_conv += G["conv"]; pool_prop += G["prop_calib"]

    print("=" * 92)
    print("POOLED — TEAM SCORE RMSE/bias  +  WIN-PROB Brier  by game-time (the driver's actual output):")
    print(f"  {'bucket':6s} {'n':>5s} | {'score RMSE':>10s} {'bias':>6s} | {'WP Brier':>9s}")
    for b in BUCKETS:
        if b in pool_team and len(pool_team[b]):
            r, bi = rmse_bias(pool_team[b])
            print(f"  {b:6s} {len(pool_team[b]):>5d} | {r:10.1f} {bi:+6.1f} | {np.mean(pool_brier[b]):9.4f}")
    print("\nPOOLED — PER-PLAYER RMSE/bias by game-time (does it shrink toward the truth?):")
    print(f"  {'bucket':6s} | " + "  ".join(f"{s:>12s}" for s in R.STATS))
    for b in ("Q1", "Q2", "Q3", "Q4", "ALL"):
        cells = []
        for s in R.STATS:
            if b in pool_pp[s] and len(pool_pp[s][b]):
                r, bi = rmse_bias(pool_pp[s][b]); cells.append(f"{r:5.2f}/{bi:+5.2f}")
            else:
                cells.append("   -   ")
        print(f"  {b:6s} | " + "  ".join(f"{x:>12s}" for x in cells))

    # WIN-PROB reliability (CAVEAT: all 3 home teams lost -> degenerate; Brier above is the usable summary)
    ca = np.array(pool_calib)
    home_wins = int(ca[:, 1].sum())
    print(f"\nWIN-PROB reliability — CAVEAT: only {home_wins}/{len(ca)} states are home-wins "
          f"(all 3 home teams lost this sample) -> the reliability curve is degenerate; use the bucketed Brier above.")
    # PER-PLAYER PROP CALIBRATION (the statistically meaningful 'is the live BOARD accurate?' test)
    print("\nLIVE-BOARD PROP CALIBRATION (predicted prob bin -> empirical hit rate; pts/reb/ast tiers, all states):")
    pr = np.array([(p, h) for p, h, _ in pool_prop], dtype=float)
    for lo, hi in [(0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.01)]:
        m = (pr[:, 0] >= lo) & (pr[:, 0] < hi)
        if m.sum():
            print(f"   pred [{lo:.1f},{hi:.1f}): n={int(m.sum()):5d}  predicted {pr[m,0].mean()*100:4.0f}%  "
                  f"actual {pr[m,1].mean()*100:4.0f}%   {'OK' if abs(pr[m,0].mean()-pr[m,1].mean())<0.07 else 'OFF'}")
    pbrier = float(np.mean((pr[:, 0] - pr[:, 1]) ** 2))
    print(f"   prop Brier {pbrier:.4f}  (n={len(pr)} player-prop-states)")
    # CONVERGENCE: error in the final minutes
    print("\nCONVERGENCE (team-score |error| as the clock runs out — must collapse to ~0):")
    cv = np.array(pool_conv)
    for lo, hi, lab in [(.75, 1.01, "Q1 (>=36 left)"), (.5, .75, "Q2"), (.25, .5, "Q3"), (.083, .25, "Q4"),
                        (0.0, .083, "final 4 min")]:
        m = (cv[:, 0] >= lo) & (cv[:, 0] < hi)
        if m.sum():
            print(f"   {lab:16s} n={int(m.sum()):4d}  mean|err| home {cv[m,1].mean():4.1f}  away {cv[m,2].mean():4.1f}")
    json.dump({"pooled_team": {b: rmse_bias(pool_team[b]) for b in pool_team if len(pool_team[b])},
               "pooled_brier": {b: float(np.mean(pool_brier[b])) for b in pool_brier if len(pool_brier[b])},
               "per_game_checkpoints": {G["game"]: G["checkpoints"] for G in games}},
              open(os.path.join(R.ROOT, ".planning", "replay", "g4_ingame_validation.json"), "w"), indent=2)
    print("\nwrote .planning/replay/g4_ingame_validation.json")


if __name__ == "__main__":
    main()
