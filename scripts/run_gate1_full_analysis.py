"""Comprehensive Gate 1 — every cut against every public Vegas archive.

Combines:
  1. 2024 NBA playoffs (DK/FD/MGM/BetRivers via reisneriv)
  2. 2025-26 mid-season + playoffs (DK/FD/MGM via benashkar)

For each window runs:
  A. L10 baseline (naive)
  B. Prod-stack walk-forward OOF (where available)
  C. UNDER-only strategy (since L10 over-predicts → UNDER has edge)
  D. Per-stat bias-corrected variant (subtract avg pred-line gap)

Reports an aggregate "best honest reading" line at the bottom.
"""
from __future__ import annotations

import csv
import glob
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
_CSV_PLAYOFFS = _ROOT / "data" / "external" / "historical_lines" / "playoffs_2024_canonical.csv"
_BENASHKAR = _ROOT / "data" / "external" / "historical_lines" / "benashkar_nba_gambling"
_NBA_DIR = _ROOT / "data" / "nba"
_OOF = _ROOT / "data" / "cache" / "pregame_oof.parquet"
_OUT = _ROOT / "data" / "cache" / "gate1_full_analysis.json"

STAT_COLS = {"pts": "PTS", "reb": "REB", "ast": "AST",
             "fg3m": "FG3M", "stl": "STL", "blk": "BLK", "tov": "TOV"}
PROP_TO_STAT = {
    "points": "pts", "rebounds": "reb", "assists": "ast",
    "threes": "fg3m", "steals": "stl", "blocks": "blk", "turnovers": "tov",
}
KEEP_BOOKS = {"draftkings", "fanduel", "betmgm", "betrivers"}


