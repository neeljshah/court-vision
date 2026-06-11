"""g4_ingame.py — ONE COMMAND, game-night ready: live in-game re-price for the upcoming game (G4).

Point it at the live feed and it re-prices the ENTIRE market menu from the current box + clock using the
**replay-VALIDATED** in-game projector and surfaces the headline live read:

    python scripts/team_system/g4_ingame.py                 # auto: latest data/live/0042500404_*.json (pre-tip -> pregame)
    python scripts/team_system/g4_ingame.py --snapshot <f>  # re-price a specific snapshot (e.g. replay a G1-G3 state)
    python scripts/team_system/g4_ingame.py --pregame       # force the pregame board

WHAT "VALIDATED + AT ITS BEST" MEANS HERE (proof: .planning/replay/REPLAY_SCORECARD.md, n=11,553 player-states):
  * TEAM score + win prob = model B (score-ANCHOR + STABLE pregame pace). RMSE shrinks monotonically by quarter
    (Q1 12.5 -> Q4 4.2); live-pace extrapolation (model C) is a REFUTED trap. The total is deflated EARLY (the sim
    over-predicts the Finals total +12 in the grind), and self-corrects late as the realized score dominates.
  * PER-PLAYER props = baseline (realized floor + pregame_mean*frac_remaining) + the ONE validated variable, the
    FOUL-OUT haircut (pts dRMSE -0.094, bias-tightening, consistent across G1/G2/G3). Minute-share / heat / FULL
    were REFUTED on RMSE+bias and are NOT applied. garbage-time stays off (untested: no qualifying state in 3 games).
  * JOINT cells (DD/TD/combos) corrected by CV_MIN_VAR (marginals preserved EXACTLY).
  * Honest: PROJECTION, not edge. Playoffs have no proven model edge. AST raw. Zero real money. EDGE on any cell
    needs captured book prices (absent offline) + forward CLV (Oct-2026). This is the model's view of what can happen.

Reuses scripts/team_system/market_intelligence.py pricing (no production-code edits -> all tests stay green).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import device, simulate_game_fast  # noqa: E402
import market_intelligence as MI  # noqa: E402
from min_var_layer import apply_min_var, min_cv_map  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GAME_ID, HOME, AWAY = "0042500404", "NYK", "SAS"
GAME_MIN = 48.0
STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk")


def _elapsed_min(period, clock_s):
    if period <= 0:
        return 0.0
    if period <= 4:
        return (period - 1) * 12.0 + (12.0 - clock_s / 60.0)
    return 48.0 + (period - 5) * 5.0 + (5.0 - clock_s / 60.0)


def foulout_mult(pf, min_so_far, frac_rem, frac_el):
    """The ONE validated in-game per-player variable (foul-out haircut on remaining minutes).
    pf>=6 -> 0 remaining; foul-prone -> haircut toward (fouls left)/(expected more fouls). Mirrors the
    replay-validated branch in pbp_replay.project_player. Returns a multiplier on the remaining term."""
    if pf >= 6:
        return 0.0
    if min_so_far <= 3 or pf < 1 or frac_el <= 0.02:
        return 1.0
    rem_min_est = min_so_far * (frac_rem / frac_el)
    exp_more = (pf / min_so_far) * rem_min_est
    if exp_more > (6 - pf):
        return max(0.45, (6 - pf) / max(exp_more, 1e-6))
    return 1.0


def latest_snapshot(game_id, path=None):
    if path:
        return json.load(open(path, encoding="utf-8")), os.path.basename(path)
    files = sorted(glob.glob(os.path.join(ROOT, "data", "live", f"{game_id}_*.json")))
    if not files:
        return None, None
    return json.load(open(files[-1], encoding="utf-8")), os.path.basename(files[-1])


def parse_state(snap):
    """Raw live snapshot (data/live format) -> (period, clock_s, elapsed, frac_rem, frac_el, scores, players-by-name)."""
    cs = MI_parse_clock(snap.get("clock"))
    per = int(snap.get("period") or 0)
    el = _elapsed_min(per, cs)
    rem_min = (GAME_MIN - el) if per <= 4 else (cs / 60.0)   # OT-aware: in OT, remaining = current-period clock
    frac_rem = max(0.0, rem_min) / GAME_MIN
    frac_el = el / GAME_MIN
    players = {}
    for p in snap.get("players", []):
        players[p["name"]] = {s: float(p.get(s) or 0) for s in STATS}
        players[p["name"]]["min"] = float(p.get("min") or 0.0)
        players[p["name"]]["pf"] = float(p.get("pf") or 0.0)
        players[p["name"]]["team"] = p.get("team")
    return dict(period=per, clock_s=cs, elapsed=el, frac_rem=frac_rem, frac_el=frac_el,
               home_score=int(snap.get("home_score") or 0), away_score=int(snap.get("away_score") or 0),
               home_team=snap.get("home_team", HOME), away_team=snap.get("away_team", AWAY),
               status=snap.get("game_status", ""), players=players)


def MI_parse_clock(c):
    if isinstance(c, (int, float)):
        return float(c)
    s = str(c).strip()
    if s[:2].upper() == "PT":                          # ISO-8601 duration, the raw cdn.nba.com liveData clock (PT##M##.##S)
        mm = re.search(r"(\d+)M", s); ss = re.search(r"([\d.]+)S", s)
        return (float(mm.group(1)) * 60 if mm else 0.0) + (float(ss.group(1)) if ss else 0.0)
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


def project(home_m, away_m, nsims, st, seed=2026, out_names=None):
    """Validated in-game projection: team = model B; per-player = floor + sim*frac*foulout_mult; then CV_MIN_VAR."""
    out_names = {n.strip() for n in (out_names or set()) if n.strip()}
    h, a = TeamModel.from_cache(home_m), TeamModel.from_cache(away_m)
    res = simulate_game_fast(h, a, n_sims=nsims, seed=seed, anchor=True, defense=True)
    if st is None:                                    # PRE-TIP: pure pregame board
        apply_min_var(res, min_cv_map(), seed=seed)
        return res, 1.0
    frac, frac_el = st["frac_rem"], st["frac_el"]
    sqf = float(np.sqrt(frac))                        # remaining VARIANCE scales linearly -> SD ~ sqrt(frac)
    cur = st["players"]

    def rest(arr, floor, mult):
        """remaining production with CORRECT dispersion: mean ~ E*frac, SD ~ SD*sqrt(frac); + realized floor,
        TRUNCATED at the floor (counts are monotone non-decreasing -- a player/team can never UN-score what's
        already on the board). Linear arr*frac under-disperses (over-confident WP); this matches the
        replay-validated sigma ~ sqrt(frac_remaining)."""
        a = np.asarray(arr, dtype=float); mu = a.mean()
        return np.maximum(floor + (mu * frac + (a - mu) * sqf) * mult, floor)

    for pid, d in res.players.items():
        c = cur.get(d["name"], {})
        mult = 0.0 if d["name"] in out_names else foulout_mult(  # --out: injury/ejection -> no remaining production
            c.get("pf", 0.0), c.get("min", 0.0), frac, frac_el)  # else the validated foul-out variable
        for stat, arr in d["samples"].items():
            floor = c.get(stat, 0.0) if stat in STATS else 0.0
            d["samples"][stat] = rest(arr, floor, mult)
    res.home_total = rest(res.home_total, st["home_score"], 1.0)   # clean model B + correct dispersion, never < current
    res.away_total = rest(res.away_total, st["away_score"], 1.0)
    apply_min_var(res, min_cv_map(), seed=seed)                    # joint correction (marginals preserved)
    return res, frac


def deflate_total(raw_total, frac_rem):
    """The Finals total over-prediction is regime-concentrated (+~12 early). Anchor-blend it down by the
    fraction of the game still being PROJECTED (the realized part needs no deflation)."""
    return raw_total - 12.0 * frac_rem


def main():
    ap = argparse.ArgumentParser(description="G4 live in-game re-pricer (validated projector)")
    ap.add_argument("--game-id", default=GAME_ID); ap.add_argument("--home", default=HOME); ap.add_argument("--away", default=AWAY)
    ap.add_argument("--snapshot", default=""); ap.add_argument("--pregame", action="store_true")
    ap.add_argument("--nsims", type=int, default=20000); ap.add_argument("--min-pts", type=float, default=10.0)
    ap.add_argument("--out", default="", help="comma-sep player names who LEFT the game (injury/ejection/DNP) -> no remaining production")
    a = ap.parse_args()
    snap, fname = (None, None) if a.pregame else latest_snapshot(a.game_id, a.snapshot or None)
    st = parse_state(snap) if snap else None
    if st and st["period"] == 0:                       # snapshot exists but tip hasn't happened
        st = None
    gid_disp = (snap.get("game_id") if snap else None) or a.game_id   # honest header: the snapshot's OWN game id
    MI._JOINT_FIX["on"] = True
    res, frac = project(a.home, a.away, a.nsims, st, out_names=set(a.out.split(",")) if a.out else None)

    hs, as_ = np.asarray(res.home_total), np.asarray(res.away_total)
    wp = float(np.mean(hs > as_) + 0.5 * np.mean(hs == as_))   # ties = half-win (a tie is NOT an away win)
    proj_h, proj_a = float(np.median(hs)), float(np.median(as_))
    raw_total = proj_h + proj_a
    if st is None:
        mode = "PRE-TIP / PREGAME"
    else:
        per_lbl = f"Q{st['period']}" if st["period"] <= 4 else f"OT{st['period']-4}"
        clk_disp = snap.get("clock") or f"{int(st['clock_s'])//60}:{int(st['clock_s'])%60:02d}"
        mode = (f"LIVE {per_lbl} {clk_disp} | {st['home_team']} {st['home_score']}-{st['away_score']} "
                f"{st['away_team']} | {frac*48:.1f} min left")
    replay_note = "  [REPLAY of a non-G4 snapshot]" if (st and gid_disp != GAME_ID) else ""
    print("=" * 92)
    print(f"IN-GAME — {a.away} @ {a.home}  ({gid_disp})  [{mode}]{replay_note}   device {device()}, {a.nsims} sims")
    print(f"  src: {fname or 'pregame sim'}   projector: model-B score-anchor + foul-out (validated) + CV_MIN_VAR joint")
    print("=" * 92)
    dt = deflate_total(raw_total, frac) if st else deflate_total(raw_total, 1.0)
    print(f"\n>>> LIVE WIN PROB: {a.home} {wp:.0%} / {a.away} {1-wp:.0%}"
          f"   |   PROJECTED FINAL: {a.home} {proj_h:.0f} - {a.away} {proj_a:.0f}"
          f"   (margin {a.home} {proj_h-proj_a:+.1f})")
    print(f">>> TOTAL: raw {raw_total:.0f}  ->  DEFLATED ~{dt:.0f}  (trust the deflated total; the sim over-predicts the Finals grind early)")
    if st is None:
        print("    (PRE-TIP read: coin flip — talent leans SAS/Wemby, home+clutch+the 2-1 series lean NYK. PROJECTION, not edge.)")

    # foul-trouble watch (the validated lever in action)
    if st is not None:
        watch = []
        for nm, c in st["players"].items():
            if c.get("pf", 0) >= 3 and c.get("min", 0) > 6:
                m = foulout_mult(c["pf"], c["min"], st["frac_rem"], st["frac_el"])
                if m < 0.999:
                    watch.append((nm, int(c["pf"]), c["team"], m))
        if watch:
            print("\nFOUL-TROUBLE WATCH (remaining-minutes haircut applied — the validated in-game variable):")
            for nm, pf, tm, m in sorted(watch, key=lambda x: x[3]):
                print(f"   {nm:22s} {tm}  {pf} PF  -> remaining x{m:.2f}" + ("  (FOULED OUT)" if m == 0 else ""))

    print(f"\nRE-PRICED MARKET BOARD (tiers: TRUSTWORTHY / JOINT_CORRECTED / TAIL_APPROX / LONGSHOT):")
    tier_counts, n = {}, 0
    for pid, d in sorted(res.players.items(), key=lambda x: -np.median(x[1]["samples"]["pts"])):
        if np.median(d["samples"]["pts"]) < a.min_pts:
            continue
        print(f"\n{d['name']} ({d['team']})")
        for m, p, odds, tier in MI.price_player(d["name"], d["samples"]):
            if 0.003 < p < 0.997:
                tier_counts[tier] = tier_counts.get(tier, 0) + 1; n += 1
                mark = "" if tier == "TRUSTWORTHY" else f"  <-{tier}"
                print(f"   {m:24s} {p*100:5.1f}%  ({odds:>6s}){mark}")
    print(f"\nGAME SCENARIOS (what can still happen):")
    for m, p in MI.scenarios(res):
        print(f"   {m:26s} {p*100:5.1f}%  ({MI.fair(p):>6s})")
    h35, h40 = MI.hot_game(res)
    print(f"   {'a 35+ scorer':26s} {h35*100:5.1f}%   {'a 40+ explosion':26s} {h40*100:5.1f}%")
    print(f"\n   markets priced: {n}  |  tiers: {tier_counts}")
    print("   PROJECTION, not edge. Playoffs no proven model edge. AST raw. Zero real money.")
    print("   Re-run after each possession for the live board; pass --snapshot <data/live/...json> to re-price any state.")


if __name__ == "__main__":
    main()
