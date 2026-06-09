"""diag_pts_pregame_deep.py — Deep, honest diagnostic of PTS pregame ROI vs real closes.

Owner intuition: "PTS pregame ~-9% ROI vs real closes, it should be positive."
This script HUNTS for a fixable cause while HOLDING THE HONEST LINE:
  * |odds| >= 100 ALWAYS (drops the invalid-odds payout trap that faked +18.38%).
  * Temporal split: tune any policy on the EARLY half of dates, grade on the
    held-out LATE half. No in-sample filter tuning.
  * Confirm every claim on a 2nd, independently-sourced corpus (extended_oos).

Three hypotheses tested:
  H1 SERVE-PATH BUG  — is the gate1 PTS number degraded by a real bug
                       (feature misalignment / label inverse / odds parse)?
  H2 BETTING POLICY  — is there a LEGITIMATE PTS-only config (direction,
                       edge-threshold, calibration, line/minutes bucket) that is
                       >= 0 held-out + on the 2nd corpus?
  H3 IRREDUCIBLE     — if not, state the honest break-even number + why.

Corpus 1 (primary, apples-to-apples): benashkar 2025-26 mainline closes joined to
the leak-free prod-stack OOF (pregame_oof.parquet). Same join run_gate1 uses.
Corpus 2 (independent): extended_oos_canonical.csv joined to the SAME OOF.

Read-only. Builds nothing destructive.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.run_gate1_full_analysis import (  # noqa: E402
    _payout, load_benashkar_bets, attach_actuals_and_l10, attach_oof,
)

RNG = np.random.default_rng(20260604)
_OOF = _ROOT / "data" / "cache" / "pregame_oof.parquet"
_EXT = _ROOT / "data" / "external" / "historical_lines" / "extended_oos_canonical.csv"
_OA2425 = _ROOT / "data" / "external" / "historical_lines" / "regular_season_2024_25_oddsapi.csv"


# ─────────────────────────────────────────────────────────────────────
# settle / roi / bootstrap (actual posted odds; |odds|>=100 enforced upstream)
# ─────────────────────────────────────────────────────────────────────

def settle(line, actual, pred, over_odds, under_odds):
    if abs(pred - line) < 1e-9 or abs(actual - line) < 1e-9:
        return None
    over = pred > line
    won = (over and actual > line) or (not over and actual < line)
    return over, won, _payout(over_odds if over else under_odds, won)


def roi(settled):
    if not settled:
        return 0, 0.0, 0.0
    n = len(settled)
    w = sum(int(x[1]) for x in settled)
    pnl = sum(x[2] for x in settled)
    return n, w / n * 100.0, pnl / (n * 100.0) * 100.0


def boot(settled):
    if not settled:
        return (0.0, 0.0, 1.0)
    pays = np.array([x[2] for x in settled])
    b = np.array([RNG.choice(pays, len(pays), replace=True).sum() / (len(pays) * 100) * 100
                  for _ in range(5000)])
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5)), float((b <= 0).mean())


# ─────────────────────────────────────────────────────────────────────
# Corpus 1: benashkar PTS bets joined to prod OOF (exactly as gate1 does)
# ─────────────────────────────────────────────────────────────────────

def load_corpus1_pts():
    bets = load_benashkar_bets(mainline_only=True)
    bets = attach_actuals_and_l10(bets)
    bets = attach_oof(bets)  # adds pred_oof
    out = []
    for b in bets:
        if b["stat"] != "pts":
            continue
        if abs(b["over_odds"]) < 100 or abs(b["under_odds"]) < 100:
            continue
        out.append({
            "pid": b["pid"], "date": b["gdate"].strftime("%Y-%m-%d"),
            "line": b["line"], "over_odds": b["over_odds"], "under_odds": b["under_odds"],
            "actual": b["actual"], "pred": b["pred_oof"], "l10": b.get("pred_l10"),
        })
    return out


# ─────────────────────────────────────────────────────────────────────
# Corpus 2: extended_oos PTS joined to the SAME OOF (independent book)
# ─────────────────────────────────────────────────────────────────────

def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s.lower())).strip()


def _load_canonical_pts(csv_path):
    """Join a (date,player,stat,closing_line,over/under_odds,actual_value) CSV to
    the PTS OOF. Shared by corpus2 (extended_oos) and corpus3 (2024-25 oddsapi)."""
    from nba_api.stats.static import players as P
    nm = {}
    for p in P.get_players():
        nm.setdefault(_norm(p["full_name"]), p["id"])
    df = pd.read_csv(csv_path)
    df = df[df["stat"] == "pts"].copy()
    df["pid"] = df["player"].map(lambda x: nm.get(_norm(x)))
    df = df.dropna(subset=["pid"])
    df["pid"] = df["pid"].astype(int)
    df["date2"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df[(df["over_odds"].abs() >= 100) & (df["under_odds"].abs() >= 100)]
    oof = pd.read_parquet(_OOF)
    oof = oof[oof["stat"] == "pts"]
    oof["d"] = pd.to_datetime(oof["game_date"]).dt.strftime("%Y-%m-%d")
    oidx = {(int(r.player_id), r.d): (float(r.oof_pred), float(r.actual))
            for r in oof.itertuples(index=False)}
    out = []
    for r in df.itertuples(index=False):
        hit = oidx.get((int(r.pid), r.date2))
        if hit is None:
            continue
        pred, oof_actual = hit
        out.append({
            "pid": int(r.pid), "date": r.date2, "line": float(r.closing_line),
            "over_odds": float(r.over_odds), "under_odds": float(r.under_odds),
            "actual": float(r.actual_value), "oof_actual": oof_actual, "pred": pred,
        })
    return out


def load_corpus3_pts():
    """2024-25 oddsapi — a GENUINELY independent (different SEASON) PTS corpus.
    extended_oos PTS only joins the Jan-Apr-2026 window (same as benashkar), so
    it tests book-robustness not time-robustness; this tests cross-season."""
    return _load_canonical_pts(_OA2425)


def load_corpus2_pts():
    from nba_api.stats.static import players as P
    nm = {}
    for p in P.get_players():
        nm.setdefault(_norm(p["full_name"]), p["id"])
    df = pd.read_csv(_EXT)
    df = df[df["stat"] == "pts"].copy()
    df["pid"] = df["player"].map(lambda x: nm.get(_norm(x)))
    df = df.dropna(subset=["pid"])
    df["pid"] = df["pid"].astype(int)
    df["date2"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df[(df["over_odds"].abs() >= 100) & (df["under_odds"].abs() >= 100)]

    oof = pd.read_parquet(_OOF)
    oof = oof[oof["stat"] == "pts"]
    oof["d"] = pd.to_datetime(oof["game_date"]).dt.strftime("%Y-%m-%d")
    oidx = {(int(r.player_id), r.d): (float(r.oof_pred), float(r.actual))
            for r in oof.itertuples(index=False)}
    out = []
    for r in df.itertuples(index=False):
        hit = oidx.get((int(r.pid), r.date2))
        if hit is None:
            continue
        pred, oof_actual = hit
        out.append({
            "pid": int(r.pid), "date": r.date2, "line": float(r.closing_line),
            "over_odds": float(r.over_odds), "under_odds": float(r.under_odds),
            "actual": float(r.actual_value), "oof_actual": oof_actual, "pred": pred,
        })
    return out


# ─────────────────────────────────────────────────────────────────────
# Policy evaluation
# ─────────────────────────────────────────────────────────────────────

def eval_policy(rows, *, direction=None, edge_min=0.0, line_lo=None, line_hi=None,
                pred_key="pred"):
    """direction: None=both, 'under', 'over'. edge_min on |pred-line|.
    line_lo/hi on the betting line."""
    settled = []
    for b in rows:
        pred = b[pred_key]
        if pred is None:
            continue
        line = b["line"]
        if abs(pred - line) < edge_min:
            continue
        if line_lo is not None and line < line_lo:
            continue
        if line_hi is not None and line > line_hi:
            continue
        over = pred > line
        if direction == "under" and over:
            continue
        if direction == "over" and not over:
            continue
        res = settle(line, b["actual"], pred, b["over_odds"], b["under_odds"])
        if res is None:
            continue
        settled.append(res)
    return settled


def temporal_split(rows):
    """Split by median date: early half (tune) / late half (held-out)."""
    dates = sorted(b["date"] for b in rows)
    if not dates:
        return [], []
    mid = dates[len(dates) // 2]
    early = [b for b in rows if b["date"] < mid]
    late = [b for b in rows if b["date"] >= mid]
    return early, late


def line(label, settled):
    n, win, r = roi(settled)
    return f"  {label:<42s} n={n:>5d}  win={win:>5.1f}%  ROI={r:>+7.2f}%"


# ─────────────────────────────────────────────────────────────────────
# H1: serve-path bug check
# ─────────────────────────────────────────────────────────────────────

def h1_serve_path(rows1):
    print("=" * 78)
    print("H1 — SERVE-PATH BUG CHECK")
    print("=" * 78)
    print("The gate1 PTS number uses pregame_oof.parquet, which trains FRESH per WF")
    print("fold with feature_columns(stat) used identically for train+predict. The")
    print("EX-5 bbref-reorder bug only bites the LIVE predict_pergame slate path")
    print("(cols[:85] slice on frozen 85-col artifacts) — it CANNOT affect the OOF")
    print("(no frozen artifact; fresh model each fold). So the bbref bug is NOT the")
    print("cause of the gate1 -8.6% PTS number. Checks below test the OOF itself.\n")

    # (a) odds validity — confirm no invalid-odds payout inflation in the PTS set
    inv = 0
    for b in rows1:
        if abs(b["over_odds"]) < 100 or abs(b["under_odds"]) < 100:
            inv += 1
    print(f"  (a) invalid |odds|<100 rows remaining after filter: {inv} (must be 0)")

    # (b) blind coherence — a coherent market has blind-O + blind-U ~ -2*vig
    def blind(over):
        s = []
        for b in rows1:
            if abs(b["actual"] - b["line"]) < 1e-9:
                continue
            won = (over and b["actual"] > b["line"]) or (not over and b["actual"] < b["line"])
            s.append((over, won, _payout(b["over_odds"] if over else b["under_odds"], won)))
        return roi(s)[2]
    bO, bU = blind(True), blind(False)
    print(f"  (b) market coherence: blind-OVER {bO:+.2f}% + blind-UNDER {bU:+.2f}% = "
          f"{bO+bU:+.2f}%  {'COHERENT' if bO+bU < 5 else 'CORRUPT!'}")

    # (c) label inverse sanity — OOF predictions in a sane PTS range, not squared/halved
    preds = np.array([b["pred"] for b in rows1])
    acts = np.array([b["actual"] for b in rows1])
    print(f"  (c) PTS pred range [{preds.min():.1f},{preds.max():.1f}] mean {preds.mean():.2f} "
          f"| actual mean {acts.mean():.2f} | bias(pred-act) {(preds-acts).mean():+.3f}")
    print(f"      (sane PTS scale + small bias => no sqrt-inverse/label-transform bug)")

    # (d) OOF-actual vs line-corpus-actual consistency (catches join/date mismatch)
    #     only available on corpus2 (carries oof_actual). Reported in main().

    # (e) does the OOF actually beat a naive L10 baseline on the SAME bets? If the
    #     model were broken it would be worse than L10. (rows1 carries l10.)
    s_oof = eval_policy(rows1, pred_key="pred")
    s_l10 = eval_policy([b for b in rows1 if b.get("l10") is not None], pred_key="l10")
    print(line("(e) OOF model all-bets", s_oof))
    print(line("    L10 baseline all-bets", s_l10))
    mae_oof = np.mean([abs(b["pred"] - b["actual"]) for b in rows1])
    mae_l10 = np.mean([abs(b["l10"] - b["actual"]) for b in rows1 if b.get("l10") is not None])
    print(f"      MAE: OOF {mae_oof:.3f} vs L10 {mae_l10:.3f} "
          f"({'OOF more accurate' if mae_oof < mae_l10 else 'OOF WORSE — investigate'})")
    print()


# ─────────────────────────────────────────────────────────────────────
# H2: betting policy search (temporal-split, both corpora)
# ─────────────────────────────────────────────────────────────────────

def h2_policy(rows1, rows2):
    print("=" * 78)
    print("H2 — BEST LEGITIMATE PTS-ONLY CONFIG (temporal-split, 2 corpora)")
    print("=" * 78)
    e1, l1 = temporal_split(rows1)
    print(f"Corpus1 (benashkar): n={len(rows1)}  early={len(e1)} late={len(l1)}  "
          f"split@{sorted(b['date'] for b in rows1)[len(rows1)//2]}")
    print(f"Corpus2 (extended_oos): n={len(rows2)}\n")

    # candidate policies: (label, kwargs)
    cands = [
        ("all both-dir", {}),
        ("UNDER-only", {"direction": "under"}),
        ("OVER-only", {"direction": "over"}),
        ("edge>=1.0 both", {"edge_min": 1.0}),
        ("edge>=1.5 both", {"edge_min": 1.5}),
        ("edge>=2.0 both", {"edge_min": 2.0}),
        ("UNDER edge>=1.0", {"direction": "under", "edge_min": 1.0}),
        ("UNDER edge>=1.5", {"direction": "under", "edge_min": 1.5}),
        ("UNDER edge>=2.0", {"direction": "under", "edge_min": 2.0}),
        ("UNDER edge>=2.5", {"direction": "under", "edge_min": 2.5}),
        ("UNDER edge>=3.0", {"direction": "under", "edge_min": 3.0}),
        ("UNDER line<=15", {"direction": "under", "line_hi": 15.0}),
        ("UNDER line>=20", {"direction": "under", "line_lo": 20.0}),
        ("UNDER line>=25", {"direction": "under", "line_lo": 25.0}),
        ("UNDER line>=20 edge>=1.5", {"direction": "under", "line_lo": 20.0, "edge_min": 1.5}),
        ("UNDER line>=25 edge>=1.5", {"direction": "under", "line_lo": 25.0, "edge_min": 1.5}),
    ]

    print(f"{'policy':<44s} {'EARLY (tune)':>16s} | {'LATE (held-out)':>18s} | {'CORPUS2 (indep)':>18s}")
    print("-" * 104)
    results = []
    for label, kw in cands:
        se = eval_policy(e1, **kw)
        sl = eval_policy(l1, **kw)
        s2 = eval_policy(rows2, **kw)
        ne, _, re_ = roi(se)
        nl, _, rl = roi(sl)
        n2, _, r2 = roi(s2)
        results.append((label, kw, ne, re_, nl, rl, n2, r2))
        print(f"{label:<44s} {re_:>+8.2f}%(n={ne:>4d}) | {rl:>+8.2f}%(n={nl:>4d}) | {r2:>+8.2f}%(n={n2:>4d})")
    print()

    # Honest selection rule: a policy "passes" only if it is >= 0 in BOTH the
    # held-out late half AND the independent corpus2 (early half is sanity only).
    print("PASS = ROI >= 0 in held-out LATE half AND in independent CORPUS2 (early=sanity):")
    passers = []
    for label, kw, ne, re_, nl, rl, n2, r2 in results:
        ok = (rl >= 0.0 and r2 >= 0.0 and nl >= 25 and n2 >= 25)
        flag = "PASS" if ok else "fail"
        if ok:
            passers.append((label, rl, r2, nl, n2))
        print(f"  [{flag}] {label:<40s} late {rl:+.2f}% (n={nl})  corpus2 {r2:+.2f}% (n={n2})")
    print()
    return passers, l1


# ─────────────────────────────────────────────────────────────────────
# H2b: per-stat calibration (CV_PREGAME_CAL) effect on PTS
# ─────────────────────────────────────────────────────────────────────

def h2b_calibration(rows1, rows2):
    """Quantify what the shipped pregame_calibration does to PTS ROI.

    The calibrator needs covariates we don't carry on the OOF join, so we
    measure the SHIPPED full-PTS-calibration effect via the calibration_gate1
    pathway if importable; otherwise we report the documented number and run a
    cheap proxy: shrink the OOF pred toward the line (which is what calibration
    does — pulls toward the conditional mean ~ market) by a grid of alphas and
    show the ROI curve. A pure shrink-to-line is the limiting case of perfect
    calibration; if even that can't make PTS positive, calibration won't either.
    """
    print("=" * 78)
    print("H2b — CALIBRATION / SHRINK-TO-LINE effect on PTS (the §5 mechanism)")
    print("=" * 78)
    print("Calibration pulls the prediction toward the conditional mean ~ the market")
    print("line. Sweep a shrink alpha: pred' = (1-a)*pred + a*line. a=1 => bet nothing")
    print("(pred==line, no edge). This bounds what ANY calibrator can do for PTS ROI.\n")
    e1, l1 = temporal_split(rows1)
    print("  Pure shrink with NO edge threshold is a no-op on direction (pred'>line iff")
    print("  pred>line), so we apply shrink THEN keep only bets that still clear edge>=0.5")
    print("  post-shrink — i.e. calibration both moves preds toward the line AND prunes")
    print("  the low-conviction bets it collapses. This is the real calibration mechanism.\n")
    for a in (0.0, 0.2, 0.4, 0.6):
        def shrink(rows):
            out = []
            for b in rows:
                out.append({**b, "psh": (1 - a) * b["pred"] + a * b["line"]})
            return out
        sl = eval_policy(shrink(l1), pred_key="psh", edge_min=0.5)
        s2 = eval_policy(shrink(rows2), pred_key="psh", edge_min=0.5)
        slu = eval_policy(shrink(l1), pred_key="psh", direction="under", edge_min=0.5)
        nl, _, rl = roi(sl)
        n2, _, r2 = roi(s2)
        nlu, _, rlu = roi(slu)
        print(f"  shrink a={a:.1f} (edge>=0.5 post)  late both {rl:+.2f}%(n={nl})  "
              f"late UNDER {rlu:+.2f}%(n={nlu})  corpus2 both {r2:+.2f}%(n={n2})")
    print()
    print("  Note: the SHIPPED CV_PREGAME_CAL applies a GBM covariate calibrator")
    print("  (docs §5: PTS -8.89% -> -5.04%). It cuts the bleed but stays negative.\n")


def h2c_line_buckets(rows1, rows2):
    """Stress the surviving UNDER-line>=20 candidate. Is it robust, or small-n luck?"""
    print("=" * 78)
    print("H2c — STRESS THE SURVIVOR: UNDER on high lines (line>=20)")
    print("=" * 78)
    e1, l1 = temporal_split(rows1)
    # line-bucket grid, UNDER-only, full corpus1 + corpus2
    buckets = [(0, 12), (12, 16), (16, 20), (20, 24), (24, 99), (20, 99)]
    print("  UNDER-only ROI by line bucket:")
    print(f"  {'bucket':<12s} {'corpus1 all':>16s} {'c1 EARLY':>14s} {'c1 LATE':>14s} {'corpus2':>16s}")
    for lo, hi in buckets:
        kw = {"direction": "under", "line_lo": lo, "line_hi": hi}
        n1, _, r1 = roi(eval_policy(rows1, **kw))
        ne, _, re_ = roi(eval_policy(e1, **kw))
        nl, _, rl = roi(eval_policy(l1, **kw))
        n2, _, r2 = roi(eval_policy(rows2, **kw))
        print(f"  [{lo:>2d},{hi:>2d})      {r1:>+7.2f}%(n={n1:>4d}) {re_:>+7.2f}%(n={ne:>3d}) "
              f"{rl:>+7.2f}%(n={nl:>3d}) {r2:>+7.2f}%(n={n2:>4d})")
    print()
    # bootstrap the headline survivor on each corpus independently
    kw = {"direction": "under", "line_lo": 20.0}
    s1 = eval_policy(rows1, **kw)
    s2 = eval_policy(rows2, **kw)
    sl = eval_policy(l1, **kw)
    for lab, s in (("corpus1 ALL", s1), ("corpus1 LATE held-out", sl), ("corpus2 indep", s2)):
        n, win, r = roi(s)
        lo, hi, p0 = boot(s)
        print(f"  UNDER line>=20 {lab:<22s} n={n:>4d} win={win:.1f}% ROI={r:+.2f}% "
              f"95%CI=[{lo:+.1f},{hi:+.1f}] P(<=0)={p0:.3f}")
    # how concentrated? unique players/games driving it
    bets20 = [b for b in rows1 if b["line"] >= 20 and (b["pred"] < b["line"])]
    pids = defaultdict(lambda: [0, 0.0])
    for b in bets20:
        res = settle(b["line"], b["actual"], b["pred"], b["over_odds"], b["under_odds"])
        if res is None:
            continue
        pids[b["pid"]][0] += 1
        pids[b["pid"]][1] += res[2]
    print(f"\n  concentration: {len(pids)} unique players in corpus1 UNDER line>=20 set "
          f"(n_bets={sum(v[0] for v in pids.values())})")
    top = sorted(pids.items(), key=lambda kv: kv[1][1], reverse=True)[:5]
    print("  top PnL players:", [(pid, f"n={v[0]} pnl={v[1]:+.0f}") for pid, v in top])
    print()


def h2d_crossseason(rows3):
    """The decisive time-robustness check: does the surviving UNDER/high-line
    policy hold on a DIFFERENT SEASON (2024-25)? extended_oos overlaps benashkar's
    window so it only proves book-robustness, not that the edge survives a regime."""
    print("=" * 78)
    print("H2d — CROSS-SEASON (2024-25 oddsapi) — the real time-robustness test")
    print("=" * 78)
    if not rows3:
        print("  (no 2024-25 PTS bets joined the OOF — cannot run)\n")
        return
    cands = [
        ("all both-dir", {}),
        ("UNDER-only", {"direction": "under"}),
        ("UNDER line>=20", {"direction": "under", "line_lo": 20.0}),
        ("UNDER edge>=1.5", {"direction": "under", "edge_min": 1.5}),
        ("UNDER line>=20 edge>=1.5", {"direction": "under", "line_lo": 20.0, "edge_min": 1.5}),
    ]
    for label, kw in cands:
        s = eval_policy(rows3, **kw)
        n, win, r = roi(s)
        lo, hi, p0 = boot(s)
        print(f"  {label:<28s} n={n:>4d} win={win:>5.1f}% ROI={r:>+7.2f}% "
              f"CI=[{lo:+.1f},{hi:+.1f}] P(<=0)={p0:.3f}")
    print("\n  If the UNDER/high-line policies are NEGATIVE here while positive on the")
    print("  Jan-Apr-2026 window, the 'survivor' is a single-window peak, NOT durable.\n")


def main():
    print("\nLoading corpus 1 (benashkar PTS -> prod OOF)...")
    rows1 = load_corpus1_pts()
    print(f"  {len(rows1)} PTS bets (|odds|>=100, OOF-joined)\n")
    print("Loading corpus 2 (extended_oos PTS -> prod OOF)...")
    rows2 = load_corpus2_pts()
    # actual-consistency check (catches join/date bug)
    mism = sum(1 for b in rows2 if abs(b["oof_actual"] - b["actual"]) > 0.5)
    print(f"  {len(rows2)} PTS bets joined; OOF-actual vs CSV-actual mismatch = "
          f"{mism} ({mism/max(len(rows2),1)*100:.1f}%)\n")

    h1_serve_path(rows1)
    print(f"  (d) corpus2 OOF-actual vs line-actual mismatch: {mism}/{len(rows2)} "
          f"({mism/max(len(rows2),1)*100:.1f}%) — low => no date/join corruption\n")

    print("Loading corpus 3 (2024-25 oddsapi PTS -> prod OOF) — cross-SEASON...")
    rows3 = load_corpus3_pts()
    d3 = sorted(b["date"] for b in rows3)
    print(f"  {len(rows3)} PTS bets, dates {d3[0] if d3 else '-'}..{d3[-1] if d3 else '-'} "
          f"(independent SEASON — the real time-robustness test)\n")

    passers, l1 = h2_policy(rows1, rows2)
    h2b_calibration(rows1, rows2)
    h2c_line_buckets(rows1, rows2)
    h2d_crossseason(rows3)

    print("=" * 78)
    print("VERDICT")
    print("=" * 78)
    nl, _, rl_all = roi(eval_policy(l1))
    # re-test any corpus1-late+corpus2 passer against the cross-season corpus3
    if passers and rows3:
        print("Re-testing each corpus1-late+corpus2 'passer' against the CROSS-SEASON")
        print("corpus3 (2024-25). A genuinely durable edge must survive a different season:")
        durable = []
        cand_kw = {"UNDER line>=20": {"direction": "under", "line_lo": 20.0},
                   "UNDER line>=25": {"direction": "under", "line_lo": 25.0},
                   "UNDER line>=20 edge>=1.5": {"direction": "under", "line_lo": 20.0, "edge_min": 1.5}}
        for label, rl, r2, n_l, n2 in passers:
            kw = cand_kw.get(label, {})
            n3, _, r3 = roi(eval_policy(rows3, **kw))
            ok = r3 >= 0 and n3 >= 8
            print(f"  {'[DURABLE]' if ok else '[BREAKS]':<10s} {label}: corpus1-late {rl:+.1f}%, "
                  f"corpus2 {r2:+.1f}%, corpus3 {r3:+.1f}% (n={n3})")
            if ok:
                durable.append(label)
        passers = durable
    if passers:
        print("\nPTS-only configs that pass ALL THREE (late held-out, corpus2, cross-season):")
        for label in passers:
            print(f"  * {label}")
    else:
        print("NO PTS-only config is >= 0 in BOTH the held-out late half AND the")
        print("independent corpus2. Best honest read: PTS pregame is a net loser /")
        print(f"break-even-minus-vig. Late-half all-bets ROI = {rl_all:+.2f}% (n={nl}).")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
