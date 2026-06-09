"""Live "X+" milestone / breakout sheet for the current game.

For people who bet MILESTONE / "to record X+" markets (NOT over/under): for every
player it prints the "X+" ladders (pts / reb / ast / threes / stl / blk + combos
PRA / P+R / P+A / R+A + double-double / triple-double) with an honest hit
probability P(final >= X).

Probability model (transparent):
  * center  = the LIVE projected final (box_score paced_final, updates each poll)
  * sigma   = pregame spread from the slate (q90-q10)/2.563, SCALED by
              sqrt(game-minutes-remaining / 48) so it tightens as the game runs
  * banked  = if the player's CURRENT stat already >= X, the milestone is LOCKED
              (shown as HIT) -- only the remaining portion carries uncertainty
  * P(>=X)  = 1 - Phi((X - 0.5 - center)/sigma)   [normal approx + continuity corr]

Read-only. Safe to run any time during the game.

Usage:
  python scripts/cv_breakout_plus.py [--game 0042500402] [--date 2026-06-05]
                                     [--min-prob 0.04] [--side both|home|away]
                                     [--top N]  (only the N most notable per player)
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import os
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STAT_TIERS = {
    "pts": [10, 15, 20, 25, 30, 35, 40],
    "reb": [4, 6, 8, 10, 12, 15],
    "ast": [4, 6, 8, 10, 12],
    "fg3m": [1, 2, 3, 4, 5, 6],
    "stl": [1, 2, 3],
    "blk": [1, 2, 3],
}
COMBO_TIERS = {
    "PRA": (("pts", "reb", "ast"), [20, 25, 30, 35, 40, 45, 50]),
    "P+R": (("pts", "reb"), [15, 20, 25, 30, 35, 40]),
    "P+A": (("pts", "ast"), [15, 20, 25, 30, 35, 40]),
    "R+A": (("reb", "ast"), [8, 10, 12, 15, 18]),
}
STAT_LABEL = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "3PM",
              "stl": "STL", "blk": "BLK"}


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _p_at_least(x: int, mean: float, sigma: float, current: float) -> float:
    """P(final >= x). Banked current locks it; else normal approx + cont. corr."""
    if current is not None and current >= x:
        return 1.0
    if sigma <= 1e-6:
        return 1.0 if mean >= x else 0.0
    # remaining uncertainty only -- the banked 'current' is certain
    return 1.0 - _phi((x - 0.5 - mean) / sigma)


def _fetch_box(game: str) -> dict:
    url = f"http://127.0.0.1:8077/api/box_score?game_id={game}"
    with urllib.request.urlopen(url, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def _game_clock_rem_frac(game: str) -> float:
    files = sorted(glob.glob(os.path.join(HERE, "data", "live", f"{game}_*.json")))
    if not files:
        return 1.0
    try:
        d = json.loads(open(files[-1], encoding="utf-8").read())
    except Exception:
        return 1.0
    try:
        period = int(d.get("period") or 1)
    except Exception:
        period = 1
    clk = str(d.get("clock") or "12:00")
    try:
        mm, ss = clk.split(":")
        crem = int(mm) + float(ss) / 60.0
    except Exception:
        crem = 12.0
    if "FINAL" in str(d.get("game_status") or "").upper():
        return 0.0
    rem = max(0.0, (4 - period) * 12.0 + crem) if period <= 4 else max(0.0, crem)
    return max(0.0, min(1.0, rem / 48.0))


def _load_slate_spread(date: str) -> dict:
    """player_id -> {stat: sigma_pregame} from (q90-q10)/2.563."""
    path = os.path.join(HERE, "data", "predictions", f"slate_{date}.csv")
    out: dict = {}
    if not os.path.exists(path):
        return out
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                pid = int(row.get("player_id"))
            except Exception:
                continue
            stat = row.get("stat")
            try:
                q10 = float(row.get("q10")); q90 = float(row.get("q90"))
            except Exception:
                continue
            sig = max(0.0, (q90 - q10) / 2.563)
            out.setdefault(pid, {})[stat] = sig
    return out


def _band(p: float) -> str:
    if p >= 0.995:
        return "HIT "
    if p >= 0.78:
        return "STRONG"
    if p >= 0.58:
        return "LEAN  "
    if p >= 0.35:
        return "COIN  "
    return "DART  "


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="0042500402")
    ap.add_argument("--date", default="2026-06-05")
    ap.add_argument("--min-prob", type=float, default=0.04)
    ap.add_argument("--side", default="both", choices=["both", "home", "away"])
    ap.add_argument("--top", type=int, default=0, help="only N most notable per player")
    args = ap.parse_args()

    box = _fetch_box(args.game)
    rem_frac = _game_clock_rem_frac(args.game)
    sig_scale = math.sqrt(max(rem_frac, 0.02))
    spreads = _load_slate_spread(args.date)

    # default per-stat sigma if the slate lacks a player (pregame league-ish)
    DEF_SIG = {"pts": 7.0, "reb": 3.0, "ast": 2.6, "fg3m": 1.5, "stl": 1.0, "blk": 1.0}

    hs = box.get("home_score"); as_ = box.get("away_score")
    print("=" * 74)
    away = box.get("away", {}).get("abbr"); home = box.get("home", {}).get("abbr")
    ct = {}
    for s in ("away", "home"):
        ct[s] = (box.get(s, {}).get("current_total_pts"))
    print(f"  {away} {ct.get('away')}  @  {home} {ct.get('home')}   "
          f"(game-time remaining {rem_frac*48:.0f} min  |  sigma x{sig_scale:.2f})")
    print(f"  X+ MILESTONE SHEET  -  P = chance player RECORDS that line (final >= X)")
    print("=" * 74)

    sides = ["away", "home"] if args.side == "both" else [args.side]
    for side in sides:
        team = box.get(side, {})
        abbr = team.get("abbr")
        players = team.get("players") or []
        # sort by projected pts desc
        players = sorted(players, key=lambda p: -(p.get("pts") or 0))
        print(f"\n################  {abbr}  ################")
        for p in players:
            # LIVE projection = paced_final (top-level p[s] is STALE pregame).
            _pf = p.get("paced_final") or {}
            cur = {s: ((p.get("current") or {}).get(s) or 0.0) for s in STAT_TIERS}
            proj = {s: max(float(_pf.get(s, p.get(s) or 0.0)), cur[s]) for s in STAT_TIERS}
            if max(proj.values()) < 1.0:
                continue  # deep bench / DNP
            pid = p.get("player_id")
            mp = p.get("minutes_played")
            # rotation filter: drop DNP / deep-bench filler (no proj, hasn't played)
            played = (mp is not None and mp >= 0.5) or any(cur[s] > 0 for s in STAT_TIERS)
            if proj["pts"] < 3.0 and not played:
                continue
            sp = spreads.get(pid, {})
            name = p.get("player_name") or p.get("player") or str(pid)
            cur_line = (f"{cur['pts']:.0f}p {cur['reb']:.0f}r {cur['ast']:.0f}a "
                        f"{cur['fg3m']:.0f}x3")
            proj_line = (f"{proj['pts']:.1f}p {proj['reb']:.1f}r {proj['ast']:.1f}a "
                         f"{proj['fg3m']:.1f}x3")
            mtxt = f"  | {mp:.0f}m" if mp is not None else ""
            print(f"\n  {name}   (now {cur_line}  ->  proj {proj_line}{mtxt})")

            rows = []  # (prob, text)
            # single-stat ladders
            for s, tiers in STAT_TIERS.items():
                sig = (sp.get(s, DEF_SIG[s])) * sig_scale
                sig = max(sig, 0.25)
                for x in tiers:
                    pr = _p_at_least(x, proj[s], sig, cur[s])
                    if pr < args.min_prob or pr > 0.999 and cur[s] < x:
                        if cur[s] < x and pr < args.min_prob:
                            continue
                    if cur[s] >= x:
                        rows.append((1.0, f"{x}+ {STAT_LABEL[s]:<3}  HIT   (banked {cur[s]:.0f})"))
                    elif pr >= args.min_prob:
                        rows.append((pr, f"{x}+ {STAT_LABEL[s]:<3}  {pr*100:4.0f}%  {_band(pr)}"))
            # combos
            for label, (parts, tiers) in COMBO_TIERS.items():
                cmean = sum(proj[s] for s in parts)
                ccur = sum(cur[s] for s in parts)
                # combined sigma = sqrt(sum sigma^2) (independence approx)
                csig = math.sqrt(sum((sp.get(s, DEF_SIG[s]) * sig_scale) ** 2 for s in parts))
                csig = max(csig, 0.3)
                for x in tiers:
                    if ccur >= x:
                        rows.append((1.0, f"{x}+ {label:<3}  HIT   (banked {ccur:.0f})"))
                        continue
                    pr = _p_at_least(x, cmean, csig, ccur)
                    if pr >= args.min_prob and pr <= 0.985:
                        rows.append((pr, f"{x}+ {label:<3}  {pr*100:4.0f}%  {_band(pr)}"))
            # double-double / triple-double
            dd_cats = [s for s in ("pts", "reb", "ast") if proj[s] >= 6 or cur[s] >= 8]
            def _p10(s):
                return _p_at_least(10, proj[s], max((sp.get(s, DEF_SIG[s]) * sig_scale), 0.25), cur[s])
            cats3 = ["pts", "reb", "ast", "stl", "blk"]
            p10 = {s: _p10(s) for s in ["pts", "reb", "ast"]}
            # DD = at least two of pts/reb/ast >= 10
            ps = sorted(p10.values(), reverse=True)
            p_dd = ps[0] * ps[1] + ps[0] * ps[2] + ps[1] * ps[2] - 2 * ps[0] * ps[1] * ps[2]
            p_td = ps[0] * ps[1] * ps[2]
            banked10 = sum(1 for s in ("pts", "reb", "ast") if cur[s] >= 10)
            if p_dd >= max(args.min_prob, 0.06) or banked10 >= 2:
                tag = "HIT  " if banked10 >= 2 else f"{p_dd*100:4.0f}% {_band(p_dd)}"
                rows.append((min(p_dd, 0.99) if banked10 < 2 else 1.0, f"DOUBLE-DOUBLE {tag}"))
            if p_td >= 0.04 or banked10 >= 3:
                tag = "HIT  " if banked10 >= 3 else f"{p_td*100:4.0f}% {_band(p_td)}"
                rows.append((min(p_td, 0.99) if banked10 < 3 else 1.0, f"TRIPLE-DOUBLE {tag}"))

            rows.sort(key=lambda r: -r[0])
            if args.top > 0:
                rows = rows[:args.top]
            for _, text in rows:
                print(f"      {text}")
    print("\n" + "=" * 74)
    print("  HIT=banked  STRONG>=78%  LEAN>=58%  COIN>=35%  DART<35% (longshot/ceiling)")
    print("  P uses LIVE projection + pregame spread scaled by time left. Re-run any time.")


if __name__ == "__main__":
    main()
