"""Reusable leak-free real-line grading harness for basketball-intelligence tests.

One place to: load a canonical line corpus at POSTED odds, attach the model's
leak-free prediction + as-of conditioners (calibration_frame_v2), attach the
as-of opponent-stat-allowed substrate, run the market-coherence guard, and grade
ROI per-stat / per-conditioner-bucket with the exact settle() semantics of
scripts/run_gate1_full_analysis.py.

DISCIPLINE baked in:
  - drop |american odds| < 100 (the +900%-payout garbage-row trap)
  - coherence guard: blind-OVER + blind-UNDER ROI must be ~ -2*vig (negative);
    a positive sum => corrupt odds => refuse to grade that corpus
  - posted-odds payout via _payout; bet direction = pred>line
  - never mutates the corpus / model; read-only except callers' own writes

Prediction source: calibration_frame_v2.parquet `pred` (per player_id,date,stat,
3 seasons). Reproduces the published §8a AST edge -> confirmed leak-free OOF.
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Callable

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LINES = os.path.join(ROOT, "data", "external", "historical_lines")
CALFRAME = os.path.join(ROOT, "data", "cache", "calibration_frame_v2.parquet")
PIT = os.path.join(ROOT, "data", "cache", "pit")
NBA = os.path.join(ROOT, "data", "nba")

# corpus -> (opp_allowed tag, is_playoffs)
CORPUS_TAG = {
    "benashkar_2026_canonical.csv": ("2025_26_reg", False),
    "extended_oos_canonical.csv": ("2025_26_reg", False),
    "regular_season_2025_26_oddsapi.csv": ("2025_26_reg", False),
    "regular_season_2024_25_oddsapi.csv": ("2024_25", False),
    "playoffs_2025_26_oddsapi.csv": ("2026_playoffs", True),
    "playoffs_2024_canonical.csv": (None, True),
    "reisneriv_2024_canonical.csv": (None, True),
}


def _parse_date(s) -> Optional[pd.Timestamp]:
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return pd.Timestamp(datetime.strptime(str(s).strip(), fmt)).normalize()
        except (ValueError, TypeError):
            continue
    try:
        return pd.Timestamp(s).normalize()
    except Exception:
        return None


def _payout(odds: float, win: bool) -> float:
    if not win:
        return -100.0
    return (100.0 / abs(odds) * 100.0) if odds < 0 else (odds / 100.0 * 100.0)


def name_to_pid() -> Dict[str, int]:
    out: Dict[str, int] = {}
    for season in ("2023-24", "2024-25", "2025-26"):
        p = os.path.join(NBA, f"player_avgs_{season}.json")
        try:
            for nm, info in json.load(open(p, encoding="utf-8")).items():
                pid = info.get("player_id")
                if pid is not None:
                    out[nm.strip().lower()] = int(pid)
        except Exception:
            continue
    return out


def load_corpus(name: str) -> List[dict]:
    """Robust canonical-CSV loader (python csv handles ragged playoffs rows).
    Returns bet dicts with posted odds, after dropping |odds|<100 and bad rows."""
    path = os.path.join(LINES, name)
    n2p = name_to_pid()
    out: List[dict] = []
    dropped_odds = dropped_name = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        rd = csv.DictReader(fh)
        for r in rd:
            stat = (r.get("stat") or "").strip().lower()
            try:
                line = float(r.get("closing_line"))
                oo = float(r.get("over_odds"))
                uo = float(r.get("under_odds"))
                actual = float(r.get("actual_value"))
            except (TypeError, ValueError):
                continue
            if abs(oo) < 100 or abs(uo) < 100:
                dropped_odds += 1
                continue
            nm = (r.get("player") or "").strip().lower()
            pid = n2p.get(nm)
            if pid is None:
                dropped_name += 1
                continue
            gd = _parse_date(r.get("date"))
            if gd is None:
                continue
            out.append({
                "player": nm, "pid": pid, "stat": stat,
                "opp": (r.get("opp") or "").strip().upper(),
                "venue": (r.get("venue") or "").strip(),
                "gdate": gd, "line": line,
                "over_odds": oo, "under_odds": uo, "actual": actual,
            })
    out.sort(key=lambda b: b["gdate"])
    print(f"  [{name}] {len(out):,} bets (dropped {dropped_odds} bad-odds, {dropped_name} unresolved-name)")
    return out


_CAL: Optional[pd.DataFrame] = None


def _cal() -> pd.DataFrame:
    global _CAL
    if _CAL is None:
        df = pd.read_parquet(CALFRAME)
        df["d"] = pd.to_datetime(df["date"]).dt.normalize()
        _CAL = df
    return _CAL


def attach_pred(bets: List[dict]) -> List[dict]:
    """Attach leak-free model `pred` + as-of conditioners from calibration_frame_v2
    via (pid, date, stat). Drops bets with no match."""
    df = _cal()
    cols = ["pred", "opp_pace", "opp_def", "rest_days", "is_b2b", "is_home",
            "l10_min", "vac_min", "vac_pts", "n_out", "std_min", "min_trend"]
    idx: Dict[tuple, dict] = {}
    for r in df.itertuples(index=False):
        idx[(int(r.player_id), r.d, r.stat)] = {c: getattr(r, c) for c in cols}
    out = []
    for b in bets:
        m = idx.get((b["pid"], b["gdate"], b["stat"]))
        if m is None:
            continue
        b.update(m)
        if b.get("pred") is None or (isinstance(b["pred"], float) and np.isnan(b["pred"])):
            continue
        out.append(b)
    return out


_OPP_CACHE: Dict[str, pd.DataFrame] = {}


def attach_opp_allowed(bets: List[dict], tag: str) -> List[dict]:
    """Attach as-of opp-stat-allowed (the player's OPPONENT is the defending team)
    keyed (team==opp, game_date). Adds opp_<stat>_allowed_asof/_vs_league + n_games_asof.
    Bets keep going even if unmatched (value=NaN) so coverage is visible."""
    if tag is None:
        return bets
    if tag not in _OPP_CACHE:
        p = os.path.join(PIT, f"opp_allowed_asof_{tag}.parquet")
        _OPP_CACHE[tag] = pd.read_parquet(p) if os.path.exists(p) else pd.DataFrame()
    oa = _OPP_CACHE[tag]
    if oa.empty:
        return bets
    oa = oa.copy()
    oa["d"] = pd.to_datetime(oa["game_date"]).dt.normalize()
    keep = [c for c in oa.columns if c.startswith("opp_") or c == "n_games_asof"]
    idx = {(r.team, r.d): {c: getattr(r, c) for c in keep} for r in oa.itertuples(index=False)}
    matched = 0
    for b in bets:
        m = idx.get((b["opp"], b["gdate"]))
        if m is not None:
            b.update(m)
            matched += 1
        else:
            for c in keep:
                b.setdefault(c, np.nan)
    print(f"    opp-allowed matched {matched}/{len(bets)} ({100*matched/max(len(bets),1):.0f}%)")
    return bets


def settle(b: dict, pred: float):
    line = b["line"]
    if abs(pred - line) < 1e-9:
        return None
    bet_over = pred > line
    actual = b["actual"]
    if abs(actual - line) < 1e-9:
        return None
    won = (bet_over and actual > line) or (not bet_over and actual < line)
    odds = b["over_odds"] if bet_over else b["under_odds"]
    return bet_over, won, _payout(odds, won)


def roi(bets, predictor="pred", edge_min=0.0, mask: Optional[Callable[[dict], bool]] = None,
        under_only=False, over_only=False):
    n = w = 0
    pnl = 0.0
    for b in bets:
        if mask is not None and not mask(b):
            continue
        pred = b.get(predictor)
        if pred is None or (isinstance(pred, float) and np.isnan(pred)):
            continue
        if abs(pred - b["line"]) < edge_min:
            continue
        bet_over = pred > b["line"]
        if under_only and bet_over:
            continue
        if over_only and not bet_over:
            continue
        res = settle(b, pred)
        if res is None:
            continue
        _, won, p = res
        n += 1
        w += won
        pnl += p
    return {"n": n, "w": w, "win_pct": (100 * w / n if n else 0.0),
            "roi_pct": (pnl / (n * 100.0) * 100 if n else 0.0), "pnl": pnl}


def coherence(bets) -> dict:
    """Blind-over + blind-under ROI. A coherent market sums to ~ -2*vig (negative).
    Positive sum => corrupt odds in the corpus."""
    bo = roi(bets, predictor="__blind_over__")
    # blind over: bet over on everything
    def _blind(side):
        n = w = 0; pnl = 0.0
        for b in bets:
            actual = b["actual"]; line = b["line"]
            if abs(actual - line) < 1e-9:
                continue
            over = side == "over"
            won = (over and actual > line) or (not over and actual < line)
            odds = b["over_odds"] if over else b["under_odds"]
            n += 1; w += won; pnl += _payout(odds, won)
        return {"n": n, "roi_pct": pnl / (n * 100.0) * 100 if n else 0.0}
    o = _blind("over"); u = _blind("under")
    s = o["roi_pct"] + u["roi_pct"]
    return {"over": o, "under": u, "sum": s, "coherent": s < 0}


def per_stat(bets, predictor="pred", edge_min=0.0, mask=None):
    stats = sorted(set(b["stat"] for b in bets))
    out = {}
    for s in stats:
        out[s] = roi(bets, predictor=predictor, edge_min=edge_min,
                     mask=(lambda b, s=s: b["stat"] == s and (mask(b) if mask else True)))
    out["ALL"] = roi(bets, predictor=predictor, edge_min=edge_min, mask=mask)
    return out


def prepare(corpus: str) -> List[dict]:
    tag, is_po = CORPUS_TAG.get(corpus, (None, False))
    bets = load_corpus(corpus)
    bets = attach_pred(bets)
    bets = attach_opp_allowed(bets, tag)
    return bets


if __name__ == "__main__":
    import sys
    corpora = sys.argv[1:] or ["benashkar_2026_canonical.csv", "regular_season_2025_26_oddsapi.csv"]
    for c in corpora:
        print(f"\n===== {c} =====")
        bets = prepare(c)
        print(f"  joined-to-pred: {len(bets)} bets")
        coh = coherence(bets)
        print(f"  COHERENCE: blind-over {coh['over']['roi_pct']:+.2f}% + blind-under "
              f"{coh['under']['roi_pct']:+.2f}% = {coh['sum']:+.2f}%  "
              f"({'OK (negative)' if coh['coherent'] else 'CORRUPT (positive!)'})")
        ps = per_stat(bets, predictor="pred", edge_min=0.0)
        print("  RAW MODEL pred>line ROI by stat:")
        for s, v in ps.items():
            print(f"    {s:5s} n={v['n']:5d} win={v['win_pct']:5.1f}% roi={v['roi_pct']:+7.2f}%")
