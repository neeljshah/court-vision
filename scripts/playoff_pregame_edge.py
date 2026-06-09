"""playoff_pregame_edge.py — quantify the pregame prop break in the PLAYOFFS, per stat.

The production OOF (data/cache/pregame_oof.parquet) ends 2026-04-12 and contains ZERO
playoff rows (verified). So playoff rows are NOT gradeable from the cached prod stack —
they must be graded with a LEAK-FREE rolling-origin retrain (train the EXACT production
stat stack strictly on the past, +/-1d actual-value-disambiguated feature match), exactly
as VS_VEGAS_ASSESSMENT.md §8e does for AST. This script generalizes that to PTS/REB/AST/FG3M
and to two independent playoff samples:

  2024 playoffs  — extended_oos / playoffs_2024_canonical (FLAT -110 only; ROI is the
                   -110 fiction so we report WIN% as the real signal + flat-ROI as indicative)
  2026 playoffs  — playoffs_2025_26_oddsapi.csv (REAL American odds; |odds|>=100 enforced;
                   real ROI gradeable)

For contrast we also grade the same model on the regular-season benashkar/extended_oos
windows via the cached OOF (no retrain) so the break is measured against a like baseline.

|odds|>=100 is enforced everywhere. Read-only. Produces JSON for the audit doc.
"""
from __future__ import annotations

import json
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

RNG = np.random.default_rng(20260604)
STATS = ["pts", "reb", "ast", "fg3m"]
HL = str(_ROOT / "data" / "external" / "historical_lines")


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s.lower())).strip()


def name_map():
    from nba_api.stats.static import players as P
    nm = {}
    for p in P.get_players():
        nm.setdefault(norm(p["full_name"]), p["id"])
    return nm


def load_corpus(fname, lo, hi, nm):
    df = pd.read_csv(Path(HL) / fname, on_bad_lines="skip", engine="python")
    df = df[df["stat"].isin(STATS)].copy()
    for c in ["over_odds", "under_odds", "closing_line", "actual_value"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["over_odds", "under_odds", "closing_line", "actual_value"])
    df["d"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["d"])
    df = df[(df["d"] >= lo) & (df["d"] <= hi)]
    df["pid"] = df["player"].map(lambda x: nm.get(norm(x)))
    df = df.dropna(subset=["pid"])
    df["pid"] = df["pid"].astype(int)
    df = df[(df["over_odds"].abs() >= 100) & (df["under_odds"].abs() >= 100)]
    # de-dup to one row per (pid, date, stat, line): keep first
    df = df.drop_duplicates(subset=["pid", "d", "stat", "closing_line"])
    return df


def rolling_origin_predict(df, rows, dates_all, by_key, stat):
    """Leak-free rolling-origin preds for one stat over df's dates. Mutates rows-of-df → preds dict."""
    fc = feature_columns(stat=stat)
    sub = df[df["stat"] == stat].copy()
    recs = []
    for r in sub.itertuples(index=False):
        # +/-1d disambiguated feature match on actual value
        cands = []
        for k in (-1, 0, 1):
            dd = (datetime.fromisoformat(r.d) + timedelta(days=k)).strftime("%Y-%m-%d")
            dr = by_key.get((int(r.pid), dd))
            if dr is not None and abs(float(dr[f"target_{stat}"]) - float(r.actual_value)) < 0.5:
                cands.append((dd, dr))
        if not cands or len({c[0] for c in cands}) > 1:
            continue
        td, dr = cands[0]
        recs.append({"pid": int(r.pid), "date": td, "line": float(r.closing_line),
                     "over_odds": float(r.over_odds), "under_odds": float(r.under_odds),
                     "actual": float(r.actual_value), "row": dr, "stat": stat})
    if not recs:
        return []
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
        y_tr = np.array([rr[f"target_{stat}"] for rr in tr_rows], float)
        y_val = np.array([rr[f"target_{stat}"] for rr in va_rows], float)
        X_ho = np.array([[r["row"][c] for c in fc] for r in bucket], float)
        td = [datetime.fromisoformat(rr["date"][:10]) for rr in tr_rows]
        sw = np.exp(-0.5 * np.array([(max(td) - d).days / 365.0 for d in td]))
        preds = _train_and_predict_stat(stat, X_tr, y_tr, X_val, y_val, X_ho, sw)
        for r, p in zip(bucket, preds):
            r["pred"] = float(p)
    return [r for r in recs if r.get("pred") is not None]


def settle(r, predkey="pred"):
    line, a, p = r["line"], r["actual"], r[predkey]
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


def boot(rs):
    if not rs:
        return (0.0, 0.0, 1.0)
    pays = np.array([p for _, _, p in rs])
    b = [RNG.choice(pays, len(pays), replace=True).sum() / (len(pays) * 100) * 100 for _ in range(6000)]
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5)), float((np.array(b) <= 0).mean())