def _parse_date(s: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _payout(odds: float, win: bool) -> float:
    if not win:
        return -100.0
    return (100.0 / abs(odds) * 100.0) if odds < 0 else (odds / 100.0 * 100.0)


def _build_name_to_pid() -> Dict[str, int]:
    out: Dict[str, int] = {}
    for season in ("2023-24", "2024-25", "2025-26"):
        path = _NBA_DIR / f"player_avgs_{season}.json"
        if not path.exists():
            continue
        try:
            for name_lc, info in json.load(open(path, encoding="utf-8")).items():
                pid = info.get("player_id")
                if pid is not None:
                    out[name_lc.strip().lower()] = int(pid)
        except Exception:
            continue
    return out


def _load_gamelog_combined(pid: int, seasons=("2023-24", "2024-25", "2025-26")) -> List[Tuple[datetime, dict]]:
    rows = []
    for season in seasons:
        path = _NBA_DIR / f"gamelog_{pid}_{season}.json"
        if not path.exists():
            continue
        try:
            for r in json.load(open(path, encoding="utf-8")):
                d = _parse_date(r.get("GAME_DATE", ""))
                if d:
                    rows.append((d, r))
        except Exception:
            continue
    rows.sort(key=lambda kv: kv[0])
    return rows


def _predict_l10(rows, cutoff, col):
    history = []
    for d, r in rows:
        if d >= cutoff:
            continue
        v = r.get(col)
        if v is None:
            continue
        try:
            history.append(float(v))
        except (TypeError, ValueError):
            continue
    if len(history) < 5:
        return None
    return sum(history[-10:]) / len(history[-10:])


def _actual_value(rows, game_date, col):
    for d, r in rows:
        if d.date() == game_date.date():
            v = r.get(col)
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None
    return None


# ─────────────────────────────────────────────────────────────────────
# Load bets from each window
# ─────────────────────────────────────────────────────────────────────

def load_playoffs_2024_bets():
    """Returns list of {player, pid, gdate, stat, line, over_odds, under_odds, actual}."""
    if not _CSV_PLAYOFFS.exists():
        return []
    name_to_pid = _build_name_to_pid()
    gl_cache: Dict[int, list] = {}
    out = []
    with open(_CSV_PLAYOFFS, encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            stat = (row.get("stat") or "").lower()
            if stat not in STAT_COLS:
                continue
            try:
                line = float(row.get("closing_line") or 0)
                actual = float(row.get("actual_value") or 0)
                over_odds = float(row.get("over_odds") or -110)
                under_odds = float(row.get("under_odds") or -110)
            except (ValueError, TypeError):
                continue
            name = (row.get("player") or "").strip().lower()
            pid = name_to_pid.get(name)
            if pid is None:
                continue
            gdate = _parse_date(row.get("date") or "")
            if gdate is None:
                continue
            out.append({
                "window": "2024_playoffs", "player": name, "pid": pid,
                "gdate": gdate, "stat": stat, "line": line,
                "over_odds": over_odds, "under_odds": under_odds, "actual": actual,
                "book": "dk_fd_mgm_br_avg", "is_alt": False,
            })
    return out


def load_benashkar_bets(mainline_only=True):
    """Loads benashkar latest-per-key closing rows. Returns bet records with
    L10 prediction + actual already joined."""
    files = sorted(glob.glob(str(_BENASHKAR / "data__output__player_props_*.csv")))
    if not files:
        return []
    latest = {}
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                book = (row.get("sportsbook") or "").lower()
                if book not in KEEP_BOOKS:
                    continue
                if mainline_only and row.get("is_alt_line", "").lower() == "true":
                    continue
                prop = (row.get("prop_type") or "").lower()
                if prop not in PROP_TO_STAT:
                    continue
                try:
                    line = float(row.get("line") or 0)
                    over_odds = float(row.get("over_odds") or 0)
                    under_odds = float(row.get("under_odds") or 0)
                except (ValueError, TypeError):
                    continue
                if over_odds == 0 or under_odds == 0:
                    continue
                player = (row.get("player_name") or "").strip().lower()
                gdate = (row.get("game_date") or "").strip()
                scraped = row.get("scraped_at", "")
                key = (player, gdate, book, prop, line)
                prev = latest.get(key)
                if prev is None or scraped > prev["scraped_at"]:
                    latest[key] = {
                        "player": player, "game_date": gdate, "book": book,
                        "prop": prop, "line": line,
                        "over_odds": over_odds, "under_odds": under_odds,
                        "scraped_at": scraped,
                        "is_alt": row.get("is_alt_line", "").lower() == "true",
                    }
    name_to_pid = _build_name_to_pid()
    out = []
    for rec in latest.values():
        stat = PROP_TO_STAT.get(rec["prop"])
        if stat is None:
            continue
        gdate = _parse_date(rec["game_date"])
        if gdate is None:
            continue
        pid = name_to_pid.get(rec["player"])
        if pid is None:
            continue
        out.append({
            "window": "2025_26", "player": rec["player"], "pid": pid,
            "gdate": gdate, "stat": stat, "line": rec["line"],
            "over_odds": rec["over_odds"], "under_odds": rec["under_odds"],
            "book": rec["book"], "is_alt": rec["is_alt"],
            "actual": None,  # filled in next pass
        })
    return out


def attach_actuals_and_l10(bets):
    """Mutates `bets` to add 'actual' and 'pred_l10'."""
    gl_cache = {}
    out = []
    for b in bets:
        pid = b["pid"]
        if pid not in gl_cache:
            gl_cache[pid] = _load_gamelog_combined(pid)
        rows = gl_cache[pid]
        col = STAT_COLS[b["stat"]]
        if b["actual"] is None:
            actual = _actual_value(rows, b["gdate"], col)
            if actual is None:
                continue
            b["actual"] = actual
        pred = _predict_l10(rows, b["gdate"], col)
        if pred is None:
            continue
        b["pred_l10"] = pred
        out.append(b)
    return out


def attach_oof(bets):
    """Adds 'pred_oof' to bets where OOF parquet has a row. Drops the rest."""
    df = pd.read_parquet(_OOF)
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.strftime("%Y-%m-%d")
    idx = {}
    for r in df.itertuples(index=False):
        idx[(int(r.player_id), r.game_date, r.stat)] = float(r.oof_pred)
    out = []
    for b in bets:
        key = (b["pid"], b["gdate"].strftime("%Y-%m-%d"), b["stat"])
        oof = idx.get(key)
        if oof is None:
            continue
        b["pred_oof"] = oof
        out.append(b)
    return out


# ─────────────────────────────────────────────────────────────────────
# Strategies
# ─────────────────────────────────────────────────────────────────────

def settle(bet, pred):
    line = bet["line"]
    if abs(pred - line) < 1e-9:
        return None
    bet_over = pred > line
    actual = bet["actual"]
    if abs(actual - line) < 1e-9:
        return None  # push
    won = (bet_over and actual > line) or (not bet_over and actual < line)
    odds = bet["over_odds"] if bet_over else bet["under_odds"]
    # B-2 (hard rule): drop invalid odds |odds| < 100. _payout treats |odds| < 100
    # as a higher-than-even payout (e.g. _payout(-50, win)=200), overstating ROI;
    # real books never post |odds| < 100, so it is a data glitch. Mirror the push
    # no-bet None return (the caller already skips None). 0 rows in the current
    # corpora carry |odds| < 100, so this is byte-identical on today's data and
    # only guards future/glitch inputs (GRADING_SETTLE_CLV_AUDIT.md B-2).
    try:
        if abs(float(odds)) < 100:
            return None
    except (TypeError, ValueError):
        return None
    return bet_over, won, _payout(odds, won)


def aggregate(bets, predictor_key, under_only=False, edge_min=0.0):
    by_stat = defaultdict(lambda: {"n": 0, "w": 0, "pnl": 0.0})
    total_n = total_w = 0
    total_pnl = 0.0
    for b in bets:
        pred = b.get(predictor_key)
        if pred is None:
            continue
        if abs(pred - b["line"]) < edge_min:
            continue
        bet_over = pred > b["line"]
        if under_only and bet_over:
            continue
        res = settle(b, pred)
        if res is None:
            continue
        bet_over, won, pnl = res
        total_n += 1
        if won:
            total_w += 1
        total_pnl += pnl
        a = by_stat[b["stat"]]
        a["n"] += 1
        if won:
            a["w"] += 1
        a["pnl"] += pnl
    return {
        "n": total_n, "w": total_w,
        "beat_pct": total_w / total_n * 100 if total_n else 0,
        "roi_pct": total_pnl / (total_n * 100.0) * 100 if total_n else 0,
        "pnl": total_pnl,
        "per_stat": {s: {**v, "beat_pct": v["w"]/v["n"]*100 if v["n"] else 0,
                         "roi_pct": v["pnl"]/(v["n"]*100.0)*100 if v["n"] else 0}
                     for s, v in by_stat.items()},
    }


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

def main():
    print("Loading 2024 playoffs bets...")
    p24 = load_playoffs_2024_bets()
    p24 = attach_actuals_and_l10(p24)
    print(f"  {len(p24):,} playoff bets ready (L10 attached)")

    print("Loading 2025-26 mainline bets...")
    p2526 = load_benashkar_bets(mainline_only=True)
    p2526 = attach_actuals_and_l10(p2526)
    print(f"  {len(p2526):,} 2025-26 mainline bets ready (L10 attached)")

    print("Attaching prod-stack OOF to 2025-26 bets...")
    p2526_oof = attach_oof(list(p2526))
    print(f"  {len(p2526_oof):,} 2025-26 bets have prod OOF prediction")

    print()
    print("=" * 72)
    print("COMBINED real-Vegas: 2024 playoffs + 2025-26 mainline (L10 baseline)")
    print("=" * 72)
    combined_l10 = p24 + p2526
    r = aggregate(combined_l10, "pred_l10")
    print(f"  N={r['n']:,}  beat={r['beat_pct']:.2f}%  ROI={r['roi_pct']:+.2f}%  PnL=${r['pnl']:+,.0f}")
    for stat, v in sorted(r["per_stat"].items()):
        print(f"    {stat:<6} n={v['n']:>6,d}  beat={v['beat_pct']:>6.2f}%  ROI={v['roi_pct']:>+6.2f}%")

    print()
    print("=" * 72)
    print("COMBINED real-Vegas — UNDER-ONLY strategy (L10 over-predicts edge)")
    print("=" * 72)
    r_under = aggregate(combined_l10, "pred_l10", under_only=True)
    print(f"  N={r_under['n']:,}  beat={r_under['beat_pct']:.2f}%  ROI={r_under['roi_pct']:+.2f}%  PnL=${r_under['pnl']:+,.0f}")
    for stat, v in sorted(r_under["per_stat"].items()):
        print(f"    {stat:<6} n={v['n']:>6,d}  beat={v['beat_pct']:>6.2f}%  ROI={v['roi_pct']:>+6.2f}%")

    print()
    print("=" * 72)
    print("2025-26 mainline — PROD-STACK walk-forward OOF (apples-to-apples)")
    print("=" * 72)
    r_prod = aggregate(p2526_oof, "pred_oof")
    print(f"  N={r_prod['n']:,}  beat={r_prod['beat_pct']:.2f}%  ROI={r_prod['roi_pct']:+.2f}%  PnL=${r_prod['pnl']:+,.0f}")
    for stat, v in sorted(r_prod["per_stat"].items()):
        print(f"    {stat:<6} n={v['n']:>6,d}  beat={v['beat_pct']:>6.2f}%  ROI={v['roi_pct']:>+6.2f}%")

    print()
    print("=" * 72)
    print("2025-26 mainline — PROD-STACK UNDER-ONLY")
    print("=" * 72)
    r_prod_u = aggregate(p2526_oof, "pred_oof", under_only=True)
    print(f"  N={r_prod_u['n']:,}  beat={r_prod_u['beat_pct']:.2f}%  ROI={r_prod_u['roi_pct']:+.2f}%  PnL=${r_prod_u['pnl']:+,.0f}")
    for stat, v in sorted(r_prod_u["per_stat"].items()):
        print(f"    {stat:<6} n={v['n']:>6,d}  beat={v['beat_pct']:>6.2f}%  ROI={v['roi_pct']:>+6.2f}%")

    print()
    print("=" * 72)
    print("2025-26 mainline — PROD-STACK with min-edge 1.0 (high-conviction)")
    print("=" * 72)
    r_prod_e1 = aggregate(p2526_oof, "pred_oof", edge_min=1.0)
    print(f"  N={r_prod_e1['n']:,}  beat={r_prod_e1['beat_pct']:.2f}%  ROI={r_prod_e1['roi_pct']:+.2f}%  PnL=${r_prod_e1['pnl']:+,.0f}")
    for stat, v in sorted(r_prod_e1["per_stat"].items()):
        print(f"    {stat:<6} n={v['n']:>6,d}  beat={v['beat_pct']:>6.2f}%  ROI={v['roi_pct']:>+6.2f}%")

    print()
    print("=" * 72)
    print("2025-26 mainline — PROD-STACK with min-edge 1.5 (highest-conviction)")
    print("=" * 72)
    r_prod_e15 = aggregate(p2526_oof, "pred_oof", edge_min=1.5)
    print(f"  N={r_prod_e15['n']:,}  beat={r_prod_e15['beat_pct']:.2f}%  ROI={r_prod_e15['roi_pct']:+.2f}%  PnL=${r_prod_e15['pnl']:+,.0f}")
    for stat, v in sorted(r_prod_e15["per_stat"].items()):
        print(f"    {stat:<6} n={v['n']:>6,d}  beat={v['beat_pct']:>6.2f}%  ROI={v['roi_pct']:>+6.2f}%")

    # Dump
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump({
        "combined_l10_naive": r,
        "combined_l10_under_only": r_under,
        "p2526_prod_stack_all": r_prod,
        "p2526_prod_stack_under_only": r_prod_u,
        "p2526_prod_stack_edge_1.0": r_prod_e1,
        "p2526_prod_stack_edge_1.5": r_prod_e15,
        "data_windows": ["2024 NBA playoffs (DK/FD/MGM/BetRivers)", "2025-26 Jan 29 - May 10 (DK/FD/MGM)"],
        "n_bets_total_combined": len(p24) + len(p2526),
    }, open(_OUT, "w", encoding="utf-8"), indent=2)
    print(f"\nResults: {_OUT.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
