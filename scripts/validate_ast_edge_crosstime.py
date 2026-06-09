"""validate_ast_edge_crosstime.py — cross-TIME independent check of the AST edge.

extended_oos_canonical (coherent, valid-odds) has AST rows OUTSIDE benashkar's Jan-Apr-2026
window that don't join the cached OOF. Generate leak-free rolling-origin predictions for them
(train strictly on the past, actual-value-disambiguated +/-1d feature match) and grade vs the
real coherent lines. The bulk (n~206) are 2026-05 PLAYOFFS — a different time AND regime than
benashkar's regular season, so read the result with the known playoff-regime caveat: a miss
here does not refute the regular-season edge; a hit is strong cross-time corroboration.

Reuses cache_pergame_oof._train_and_predict_stat (production training). Read-only.
"""
from __future__ import annotations

import re
import sys
import unicodedata
import warnings
from datetime import datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from src.prediction.prop_pergame import build_pergame_dataset, feature_columns  # noqa: E402
from scripts.cache_pergame_oof import _train_and_predict_stat  # noqa: E402
from scripts.run_gate1_full_analysis import _payout  # noqa: E402

RNG = np.random.default_rng(20260601)
STAT = "ast"
BEN_LO, BEN_HI = "2026-01-29", "2026-04-05"


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s.lower())).strip()


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="extended_oos_canonical.csv",
                    help="CSV under data/external/historical_lines/")
    ap.add_argument("--exclude-benashkar", action="store_true",
                    help="drop rows inside benashkar's Jan-Apr-2026 window (use for extended_oos overlap)")
    args = ap.parse_args()

    from nba_api.stats.static import players as P
    nm = {}
    for p in P.get_players():
        nm.setdefault(norm(p["full_name"]), p["id"])

    print(f"corpus={args.corpus}  exclude_benashkar={args.exclude_benashkar}", flush=True)
    print("building dataset ...", flush=True)
    rows, _ = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    fc = feature_columns(stat=STAT)
    by_key = {(int(r.get("player_id", 0)), str(r["date"])[:10]): r for r in rows}
    dates_all = [str(r["date"])[:10] for r in rows]
    print(f"  dataset rows={len(rows)}", flush=True)

    df = pd.read_csv(_ROOT / "data" / "external" / "historical_lines" / args.corpus)
    df = df[df["stat"] == "ast"].copy()
    df["pid"] = df["player"].map(lambda x: nm.get(norm(x)))
    df = df.dropna(subset=["pid"])
    df["pid"] = df["pid"].astype(int)
    df = df[(df["over_odds"].abs() >= 100) & (df["under_odds"].abs() >= 100)]
    df["date2"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    if args.exclude_benashkar:
        df = df[~((df["date2"] >= BEN_LO) & (df["date2"] <= BEN_HI))]

    recs = []
    for r in df.itertuples(index=False):
        cands = []
        for k in (-1, 0, 1):
            dd = (datetime.fromisoformat(r.date2) + timedelta(days=k)).strftime("%Y-%m-%d")
            dr = by_key.get((int(r.pid), dd))
            if dr is not None and abs(float(dr[f"target_{STAT}"]) - float(r.actual_value)) < 0.5:
                cands.append((dd, dr))
        if not cands or len({c[0] for c in cands}) > 1:
            continue
        td, dr = cands[0]
        recs.append({"date": td, "line": float(r.closing_line), "over_odds": float(r.over_odds),
                     "under_odds": float(r.under_odds), "actual": float(r.actual_value), "row": dr})
    print(f"  extended_oos out-of-window AST matched: n={len(recs)}", flush=True)

    months = sorted({r["date"][:7] for r in recs})
    cut_for = {m: min(r["date"] for r in recs if r["date"][:7] == m) for m in months}
    for m in months:
        cutoff = cut_for[m]
        bucket = [r for r in recs if r["date"][:7] == m]
        tr_idx = [i for i, d in enumerate(dates_all) if d < cutoff]
        if len(tr_idx) < 2000:
            for r in bucket:
                r["pred"] = None
            continue
        n_tr = len(tr_idx)
        va = int(n_tr * 0.85)
        tr_rows = [rows[i] for i in tr_idx[:va]]
        va_rows = [rows[i] for i in tr_idx[va:]]
        X_tr = np.array([[rr[c] for c in fc] for rr in tr_rows], float)
        X_val = np.array([[rr[c] for c in fc] for rr in va_rows], float)
        y_tr = np.array([rr[f"target_{STAT}"] for rr in tr_rows], float)
        y_val = np.array([rr[f"target_{STAT}"] for rr in va_rows], float)
        X_ho = np.array([[r["row"][c] for c in fc] for r in bucket], float)
        td = [datetime.fromisoformat(rr["date"][:10]) for rr in tr_rows]
        sw = np.exp(-0.5 * np.array([(max(td) - d).days / 365.0 for d in td]))
        preds = _train_and_predict_stat(STAT, X_tr, y_tr, X_val, y_val, X_ho, sw)
        for r, p in zip(bucket, preds):
            r["pred"] = float(p)
        mae = np.mean([abs(r["pred"] - r["actual"]) for r in bucket])
        print(f"  [{m}] cutoff {cutoff}  train_n={n_tr}  bucket_n={len(bucket)}  ho_mae={mae:.3f}", flush=True)

    graded = [r for r in recs if r.get("pred") is not None]

    def settle(r):
        line, a, p = r["line"], r["actual"], r["pred"]
        if abs(p - line) < 1e-9 or abs(a - line) < 1e-9:
            return None
        over = p > line
        won = (over and a > line) or (not over and a < line)
        return over, won, _payout(r["over_odds"] if over else r["under_odds"], won)

    def roi(rs):
        if not rs:
            return 0, 0.0, 0.0
        n = len(rs)
        return n, sum(int(w) for _, w, _ in rs) / n * 100, sum(p for _, _, p in rs) / (n * 100) * 100

    s = [(r, settle(r)) for r in graded]
    s = [(r, x) for r, x in s if x is not None]
    allx = [x for _, x in s]
    # blind coherence
    def forced(over):
        out = []
        for r in graded:
            if abs(r["actual"] - r["line"]) < 1e-9:
                continue
            won = (over and r["actual"] > r["line"]) or (not over and r["actual"] < r["line"])
            out.append((over, won, _payout(r["over_odds"] if over else r["under_odds"], won)))
        return out
    bO, bU = roi(forced(True))[2], roi(forced(False))[2]
    g = [x for r, x in s if abs(r["pred"] - r["line"]) >= 0.75 and r["line"] <= 7.5]
    pays = np.array([p for _, _, p in allx])
    bt = [RNG.choice(pays, len(pays), replace=True).sum() / (len(pays) * 100) * 100 for _ in range(8000)] if len(pays) else [0]
    lo, hi = np.percentile(bt, [2.5, 97.5])
    n, win, r_ = roi(allx)
    print(f"\n=== CROSS-TIME AST GRADE ({args.corpus}, leak-free) n={n} ===")
    print(f"  dates: {min(r['date'] for r,_ in s)}..{max(r['date'] for r,_ in s)}")
    print(f"  coherence: blind O {bO:+.1f}% + blind U {bU:+.1f}% = {bO+bU:+.1f}%")
    print(f"  ALL   n={n}  win={win:.1f}%  ROI={r_:+.2f}%  95%CI=[{lo:+.1f},{hi:+.1f}]  P(<=0)={(np.array(bt)<=0).mean():.3f}")
    print(f"  ast_high-gated  n={roi(g)[0]}  win={roi(g)[1]:.1f}%  ROI={roi(g)[2]:+.2f}%")
    print("  >> benashkar reference: ALL +7.03%, gated +19.17%.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
