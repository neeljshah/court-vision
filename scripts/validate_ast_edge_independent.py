"""validate_ast_edge_independent.py — does the AST edge replicate on an INDEPENDENT corpus?

The §8 AST edge is validated only on the benashkar 9-week window (2026-01-29..04-05). The
single most valuable de-risking is an out-of-corpus replication. eval_2025_26_combined.csv is
a different line source spanning 21 dates Oct-2025..May-2026 (partly outside benashkar), but
the cached OOF doesn't cover its dates (structural fold gaps — see VS_VEGAS_ASSESSMENT §1).

So regenerate leak-free predictions for the eval AST rows via a ROLLING-ORIGIN backtest:
for each monthly cutoff C, train the EXACT production AST stack (cache_pergame_oof.
_train_and_predict_stat) on dataset rows strictly before C, then predict the eval AST rows
dated >= C (and < next cutoff). Strictly train-on-past => leak-free by construction; uses the
identical XGB+LGB+MLP→NNLS code as the shipped OOF, so it's methodologically faithful.

Grade those fresh preds vs eval's real closing AST lines at ACTUAL posted odds. If the edge
(~+7% on benashkar, both directions, bootstrap-significant) replicates here, confidence in the
one bettable edge jumps. If it vanishes, that's a critical red flag worth knowing.
"""
from __future__ import annotations

import re
import sys
import unicodedata
import warnings
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


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s.lower())).strip()


def name_to_id():
    from nba_api.stats.static import players as P
    nm = {}
    for p in P.get_players():
        nm.setdefault(norm(p["full_name"]), p["id"])
    return nm


def load_eval_ast():
    df = pd.read_csv(_ROOT / "data" / "cache" / "eval_2025_26_combined.csv")
    df = df[df["stat"] == STAT].copy()
    nm = name_to_id()
    df["pid"] = df["player"].map(lambda x: nm.get(norm(x)))
    df = df.dropna(subset=["pid"])
    df["pid"] = df["pid"].astype(int)
    return df


