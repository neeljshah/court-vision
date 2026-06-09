"""Live model-vs-DraftKings edge sheet (OVERS) + predicted points.

Goes off REAL DraftKings lines (data/lines/<date>_dk_inplay.csv, the live scrape;
falls back to the pregame _dk.csv). For every player/stat with a DK line it shows:
  * DK line + over/under price (the actual market you'd bet)
  * model projected final (live, updates each poll)
  * P(over)  -- model chance the OVER hits (normal approx, banked stats locked)
  * mkt%     -- DK's devigged implied over probability
  * edge     -- P(over) - mkt%   (model's disagreement with the market)
  * EV       -- expected value per $1 on the OVER at the DK over price
  * a LAG flag when the model is merely behind a hot/cold start (early game)

Read-only. Honest: early game the model is pregame-anchored and DK in-play lines
are already game-adjusted, so many "edges" are the model lagging, not real. The
script flags those. Re-run any time.

Usage:
  python scripts/cv_dk_edge.py [--game 0042500402] [--date 2026-06-05]
                               [--min-ev 0.0] [--side both|home|away]
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEF_SIG = {"pts": 7.0, "reb": 3.0, "ast": 2.6, "fg3m": 1.5, "stl": 1.0, "blk": 1.0}
STAT_LABEL = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "3PM",
              "stl": "STL", "blk": "BLK"}


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _p_over(line: float, mean: float, sigma: float, current: float) -> float:
    """P(final > line). DK lines are .5, so over = final >= ceil(line)."""
    thr = math.ceil(line)
    if current is not None and current >= thr:
        return 1.0
    if sigma <= 1e-6:
        return 1.0 if mean >= thr else 0.0
    return 1.0 - _phi((thr - 0.5 - mean) / sigma)


def _am_to_dec(price: float) -> float:
    p = float(price)
    return 1.0 + (p / 100.0 if p > 0 else 100.0 / abs(p))


def _am_to_prob(price: float) -> float:
    p = float(price)
    return (100.0 / (p + 100.0)) if p > 0 else (abs(p) / (abs(p) + 100.0))


def _norm(name: str) -> str:
    s = name.lower().strip()
    s = (s.replace("é", "e").replace("í", "i").replace("á", "a")
         .replace("ó", "o").replace("ü", "u").replace("ć", "c"))
    s = re.sub(r"[.\-']", "", s)
    s = re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _fetch_box(game: str) -> dict:
    url = f"http://127.0.0.1:8077/api/box_score?game_id={game}"
    with urllib.request.urlopen(url, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def _rem_frac(game: str):
    files = sorted(glob.glob(os.path.join(HERE, "data", "live", f"{game}_*.json")))
    if not files:
        return 1.0, "?", "?"
    try:
        d = json.loads(open(files[-1], encoding="utf-8").read())
    except Exception:
        return 1.0, "?", "?"
    try:
        period = int(d.get("period") or 1)
    except Exception:
        period = 1
    clk = str(d.get("clock") or "12:00")
    try:
        mm, ss = clk.split(":"); crem = int(mm) + float(ss) / 60.0
    except Exception:
        crem = 12.0
    if "FINAL" in str(d.get("game_status") or "").upper():
        return 0.0, period, clk
    rem = max(0.0, (4 - period) * 12.0 + crem) if period <= 4 else max(0.0, crem)
    return max(0.0, min(1.0, rem / 48.0)), period, clk


def _load_slate_spread(date: str) -> dict:
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
            try:
                q10 = float(row.get("q10")); q90 = float(row.get("q90"))
            except Exception:
                continue
            out.setdefault(pid, {})[row.get("stat")] = max(0.0, (q90 - q10) / 2.563)
    return out


def _load_dk(date: str):
    """latest DK line per (norm_name, stat). Prefer in-play, fall back pregame."""
    inplay = os.path.join(HERE, "data", "lines", f"{date}_dk_inplay.csv")
    pregame = os.path.join(HERE, "data", "lines", f"{date}_dk.csv")
    latest: dict = {}
    src = None
    for path, tag in ((inplay, "dk_inplay"), (pregame, "dk_pregame")):
        if not os.path.exists(path):
            continue
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                st = r.get("stat")
                if st not in STAT_LABEL:
                    continue
                k = (_norm(r.get("player_name", "")), st)
                ca = r.get("captured_at", "")
                if k not in latest or ca > latest[k]["captured_at"]:
                    try:
                        line = float(r.get("line"))
                        op = float(r.get("over_price")); up = float(r.get("under_price"))
                    except Exception:
                        continue
                    latest[k] = {"line": line, "over_price": op, "under_price": up,
                                 "captured_at": ca, "src": tag}
        if latest and src is None:
            src = tag
        if tag == "dk_inplay" and latest:
            break  # in-play present -> use it
    return latest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="0042500402")
    ap.add_argument("--date", default="2026-06-05")
    ap.add_argument("--min-ev", type=float, default=-1.0)
    ap.add_argument("--side", default="both", choices=["both", "home", "away"])
    args = ap.parse_args()

    box = _fetch_box(args.game)
    rem_frac, period, clk = _rem_frac(args.game)
    sig_scale = math.sqrt(max(rem_frac, 0.02))
    spreads = _load_slate_spread(args.date)
    dk = _load_dk(args.date)

    away = box.get("away", {}).get("abbr"); home = box.get("home", {}).get("abbr")
    cta = box.get("away", {}).get("current_total_pts")
    cth = box.get("home", {}).get("current_total_pts")
    dk_cap = max((v["captured_at"] for v in dk.values()), default="?")
    print("=" * 88)
    print(f"  {away} {cta} @ {home} {cth}   Q{period} {clk}   "
          f"(rem {rem_frac*48:.0f}min, sigma x{sig_scale:.2f})   DK last {dk_cap[-9:]}")
    print("  MODEL vs DRAFTKINGS  -  OVERS.   P(o)=model over prob  mkt=DK devig  "
          "EV=$/1 on over")
    print("=" * 88)

    rows = []  # (ev, edge, line)
    pts_table = []
    sides = ["away", "home"] if args.side == "both" else [args.side]
    for side in sides:
        for p in (box.get(side, {}).get("players") or []):
            nm = p.get("player_name") or p.get("player") or ""
            nn = _norm(nm)
            pid = p.get("player_id")
            cur = p.get("current") or {}
            sp = spreads.get(pid, {})
            for st in STAT_LABEL:
                key = (nn, st)
                if key not in dk:
                    continue
                d = dk[key]
                line = d["line"]
                # LIVE projection = paced_final (shrink-blended, floored at current);
                # the top-level p[st] is the STALE pregame number -> do NOT use it.
                pf = p.get("paced_final") or {}
                proj = pf.get(st)
                if proj is None:
                    proj = p.get(st) or 0.0
                c = cur.get(st) or 0.0
                proj = max(float(proj), float(c))  # never below banked
                sig = max((sp.get(st, DEF_SIG[st])) * sig_scale, 0.25)
                po = _p_over(line, proj, sig, c)
                im_o = _am_to_prob(d["over_price"]); im_u = _am_to_prob(d["under_price"])
                mkt = im_o / (im_o + im_u) if (im_o + im_u) > 0 else im_o
                edge = po - mkt
                dec = _am_to_dec(d["over_price"])
                ev = po * (dec - 1.0) - (1.0 - po)
                thr = math.ceil(line)
                lag = (c < thr) and (proj < line) and (c >= 0.45 * line) and rem_frac > 0.7
                rows.append({
                    "name": nm, "team": box.get(side, {}).get("abbr"), "stat": st,
                    "line": line, "op": d["over_price"], "proj": proj, "cur": c,
                    "po": po, "mkt": mkt, "edge": edge, "ev": ev, "lag": lag,
                })
                if st == "pts":
                    pts_table.append((box.get(side, {}).get("abbr"), nm, c, proj, line,
                                      proj - line, po, ev))

    # ---- BEST OVERS (by EV, excluding lag-flagged unless strong) ----
    overs = [r for r in rows if r["ev"] >= args.min_ev and r["po"] < 0.999]
    overs.sort(key=lambda r: -r["ev"])
    print("\n  >>> BEST OVERS (model says over is +EV at the DK price) <<<")
    print(f"  {'PLAYER':22s}{'MKT':10s}{'LINE':>6} {'oPRICE':>7} {'PROJ':>6} "
          f"{'NOW':>4} {'P(o)':>6} {'MKT%':>6} {'EDGE':>6} {'EV':>7}  FLAG")
    shown = 0
    for r in overs:
        if r["ev"] <= 0 and shown >= 12:
            break
        flag = "LAG?" if r["lag"] else ("BANKED" if r["cur"] >= math.ceil(r["line"]) else "")
        print(f"  {r['name'][:21]:22s}{STAT_LABEL[r['stat']]:10s}{r['line']:>6.1f} "
              f"{r['op']:>+7.0f} {r['proj']:>6.1f} {r['cur']:>4.0f} {r['po']*100:>5.0f}% "
              f"{r['mkt']*100:>5.0f}% {r['edge']*100:>+5.0f}% {r['ev']*100:>+6.1f}%  {flag}")
        shown += 1
        if shown >= 24:
            break

    # ---- PREDICTED POINTS vs DK pts line ----
    pts_table.sort(key=lambda x: -x[3])
    print("\n  >>> PREDICTED POINTS  (proj final vs DK pts line) <<<")
    print(f"  {'PLAYER':22s}{'TEAM':5s}{'NOW':>4} {'PROJ':>6} {'DK':>6} {'DIFF':>6} {'P(o)':>6}")
    for team, nm, c, proj, line, diff, po, ev in pts_table:
        arrow = "OVER " if diff > 0 else "under"
        print(f"  {nm[:21]:22s}{team:5s}{c:>4.0f} {proj:>6.1f} {line:>6.1f} "
              f"{diff:>+6.1f} {po*100:>5.0f}%  {arrow}")

    print("\n" + "=" * 88)
    print("  LAG? = model still pregame-anchored & behind a hot/cold start -> NOT a real")
    print("  edge yet (DK already adjusted). EV uses the real DK over price (vig included).")
    print("  Re-run as the game develops; edges firm up once shrink-weight rises (Q2+).")


if __name__ == "__main__":
    main()
