"""validate_vac_stack_feature.py — decisive vac-load lever test on ONE substrate.

Tests three production feature sets via the SAME leak-free rolling-origin retrain
(XGB+LGB+MLP->NNLS, scripts.cache_pergame_oof._train_and_predict_stat), apples-to-
apples (identical rows, identical box-signal source from _scratch_ben_ortho.build_signals):
  OFF   = production feature_columns(stat)
  TEAM  = OFF + [vac_min, vac_pts, n_out]                 (team-total vacated load)
  STACK = TEAM + [pos_vac_min, pos_vac_pts, pos_n_out]    (+ position-matched, ortho-confirmed)

Leak-free: per-month rolling origin (train strictly date<cutoff); all vac signals are
strictly as-of L10 prior-games-only (build_signals). Grades vs REAL lines (Family A
benashkar 2025-26 reg; Family C 2024-25 odds-api cross-season) with intel_grade
discipline (drop |odds|<100, coherence guard, MAE paired bootstrap, ungated + edge>=1
ROI, bootstrap CI). Tells us: (1) does team-total vac lift PTS/REB ROI cross-season?
(2) does position-matched add incrementally beyond team-total?

Read-only except per-row parquets data/cache/pit/vacstack_prod_rows_*.parquet + this
file. No production code, no git commit.

Run (GPU, heavy):
  conda run -n basketball_ai python scripts/pit/validate_vac_stack_feature.py --stats pts,reb --sets off,team,stack
"""
from __future__ import annotations
import argparse, sys
from datetime import datetime, timedelta
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "pit"))

# reuse grading primitives + corpora from the team-total validator
from validate_vac_load_feature import (  # noqa: E402
    CORPORA, OUT_DIR, norm, _name_pid_map, _load_corpus_df,
    roi_list, boot_ci, coherence,
)
from _scratch_ben_ortho import build_signals  # noqa: E402

TEAM_KEYS = ["vac_min", "vac_pts", "n_out"]
POS_KEYS = ["pos_vac_min", "pos_vac_pts", "pos_n_out"]


def attach_signals(rows):
    """Attach team + pos vac to each dataset row (default 0 where no out-regulars)."""
    sig = build_signals()
    matched = 0
    for r in rows:
        pid = int(r.get("player_id", 0)); ds = str(r.get("date"))[:10]
        rec = sig.get((pid, ds))
        if rec is None:
            r["vac_min"] = r["vac_pts"] = r["n_out"] = 0.0
            r["pos_vac_min"] = r["pos_vac_pts"] = r["pos_n_out"] = 0.0
        else:
            r["vac_min"] = rec["team_vac_min"]; r["vac_pts"] = rec["team_vac_pts"]; r["n_out"] = rec["team_n_out"]
            r["pos_vac_min"] = rec["pos_vac_min"]; r["pos_vac_pts"] = rec["pos_vac_pts"]; r["pos_n_out"] = rec["pos_n_out"]
            matched += 1
    print(f"  rows with vac-signal match: {matched}/{len(rows)} ({100*matched/max(1,len(rows)):.1f}%)", flush=True)


def rolling_predict(stat, recs, rows, dates_all, fc, tag):
    from scripts.cache_pergame_oof import _train_and_predict_stat
    tgt = f"target_{stat}"
    months = sorted({r["date"][:7] for r in recs})
    cut_for = {m: min(r["date"] for r in recs if r["date"][:7] == m) for m in months}
    for m in months:
        cutoff = cut_for[m]
        bucket = [r for r in recs if r["date"][:7] == m]
        tr_idx = [i for i, d in enumerate(dates_all) if d < cutoff]
        if len(tr_idx) < 2000:
            for r in bucket:
                r[tag] = None
            continue
        n_tr = len(tr_idx); va = int(n_tr * 0.85)
        tr_rows = [rows[i] for i in tr_idx[:va]]; va_rows = [rows[i] for i in tr_idx[va:]]
        X_tr = np.array([[rr[c] for c in fc] for rr in tr_rows], float)
        X_val = np.array([[rr[c] for c in fc] for rr in va_rows], float)
        y_tr = np.array([rr[tgt] for rr in tr_rows], float)
        y_val = np.array([rr[tgt] for rr in va_rows], float)
        X_ho = np.array([[r["row"][c] for c in fc] for r in bucket], float)
        td = [datetime.fromisoformat(rr["date"][:10]) for rr in tr_rows]
        sw = np.exp(-0.5 * np.array([(max(td) - d).days / 365.0 for d in td]))
        preds = _train_and_predict_stat(stat, X_tr, y_tr, X_val, y_val, X_ho, sw)
        for r, p in zip(bucket, preds):
            r[tag] = float(p)


