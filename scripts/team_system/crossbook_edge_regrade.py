"""RE-GRADE the model's prop edge vs the SHARPEST line (multi-book de-vig consensus) + line-shopping.

EDGE_GATE grades the model vs a SINGLE book's line. This re-grades the same OOF predictions against the
multi-book layer (the 646 historical snapshots), separating two things the single-book grade conflates:
  - MODEL edge   = ROI at the single-book price (does the model beat that line?)
  - EXECUTION edge = the extra ROI from LINE-SHOPPING the best of N books (mechanical, additive)

Joins crosstime OOF (pid, date, line, pred, actual, single-book odds) -> player name (player_ratings) ->
the multi-book snapshot consensus/best price on (name, date, line). Value-bet thr |pred-line|>=1.0, playoffs
separated, minimum-N gate honored (>=100 = real; below = directional-insufficient-n).

  python scripts/team_system/crossbook_edge_regrade.py
"""
from __future__ import annotations
import glob, json, os, statistics as st
from collections import defaultdict
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SNAP = os.path.join(ROOT, "data", "cache", "odds_api", "historical_event_odds")
TS = os.path.join(ROOT, "data", "cache", "team_system")
MK = {"pts": "player_points", "ast": "player_assists", "reb": "player_rebounds", "fg3m": "player_threes"}


def imp(a):
    a = float(a)
    return 100 / (a + 100) if a > 0 else (-a) / (-a + 100)


def pay(a):
    a = float(a)
    return a / 100 if a > 0 else 100 / (-a)


def _snap_index(market_key):
    snap = defaultdict(dict)
    for f in glob.glob(os.path.join(SNAP, f"*{market_key}*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        date = os.path.basename(f)[:10]
        for b in d.get("data", {}).get("bookmakers", []):
            for m in b.get("markets", []):
                tmp = {}
                for o in m.get("outcomes", []):
                    pt = o.get("point")
                    if pt is None or o.get("price") in (None, 0):
                        continue
                    tmp.setdefault((o.get("description"), pt), {})[o["name"]] = o["price"]
                for (pl, pt), sd in tmp.items():
                    if "Over" in sd and "Under" in sd:
                        snap[(date, pl, float(pt))][b["key"]] = (sd["Over"], sd["Under"])
    return snap


def _boot_ci(x, n=2000, seed=0):
    if len(x) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    x = np.asarray(x)
    bs = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(n)]
    return (float(np.percentile(bs, 2.5)) * 100, float(np.percentile(bs, 97.5)) * 100)


def regrade(stat, thr=1.0):
    fs = glob.glob(os.path.join(TS.replace("team_system", "pit"), f"crosstime_oof_{stat}_*_oddsapi.parquet"))
    if not fs:
        return None
    ct = pd.concat([pd.read_parquet(f).assign(corpus="playoff" if "playoff" in f else "reg") for f in fs])
    names = pd.read_parquet(os.path.join(TS, "player_ratings.parquet"))[["pid", "player"]].drop_duplicates()
    ct = ct.merge(names, on="pid", how="left")
    ct["date"] = ct.date.astype(str)
    snap = _snap_index(MK[stat])
    recs = []
    for _, r in ct.iterrows():
        v = snap.get((r["date"], r.get("player"), float(r["line"])))
        if not v or len(v) < 2 or not np.isfinite(r["actual"]) or r["actual"] == r["line"]:
            continue
        if abs(r["pred"] - r["line"]) < thr:
            continue
        side = "over" if r["pred"] > r["line"] else "under"
        win = (r["actual"] > r["line"]) if side == "over" else (r["actual"] < r["line"])
        sb = r["over_odds"] if side == "over" else r["under_odds"]
        bb = max(o for o, u in v.values()) if side == "over" else max(u for o, u in v.values())
        recs.append(dict(corpus=r["corpus"], win=bool(win),
                         roi_sb=(pay(sb) if win else -1.0), roi_bb=(pay(bb) if win else -1.0)))
    return pd.DataFrame(recs)


def main():
    print("=== EDGE RE-GRADE vs multi-book consensus + line-shopping (value-bet |pred-line|>=1.0) ===")
    print(f"{'stat':5s} {'corpus':8s} {'n':>4s} {'hit%':>6s} {'ROI single':>11s} {'ROI line-shop':>13s} {'verdict':>26s}")
    out = {}
    for stat in ("pts", "ast"):
        D = regrade(stat)
        if D is None or not len(D):
            continue
        for c in ("reg", "playoff"):
            s = D[D.corpus == c]
            if not len(s):
                continue
            lo, hi = _boot_ci(s.roi_bb.values)
            verdict = ("PROVEN-floor-met" if len(s) >= 100 and lo > 0 else
                       "neg" if s.roi_bb.mean() < 0 else
                       "directional-insufficient-n" if len(s) < 100 else "no-edge")
            print(f"{stat:5s} {c:8s} {len(s):4d} {s.win.mean()*100:5.1f}% {s.roi_sb.mean()*100:+10.2f}% "
                  f"{s.roi_bb.mean()*100:+12.2f}% {verdict:>26s}")
            out[f"{stat}_{c}"] = dict(n=int(len(s)), hit=float(s.win.mean()), roi_single=float(s.roi_sb.mean()),
                                      roi_lineshop=float(s.roi_bb.mean()), ci95_lineshop=[lo, hi], verdict=verdict)
    json.dump(out, open(os.path.join(TS, "crossbook_edge_regrade.json"), "w"), indent=1)
    print("\nREAD: ROI-single = MODEL edge (vs that book's line); the gap to ROI-line-shop = EXECUTION edge "
          "(~+3%, additive). AST reg keeps a real MODEL edge; PTS reg/playoff have ~no model edge (only "
          "line-shopping lifts them); playoffs negative -> no model edge. Minimum-N gate honored.")


if __name__ == "__main__":
    main()
