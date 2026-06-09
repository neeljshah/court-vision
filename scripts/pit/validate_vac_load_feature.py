"""validate_vac_load_feature.py — generalize the vac_ast win to TEAM VACATED LOAD
as TRAINED features for PTS / REB (and optionally FG3M).

WHY: the orthogonality screen (scripts/pit/ortho_screen_conditioners.py) shows the
production model trains on ZERO vacated-load features (vac_min/vac_pts/n_out are
absent from feature_columns), yet they carry strong residual correlation:
  vac_pts -> PTS resid +0.155, REB +0.119, AST +0.112; vac_min similar; n_out too.
The model systematically UNDER-predicts when teammates are out. vac_ast was the
AST-specific case of this. This script tests the GENERALIZATION leak-free, on the
PRODUCTION rolling-origin retrain path (identical to validate_vac_ast_feature.py).

WHAT: OFF model = production feature_columns(stat). ON model = same +3 leak-free
columns [vac_min, vac_pts, n_out]. Both train via
scripts.cache_pergame_oof._train_and_predict_stat (XGB+LGB+MLP->NNLS), GPU, same
folds/seed/sample-weights, on the SAME row substrate (vac cols attached once).
Per-month rolling origin (train strictly date<cutoff). vac_* leak-free by
construction (as-of L10, prior games only — mirrors build_vac_ast_lookup, extended
to PTS so we get vac_pts/vac_min/n_out from the SAME out-regulars set).

GRADE: intel_grade discipline — drop |odds|<100, coherence guard, MAE paired
bootstrap, ROI ungated + gated, bootstrap CI. TWO corpora:
  A = benashkar_2026_canonical.csv (2025-26 reg, DK/FD/MGM)  [<=2026-04-12]
  C = regular_season_2024_25_oddsapi.csv (DIFFERENT season — cross-season check)
SHIP rule: ON lowers MAE on A AND lifts (or for PTS: makes-less-negative) ROI on A
AND does NOT invert cross-season on C.

Read-only except per-row parquets under data/cache/pit/vacload_prod_rows_*.parquet
and this file. No production code, no vault, no git commit.

Run (GPU):
  conda run -n basketball_ai python scripts/pit/validate_vac_load_feature.py --stats pts,reb
  conda run -n basketball_ai python scripts/pit/validate_vac_load_feature.py --stats pts,reb --corpus A
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import unicodedata
import warnings
from collections import defaultdict
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
CVFIX = ROOT / "data" / "cache" / "cv_fix"
NBA_CACHE = ROOT / "data" / "nba"

RNG = np.random.default_rng(20260601)
VAC_KEYS = ["vac_min", "vac_pts", "n_out"]

# per-stat gate used for the gated-ROI slice (selection where |edge| big enough).
# PTS/REB have no validated gate -> report ungated as primary + an edge>=1.0 slice.
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


def _vac_team_of_matchup(matchup):
    if not matchup:
        return None
    m = str(matchup).split()
    return m[0].upper() if m else None


# ── leak-free vacated-LOAD lookup (mirrors build_vac_ast_lookup, +PTS) ─────────
def build_vac_load_lookup() -> dict:
    """{(pid_appeared, 'YYYY-MM-DD'): {vac_min, vac_pts, n_out}}  leak-free.

    Same out-regulars logic as prop_pergame.build_vac_ast_lookup: roster = players
    who appeared in the team's prior 3 games; out = roster - appeared with as-of L10
    minutes >= 15. vac_min/vac_pts = sum of those out-regulars' as-of L10 min/pts;
    n_out = count. As-of (prior games only) => leak-free.
    """
    rows = []  # (date_ts, team, pid, ast(unused), min, pts)

    for fn in ("leaguegamelog_regular_season.parquet", "leaguegamelog_playoffs.parquet"):
        p = CVFIX / fn
        if not p.is_file():
            continue
        try:
            df = pd.read_parquet(p)
        except Exception:
            continue
        for r in df.itertuples(index=False):
            d = pd.to_datetime(getattr(r, "GAME_DATE", None), errors="coerce")
            if pd.isna(d):
                continue
            try:
                mn = float(r.MIN) if pd.notna(r.MIN) else None
            except (TypeError, ValueError):
                mn = None
            try:
                pts = float(r.PTS) if pd.notna(r.PTS) else 0.0
            except (TypeError, ValueError):
                pts = 0.0
            rows.append((d.normalize(), str(r.TEAM_ABBREVIATION).upper(),
                         int(r.PLAYER_ID), mn, pts))

    for fp in glob.glob(str(NBA_CACHE / "gamelog_*_2024-25.json")):
        base = os.path.basename(fp)
        if not base.endswith("_2024-25.json"):
            continue
        try:
            pid = int(base.split("_")[1])
        except (IndexError, ValueError):
            continue
        try:
            log = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(log, list):
            continue
        for g in log:
            d = pd.to_datetime(g.get("GAME_DATE"), errors="coerce")
            team = _vac_team_of_matchup(g.get("MATCHUP"))
            if pd.isna(d) or team is None:
                continue
            try:
                mn = float(g.get("MIN")) if g.get("MIN") is not None else None
            except (TypeError, ValueError):
                mn = None
            try:
                pts = float(g.get("PTS") or 0.0)
            except (TypeError, ValueError):
                pts = 0.0
            rows.append((d.normalize(), team, pid, mn, pts))

    if not rows:
        return {}

    by_player = defaultdict(list)     # pid -> [(date, min, pts)]
    team_games = defaultdict(set)     # (team, date) -> {pid appeared min>=1}
    team_dates = defaultdict(set)
    for d, team, pid, mn, pts in rows:
        by_player[pid].append((d, mn, pts))
        if mn is not None and mn >= 1:
            team_games[(team, d)].add(pid)
            team_dates[team].add(d)
    for pid in by_player:
        by_player[pid].sort()

    def asof_l10(pid, d):
        hist = [(mn, pts) for (dd, mn, pts) in by_player.get(pid, [])
                if dd < d and mn is not None and mn >= 1]
        if not hist:
            return 0.0, 0.0
        h = hist[-10:]
        return (float(np.mean([x[0] for x in h])), float(np.mean([x[1] for x in h])))

    out = {}
    for (team, d), appeared in team_games.items():
        tdates = sorted(team_dates[team])
        i = tdates.index(d)
        if i < 3:
            continue
        prior3 = tdates[max(0, i - 3):i]
        roster = set()
        for pd_ in prior3:
            roster |= team_games[(team, pd_)]
        vac_min = vac_pts = 0.0
        n_out = 0
        for pid in roster:
            if pid in appeared:
                continue
            lm, lp = asof_l10(pid, d)
            if lm >= 15:
                vac_min += lm
                vac_pts += lp
                n_out += 1
        ds = d.date().isoformat()
        rec = {"vac_min": float(vac_min), "vac_pts": float(vac_pts), "n_out": float(n_out)}
        for pid in appeared:
            out[(int(pid), ds)] = rec
    return out


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


def _load_corpus_df(corpus, stat):
    import csv
    rows = []
    with open(LINES / corpus, encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            if (r.get("stat") or "").strip().lower() != stat:
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


# ── rolling-origin production retrain, per stat, OFF vs ON ─────────────────────
def run_corpus_stat(key, stat, rows, dates_all, fc_off, fc_on, nm):
    from scripts.cache_pergame_oof import _train_and_predict_stat

    corpus, lo, hi, label = CORPORA[key]
    tgt = f"target_{stat}"

    df = _load_corpus_df(corpus, stat)
    if df.empty:
        print(f"  [{key}/{stat}] 0 corpus rows"); return None
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
    print(f"  [{key}/{stat}] corpus rows matched to dataset: n={len(recs)}", flush=True)
    if len(recs) < 30:
        print(f"  [{key}/{stat}] <30 matched — SKIP"); return None

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
            y_tr = np.array([rr[tgt] for rr in tr_rows], float)
            y_val = np.array([rr[tgt] for rr in va_rows], float)
            X_ho = np.array([[r["row"][c] for c in fc] for r in bucket], float)
            td = [datetime.fromisoformat(rr["date"][:10]) for rr in tr_rows]
            sw = np.exp(-0.5 * np.array([(max(td) - d).days / 365.0 for d in td]))
            preds = _train_and_predict_stat(stat, X_tr, y_tr, X_val, y_val, X_ho, sw)
            for r, p in zip(bucket, preds):
                r[tag] = float(p)

    print(f"  [{key}/{stat}] rolling OFF ({len(fc_off)} cols)...", flush=True)
    rolling(fc_off, "pred_off")
    print(f"  [{key}/{stat}] rolling ON ({len(fc_on)} cols, +vac_min,vac_pts,n_out)...", flush=True)
    rolling(fc_on, "pred_on")

    graded = [r for r in recs if r.get("pred_off") is not None and r.get("pred_on") is not None]
    if len(graded) < 30:
        print(f"  [{key}/{stat}] <30 graded — SKIP"); return None

    pd.DataFrame([{"date": r["date"], "pid": r["pid"], "stat": stat, "line": r["line"],
                   "actual": r["actual"], "pred_off": r["pred_off"], "pred_on": r["pred_on"],
                   "over_odds": r["over_odds"], "under_odds": r["under_odds"]} for r in graded]
                 ).to_parquet(OUT_DIR / f"vacload_prod_rows_{key}_{stat}.parquet", index=False)

    cb = [{"line": r["line"], "actual": r["actual"], "over_odds": r["over_odds"],
           "under_odds": r["under_odds"]} for r in graded]
    o, u, s = coherence(cb)
    coh_ok = s < 0
    if not coh_ok:
        print(f"  [{key}/{stat}] coherence {s:+.2f}% CORRUPT — refuse"); return None

    ae0 = np.array([abs(r["pred_off"] - r["actual"]) for r in graded], float)
    ae1 = np.array([abs(r["pred_on"] - r["actual"]) for r in graded], float)
    mae0, mae1 = float(ae0.mean()), float(ae1.mean())
    dmae = ae0 - ae1
    bm = np.array([RNG.choice(dmae, len(dmae), replace=True).mean() for _ in range(5000)])
    p_on_better = float((bm > 0).mean())

    def mk(r, kk):
        return {"pred": r[kk], "line": r["line"], "actual": r["actual"],
                "over_odds": r["over_odds"], "under_odds": r["under_odds"]}
    b_off = [mk(r, "pred_off") for r in graded]
    b_on = [mk(r, "pred_on") for r in graded]

    def edge_gate(bs, e):
        return [b for b in bs if abs(b["pred"] - b["line"]) >= e]
    r_off = roi_list(b_off, "pred"); r_on = roi_list(b_on, "pred")
    g_off = roi_list(edge_gate(b_off, 1.0), "pred"); g_on = roi_list(edge_gate(b_on, 1.0), "pred")
    flips = sum(1 for r in graded if (r["pred_off"] > r["line"]) != (r["pred_on"] > r["line"]))
    u_off_ci = boot_ci(r_off["pnls"]); u_on_ci = boot_ci(r_on["pnls"])

    print(f"  ===== {key}/{stat} n={len(graded)} coherence={s:+.2f}% =====")
    print(f"    MAE    OFF={mae0:.4f} ON={mae1:.4f} dMAE={mae1-mae0:+.4f} "
          f"({'IMPROVES' if mae1 < mae0-1e-4 else ('flat' if mae1 <= mae0+1e-4 else 'WORSE')}) "
          f"P(ON better)={p_on_better:.3f}")
    print(f"    ROI ungated OFF={r_off['roi_pct']:+.2f}% (n{r_off['n']}, CI[{u_off_ci[0]:+.1f},{u_off_ci[1]:+.1f}]) "
          f"ON={r_on['roi_pct']:+.2f}% (n{r_on['n']}, CI[{u_on_ci[0]:+.1f},{u_on_ci[1]:+.1f}]) "
          f"lift={r_on['roi_pct']-r_off['roi_pct']:+.2f}pp")
    print(f"    ROI edge>=1 OFF={g_off['roi_pct']:+.2f}% (n{g_off['n']}) ON={g_on['roi_pct']:+.2f}% (n{g_on['n']}) "
          f"lift={g_on['roi_pct']-g_off['roi_pct']:+.2f}pp  flips={flips}")
    return {"key": key, "stat": stat, "n": len(graded), "mae0": mae0, "mae1": mae1,
            "p_on_better": p_on_better, "ung_off": r_off["roi_pct"], "ung_on": r_on["roi_pct"],
            "g_off": g_off["roi_pct"], "g_on": g_on["roi_pct"], "flips": flips}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", default="pts,reb")
    ap.add_argument("--corpus", choices=["A", "B", "C", "both"], default="both")
    args = ap.parse_args()
    stats = [s.strip().lower() for s in args.stats.split(",") if s.strip()]

    from src.prediction.prop_pergame import build_pergame_dataset, feature_columns

    print("Building per-game dataset ...", flush=True)
    rows, _ = build_pergame_dataset(min_prior=0)
    print(f"  dataset rows={len(rows)}; building vac_load lookup ...", flush=True)
    vl = build_vac_load_lookup()
    print(f"  vac_load lookup keys={len(vl)}", flush=True)
    matched = 0
    for r in rows:
        pid = int(r.get("player_id", 0))
        ds = str(r.get("date"))[:10]
        rec = vl.get((pid, ds))
        if rec is None:
            r["vac_min"] = 0.0; r["vac_pts"] = 0.0; r["n_out"] = 0.0
        else:
            r["vac_min"] = rec["vac_min"]; r["vac_pts"] = rec["vac_pts"]; r["n_out"] = rec["n_out"]
            matched += 1
    print(f"  rows with vac_load match: {matched}/{len(rows)} "
          f"({100*matched/max(1,len(rows)):.1f}%)", flush=True)
    rows.sort(key=lambda r: r["date"])
    dates_all = [str(r["date"])[:10] for r in rows]

    nm = _name_pid_map()
    keys = ["A", "C"] if args.corpus == "both" else [args.corpus]
    results = []
    for stat in stats:
        fc_off = feature_columns(stat=stat)
        fc_on = fc_off + VAC_KEYS
        print(f"\n{'#'*78}\n# STAT {stat}: OFF={len(fc_off)} cols  ON={len(fc_on)} cols\n{'#'*78}")
        for k in keys:
            res = run_corpus_stat(k, stat, rows, dates_all, fc_off, fc_on, nm)
            if res:
                results.append(res)

    print("\n" + "=" * 90)
    print(" SUMMARY — vac_load (vac_min,vac_pts,n_out) as TRAINED features, production path")
    print("=" * 90)
    print(f"  {'corpus/stat':22s} {'n':>5s} {'MAE OFF':>8s} {'MAE ON':>8s} {'P(ON<)':>7s} "
          f"{'ungROI OFF':>10s} {'ungROI ON':>10s} {'lift':>7s}")
    for r in results:
        tag = f"{CORPORA[r['key']][3][:10]}/{r['stat']}"
        print(f"  {tag:22s} {r['n']:5d} {r['mae0']:8.4f} {r['mae1']:8.4f} {r['p_on_better']:7.3f} "
              f"{r['ung_off']:+9.2f}% {r['ung_on']:+9.2f}% {r['ung_on']-r['ung_off']:+6.2f}pp")
    print("\n  SHIP rule: ON lowers MAE on A AND improves (less-negative for PTS) ROI on A "
          "AND does NOT invert on C (cross-season).")


if __name__ == "__main__":
    main()