def main():
    print("building dataset ...", flush=True)
    rows, _ = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    fc = feature_columns(stat=STAT)
    # The eval corpus dates are shifted by a day for many slates (line-post vs
    # game-date convention). Match each eval bet to the dataset game in a +/-1 day
    # window whose realized AST EQUALS eval.actual_value -> unambiguously identifies
    # the true game (and its pregame features + true date for the leak-free cutoff).
    from datetime import datetime, timedelta
    by_key = {(int(r.get("player_id", 0)), str(r["date"])[:10]): r for r in rows}
    print(f"  dataset rows={len(rows)}  feat={len(fc)}", flush=True)

    ev = load_eval_ast()
    recs = []
    ambiguous = unmatched = 0
    for t in ev.itertuples(index=False):
        d0 = str(t.date)[:10]
        cands = []
        for k in (-1, 0, 1):
            dd = (datetime.fromisoformat(d0) + timedelta(days=k)).strftime("%Y-%m-%d")
            dr = by_key.get((int(t.pid), dd))
            if dr is not None and abs(float(dr[f"target_{STAT}"]) - float(t.actual_value)) < 0.5:
                cands.append((dd, dr))
        if not cands:
            unmatched += 1
            continue
        if len({c[0] for c in cands}) > 1:
            ambiguous += 1
            continue  # same actual on 2 days in window -> can't disambiguate
        true_date, dr = cands[0]
        recs.append({"pid": int(t.pid), "date": true_date, "line": float(t.closing_line),
                     "over_odds": float(t.over_odds), "under_odds": float(t.under_odds),
                     "actual": float(t.actual_value), "row": dr})
    print(f"  eval AST matched (actual-value disambiguated): {len(recs)} / {len(ev)}  "
          f"(unmatched={unmatched}, ambiguous-dropped={ambiguous})", flush=True)
    if len(recs) < 60:
        print("  too few to validate"); return 1

    # monthly cutoffs: cutoff = first eval-date of each month present
    months = sorted({d[:7] for d in (r["date"] for r in recs)})
    cut_for = {m: min(r["date"] for r in recs if r["date"][:7] == m) for m in months}
    print(f"  monthly cutoffs: {cut_for}\n", flush=True)

    dates_all = [str(r["date"])[:10] for r in rows]

    for m in months:
        cutoff = cut_for[m]
        bucket = [r for r in recs if cut_for[r["date"][:7]] == cutoff]
        tr_idx = [i for i, d in enumerate(dates_all) if d < cutoff]
        if len(tr_idx) < 2000:
            print(f"  [{m}] cutoff {cutoff}: train too small ({len(tr_idx)}) — skip bucket")
            for r in bucket:
                r["pred"] = None
            continue
        n_tr = len(tr_idx)
        va_start = int(n_tr * 0.85)
        tr_rows = [rows[i] for i in tr_idx[:va_start]]
        va_rows = [rows[i] for i in tr_idx[va_start:]]
        X_tr = np.array([[rr[c] for c in fc] for rr in tr_rows], dtype=float)
        X_val = np.array([[rr[c] for c in fc] for rr in va_rows], dtype=float)
        y_tr = np.array([rr[f"target_{STAT}"] for rr in tr_rows], dtype=float)
        y_val = np.array([rr[f"target_{STAT}"] for rr in va_rows], dtype=float)
        X_ho = np.array([[r["row"][c] for c in fc] for r in bucket], dtype=float)
        from datetime import datetime
        td = [datetime.fromisoformat(rr["date"][:10]) for rr in tr_rows]
        age = np.array([(max(td) - d).days / 365.0 for d in td])
        sw = np.exp(-0.5 * age)
        preds = _train_and_predict_stat(STAT, X_tr, y_tr, X_val, y_val, X_ho, sw)
        for r, p in zip(bucket, preds):
            r["pred"] = float(p)
        mae = np.mean([abs(r["pred"] - r["actual"]) for r in bucket])
        print(f"  [{m}] cutoff {cutoff}  train_n={n_tr}  bucket_n={len(bucket)}  ho_mae={mae:.3f}", flush=True)

    graded = [r for r in recs if r.get("pred") is not None]
    print(f"\n=== INDEPENDENT AST GRADE (n={len(graded)}, leak-free rolling-origin) ===")

    def settle(r):
        line, actual, pred = r["line"], r["actual"], r["pred"]
        if abs(pred - line) < 1e-9 or abs(actual - line) < 1e-9:
            return None
        over = pred > line
        won = (over and actual > line) or (not over and actual < line)
        return over, won, _payout(r["over_odds"] if over else r["under_odds"], won)

    s = [(r, settle(r)) for r in graded]
    s = [(r, x) for r, x in s if x is not None]

    def roi(rows_):
        if not rows_:
            return 0, 0.0, 0.0
        n = len(rows_)
        return n, sum(int(w) for _, w, _ in rows_) / n * 100, sum(p for _, _, p in rows_) / (n * 100) * 100

    allx = [x for _, x in s]
    overs = [x for _, x in s if x[0]]
    unders = [x for _, x in s if not x[0]]
    n, win, r_ = roi(allx)
    print(f"  ALL   n={n}  win={win:.1f}%  ROI={r_:+.2f}%")
    print(f"  OVER  n={roi(overs)[0]}  win={roi(overs)[1]:.1f}%  ROI={roi(overs)[2]:+.2f}%   | "
          f" UNDER n={roi(unders)[0]}  win={roi(unders)[1]:.1f}%  ROI={roi(unders)[2]:+.2f}%")
    # blind baselines
    def forced(over):
        out = []
        for r in graded:
            if abs(r["actual"] - r["line"]) < 1e-9:
                continue
            won = (over and r["actual"] > r["line"]) or (not over and r["actual"] < r["line"])
            out.append((over, won, _payout(r["over_odds"] if over else r["under_odds"], won)))
        return out
    print(f"  blind OVER ROI={roi(forced(True))[2]:+.2f}%   blind UNDER ROI={roi(forced(False))[2]:+.2f}%")
    # bootstrap
    pays = np.array([p for _, _, p in allx])
    boot = [RNG.choice(pays, len(pays), replace=True).sum() / (len(pays) * 100) * 100 for _ in range(8000)]
    lo, hi = np.percentile(boot, [2.5, 97.5])
    print(f"  bootstrap 95% CI=[{lo:+.2f}%, {hi:+.2f}%]  P(ROI<=0)={(np.array(boot) <= 0).mean():.3f}")
    # edge-gated (ast_high analog: |pred-line|>=0.75, line<=7.5)
    g = [x for r, x in s if abs(r["pred"] - r["line"]) >= 0.75 and r["line"] <= 7.5]
    print(f"  ast_high-gated  n={roi(g)[0]}  win={roi(g)[1]:.1f}%  ROI={roi(g)[2]:+.2f}%")
    print("\n  >> benashkar reference: ALL +7.03%, gated +19.17%. Replication = edge is not corpus-specific.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
