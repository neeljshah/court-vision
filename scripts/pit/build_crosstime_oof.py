"""Generalized leak-free rolling-origin OOF generator that SAVES per-bet
predictions + as-of conditioners — the reusable cross-season test substrate.

The pred-join (calibration_frame_v2.pred) only covers non-contiguous OOF holdout
windows (~4068 bets, mostly 2026). To test ANY conditioner (pace, rest, n_out,
opp-allowed) on an INDEPENDENT regular season with real power, we need leak-free
predictions for the line-corpus dates that the cached OOF misses.

This mirrors the validated scripts/validate_ast_edge_crosstime.py engine
(build_pergame_dataset + cache_pergame_oof._train_and_predict_stat, train strictly
on the past, per-month rolling origin, +/-1d actual-disambiguated feature match)
but writes data/cache/pit/crosstime_oof_<stat>_<tag>.parquet with, per graded bet:
date, pid, line, over_odds, under_odds, actual, pred, and the as-of conditioners
pulled from the dataset row (opp_pace, opp_def, rest_days, is_b2b, is_home, n_out,
vac_pts, l10_min, ...). Read-only except its own parquet.

Run (background):
  python scripts/pit/build_crosstime_oof.py --stat ast \
      --corpora regular_season_2024_25_oddsapi.csv regular_season_2025_26_oddsapi.csv
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
import warnings
from datetime import datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))
from src.prediction.prop_pergame import build_pergame_dataset, feature_columns  # noqa: E402
from scripts.cache_pergame_oof import _train_and_predict_stat  # noqa: E402

OUT_DIR = _ROOT / "data" / "cache" / "pit"
LINES = _ROOT / "data" / "external" / "historical_lines"

# conditioners to persist (must be keys present in the dataset row dict)
COND_KEYS = ["opp_pace", "opp_def", "rest_days", "is_b2b", "is_home",
             "n_out", "vac_pts", "vac_min", "l10_min", "std_min"]


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s.lower())).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stat", default="ast")
    ap.add_argument("--corpora", nargs="+",
                    default=["regular_season_2024_25_oddsapi.csv",
                             "regular_season_2025_26_oddsapi.csv"])
    args = ap.parse_args()
    STAT = args.stat

    from nba_api.stats.static import players as P
    nm = {}
    for p in P.get_players():
        nm.setdefault(norm(p["full_name"]), p["id"])

    print("building dataset (shared across corpora) ...", flush=True)
    rows, _ = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    fc = feature_columns(stat=STAT)
    by_key = {(int(r.get("player_id", 0)), str(r["date"])[:10]): r for r in rows}
    dates_all = [str(r["date"])[:10] for r in rows]
    print(f"  dataset rows={len(rows)}  features={len(fc)}", flush=True)

    for corpus in args.corpora:
        path = LINES / corpus
        if not path.exists():
            print(f"  [{corpus}] MISSING, skip", flush=True)
            continue
        df = pd.read_csv(path)
        df = df[df["stat"] == STAT].copy()
        df["pid"] = df["player"].map(lambda x: nm.get(norm(x)))
        df = df.dropna(subset=["pid"])
        df["pid"] = df["pid"].astype(int)
        df = df[(df["over_odds"].abs() >= 100) & (df["under_odds"].abs() >= 100)]
        df["date2"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

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
            recs.append({"date": td, "pid": int(r.pid), "line": float(r.closing_line),
                         "over_odds": float(r.over_odds), "under_odds": float(r.under_odds),
                         "actual": float(r.actual_value), "row": dr})
        print(f"  [{corpus}] matched n={len(recs)}", flush=True)
        if not recs:
            continue

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
            mae = np.mean([abs(r["pred"] - r["actual"]) for r in bucket if r.get("pred") is not None])
            print(f"    [{m}] train_n={n_tr} bucket_n={len(bucket)} ho_mae={mae:.3f}", flush=True)

        graded = [r for r in recs if r.get("pred") is not None]
        out_rows = []
        for r in graded:
            d = {"date": r["date"], "pid": r["pid"], "stat": STAT, "line": r["line"],
                 "over_odds": r["over_odds"], "under_odds": r["under_odds"],
                 "actual": r["actual"], "pred": r["pred"]}
            for k in COND_KEYS:
                d[k] = r["row"].get(k, np.nan)
            out_rows.append(d)
        tag = corpus.replace(".csv", "")
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        outp = OUT_DIR / f"crosstime_oof_{STAT}_{tag}.parquet"
        pd.DataFrame(out_rows).to_parquet(outp, index=False)
        print(f"  [{corpus}] saved {len(out_rows)} graded rows -> {outp}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