def grade_stat(graded, predkey="pred"):
    s = [(r, settle(r, predkey)) for r in graded]
    s = [(r, x) for r, x in s if x is not None]
    allx = [x for _, x in s]
    overs = [x for _, x in s if x[0]]
    unders = [x for _, x in s if not x[0]]

    def forced(over):
        out = []
        for r in graded:
            if abs(r["actual"] - r["line"]) < 1e-9:
                continue
            won = (over and r["actual"] > r["line"]) or (not over and r["actual"] < r["line"])
            out.append((over, won, _payout(r["over_odds"] if over else r["under_odds"], won)))
        return out
    bO = roi(forced(True))[2]
    bU = roi(forced(False))[2]
    g = [x for r, x in s if abs(r[predkey] - r["line"]) >= 0.75 and r["line"] <= 7.5]
    n, win, r_ = roi(allx)
    lo, hi, p0 = boot(allx)
    return {
        "n": n, "win": round(win, 1), "roi": round(r_, 2),
        "ci": [round(lo, 1), round(hi, 1)], "p_le0": round(p0, 3),
        "over_n": roi(overs)[0], "over_roi": round(roi(overs)[2], 2),
        "under_n": roi(unders)[0], "under_roi": round(roi(unders)[2], 2),
        "gated_n": roi(g)[0], "gated_win": round(roi(g)[1], 1), "gated_roi": round(roi(g)[2], 2),
        "blind_O": round(bO, 1), "blind_U": round(bU, 1), "coherent": (bO + bU) < 5,
    }


def main():
    nm = name_map()
    print("building production per-game dataset ...", flush=True)
    rows, _ = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    by_key = {(int(r.get("player_id", 0)), str(r["date"])[:10]): r for r in rows}
    dates_all = [str(r["date"])[:10] for r in rows]
    print(f"  dataset rows={len(rows)}  dates {dates_all[0]}..{dates_all[-1]}", flush=True)

    corpora = {
        # 2024 playoffs: real odds unavailable -> flat -110; WIN% is the real signal.
        "2024_playoffs": ("playoffs_2024_canonical.csv", "2024-04-15", "2024-06-30"),
        # 2026 playoffs: REAL odds.
        "2026_playoffs": ("playoffs_2025_26_oddsapi.csv", "2026-04-15", "2026-06-30"),
    }

    out = {"corpora": {}, "per_stat": {}}
    all_graded = {}
    for cname, (fname, lo, hi) in corpora.items():
        df = load_corpus(fname, lo, hi, nm)
        print(f"\n{'='*72}\n{cname}: {fname}  rows(valid-odds)={len(df)}  dates {df['d'].min()}..{df['d'].max()}", flush=True)
        flat = bool(((df["over_odds"] == -110) & (df["under_odds"] == -110)).mean() > 0.99)
        out["corpora"][cname] = {"file": fname, "n_rows": int(len(df)),
                                 "dates": [df["d"].min(), df["d"].max()],
                                 "flat_110": flat, "uniq_dates": int(df["d"].nunique())}
        all_graded[cname] = {}
        for stat in STATS:
            graded = rolling_origin_predict(df, rows, dates_all, by_key, stat)
            if not graded:
                print(f"  {stat}: n=0 (no leak-free matches)")
                continue
            mae = float(np.mean([abs(r["pred"] - r["actual"]) for r in graded]))
            line_mae = float(np.mean([abs(r["line"] - r["actual"]) for r in graded]))
            res = grade_stat(graded)
            res["model_mae"] = round(mae, 3)
            res["line_mae"] = round(line_mae, 3)
            res["flat_110"] = flat
            out["per_stat"].setdefault(stat, {})[cname] = res
            all_graded[cname][stat] = graded
            tag = "(WIN% real; ROI=-110 fiction)" if flat else "(REAL odds ROI)"
            print(f"  {stat:<5} n={res['n']:>4} win={res['win']:>5.1f}% ROI={res['roi']:>+6.2f}% "
                  f"CI[{res['ci'][0]:+.0f},{res['ci'][1]:+.0f}] mMAE={mae:.2f} lineMAE={line_mae:.2f} "
                  f"gated(n={res['gated_n']})={res['gated_roi']:+.1f}% {tag}", flush=True)

    outp = _ROOT / "data" / "cache" / "playoff_pregame_edge.json"
    json.dump(out, open(outp, "w", encoding="utf-8"), indent=2)
    # also persist graded rows for downstream mechanism/sub-policy scripts
    import pickle
    pickle.dump(all_graded, open(_ROOT / "data" / "cache" / "playoff_graded.pkl", "wb"))
    print(f"\nwrote {outp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
