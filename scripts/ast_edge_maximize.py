"""ast_edge_maximize.py — find the optimal HONEST AST-only betting policy + Kelly sizing.

GOAL: push the ONE durable pregame edge (AST) to its best honest betting config and
correct fractional-Kelly sizing. HOLD THE HONEST LINE: AST's in-window +19% gated is a
regime-inflated PEAK; the durable cross-season core is ~+5% (docs/VS_VEGAS_ASSESSMENT.md
§8e). It BREAKS in playoffs. Any "improvement" must survive a temporal split AND the
independent 2024-25 SEASON corpus AND |odds|>=100, or it is overfit.

This script does NOT touch any production model, projection, calibration, or flag. It is a
read-only analysis that grades the EXISTING leak-free AST predictions against real lines:

  Corpus 1 (in-window benashkar)  — prod OOF join, real DK/FD/MGM closes  (2026-01..04)
  Corpus 2 (extended_oos)         — prod OOF join, different book, same games (independent)
  Corpus 3 (2024-25 reg season)   — leak-free ROLLING-ORIGIN retrain (different SEASON)

For each it sweeps:
  1. Direction      : both / over-only / under-only
  2. Edge threshold : |pred - line| in {0.0,0.25,0.5,0.75,1.0,1.25,1.5}
  3. Line cap       : line<=7.5 vs uncapped vs by-bucket (low/mid/high/very_high)
  4. Pace tilt      : opp_pace tercile (sizing lever, not a hard filter)
  5. Kelly sizing   : fractional-Kelly stake from the DURABLE ~+5% edge + per-bet win prob

The "durable" verdict for any config = positive in BOTH temporal halves of the in-window
corpus AND positive (sign-consistent) on the 2024-25 SEASON corpus. We size on the
cross-season magnitude, never the in-window peak.

Reuses: scripts.run_gate1_full_analysis (loaders/settle/_payout),
        scripts.cache_pergame_oof._train_and_predict_stat (production training stack),
        src.prediction.prop_pergame.build_pergame_dataset / feature_columns.
Read-only. No commit, no flag flips.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
import warnings
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")
try:  # Windows cp1252 console can't encode box-drawing chars
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from scripts.run_gate1_full_analysis import (  # noqa: E402
    load_benashkar_bets, attach_actuals_and_l10, attach_oof, settle, _payout)

RNG = np.random.default_rng(20260604)
BEN_LO, BEN_HI = "2026-01-29", "2026-04-05"
FRAME = _ROOT / "data" / "cache" / "calibration_frame_v2.parquet"
EXTOOS = _ROOT / "data" / "external" / "historical_lines" / "extended_oos_canonical.csv"
REG2425 = _ROOT / "data" / "external" / "historical_lines" / "regular_season_2024_25_oddsapi.csv"
OOF_PROD = _ROOT / "data" / "cache" / "pregame_oof.parquet"
OOF_FAITH = _ROOT / "data" / "cache" / "pregame_oof_faithful.parquet"
OUT = _ROOT / "data" / "cache" / "ast_edge_maximize.json"

EDGE_GRID = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5]


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s.lower())).strip()


# ────────────────────────────────────────────────────────────────────────────
# Settle / ROI / bootstrap helpers — all at ACTUAL posted odds, |odds|>=100
# ────────────────────────────────────────────────────────────────────────────

def _settle_rec(line, actual, pred, over_odds, under_odds):
    """Return (over_bool, won_bool, payout) or None for push/no-bet."""
    if abs(pred - line) < 1e-9 or abs(actual - line) < 1e-9:
        return None
    over = pred > line
    won = (over and actual > line) or (not over and actual < line)
    return over, won, _payout(over_odds if over else under_odds, won)


def roi(rows):
    """rows = list of (over, won, payout). Returns (n, win%, roi%)."""
    if not rows:
        return 0, 0.0, 0.0
    n = len(rows)
    return n, sum(int(w) for _, w, _ in rows) / n * 100, sum(p for _, _, p in rows) / (n * 100) * 100


def boot_ci(rows, n_boot=8000):
    if not rows:
        return (0.0, 0.0, 1.0)
    pays = np.array([p for _, _, p in rows], float)
    bs = [RNG.choice(pays, len(pays), replace=True).sum() / (len(pays) * 100) * 100 for _ in range(n_boot)]
    bs = np.array(bs)
    return float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)), float((bs <= 0).mean())


def blind(records):
    """Market coherence: blind-OVER ROI + blind-UNDER ROI. Coherent if sum ~ -2*vig."""
    def forced(over):
        out = []
        for r in records:
            if abs(r["actual"] - r["line"]) < 1e-9:
                continue
            won = (over and r["actual"] > r["line"]) or (not over and r["actual"] < r["line"])
            out.append((over, won, _payout(r["over_odds"] if over else r["under_odds"], won)))
        return out
    return roi(forced(True))[2], roi(forced(False))[2]


# ────────────────────────────────────────────────────────────────────────────
# Corpus builders — produce a uniform record:
#   {date, line, actual, pred, over_odds, under_odds, opp_pace(optional)}
# ────────────────────────────────────────────────────────────────────────────

def _load_pace_frame():
    df = pd.read_parquet(FRAME)
    df = df[df["stat"] == "ast"][["player_id", "date", "opp_pace"]].copy()
    df["d"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return {(int(r.player_id), r.d): float(r.opp_pace)
            for r in df.itertuples(index=False) if pd.notna(r.opp_pace)}


def build_benashkar(oof_path=OOF_PROD):
    """In-window benashkar AST bets graded on a chosen OOF parquet (prod or faithful)."""
    bets = attach_actuals_and_l10(load_benashkar_bets(mainline_only=True))
    # attach_oof reads the module-level _OOF (prod). For faithful, do our own join.
    oof = pd.read_parquet(oof_path)
    oof["d"] = pd.to_datetime(oof["game_date"]).dt.strftime("%Y-%m-%d")
    idx = {(int(r.player_id), r.d, r.stat): float(r.oof_pred) for r in oof.itertuples(index=False)}
    pace = _load_pace_frame()
    recs = []
    for b in bets:
        if b["stat"] != "ast":
            continue
        d = b["gdate"].strftime("%Y-%m-%d")
        pred = idx.get((b["pid"], d, "ast"))
        if pred is None:
            continue
        recs.append({"pid": b["pid"], "date": d, "line": b["line"], "actual": b["actual"],
                     "pred": pred, "over_odds": b["over_odds"], "under_odds": b["under_odds"],
                     "opp_pace": pace.get((b["pid"], d))})
    recs.sort(key=lambda r: r["date"])
    return recs


def build_extoos(independent_only=True):
    """extended_oos AST joined to prod OOF (a DIFFERENT book than benashkar, same games).

    independent_only=True drops rows inside benashkar's window (the cleanest cross-book
    check); False keeps the full join (larger n, same-window overlap included).
    NOTE: blind-coherence of extended_oos is borderline (+1.8% on the tiny independent
    slice); always read its blindO/blindU split before trusting its ROI.
    """
    from nba_api.stats.static import players as P
    nm = {}
    for p in P.get_players():
        nm.setdefault(norm(p["full_name"]), p["id"])
    df = pd.read_csv(EXTOOS)
    df = df[df["stat"] == "ast"].copy()
    df["pid"] = df["player"].map(lambda x: nm.get(norm(x)))
    df = df.dropna(subset=["pid"])
    df["pid"] = df["pid"].astype(int)
    df = df[(df["over_odds"].abs() >= 100) & (df["under_odds"].abs() >= 100)]
    df["d"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    if independent_only:
        df = df[~((df["d"] >= BEN_LO) & (df["d"] <= BEN_HI))]
    oof = pd.read_parquet(OOF_PROD)
    oof["d"] = pd.to_datetime(oof["game_date"]).dt.strftime("%Y-%m-%d")
    idx = {(int(r.player_id), r.d, r.stat): float(r.oof_pred) for r in oof.itertuples(index=False)}
    pace = _load_pace_frame()
    recs = []
    for r in df.itertuples(index=False):
        pred = idx.get((int(r.pid), r.d, "ast"))
        if pred is None:
            continue
        recs.append({"pid": int(r.pid), "date": r.d, "line": float(r.closing_line),
                     "actual": float(r.actual_value), "pred": pred,
                     "over_odds": float(r.over_odds), "under_odds": float(r.under_odds),
                     "opp_pace": pace.get((int(r.pid), r.d))})
    recs.sort(key=lambda r: r["date"])
    return recs


def build_2024_25_rollingorigin():
    """2024-25 reg-season AST, leak-free rolling-origin retrain of the production stack.

    For each game-month, train the EXACT prod stack strictly on the past, predict the
    month's held-out AST bets. +/-1-day actual-value-disambiguated feature match.
    """
    from nba_api.stats.static import players as P
    from src.prediction.prop_pergame import build_pergame_dataset, feature_columns
    from scripts.cache_pergame_oof import _train_and_predict_stat
    nm = {}
    for p in P.get_players():
        nm.setdefault(norm(p["full_name"]), p["id"])

    print("  building pergame dataset for rolling-origin (2024-25) ...", flush=True)
    rows, _ = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    fc = feature_columns(stat="ast")
    by_key = {(int(r.get("player_id", 0)), str(r["date"])[:10]): r for r in rows}
    dates_all = [str(r["date"])[:10] for r in rows]

    df = pd.read_csv(REG2425)
    df = df[df["stat"] == "ast"].copy()
    df["pid"] = df["player"].map(lambda x: nm.get(norm(x)))
    df = df.dropna(subset=["pid"])
    df["pid"] = df["pid"].astype(int)
    df = df[(df["over_odds"].abs() >= 100) & (df["under_odds"].abs() >= 100)]
    df["d"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    pace = _load_pace_frame()
    recs = []
    for r in df.itertuples(index=False):
        cands = []
        for k in (-1, 0, 1):
            dd = (datetime.fromisoformat(r.d) + timedelta(days=k)).strftime("%Y-%m-%d")
            dr = by_key.get((int(r.pid), dd))
            if dr is not None and abs(float(dr["target_ast"]) - float(r.actual_value)) < 0.5:
                cands.append((dd, dr))
        if not cands or len({c[0] for c in cands}) > 1:
            continue
        td, dr = cands[0]
        recs.append({"pid": int(r.pid), "date": td, "line": float(r.closing_line),
                     "actual": float(r.actual_value), "over_odds": float(r.over_odds),
                     "under_odds": float(r.under_odds), "row": dr,
                     "opp_pace": pace.get((int(r.pid), td)), "pred": None})
    print(f"  2024-25 AST matched to pergame dataset: n={len(recs)}", flush=True)

    months = sorted({r["date"][:7] for r in recs})
    for m in months:
        cutoff = min(r["date"] for r in recs if r["date"][:7] == m)
        bucket = [r for r in recs if r["date"][:7] == m]
        tr_idx = [i for i, d in enumerate(dates_all) if d < cutoff]
        if len(tr_idx) < 2000:
            continue
        n_tr = len(tr_idx)
        va = int(n_tr * 0.85)
        tr_rows = [rows[i] for i in tr_idx[:va]]
        va_rows = [rows[i] for i in tr_idx[va:]]
        X_tr = np.array([[rr[c] for c in fc] for rr in tr_rows], float)
        X_val = np.array([[rr[c] for c in fc] for rr in va_rows], float)
        y_tr = np.array([rr["target_ast"] for rr in tr_rows], float)
        y_val = np.array([rr["target_ast"] for rr in va_rows], float)
        X_ho = np.array([[r["row"][c] for c in fc] for r in bucket], float)
        td = [datetime.fromisoformat(rr["date"][:10]) for rr in tr_rows]
        sw = np.exp(-0.5 * np.array([(max(td) - d).days / 365.0 for d in td]))
        preds = _train_and_predict_stat("ast", X_tr, y_tr, X_val, y_val, X_ho, sw)
        for r, p in zip(bucket, preds):
            r["pred"] = float(p)
        mae = np.mean([abs(r["pred"] - r["actual"]) for r in bucket])
        print(f"    [{m}] cutoff {cutoff} train_n={n_tr} bucket_n={len(bucket)} ho_mae={mae:.3f}", flush=True)

    out = [r for r in recs if r.get("pred") is not None]
    for r in out:
        r.pop("row", None)
    out.sort(key=lambda r: r["date"])
    return out


# ────────────────────────────────────────────────────────────────────────────
# Policy filter + grading
# ────────────────────────────────────────────────────────────────────────────

def filter_settle(recs, direction="both", edge_min=0.0, line_cap=None, line_lo=None,
                   pace_hi_only=False, pace_thresh=None):
    """Apply an AST policy and return list of (over, won, payout)."""
    out = []
    for r in recs:
        pred, line = r["pred"], r["line"]
        if abs(pred - line) < edge_min:
            continue
        if line_cap is not None and line > line_cap:
            continue
        if line_lo is not None and line <= line_lo:
            continue
        if pace_hi_only:
            p = r.get("opp_pace")
            if p is None or pace_thresh is None or p <= pace_thresh:
                continue
        over = pred > line
        if direction == "over" and not over:
            continue
        if direction == "under" and over:
            continue
        s = _settle_rec(line, r["actual"], pred, r["over_odds"], r["under_odds"])
        if s is None:
            continue
        out.append(s)
    return out


def temporal_halves(recs):
    if not recs:
        return None, None
    mid = recs[len(recs) // 2]["date"]
    return [r for r in recs if r["date"] < mid], [r for r in recs if r["date"] >= mid]


# ────────────────────────────────────────────────────────────────────────────
# Analyses
# ────────────────────────────────────────────────────────────────────────────

def section_faithful_check(ben_prod, ben_faith):
    print("\n" + "=" * 78)
    print("0. FAITHFUL-OOF RE-CONFIRM  (task: AST is a blend, should be ~unchanged)")
    print("=" * 78)
    for label, recs in [("prod OOF", ben_prod), ("faithful OOF", ben_faith)]:
        all_s = filter_settle(recs, "both", 0.0, None)
        g = filter_settle(recs, "both", 0.75, 7.5)
        n, w, r = roi(all_s); gn, gw, gr = roi(g)
        print(f"  benashkar {label:12s}: ALL n={n} ROI={r:+.2f}% win={w:.1f}% | "
              f"gated(0.75,<=7.5) n={gn} ROI={gr:+.2f}% win={gw:.1f}%")
    # pred agreement
    pf = {(r["pid"], r["date"]): r["pred"] for r in ben_faith}
    diffs = [abs(r["pred"] - pf[(r["pid"], r["date"])]) for r in ben_prod if (r["pid"], r["date"]) in pf]
    if diffs:
        print(f"  AST pred mean|prod-faithful|={np.mean(diffs):.3f}  max={np.max(diffs):.3f}  "
              f"n_overlap={len(diffs)}")
        print("  >> if ROI/gated are materially the same, the AST verdict is OOF-version-robust.")


def section_direction(recs, label):
    print(f"\n── DIRECTION sweep [{label}] (gated edge>=0.75, line<=7.5) ──")
    e, l = temporal_halves(recs)
    for d in ("both", "over", "under"):
        a = roi(filter_settle(recs, d, 0.75, 7.5))
        er = roi(filter_settle(e, d, 0.75, 7.5)) if e else (0, 0, 0)
        lr = roi(filter_settle(l, d, 0.75, 7.5)) if l else (0, 0, 0)
        lo, hi, p0 = boot_ci(filter_settle(recs, d, 0.75, 7.5))
        rob = "DURABLE" if (er[2] > 0 and lr[2] > 0) else "no"
        print(f"  {d:6s}  ALL n={a[0]:4d} ROI={a[2]:+6.2f}% win={a[1]:.1f}%  "
              f"CI[{lo:+.1f},{hi:+.1f}] P0={p0:.3f} | early {er[2]:+6.1f}%({er[0]}) "
              f"late {lr[2]:+6.1f}%({lr[0]})  {rob}")


def section_edge_threshold(recs, label):
    print(f"\n── EDGE-THRESHOLD sweep [{label}] (both dir, line<=7.5) — durable = both halves >0 ──")
    e, l = temporal_halves(recs)
    rows_out = []
    for em in EDGE_GRID:
        a = roi(filter_settle(recs, "both", em, 7.5))
        er = roi(filter_settle(e, "both", em, 7.5)) if e else (0, 0, 0)
        lr = roi(filter_settle(l, "both", em, 7.5)) if l else (0, 0, 0)
        rob = "DURABLE" if (er[2] > 0 and lr[2] > 0) else "no"
        print(f"  edge>={em:<4} ALL n={a[0]:4d} ROI={a[2]:+6.2f}% | early {er[2]:+6.1f}%({er[0]}) "
              f"late {lr[2]:+6.1f}%({lr[0]})  {rob}")
        rows_out.append({"edge": em, "n": a[0], "roi": a[2], "early_roi": er[2],
                         "late_roi": lr[2], "durable": rob == "DURABLE"})
    return rows_out


def section_line_bucket(recs, label):
    print(f"\n── LINE-BUCKET [{label}] (both dir, edge>=0.75) — confirm the line cap ──")
    e, l = temporal_halves(recs)
    buckets = [("low (<=3.5)", None, 3.5), ("mid (3.5-5.5)", 3.5, 5.5),
               ("high (5.5-7.5)", 5.5, 7.5), ("very_high (>7.5)", 7.5, None)]
    for name, lo, hi in buckets:
        a = roi(filter_settle(recs, "both", 0.75, hi, lo))
        er = roi(filter_settle(e, "both", 0.75, hi, lo)) if e else (0, 0, 0)
        lr = roi(filter_settle(l, "both", 0.75, hi, lo)) if l else (0, 0, 0)
        rob = "DURABLE" if (er[2] > 0 and lr[2] > 0) else "no"
        print(f"  {name:18s} ALL n={a[0]:4d} ROI={a[2]:+7.2f}% | early {er[2]:+7.1f}%({er[0]}) "
              f"late {lr[2]:+7.1f}%({lr[0]})  {rob}")


def section_pace(recs, label):
    """Pace tilt: high-pace tercile vs low+mid. Sizing lever, not a hard filter."""
    print(f"\n── PACE TILT [{label}] (gated edge>=0.75, line<=7.5; opp_pace tercile) ──")
    gated = [r for r in recs if abs(r["pred"] - r["line"]) >= 0.75 and r["line"] <= 7.5
             and r.get("opp_pace") is not None]
    if len(gated) < 20:
        print(f"  insufficient pace-tagged gated bets (n={len(gated)}) — skip")
        return None
    paces = np.array([r["opp_pace"] for r in gated])
    t1, t2 = np.percentile(paces, [33.33, 66.67])
    e, l = temporal_halves(gated)

    def slc(rows, pred):
        return [_settle_rec(r["line"], r["actual"], r["pred"], r["over_odds"], r["under_odds"])
                for r in rows if pred(r["opp_pace"])
                and _settle_rec(r["line"], r["actual"], r["pred"], r["over_odds"], r["under_odds"]) is not None]
    out = {}
    for name, pred in [(f"high (>{t2:.1f})", lambda v: v > t2),
                       (f"low+mid (<={t2:.1f})", lambda v: v <= t2)]:
        a = roi(slc(gated, pred)); er = roi(slc(e, pred)) if e else (0, 0, 0)
        lr = roi(slc(l, pred)) if l else (0, 0, 0)
        lo, hi, p0 = boot_ci(slc(gated, pred))
        rob = "DURABLE" if (er[2] > 0 and lr[2] > 0) else "no"
        print(f"  {name:16s} ALL n={a[0]:4d} ROI={a[2]:+6.2f}% win={a[1]:.1f}% CI[{lo:+.1f},{hi:+.1f}] "
              f"P0={p0:.3f} | early {er[2]:+6.1f}%({er[0]}) late {lr[2]:+6.1f}%({lr[0]})  {rob}")
        out[name] = {"n": a[0], "roi": a[2], "win": a[1], "ci": [lo, hi], "p0": p0}
    # difference test (high - low/mid) via bootstrap on per-bet payouts
    hi_pays = np.array([p for _, _, p in slc(gated, lambda v: v > t2)])
    lm_pays = np.array([p for _, _, p in slc(gated, lambda v: v <= t2)])
    if len(hi_pays) and len(lm_pays):
        diffs = []
        for _ in range(8000):
            dh = RNG.choice(hi_pays, len(hi_pays), replace=True).mean()
            dl = RNG.choice(lm_pays, len(lm_pays), replace=True).mean()
            diffs.append((dh - dl) / 100 * 100)
        diffs = np.array(diffs)
        print(f"  high - low/mid diff: {diffs.mean():+.1f}% CI[{np.percentile(diffs,2.5):+.1f},"
              f"{np.percentile(diffs,97.5):+.1f}] P(high<=low/mid)={(diffs<=0).mean():.3f}")
        out["pace_thresh"] = float(t2)
        out["diff_p"] = float((diffs <= 0).mean())
    return out


# ────────────────────────────────────────────────────────────────────────────
# Kelly sizing
# ────────────────────────────────────────────────────────────────────────────

def kelly_fraction(p_win, american_odds):
    """Full-Kelly fraction for a single American-odds bet with win prob p_win."""
    b = (american_odds / 100.0) if american_odds > 0 else (100.0 / abs(american_odds))
    q = 1.0 - p_win
    f = (b * p_win - q) / b
    return max(0.0, f)


def section_kelly(ben_recs):
    """Derive a concrete fractional-Kelly rule sized on the DURABLE ~+5% edge.

    Per-bet win prob is estimated from the gated AST win rate; the edge magnitude is
    PINNED to the cross-season durable core (~+5% ROI at -110), NOT the in-window +19%.
    """
    print("\n" + "=" * 78)
    print("KELLY SIZING (size on the DURABLE ~+5% core, never the +19% in-window peak)")
    print("=" * 78)
    gated = filter_settle(ben_recs, "both", 0.75, 7.5)
    n, win, r = roi(gated)
    # Implied win prob at -110 to hit a given ROI: ROI = win*(b) - (1-win); b=0.909
    b = 100.0 / 110.0
    # Solve win for durable ROI core 5% and observed
    def win_for_roi(roi_frac):
        return (roi_frac + 1.0) / (1.0 + b)
    p_obs = win / 100.0
    p_durable = win_for_roi(0.05)   # win rate consistent with +5% ROI at -110
    breakeven = win_for_roi(0.0)    # 52.38%
    print(f"  gated AST in-window: n={n}  win={win:.1f}%  ROI={r:+.2f}%  (breakeven win={breakeven*100:.2f}%)")
    print(f"  implied win for the DURABLE +5% core at -110: {p_durable*100:.2f}%")
    f_obs = kelly_fraction(p_obs, -110)
    f_dur = kelly_fraction(p_durable, -110)
    print(f"  full-Kelly @ observed win {p_obs*100:.1f}%  -> f*={f_obs*100:.2f}% of bankroll")
    print(f"  full-Kelly @ DURABLE win {p_durable*100:.1f}% -> f*={f_dur*100:.2f}% of bankroll")
    # Regime/variance haircut. The bootstrap CI is wide and 2024-25 ~ +5% (CI crosses 0),
    # playoffs negative => use a heavy fractional-Kelly (1/4) on the DURABLE f*, and
    # additionally cap absolute stake. Pace tilt scales WITHIN [base, base*pace_mult].
    quarter = 0.25
    base_stake = f_dur * quarter
    print(f"\n  RECOMMENDED RULE (per gated AST bet, regular season only):")
    print(f"    stake = clip( 0.25 * fullKelly(p_durable={p_durable*100:.1f}%, posted_odds), 0, {base_stake*1.5*100:.2f}% )")
    print(f"    base (1/4-Kelly on +5% core) ~= {base_stake*100:.2f}% of bankroll per bet")
    print(f"    high-pace tercile: scale base x1.5  (-> ~{base_stake*1.5*100:.2f}%)")
    print(f"    low/mid pace:      scale base x0.75 (-> ~{base_stake*0.75*100:.2f}%)")
    print(f"    NEVER size on the in-window +19% peak (that f* would be ~{kelly_fraction(win_for_roi(0.19),-110)*100:.1f}% — massive over-bet)")
    return {"win_obs": p_obs, "win_durable": p_durable, "breakeven": breakeven,
            "fullkelly_durable_pct": f_dur * 100, "base_stake_pct": base_stake * 100,
            "high_pace_stake_pct": base_stake * 1.5 * 100, "lowmid_pace_stake_pct": base_stake * 0.75 * 100}


# ────────────────────────────────────────────────────────────────────────────

def main():
    summary = {}

    print("Building corpora (read-only, leak-free) ...", flush=True)
    ben_prod = build_benashkar(OOF_PROD)
    print(f"  benashkar prod-OOF AST recs: n={len(ben_prod)}", flush=True)
    ben_faith = build_benashkar(OOF_FAITH) if OOF_FAITH.exists() else []
    extoos = build_extoos(independent_only=True)
    extoos_full = build_extoos(independent_only=False)
    print(f"  extended_oos independent AST recs: n={len(extoos)}  (full join n={len(extoos_full)})", flush=True)
    reg2425 = build_2024_25_rollingorigin()
    print(f"  2024-25 rolling-origin AST recs: n={len(reg2425)}", flush=True)

    # Coherence sanity per corpus
    print("\nMarket coherence (blind-O + blind-U should be ~ -2*vig; positive => corrupt):")
    for lbl, recs in [("benashkar", ben_prod), ("extended_oos(indep)", extoos),
                      ("extended_oos(full)", extoos_full), ("2024-25", reg2425)]:
        bo, bu = blind(recs)
        print(f"  {lbl:22s} blindO {bo:+.1f}% + blindU {bu:+.1f}% = {bo+bu:+.1f}%  "
              f"{'COHERENT' if bo+bu < 5 else 'CORRUPT'}")
    # The independent extended_oos slice is tiny (OOF date-coverage gap); use the FULL
    # join as the cross-BOOK robustness corpus (same games, different book vs benashkar).

    # 0. faithful re-confirm
    if ben_faith:
        section_faithful_check(ben_prod, ben_faith)

    # 1. direction (each corpus)
    print("\n" + "=" * 78)
    print("1. DIRECTION — both vs over vs under (which maximizes the DURABLE edge?)")
    print("=" * 78)
    section_direction(ben_prod, "benashkar in-window")
    section_direction(extoos_full, "extended_oos cross-book (full)")
    section_direction(reg2425, "2024-25 SEASON")

    # 2. edge threshold
    print("\n" + "=" * 78)
    print("2. EDGE THRESHOLD sweep")
    print("=" * 78)
    summary["edge_benashkar"] = section_edge_threshold(ben_prod, "benashkar")
    summary["edge_extoos"] = section_edge_threshold(extoos_full, "extended_oos cross-book")
    summary["edge_2024_25"] = section_edge_threshold(reg2425, "2024-25 SEASON")

    # 5. line bucket (run before pace so cap is confirmed)
    print("\n" + "=" * 78)
    print("5. LINE BUCKET — confirm the line<=7.5 cap on the durable core")
    print("=" * 78)
    section_line_bucket(ben_prod, "benashkar")
    section_line_bucket(extoos_full, "extended_oos cross-book")
    section_line_bucket(reg2425, "2024-25 SEASON")

    # 3. pace tilt
    print("\n" + "=" * 78)
    print("3. PACE TILT — cross-season re-validation (sizing lever, not hard filter)")
    print("=" * 78)
    summary["pace_benashkar"] = section_pace(ben_prod, "benashkar")
    summary["pace_extoos"] = section_pace(extoos_full, "extended_oos cross-book")
    summary["pace_2024_25"] = section_pace(reg2425, "2024-25 SEASON")

    # 4. Kelly
    summary["kelly"] = section_kelly(ben_prod)

    # ── Final durable policy readout ──
    print("\n" + "=" * 78)
    print("FINAL — durable AST policy ROI on the optimal config (edge>=0.75, line<=7.5, both dir)")
    print("=" * 78)
    final = {}
    for lbl, recs in [("benashkar in-window", ben_prod),
                      ("extended_oos cross-book (full)", extoos_full),
                      ("extended_oos independent", extoos),
                      ("2024-25 SEASON (rolling-origin)", reg2425)]:
        g = filter_settle(recs, "both", 0.75, 7.5)
        n, w, r = roi(g); lo, hi, p0 = boot_ci(g)
        print(f"  {lbl:34s} n={n:4d}  win={w:.1f}%  ROI={r:+.2f}%  CI[{lo:+.1f},{hi:+.1f}]  P(<=0)={p0:.3f}")
        final[lbl] = {"n": n, "win": w, "roi": r, "ci": [lo, hi], "p0": p0}
    summary["final_durable"] = final

    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(summary, open(OUT, "w", encoding="utf-8"), indent=2, default=str)
    print(f"\nResults JSON: {OUT.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
