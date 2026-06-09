"""validate_vac_ast_feature.py — PRODUCTION-PATH validation of the gated
`vac_ast` AST model feature (flag CV_AST_VAC_FEATURE in
src/prediction/prop_pergame.py), on the AUTHORITATIVE rolling-origin retrain.

WHAT THIS DOES (and how it differs from exp_crosseason_validate.cmd_vacfeat):
  * exp_crosseason hand-appended a single vac_ast column to the X matrix.
  * THIS drives the contrast through the PRODUCTION `feature_columns("ast")`:
      - OFF model  -> the legacy 129-col AST feature list (flag absent)
      - ON  model  -> feature_columns("ast") with CV_AST_VAC_FEATURE=1
                       == 131 cols (vac_ast + vac_ast_share appended last)
    Both models train via the SAME scripts.cache_pergame_oof._train_and_predict_stat
    (XGB+LGB+MLP -> NNLS, identical to the shipped OOF stack), GPU, same folds /
    seed / sample weights, on the SAME row substrate (dataset built ONCE with the
    flag ON so every row carries vac_ast; OFF simply omits the 2 cols). This is a
    true apples-to-apples production comparison.

LEAK-FREE: per-month rolling origin, train strictly on rows dated < cutoff,
predict the held-out month; +/-1d actual-disambiguated corpus match (mirrors
exp_crosseason gen_rolling_preds). vac_ast itself is leak-free by construction
(as-of L10, prior games only — see prop_pergame.build_vac_ast_lookup).

GRADING: intel_grade discipline — drop |odds|<100, coherence guard, gated-AST
ROI (edge>=0.75, line<=7.5), paired bootstrap on per-row |residual| for MAE,
bootstrap CI on ROI. TWO corpora:
  * Family A — benashkar_2026_canonical.csv (2025-26 reg, DK/FD/MGM), reg part
    only (<=2026-04-12, the substrate/regular-season window).
  * Family C — regular_season_2024_25_oddsapi.csv (DIFFERENT season) — the
    CROSS-SEASON robustness check (the gate INVERTED here; does the FEATURE?).

DISJOINT WRITE: this file + per-row parquets under data/cache/pit/
vacfeat_prod_rows_<corpus>.parquet. No production code, no vault, no git commit.

Run (GPU, ~minutes per corpus; AST-only):
  conda run -n basketball_ai python scripts/pit/validate_vac_ast_feature.py
  conda run -n basketball_ai python scripts/pit/validate_vac_ast_feature.py --corpus A
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

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "pit"))

OUT_DIR = ROOT / "data" / "cache" / "pit"
LINES = ROOT / "data" / "external" / "historical_lines"

EDGE_MIN, LINE_CAP = 0.75, 7.5      # the shipped gated-AST set
RNG = np.random.default_rng(20260601)

CORPORA = {
    "A": ("benashkar_2026_canonical.csv", "2026-01-28", "2026-04-12", "Family A (2025-26 reg, DK/FD/MGM)"),
    "B": ("regular_season_2025_26_oddsapi.csv", "2025-10-01", "2026-04-12", "Family B (2025-26 reg, odds-api — INDEP same-season cross-book)"),
    "C": ("regular_season_2024_25_oddsapi.csv", "2024-10-01", "2025-05-31", "Family C (2024-25 reg, odds-api — CROSS-SEASON)"),
}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s.lower())).strip()


def _name_pid_map():
    from nba_api.stats.static import players as P
    nm = {}
    for p in P.get_players():
        nm.setdefault(norm(p["full_name"]), p["id"])
    return nm


def _load_corpus_df(corpus):
    """Robust ragged-CSV load -> AST rows only, with |odds|>=100 enforced."""
    import csv
    rows = []
    with open(LINES / corpus, encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            if (r.get("stat") or "").strip().lower() != "ast":
                continue
            try:
                line = float(r["closing_line"]); oo = float(r["over_odds"])
                uo = float(r["under_odds"]); act = float(r["actual_value"])
            except (TypeError, ValueError, KeyError):
                continue
            if abs(oo) < 100 or abs(uo) < 100:
                continue
            rows.append({"date": (r.get("date") or "").strip(),
                         "player": (r.get("player") or "").strip(),
                         "closing_line": line, "over_odds": oo,
                         "under_odds": uo, "actual_value": act})
    return pd.DataFrame(rows)


# ── settle / ROI (intel_grade semantics) ──────────────────────────────────────
def _payout(odds, win):
    if not win:
        return -100.0
    return (100.0 / abs(odds) * 100.0) if odds < 0 else (odds / 100.0 * 100.0)


def _bet_pnl(b, predictor):
    pred = b.get(predictor)
    if pred is None or (isinstance(pred, float) and np.isnan(pred)):
        return None
    line, actual = b["line"], b["actual"]
    if abs(pred - line) < 1e-9 or abs(actual - line) < 1e-9:
        return None
    bet_over = pred > line
    won = (bet_over and actual > line) or (not bet_over and actual < line)
    odds = b["over_odds"] if bet_over else b["under_odds"]
    return _payout(odds, won), bool(won)


def roi_list(bets, predictor):
    pnls = []
    for b in bets:
        r = _bet_pnl(b, predictor)
        if r is not None:
            pnls.append(r[0])
    if not pnls:
        return {"n": 0, "roi_pct": 0.0, "win_pct": 0.0, "pnls": np.array([])}
    pnls = np.array(pnls, float)
    return {"n": len(pnls), "roi_pct": float(pnls.mean()),
            "win_pct": float(100 * (pnls > 0).mean()), "pnls": pnls}


def boot_ci(pnls, n_boot=5000):
    if len(pnls) < 5:
        return (np.nan, np.nan, np.nan)
    pnls = np.asarray(pnls, float)
    means = np.array([RNG.choice(pnls, len(pnls), replace=True).mean() for _ in range(n_boot)])
    return (float(np.percentile(means, 5)), float(np.percentile(means, 95)), float((means <= 0).mean()))


def coherence(bets):
    def blind(side):
        ps = []
        for b in bets:
            if abs(b["actual"] - b["line"]) < 1e-9:
                continue
            over = side == "over"
            won = (over and b["actual"] > b["line"]) or (not over and b["actual"] < b["line"])
            odds = b["over_odds"] if over else b["under_odds"]
            ps.append(_payout(odds, won))
        return float(np.mean(ps)) if ps else 0.0
    o, u = blind("over"), blind("under")
    return o, u, o + u


# ── rolling-origin production retrain, AST-only, OFF vs ON ────────────────────
def run_corpus(key, rows, dates_all, fc_off, fc_on):
    from scripts.cache_pergame_oof import _train_and_predict_stat

    corpus, lo, hi, label = CORPORA[key]
    print("\n" + "#" * 78)
    print(f"# CORPUS {key}: {label}")
    print(f"#   file={corpus}  window {lo}..{hi}")
    print("#" * 78)

    nm = _name_pid_map()
    df = _load_corpus_df(corpus)
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
            if dr is not None and abs(float(dr["target_ast"]) - float(r.actual_value)) < 0.5:
                cands.append((dd, dr))
        if not cands or len({c[0] for c in cands}) > 1:
            continue
        td, dr = cands[0]
        recs.append({"date": td, "pid": int(r.pid), "line": float(r.closing_line),
                     "over_odds": float(r.over_odds), "under_odds": float(r.under_odds),
                     "actual": float(r.actual_value), "row": dr})
    print(f"  corpus AST rows matched to dataset: n={len(recs)}")
    if not recs:
        print("  !! 0 matched — corpus window not in build_pergame_dataset, SKIP")
        return None

    def rolling(fc, tag):
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
            y_tr = np.array([rr["target_ast"] for rr in tr_rows], float)
            y_val = np.array([rr["target_ast"] for rr in va_rows], float)
            X_ho = np.array([[r["row"][c] for c in fc] for r in bucket], float)
            td = [datetime.fromisoformat(rr["date"][:10]) for rr in tr_rows]
            sw = np.exp(-0.5 * np.array([(max(td) - d).days / 365.0 for d in td]))
            preds = _train_and_predict_stat("ast", X_tr, y_tr, X_val, y_val, X_ho, sw)
            for r, p in zip(bucket, preds):
                r[tag] = float(p)

    print(f"  [rolling-origin OFF: {len(fc_off)} cols] ...", flush=True)
    rolling(fc_off, "pred_off")
    print(f"  [rolling-origin ON : {len(fc_on)} cols (+vac_ast,vac_ast_share)] ...", flush=True)
    rolling(fc_on, "pred_on")

    graded = [r for r in recs if r.get("pred_off") is not None and r.get("pred_on") is not None]
    if not graded:
        print("  !! no graded rows"); return None

    # persist per-row
    pd.DataFrame([{"date": r["date"], "pid": r["pid"], "line": r["line"], "actual": r["actual"],
                   "pred_off": r["pred_off"], "pred_on": r["pred_on"],
                   "over_odds": r["over_odds"], "under_odds": r["under_odds"]} for r in graded]
                 ).to_parquet(OUT_DIR / f"vacfeat_prod_rows_{key}.parquet", index=False)

    # coherence guard
    cb = [{"line": r["line"], "actual": r["actual"], "over_odds": r["over_odds"],
           "under_odds": r["under_odds"]} for r in graded]
    o, u, s = coherence(cb)
    print(f"  coherence: blind-O {o:+.2f}% + blind-U {u:+.2f}% = {s:+.2f}% "
          f"({'OK (negative)' if s < 0 else 'CORRUPT — refuse'})")
    if s >= 0:
        print("  !! corrupt odds — refusing to grade")
        return None

    # MAE (paired bootstrap on per-row |residual| improvement)
    ae0 = np.array([abs(r["pred_off"] - r["actual"]) for r in graded], float)
    ae1 = np.array([abs(r["pred_on"] - r["actual"]) for r in graded], float)
    mae0, mae1 = float(ae0.mean()), float(ae1.mean())
    dmae = ae0 - ae1  # >0 => ON better
    bm = np.array([RNG.choice(dmae, len(dmae), replace=True).mean() for _ in range(5000)])
    p_on_better = float((bm > 0).mean())

    # ROI: ungated + gated
    def mk(r, key_):
        return {"pred": r[key_], "line": r["line"], "actual": r["actual"],
                "over_odds": r["over_odds"], "under_odds": r["under_odds"]}
    b_off = [mk(r, "pred_off") for r in graded]
    b_on = [mk(r, "pred_on") for r in graded]

    def gated(bs):
        return [b for b in bs if abs(b["pred"] - b["line"]) >= EDGE_MIN and b["line"] <= LINE_CAP]
    r_off = roi_list(b_off, "pred"); r_on = roi_list(b_on, "pred")
    g_off = roi_list(gated(b_off), "pred"); g_on = roi_list(gated(b_on), "pred")
    g_off_ci = boot_ci(g_off["pnls"]); g_on_ci = boot_ci(g_on["pnls"])
    flips = sum(1 for r in graded if (r["pred_off"] > r["line"]) != (r["pred_on"] > r["line"]))

    print(f"\n  ===== RESULT corpus {key} (n={len(graded)}) =====")
    print(f"  MAE      OFF={mae0:.4f}  ON={mae1:.4f}  dMAE={mae1-mae0:+.4f} "
          f"({'IMPROVES' if mae1 < mae0 - 1e-4 else ('no MAE gain' if mae1 <= mae0 + 1e-4 else 'WORSE')})  "
          f"P(ON better, paired boot)={p_on_better:.3f}")
    print(f"  ungated  OFF={r_off['roi_pct']:+.2f}% (n{r_off['n']})  ON={r_on['roi_pct']:+.2f}% (n{r_on['n']})")
    print(f"  GATED    OFF={g_off['roi_pct']:+.2f}% (n{g_off['n']}, win {g_off['win_pct']:.1f}%, "
          f"CI[{g_off_ci[0]:+.1f},{g_off_ci[1]:+.1f}])")
    print(f"           ON ={g_on['roi_pct']:+.2f}% (n{g_on['n']}, win {g_on['win_pct']:.1f}%, "
          f"CI[{g_on_ci[0]:+.1f},{g_on_ci[1]:+.1f}])  lift={g_on['roi_pct']-g_off['roi_pct']:+.2f}pp")
    print(f"  direction flips from adding vac_ast: {flips}/{len(graded)}")
    return {"key": key, "n": len(graded), "mae0": mae0, "mae1": mae1,
            "p_on_better": p_on_better, "g_off": g_off, "g_on": g_on,
            "g_off_ci": g_off_ci, "g_on_ci": g_on_ci,
            "ung_off": r_off, "ung_on": r_on, "flips": flips}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", choices=["A", "B", "C", "both"], default="both")
    args = ap.parse_args()

    # Build the dataset ONCE with the flag ON so every row carries vac_ast /
    # vac_ast_share. The OFF model just doesn't read those 2 cols.
    os.environ["CV_AST_VAC_FEATURE"] = "1"
    from src.prediction.prop_pergame import build_pergame_dataset, feature_columns

    print("Building per-game dataset (flag ON so rows carry vac_ast) ...", flush=True)
    rows, _ = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    dates_all = [str(r["date"])[:10] for r in rows]
    fc_on = feature_columns(stat="ast")
    fc_off = [c for c in fc_on if c not in ("vac_ast", "vac_ast_share")]
    print(f"  dataset rows={len(rows)}  OFF cols={len(fc_off)}  ON cols={len(fc_on)}")
    assert len(fc_on) == len(fc_off) + 2 and fc_on[-2:] == ["vac_ast", "vac_ast_share"]

    keys = ["A", "C"] if args.corpus == "both" else [args.corpus]
    results = {}
    for k in keys:
        res = run_corpus(k, rows, dates_all, fc_off, fc_on)
        if res:
            results[k] = res

    # ── verdict summary ──
    print("\n" + "=" * 78)
    print(" SUMMARY — vac_ast as a TRAINED AST feature (ON vs OFF), production path")
    print("=" * 78)
    print(f"  {'corpus':28s} {'n':>5s} {'MAE OFF':>9s} {'MAE ON':>9s} {'P(ON<)':>7s} "
          f"{'gROI OFF':>9s} {'gROI ON':>9s} {'lift':>7s}")
    for k in keys:
        if k not in results:
            print(f"  {CORPORA[k][3]:28.28s}  (no graded rows)")
            continue
        r = results[k]
        print(f"  {CORPORA[k][3]:28.28s} {r['n']:5d} {r['mae0']:9.4f} {r['mae1']:9.4f} "
              f"{r['p_on_better']:7.3f} {r['g_off']['roi_pct']:+8.2f}% {r['g_on']['roi_pct']:+8.2f}% "
              f"{r['g_on']['roi_pct']-r['g_off']['roi_pct']:+6.2f}pp")
    print("\n  SHIP rule: ON lowers MAE on A AND does NOT degrade cross-season (C) "
          "(the FEATURE must be more robust than the gate that INVERTED on C).")


if __name__ == "__main__":
    main()
