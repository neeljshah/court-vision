"""validate_ast_edge_extoos.py — independent cross-check of the AST edge on extended_oos.

The §8 AST edge is validated only on benashkar (2026-01-29..04-05). extended_oos_canonical.csv
is a DIFFERENT, coherent line corpus (blind-both -11.7%, all valid American odds) spanning
2024-04..2026-05 that joins 1,062 of the EXISTING leak-free OOF AST predictions — so it can
be graded with no retraining. The cleanest independent slice is the rows OUTSIDE benashkar's
Jan-Apr-2026 window. If the AST edge holds there, it is not a benashkar-only result.

settle() uses ACTUAL posted odds; OOF preds are walk-forward leak-free by construction. Invalid
American odds (|odds|<100) are dropped. Read-only.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from scripts.run_gate1_full_analysis import _payout  # noqa: E402

RNG = np.random.default_rng(20260601)
BEN_LO, BEN_HI = "2026-01-29", "2026-04-05"   # benashkar window (exclude for independence)
CSV = _ROOT / "data" / "external" / "historical_lines" / "extended_oos_canonical.csv"


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s.lower())).strip()


def load():
    from nba_api.stats.static import players as P
    nm = {}
    for p in P.get_players():
        nm.setdefault(norm(p["full_name"]), p["id"])
    df = pd.read_csv(CSV)
    df = df[df["stat"] == "ast"].copy()
    df["pid"] = df["player"].map(lambda x: nm.get(norm(x)))
    df = df.dropna(subset=["pid"])
    df["pid"] = df["pid"].astype(int)
    df["date2"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df[(df["over_odds"].abs() >= 100) & (df["under_odds"].abs() >= 100)]

    oof = pd.read_parquet(_ROOT / "data" / "cache" / "pregame_oof.parquet")
    oof["d"] = pd.to_datetime(oof["game_date"]).dt.strftime("%Y-%m-%d")
    oidx = {(int(r.player_id), r.d, r.stat): (float(r.oof_pred), float(r.actual))
            for r in oof.itertuples(index=False)}
    recs = []
    for r in df.itertuples(index=False):
        key = (int(r.pid), r.date2, "ast")
        hit = oidx.get(key)
        if hit is None:
            continue
        pred, oof_actual = hit
        recs.append({"pid": int(r.pid), "date": r.date2, "line": float(r.closing_line),
                     "over_odds": float(r.over_odds), "under_odds": float(r.under_odds),
                     "actual": float(r.actual_value), "oof_actual": oof_actual, "pred": pred})
    return recs


def settle(b):
    line, actual, pred = b["line"], b["actual"], b["pred"]
    if abs(pred - line) < 1e-9 or abs(actual - line) < 1e-9:
        return None
    over = pred > line
    won = (over and actual > line) or (not over and actual < line)
    return over, won, _payout(b["over_odds"] if over else b["under_odds"], won)


def roi(rows):
    if not rows:
        return 0, 0.0, 0.0
    n = len(rows)
    return n, sum(int(w) for _, w, _ in rows) / n * 100, sum(p for _, _, p in rows) / (n * 100) * 100


def boot(rows):
    if not rows:
        return (0, 0, 1)
    pays = np.array([p for _, _, p in rows])
    b = [RNG.choice(pays, len(pays), replace=True).sum() / (len(pays) * 100) * 100 for _ in range(8000)]
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5)), float((np.array(b) <= 0).mean())


def report(label, recs):
    s = [(b, settle(b)) for b in recs]
    s = [(b, x) for b, x in s if x is not None]
    allx = [x for _, x in s]
    overs = [x for _, x in s if x[0]]
    unders = [x for _, x in s if not x[0]]
    # blind sanity
    def forced(over):
        out = []
        for b in recs:
            if abs(b["actual"] - b["line"]) < 1e-9:
                continue
            won = (over and b["actual"] > b["line"]) or (not over and b["actual"] < b["line"])
            out.append((over, won, _payout(b["over_odds"] if over else b["under_odds"], won)))
        return out
    bO = roi(forced(True))[2]; bU = roi(forced(False))[2]
    g = [x for b, x in s if abs(b["pred"] - b["line"]) >= 0.75 and b["line"] <= 7.5]
    n, win, r = roi(allx)
    lo, hi, p0 = boot(allx)
    print(f"=== {label} ===")
    print(f"  market coherence (blind O {bO:+.1f}% + blind U {bU:+.1f}% = {bO+bU:+.1f}%)  "
          f"{'COHERENT' if bO+bU < 5 else 'CORRUPT'}")
    print(f"  ALL   n={n:4d}  win={win:.1f}%  ROI={r:+.2f}%   95%CI=[{lo:+.1f},{hi:+.1f}]  P(<=0)={p0:.3f}")
    print(f"  OVER  n={roi(overs)[0]:4d}  ROI={roi(overs)[2]:+.2f}%   |  UNDER n={roi(unders)[0]:4d}  ROI={roi(unders)[2]:+.2f}%")
    print(f"  ast_high-gated  n={roi(g)[0]:4d}  win={roi(g)[1]:.1f}%  ROI={roi(g)[2]:+.2f}%")
    print()


def main():
    recs = load()
    # consistency: OOF actual vs CSV actual_value
    mism = sum(1 for b in recs if abs(b["oof_actual"] - b["actual"]) > 0.5)
    dmin = min(b["date"] for b in recs); dmax = max(b["date"] for b in recs)
    print(f"extended_oos AST joined to OOF: n={len(recs)}  dates {dmin}..{dmax}  "
          f"actual-mismatch(OOF vs CSV)={mism} ({mism/len(recs)*100:.1f}%)\n")
    report("FULL extended_oos AST", recs)
    indep = [b for b in recs if not (BEN_LO <= b["date"] <= BEN_HI)]
    inwin = [b for b in recs if BEN_LO <= b["date"] <= BEN_HI]
    report(f"OUTSIDE benashkar window (independent) [{len(indep)} bets]", indep)
    report(f"INSIDE benashkar window (overlap check) [{len(inwin)} bets]", inwin)
    print(">> benashkar reference: ALL +7.03%, gated +19.17%. Independent slice = the real cross-check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