def match_corpus(key, stat, rows, nm):
    corpus, lo, hi, label = CORPORA[key]
    tgt = f"target_{stat}"
    df = _load_corpus_df(corpus, stat)
    if df.empty:
        return []
    df["pid"] = df["player"].map(lambda x: nm.get(norm(x)))
    df = df.dropna(subset=["pid"]); df["pid"] = df["pid"].astype(int)
    df["date2"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    by_key = {(int(r.get("player_id", 0)), str(r["date"])[:10]): r for r in rows}
    recs = []
    for r in df.itertuples(index=False):
        if not (lo <= r.date2 <= hi):
            continue
        cands = []
        for k in (-1, 0, 1):
            dd = (datetime.fromisoformat(r.date2) + timedelta(days=k)).strftime("%Y-%m-%d")
            dr = by_key.get((int(r.pid), dd))
            if dr is not None and abs(float(dr[tgt]) - float(r.actual_value)) < 0.5:
                cands.append((dd, dr))
        if not cands or len({c[0] for c in cands}) > 1:
            continue
        td, dr = cands[0]
        recs.append({"date": td, "pid": int(r.pid), "line": float(r.closing_line),
                     "over_odds": float(r.over_odds), "under_odds": float(r.under_odds),
                     "actual": float(r.actual_value), "row": dr})
    return recs


def grade(graded, key, stat, sets):
    cb = [{"line": r["line"], "actual": r["actual"], "over_odds": r["over_odds"],
           "under_odds": r["under_odds"]} for r in graded]
    o, u, s = coherence(cb)
    if s >= 0:
        print(f"  [{key}/{stat}] coherence {s:+.2f}% CORRUPT — refuse"); return None
    res = {"key": key, "stat": stat, "n": len(graded), "coh": s, "sets": {}}
    base_tag = f"pred_{sets[0]}"
    for tag in sets:
        pk = f"pred_{tag}"
        ae = np.array([abs(r[pk] - r["actual"]) for r in graded], float)
        mae = float(ae.mean())
        bets = [{"pred": r[pk], "line": r["line"], "actual": r["actual"],
                 "over_odds": r["over_odds"], "under_odds": r["under_odds"]} for r in graded]
        ung = roi_list(bets, "pred")
        gated = roi_list([b for b in bets if abs(b["pred"] - b["line"]) >= 1.0], "pred")
        ci = boot_ci(ung["pnls"])
        flips = sum(1 for r in graded if (r[pk] > r["line"]) != (r[base_tag] > r["line"]))
        res["sets"][tag] = {"mae": mae, "ung": ung["roi_pct"], "ung_n": ung["n"],
                            "gated": gated["roi_pct"], "gated_n": gated["n"],
                            "ci": ci, "flips": flips}
    pd.DataFrame([{"date": r["date"], "pid": r["pid"], "stat": stat, "line": r["line"],
                   "actual": r["actual"], **{f"pred_{t}": r[f"pred_{t}"] for t in sets},
                   "over_odds": r["over_odds"], "under_odds": r["under_odds"]} for r in graded]
                 ).to_parquet(OUT_DIR / f"vacstack_prod_rows_{key}_{stat}.parquet", index=False)
    print(f"  ===== {key}/{stat} n={len(graded)} coh={s:+.2f}% =====")
    for tag in sets:
        d = res["sets"][tag]
        print(f"    {tag:6s} MAE={d['mae']:.4f}  ungROI={d['ung']:+.2f}% (n{d['ung_n']}, CI[{d['ci'][0]:+.1f},{d['ci'][1]:+.1f}])  "
              f"edge>=1 ROI={d['gated']:+.2f}% (n{d['gated_n']})  flips_vs_{sets[0]}={d['flips']}")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", default="pts,reb")
    ap.add_argument("--sets", default="off,team,stack")
    ap.add_argument("--corpus", choices=["A", "C", "both"], default="both")
    args = ap.parse_args()
    stats = [s.strip() for s in args.stats.split(",") if s.strip()]
    sets = [s.strip() for s in args.sets.split(",") if s.strip()]

    from src.prediction.prop_pergame import build_pergame_dataset, feature_columns
    print("Building dataset + attaching vac signals ...", flush=True)
    rows, _ = build_pergame_dataset(min_prior=0)
    attach_signals(rows)
    rows.sort(key=lambda r: r["date"])
    dates_all = [str(r["date"])[:10] for r in rows]
    nm = _name_pid_map()

    def feats(stat, tag):
        base = feature_columns(stat=stat)
        if tag == "off":
            return base
        if tag == "team":
            return base + TEAM_KEYS
        return base + TEAM_KEYS + POS_KEYS

    keys = ["A", "C"] if args.corpus == "both" else [args.corpus]
    allres = []
    for stat in stats:
        print(f"\n{'#'*78}\n# STAT {stat}\n{'#'*78}")
        for key in keys:
            recs = match_corpus(key, stat, rows, nm)
            print(f"  [{key}/{stat}] matched n={len(recs)}", flush=True)
            if len(recs) < 30:
                print(f"  [{key}/{stat}] <30 — skip"); continue
            for tag in sets:
                fc = feats(stat, tag)
                print(f"  [{key}/{stat}] rolling {tag} ({len(fc)} cols)...", flush=True)
                rolling_predict(stat, recs, rows, dates_all, fc, f"pred_{tag}")
            graded = [r for r in recs if all(r.get(f"pred_{t}") is not None for t in sets)]
            if len(graded) < 30:
                print(f"  [{key}/{stat}] <30 graded — skip"); continue
            res = grade(graded, key, stat, sets)
            if res:
                allres.append(res)

    print("\n" + "=" * 100)
    print(" SUMMARY — OFF vs TEAM-vac vs STACK(+pos), production rolling-origin, vs real lines")
    print("=" * 100)
    for r in allres:
        tag = f"{CORPORA[r['key']][3][:10]}/{r['stat']}"
        line = f"  {tag:20s} n={r['n']:4d}  "
        for t in r["sets"]:
            d = r["sets"][t]
            line += f"{t}:MAE{d['mae']:.3f}/ung{d['ung']:+.1f}%/e1{d['gated']:+.1f}%  "
        print(line)
    print("\n  Read: team-lift = team.ung - off.ung; pos-incremental = stack.ung - team.ung. "
          "Want positive on A AND not inverted on C.")


if __name__ == "__main__":
    main()
