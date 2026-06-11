"""pbp_replay.py — replay a played Finals game PLAY-BY-PLAY through the validated in-game projector.

Walk the live snapshots in time order; at every distinct state build the in-game state (per-player
box-so-far + fouls + minutes + on-court, team score, clock) and project the REST-OF-GAME to the final.
Grade vs the ACTUAL final on RMSE + signed BIAS (NEVER MAE -- the in-game MAE-vs-RMSE artifact keystone:
'shrink toward current' wins MAE as a median-vs-mean trick while worsening RMSE+bias).

TEAM score: model B (validated) = current_score + pregame_remaining * frac_game_remaining (score-anchor +
            stable pregame pace). NOT live-pace extrapolation (model C, a refuted trap: Q1 RMSE 23.7).
WIN PROB:   Phi(proj_margin / sigma), sigma = 13.5*sqrt(frac_remaining) (uncertainty shrinks as the game
            completes -- principled, not data-fit). Brier vs actual_home_won, bucketed by game-time.
PER-PLAYER: baseline = stat_so_far + pregame_mean * frac_game_remaining (the per-player analog of team B).
            The frozen pregame projection (sim) is the RATE anchor; the live state only re-weights
            minutes/usage and adds the realized floor -> leak-safe, no look-ahead. Each in-game VARIABLE
            (minute-share / foul-out / garbage-time / minutes-cap / heat) is an ABLATION modifier on the
            remaining term -> kept ONLY if it improves per-player RMSE+bias; honest rejects recorded.

LEAK NOTE: pregame rates are the CURRENT cache (fit through G2; cdn=403 -> G3 box not ingested). Grading G3
           is therefore fully leak-free (G3 not in the fit). Grading G1/G2 uses a rate anchor that includes
           those games (mild look-ahead in the RATE anchor only, never in the live state); the score-anchored
           projector's late-game accuracy is dominated by the realized floor, so the effect shrinks by quarter.
           Flagged honestly; Phase-5 leak audit bounds it.

  python scripts/team_system/pbp_replay.py --game G3
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import simulate_game_fast  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPLAY = os.path.join(ROOT, "data", "cache", "ingame", "finals_replay_eval.parquet")
GAMES = {"G1": "0042500401", "G2": "0042500402", "G3": "0042500403"}
HOMEAWAY = {"G1": ("SAS", "NYK"), "G2": ("SAS", "NYK"), "G3": ("NYK", "SAS")}  # G1/G2 at SAS, G3 at NYK
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk"]
GAME_MIN = 48.0


def parse_clock(c):
    if isinstance(c, (int, float)):
        return float(c)
    s = str(c).strip()
    if ":" in s:
        try:
            m, sec = s.split(":")[:2]
            return float(m) * 60 + float(sec)
        except Exception:
            return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def elapsed_min(period, clock_s):
    if period <= 0:
        return 0.0
    if period <= 4:
        return (period - 1) * 12.0 + (12.0 - clock_s / 60.0)
    return 48.0 + (period - 5) * 5.0 + (5.0 - clock_s / 60.0)


def load_states(game_id):
    """Distinct in-game states in time order (de-dup consecutive identical box+score+clock)."""
    files = sorted(glob.glob(os.path.join(ROOT, "data", "live", f"{game_id}_*.json")))
    states, last_key = [], None
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        cs = parse_clock(d.get("clock"))
        per = int(d.get("period") or 0)
        key = (per, round(cs), d.get("home_score"), d.get("away_score"))
        if key == last_key:
            continue
        last_key = key
        pl = {}
        for p in d.get("players", []):
            pl[int(p["player_id"])] = {k: p.get(k) for k in
                                       ("name", "team", "min", "pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "pf", "is_starter")}
        states.append(dict(period=per, clock_s=cs, home_score=d["home_score"], away_score=d["away_score"],
                           home_team=d["home_team"], away_team=d["away_team"], players=pl,
                           status=d.get("game_status", "")))
    return states


def actual_final(states):
    """Per-player + team actual final = last snapshot box."""
    last = states[-1]
    per_player = {pid: {s: float(p.get(s) or 0) for s in STATS + ["min"]} for pid, p in last["players"].items()}
    return per_player, last["home_score"], last["away_score"], last["home_team"], last["away_team"]


def pregame_anchor(home, away):
    """Frozen pregame projection (the rate anchor): per-player stat means + implied minutes + team totals."""
    h, a = TeamModel.from_cache(home), TeamModel.from_cache(away)
    res = simulate_game_fast(h, a, n_sims=4000, seed=2026, anchor=True, defense=True)
    means, m0 = {}, {}
    for pid, d in res.players.items():
        means[pid] = {"pts": float(d["mean"]["pts"]), "reb": float(d["reb_mean"]),
                      "ast": float(d["mean"]["ast"]), "fg3m": float(d["mean"]["fg3m"]),
                      "stl": float(d["mean"]["stl"]), "blk": float(d["mean"]["blk"]),
                      "name": d["name"], "team": d["team"]}
    for tm in (h, a):
        share = defaultdict(float)
        for L, p in zip(tm.lineup_ids, tm.lineup_p):
            for pid in L:
                share[pid] += float(p)
        for pid, s in share.items():
            m0[pid] = 48.0 * s
    proj_home, proj_away = float(np.median(res.home_total)), float(np.median(res.away_total))
    return means, m0, proj_home, proj_away


# --------------------------------------------------------------------------- per-player remaining model
def project_player(pre, m0, st_pl, frac_rem, frac_el, margin_abs, cfg):
    """Project one player's final stat line from a live state. cfg toggles each in-game variable.
    Baseline (all-off) = stat_so_far + pregame_mean * frac_game_remaining (per-player analog of team B)."""
    out = {}
    min_so_far = float(st_pl.get("min") or 0.0)
    pf = float(st_pl.get("pf") or 0.0)
    is_starter = bool(st_pl.get("is_starter"))
    # remaining-minutes multiplier (relative to the pregame share built into pregame_mean*frac_rem)
    mult = 1.0
    if pf >= 6:                                                # fouled out -> no remaining production
        mult = 0.0
    else:
        if cfg.get("share") and min_so_far > 4 and frac_el > 0.05 and m0 and m0 > 4:
            realized_share = (min_so_far / max(frac_el, 1e-6)) / GAME_MIN   # realized min per game-min, /48
            pregame_share = m0 / GAME_MIN
            mult *= float(np.clip(realized_share / max(pregame_share, 1e-6), 0.4, 2.0))
        rem_min_est = min_so_far * (frac_rem / max(frac_el, 1e-6)) if frac_el > 0.02 else 0.0
        if cfg.get("foulout") and min_so_far > 3 and pf >= 1:
            exp_more = (pf / min_so_far) * rem_min_est
            if exp_more > (6 - pf):
                mult *= max(0.45, (6 - pf) / max(exp_more, 1e-6))
        if cfg.get("cap"):                                     # season minutes cap (fatigue)
            cap_rem = max(0.0, 42.0 - min_so_far)
            if rem_min_est > 1e-6:
                mult *= min(1.0, cap_rem / rem_min_est)
        if cfg.get("garbage") and frac_rem < 0.20 and margin_abs >= 16:
            mult *= 0.55 if is_starter else 1.6
    heat = 1.0
    if cfg.get("heat") and min_so_far > 6:
        exp_pts = pre["pts"] * (min_so_far / GAME_MIN)         # pregame-paced pts by now
        if exp_pts > 1:
            heat = float(np.clip(1.0 + 0.10 * (st_pl["pts"] / exp_pts - 1.0), 0.92, 1.12))
    for s in STATS:
        floor = float(st_pl.get(s) or 0.0)
        rem = pre[s] * frac_rem * mult
        if s == "pts":
            rem *= heat
        out[s] = floor + rem
    return out


def rmse_bias(errs):
    e = np.asarray(errs, dtype=float)
    return (math.sqrt(float(np.mean(e ** 2))), float(np.mean(e))) if len(e) else (float("nan"), float("nan"))


def run(game_key, min_final_min=10.0):
    gid = GAMES[game_key]
    home_m, away_m = HOMEAWAY[game_key]
    states = load_states(gid)
    fin_pl, fin_h, fin_a, ht, at_ = actual_final(states)
    means, m0, proj_h, proj_a = pregame_anchor(home_m, away_m)
    proj_rem_h, proj_rem_a = proj_h, proj_a                    # pregame remaining-pace totals per side
    home_won = 1 if fin_h > fin_a else 0

    CONFIGS = {
        "baseline":   dict(),
        "+share":     dict(share=True),
        "+foulout":   dict(foulout=True),
        "+garbage":   dict(garbage=True),
        "+cap":       dict(cap=True),
        "+heat":      dict(heat=True),
        "FULL":       dict(share=True, foulout=True, garbage=True, cap=True, heat=True),
    }
    team_err = defaultdict(list)         # bucket -> [signed errs] for team score (model B)
    wp_brier = defaultdict(list)         # bucket -> [(p-actual)^2]
    pp_err = {c: {s: defaultdict(list) for s in STATS} for c in CONFIGS}  # cfg -> stat -> bucket -> errs
    n_states = 0

    rotation = {pid for pid, v in fin_pl.items() if v["min"] >= min_final_min and pid in means}
    for st in states:
        el = elapsed_min(st["period"], st["clock_s"])
        if el < 6 or el > 47.5:
            continue
        frac_rem = max(0.0, (GAME_MIN - el) / GAME_MIN)
        frac_el = el / GAME_MIN
        bucket = f"Q{min(int(st['period']), 4)}"
        n_states += 1
        # TEAM model B (score-anchored + stable pregame pace)
        predB_h = st["home_score"] + proj_rem_h * frac_rem
        predB_a = st["away_score"] + proj_rem_a * frac_rem
        team_err[bucket].append(predB_h - fin_h); team_err[bucket].append(predB_a - fin_a)
        team_err["ALL"].append(predB_h - fin_h); team_err["ALL"].append(predB_a - fin_a)
        # WIN PROB from projected margin
        margin = predB_h - predB_a
        sigma = max(2.0, 13.5 * math.sqrt(max(frac_rem, 1e-6)))
        p_home = 0.5 * (1 + math.erf(margin / (sigma * math.sqrt(2))))
        for b in (bucket, "ALL"):
            wp_brier[b].append((p_home - home_won) ** 2)
        # PER-PLAYER, every config
        margin_abs = abs(st["home_score"] - st["away_score"])
        for pid in rotation:
            if pid not in st["players"]:
                continue
            pre, stp = means[pid], st["players"][pid]
            for cname, cfg in CONFIGS.items():
                proj = project_player(pre, m0.get(pid, 0.0), stp, frac_rem, frac_el, margin_abs, cfg)
                for s in STATS:
                    err = proj[s] - fin_pl[pid][s]
                    pp_err[cname][s][bucket].append(err)
                    pp_err[cname][s]["ALL"].append(err)
    return dict(game=game_key, gid=gid, home=ht, away=at_, final=(fin_h, fin_a), home_won=home_won,
                n_states=n_states, n_rotation=len(rotation), proj_pre=(round(proj_h, 1), round(proj_a, 1)),
                team_err=team_err, wp_brier=wp_brier, pp_err=pp_err, CONFIGS=list(CONFIGS))


def report(R):
    print("=" * 96)
    print(f"PBP REPLAY — {R['game']} ({R['gid']})  {R['away']} @ {R['home']}  actual {R['final'][0]}-{R['final'][1]}"
          f"  | pregame sim proj {R['home']} {R['proj_pre'][0]} {R['away']} {R['proj_pre'][1]}")
    print(f"  states graded: {R['n_states']}  | rotation players: {R['n_rotation']}  (RMSE + signed BIAS, NEVER MAE)")
    print("=" * 96)
    print("\nTEAM SCORE (model B: score-anchor + stable pregame pace) by game-time:")
    print(f"  {'bucket':6s} {'n':>4s} | {'RMSE':>6s}  {'bias':>6s}")
    for b in ("Q1", "Q2", "Q3", "Q4", "ALL"):
        if b in R["team_err"]:
            r, bi = rmse_bias(R["team_err"][b])
            print(f"  {b:6s} {len(R['team_err'][b]):>4d} | {r:6.1f}  {bi:+6.1f}")
    print("\nWIN PROB (Brier vs actual_home_won) by game-time:")
    for b in ("Q1", "Q2", "Q3", "Q4", "ALL"):
        if b in R["wp_brier"]:
            arr = R["wp_brier"][b]
            print(f"  {b:6s} {len(arr):>4d} | Brier {np.mean(arr):.4f}")
    print("\nPER-PLAYER stat projection — RMSE / bias (ALL states) by config:")
    print(f"  {'config':10s} | " + "  ".join(f"{s:>14s}" for s in STATS))
    for c in R["CONFIGS"]:
        cells = []
        for s in STATS:
            r, bi = rmse_bias(R["pp_err"][c][s]["ALL"])
            cells.append(f"{r:5.2f}/{bi:+5.2f}")
        print(f"  {c:10s} | " + "  ".join(f"{x:>14s}" for x in cells))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="G3", choices=list(GAMES))
    ap.add_argument("--json-out", default="")
    a = ap.parse_args()
    R = run(a.game)
    report(R)
    if a.json_out:
        ser = dict(R)
        for k in ("team_err", "wp_brier"):
            ser[k] = {b: rmse_bias(v) if k == "team_err" else float(np.mean(v)) for b, v in R[k].items()}
        ser["pp_err"] = {c: {s: {b: rmse_bias(v) for b, v in R["pp_err"][c][s].items()} for s in STATS}
                         for c in R["CONFIGS"]}
        json.dump(ser, open(a.json_out, "w"), indent=2)
        print(f"\nwrote {a.json_out}")


if __name__ == "__main__":
    main()
