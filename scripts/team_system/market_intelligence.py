"""market_intelligence.py — the UNIFIED full-market engine (pregame + IN-GAME ready).

One coherent possession sim -> the ENTIRE market menu + the scenario distribution + an inconsistency
audit. Models and prices EVERY bet (player every-stat tiers, alt-lines, combos, double/triple-doubles,
5x5, 50-burst longshots at +10000, team/game derivatives, blowout/shootout/rockfight/OT scenarios) as a
method of basketball intelligence. In-game: pass a live `state` (current box + minutes remaining) and it
re-prices the whole menu from a rest-of-game sim.

THE HONESTY LAYER (the "see all inconsistencies" function): every market is tagged with a CALIBRATION
TIER so you know what to trust:
  TRUSTWORTHY      -- off the calibrated marginals (the prop-model walk-forward MAE)
  JOINT_PENDING    -- combo/DD: sim models same-player cross-stats ~independent (corr~0) vs realized
                      +0.2..0.35 -> star combos/DDs are UNDER-priced; fix = CV_MIN_VAR (candidate).
  TAIL_APPROX      -- extreme tails (35+/40+/TD): intervals under-dispersed (cov80 ~74-78%) -> approx,
                      likely conservative.
  LONGSHOT         -- +1500 or longer: the least-reliable cell; price it, but it lives in the thin tail.
  TOTAL_BIASED     -- team-total overs inherit the sim's +12..22 Finals total over-prediction -> biased
                      HIGH; deflate before use (actual Finals totals 200/209/226).
NO EDGE is claimed: edge = sim_prob vs the book's de-vigged prob, which needs CAPTURED prices (absent
offline) + forward CLV (Oct-2026). This prints the model's view of "what can happen & how often."
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import simulate_game_fast  # noqa: E402
from min_var_layer import apply_min_var, min_cv_map  # noqa: E402

DD = ("pts", "reb", "ast", "stl", "blk")
_JOINT_FIX = {"on": False}  # set by --joint-fix; relabels JOINT cells corrected vs pending


def fair(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return f"{-round(100*p/(1-p)):+d}" if p >= 0.5 else f"{round(100*(1-p)/p):+d}"


def _tier(market, p, joint=False, total=False):
    # longshot = LOW-probability UNDERDOG (+1500 or longer), not a heavy favorite near-lock.
    if total and "over" in market:
        return "TOTAL_BIASED"
    if joint:
        return "JOINT_CORRECTED" if _JOINT_FIX["on"] else "JOINT_PENDING"
    if "triple_double" in market or "50+" in market or "5x5" in market or p < 0.06:
        return "LONGSHOT"             # structural longshot or ~+1500-or-longer underdog
    if p < 0.13:                      # low-probability upper tail (under-dispersed -> approx)
        return "TAIL_APPROX"
    return "TRUSTWORTHY"              # includes near-locks (high p) -- reliable


def rest_of_game(home, away, nsims, state):
    """IN-GAME: rest-of-game sim scaled to fraction remaining, + current box. Honest approximation of the
    production unified_projector (frozen-current + RoG sim)."""
    res = simulate_game_fast(home, away, n_sims=nsims, seed=2026, anchor=True, defense=True)
    frac = max(0.0, min(1.0, state.get("minutes_remaining", 48) / 48.0))
    cur = state.get("players", {})
    for pid, d in res.players.items():
        c = cur.get(d["name"], {})
        for stat, arr in d["samples"].items():
            d["samples"][stat] = c.get(stat, 0.0) + np.asarray(arr) * frac
    hs0, as0 = state.get("home_score", 0), state.get("away_score", 0)
    res.home_total = hs0 + res.home_total * frac
    res.away_total = as0 + res.away_total * frac
    return res


def price_player(name, s):
    out = []
    pts, reb, ast = (np.asarray(s["pts"]), np.asarray(s["reb"]), np.asarray(s["ast"]))
    fg3m = np.asarray(s.get("fg3m", np.zeros_like(pts))); stl = np.asarray(s.get("stl", np.zeros_like(pts)))
    blk = np.asarray(s.get("blk", np.zeros_like(pts)))
    ddc = sum((np.asarray(s.get(k, np.zeros_like(pts))) >= 10).astype(int) for k in DD)
    def add(m, mask, joint=False):
        p = float(np.mean(mask)); out.append((m, p, fair(p), _tier(m, p, joint)))
    for t in (10, 15, 20, 25, 30, 35, 40, 50):
        add(f"pts {t}+", pts >= t)
    for t in (6, 8, 10, 12, 15):
        add(f"reb {t}+", reb >= t)
    for t in (5, 8, 10, 12):
        add(f"ast {t}+", ast >= t)
    for t in (2, 3, 4, 5, 6):
        add(f"3PM {t}+", fg3m >= t)
    add("stocks 3+", (stl + blk) >= 3); add("stocks 4+", (stl + blk) >= 4)
    for t in (25, 30, 35, 40, 45):
        add(f"pra {t}+", (pts + reb + ast) >= t)
    add("pts25 & reb10", (pts >= 25) & (reb >= 10), joint=True)
    add("pts25 & ast8", (pts >= 25) & (ast >= 8), joint=True)
    add("20/10/5", (pts >= 20) & (reb >= 10) & (ast >= 5), joint=True)
    add("double_double", ddc >= 2, joint=True)
    add("triple_double", ddc >= 3, joint=True)
    add("5x5 (5+ in five cats)", sum((np.asarray(s.get(k, np.zeros_like(pts))) >= 5).astype(int) for k in DD) >= 5, joint=True)
    return out


def scenarios(res):
    hs, as_ = res.home_total, res.away_total
    tot, mar = hs + as_, hs - as_
    return [
        ("blowout 15+ (either)", float(np.mean(np.abs(mar) >= 15))),
        ("blowout 20+ (either)", float(np.mean(np.abs(mar) >= 20))),
        ("nail-biter (within 3)", float(np.mean(np.abs(mar) <= 3))),
        ("OT-likely (within 2)", float(np.mean(np.abs(mar) <= 2))),
        ("shootout (total 230+)", float(np.mean(tot >= 230))),
        ("track-meet (total 240+)", float(np.mean(tot >= 240))),
        ("rock-fight (total < 205)", float(np.mean(tot < 205))),
        ("low game (total < 195)", float(np.mean(tot < 195))),
    ]


def hot_game(res):
    pts = {d["name"]: np.asarray(d["samples"]["pts"]) for d in res.players.values()}
    any35 = np.zeros(len(next(iter(pts.values()))), dtype=bool)
    any40 = any35.copy()
    for arr in pts.values():
        any35 |= arr >= 35; any40 |= arr >= 40
    return float(any35.mean()), float(any40.mean())


def main():
    ap = argparse.ArgumentParser(description="Unified full-market intelligence engine (pregame + in-game)")
    ap.add_argument("--home", default="NYK"); ap.add_argument("--away", default="SAS")
    ap.add_argument("--nsims", type=int, default=20000); ap.add_argument("--min-pts", type=float, default=12.0)
    ap.add_argument("--state", default="", help="JSON file with a live in-game state (re-prices the whole menu)")
    ap.add_argument("--joint-fix", action="store_true", help="apply CV_MIN_VAR joint corrector (combo/DD/longshot cells)")
    a = ap.parse_args()
    h = TeamModel.from_cache(a.home); aw = TeamModel.from_cache(a.away)
    mode = "PREGAME"
    if a.state and os.path.exists(a.state):
        st = json.load(open(a.state, encoding="utf-8")); res = rest_of_game(h, aw, a.nsims, st)
        mode = f"IN-GAME (re-priced from live state, {st.get('minutes_remaining','?')} min left)"
    else:
        res = simulate_game_fast(h, aw, n_sims=a.nsims, seed=2026, anchor=True, defense=True)
    if a.joint_fix:
        _JOINT_FIX["on"] = True
        apply_min_var(res, min_cv_map(), seed=2026)   # joint correction; marginals preserved EXACTLY
        mode += " +CV_MIN_VAR(joint)"

    print("=" * 92)
    print(f"FULL-MARKET INTELLIGENCE — {a.away} @ {a.home}  [{mode}, {a.nsims} sims]")
    print("  models & prices EVERY market. tiers: TRUSTWORTHY / JOINT_PENDING(CV_MIN_VAR) / TAIL_APPROX / LONGSHOT / TOTAL_BIASED")
    print("=" * 92)
    tier_counts, n = {}, 0
    rows = sorted(res.players.items(), key=lambda x: -x[1]["mean"]["pts"])
    for pid, d in rows:
        if d["mean"]["pts"] < a.min_pts:
            continue
        print(f"\n{d['name']} ({d['team']})")
        for m, p, odds, tier in price_player(d["name"], d["samples"]):
            if 0.003 < p < 0.997:
                tier_counts[tier] = tier_counts.get(tier, 0) + 1; n += 1
                mark = "" if tier == "TRUSTWORTHY" else f"  <-{tier}"
                print(f"   {m:24s} {p*100:5.1f}%  ({odds:>6s}){mark}")
    print(f"\nGAME SCENARIOS (what can happen):")
    for m, p in scenarios(res):
        print(f"   {m:26s} {p*100:5.1f}%  ({fair(p):>6s})"); n += 1
    h35, h40 = hot_game(res)
    print(f"   {'hot game (a 35+ scorer)':26s} {h35*100:5.1f}%  ({fair(h35):>6s})")
    print(f"   {'explosion (a 40+ scorer)':26s} {h40*100:5.1f}%  ({fair(h40):>6s})  <-TAIL_APPROX")
    print(f"\nINCONSISTENCY / CALIBRATION AUDIT (the LLM-reasoning honesty layer):")
    print(f"   markets priced: {n}  |  tier mix: {tier_counts}")
    print("   * JOINT_PENDING cells (DD / combos): sim cross-stat corr ~0 vs realized +0.2..0.35 -> star")
    print("     double-doubles & positive combos are UNDER-priced -> fix = CV_MIN_VAR (validated candidate).")
    print("   * TAIL_APPROX / LONGSHOT cells: intervals under-dispersed -> extreme overs likely CONSERVATIVE.")
    print("   * TOTAL_BIASED: team-total overs inherit +12..22 Finals over-prediction -> deflate (totals 200/209/226).")
    print("   * EDGE needs captured book prices (absent offline) + forward CLV (Oct-2026). This is the model's view,")
    print("     not a bet. In-game: pass --state <live.json> to re-price the whole menu from the current box + clock.")


if __name__ == "__main__":
    main()
