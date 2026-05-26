"""Gate 1 against REAL Vegas — MAXIMUM-sample variant for 2025-26.

Uses every benashkar/nba_gambling row regardless of mainline vs alt, and
scores against L10 baseline (no OOF parquet filter) so we don't drop the
73% of rows where OOF predictions are missing.

This gives the broadest possible sample of (player, game, book, line)
combinations and the strongest statistical confidence. L10 is the
weakest predictor — so any positive edge here is conservative.

Also dumps per-stat detail: hit-rate split by bet direction (over vs
under), to diagnose underprediction bias surfaced in CLAUDE-state.md
item #5.
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

_ROOT = Path(__file__).resolve().parent.parent
_SNAPS_DIR = _ROOT / "data" / "external" / "historical_lines" / "benashkar_nba_gambling"
_NBA_DIR = _ROOT / "data" / "nba"
_OUT = _ROOT / "data" / "cache" / "gate1_2025_26_maxsample_results.json"

PROP_TO_STAT: Dict[str, Tuple[str, str]] = {
    "points": ("pts", "PTS"),
    "rebounds": ("reb", "REB"),
    "assists": ("ast", "AST"),
    "threes": ("fg3m", "FG3M"),
}
KEEP_BOOKS = {"draftkings", "fanduel", "betmgm"}


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
    for season in ("2024-25", "2025-26"):
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


def _load_gamelog_combined(pid: int) -> List[Tuple[datetime, dict]]:
    rows = []
    for season in ("2024-25", "2025-26"):
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


def _predict_l10(rows: List[Tuple[datetime, dict]], cutoff: datetime, col: str) -> Optional[float]:
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


def _actual_value(rows: List[Tuple[datetime, dict]], game_date: datetime, col: str) -> Optional[float]:
    for d, r in rows:
        if d.date() == game_date.date():
            v = r.get(col)
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None
    return None


def main() -> int:
    files = sorted(glob.glob(str(_SNAPS_DIR / "data__output__player_props_*.csv")))
    print(f"Loading {len(files)} snapshot files (mainline + alt lines)...")

    # Closing-proxy: keep LATEST scrape per (player, game_date, book, prop, line)
    latest: Dict[Tuple[str, str, str, str, float], dict] = {}
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                book = (row.get("sportsbook") or "").lower()
                if book not in KEEP_BOOKS:
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
                is_alt = row.get("is_alt_line", "").lower() == "true"
                key = (player, gdate, book, prop, line)
                prev = latest.get(key)
                if prev is None or scraped > prev["scraped_at"]:
                    latest[key] = {
                        "player": player, "game_date": gdate, "book": book,
                        "prop": prop, "line": line,
                        "over_odds": over_odds, "under_odds": under_odds,
                        "scraped_at": scraped, "is_alt": is_alt,
                    }
    print(f"  unique closing rows (mainline + alt): {len(latest):,}")

    name_to_pid = _build_name_to_pid()
    print(f"  name -> pid map: {len(name_to_pid):,}")
    gl_cache: Dict[int, List[Tuple[datetime, dict]]] = {}

    stats: Dict[str, Dict[str, dict]] = defaultdict(lambda: {
        "by_dir":       defaultdict(lambda: {"n": 0, "w": 0, "pnl": 0.0}),
        "by_alt":       defaultdict(lambda: {"n": 0, "w": 0, "pnl": 0.0}),
        "by_book":      defaultdict(lambda: {"n": 0, "w": 0, "pnl": 0.0}),
        "by_edge_bin":  defaultdict(lambda: {"n": 0, "w": 0, "pnl": 0.0}),
        "n": 0, "w": 0, "pnl": 0.0, "stake": 0.0,
        "pred_minus_line_sum": 0.0, "actual_minus_line_sum": 0.0,
    })
    n_unmatched = 0
    n_no_actual = 0
    n_no_pred = 0
    n_bets = 0

    for rec in latest.values():
        stat_info = PROP_TO_STAT.get(rec["prop"])
        if stat_info is None:
            continue
        stat, col = stat_info

        gdate_dt = _parse_date(rec["game_date"])
        if gdate_dt is None:
            continue
        pid = name_to_pid.get(rec["player"])
        if pid is None:
            n_unmatched += 1
            continue
        if pid not in gl_cache:
            gl_cache[pid] = _load_gamelog_combined(pid)
        rows = gl_cache[pid]

        actual = _actual_value(rows, gdate_dt, col)
        if actual is None:
            n_no_actual += 1
            continue
        pred = _predict_l10(rows, gdate_dt, col)
        if pred is None:
            n_no_pred += 1
            continue

        line = rec["line"]
        if abs(pred - line) < 1e-9:
            continue
        bet_over = pred > line
        if abs(actual - line) < 1e-9:
            continue  # push

        won = (bet_over and actual > line) or (not bet_over and actual < line)
        odds = rec["over_odds"] if bet_over else rec["under_odds"]
        pnl = _payout(odds, won)

        n_bets += 1
        agg = stats[stat]
        agg["n"] += 1
        agg["stake"] += 100.0
        agg["pnl"] += pnl
        if won:
            agg["w"] += 1
        agg["pred_minus_line_sum"] += (pred - line)
        agg["actual_minus_line_sum"] += (actual - line)

        # By direction
        dkey = "OVER" if bet_over else "UNDER"
        a = agg["by_dir"][dkey]
        a["n"] += 1; a["pnl"] += pnl
        if won: a["w"] += 1
        # By alt
        akey = "alt" if rec["is_alt"] else "mainline"
        a = agg["by_alt"][akey]
        a["n"] += 1; a["pnl"] += pnl
        if won: a["w"] += 1
        # By book
        a = agg["by_book"][rec["book"]]
        a["n"] += 1; a["pnl"] += pnl
        if won: a["w"] += 1
        # By edge bin (|pred - line|)
        edge = abs(pred - line)
        bin_ = "0.0-0.5" if edge < 0.5 else "0.5-1.0" if edge < 1.0 else "1.0-2.0" if edge < 2.0 else "2.0+"
        a = agg["by_edge_bin"][bin_]
        a["n"] += 1; a["pnl"] += pnl
        if won: a["w"] += 1

    print()
    print("=== Gate 1 MAX-SAMPLE — 2025-26 (DK/FD/MGM, L10 baseline, mainline+alt) ===")
    print(f"  unmatched name:    {n_unmatched:,}")
    print(f"  no actual stat:    {n_no_actual:,}")
    print(f"  no L10 pred:       {n_no_pred:,}")
    print(f"  resolved bets:     {n_bets:,}")
    print()

    grand_n = sum(s["n"] for s in stats.values())
    grand_w = sum(s["w"] for s in stats.values())
    grand_pnl = sum(s["pnl"] for s in stats.values())
    grand_stake = sum(s["stake"] for s in stats.values())
    print(f"TOTAL: n={grand_n:,}  beat={grand_w/grand_n*100:.2f}%  ROI={grand_pnl/grand_stake*100:+.2f}%  PnL=${grand_pnl:+,.2f} on ${grand_stake:,.0f}")
    print()

    print(f"{'stat':<6} {'n':>7} {'beat%':>7} {'ROI%':>7} {'avg_pred-line':>14} {'avg_actual-line':>16}")
    out_per_stat = {}
    for stat in sorted(stats):
        a = stats[stat]
        if a["n"] == 0:
            continue
        beat = a["w"] / a["n"] * 100.0
        roi = a["pnl"] / a["stake"] * 100.0
        avg_pl = a["pred_minus_line_sum"] / a["n"]
        avg_al = a["actual_minus_line_sum"] / a["n"]
        print(f"{stat:<6} {a['n']:>7d} {beat:>6.2f}% {roi:>+6.2f}% {avg_pl:>+13.3f} {avg_al:>+15.3f}")
        out_per_stat[stat] = {
            "n": a["n"], "w": a["w"], "beat_pct": beat, "roi_pct": roi,
            "avg_pred_minus_line": avg_pl, "avg_actual_minus_line": avg_al,
            "by_dir": {k: dict(v) for k, v in a["by_dir"].items()},
            "by_alt": {k: dict(v) for k, v in a["by_alt"].items()},
            "by_book": {k: dict(v) for k, v in a["by_book"].items()},
            "by_edge_bin": {k: dict(v) for k, v in a["by_edge_bin"].items()},
        }

    print()
    print("--- bet-direction diagnosis (which way is the edge?) ---")
    for stat in sorted(stats):
        a = stats[stat]
        if a["n"] == 0:
            continue
        for d in ("OVER", "UNDER"):
            ad = a["by_dir"].get(d)
            if ad is None or ad["n"] == 0:
                continue
            beat = ad["w"] / ad["n"] * 100.0
            roi = ad["pnl"] / (ad["n"] * 100.0) * 100.0
            print(f"  {stat:<6} {d:<6} n={ad['n']:>6,d}  beat={beat:>6.2f}%  ROI={roi:>+6.2f}%")

    print()
    print("--- alt vs mainline ---")
    for stat in sorted(stats):
        a = stats[stat]
        if a["n"] == 0:
            continue
        for k in ("mainline", "alt"):
            ad = a["by_alt"].get(k)
            if ad is None or ad["n"] == 0:
                continue
            beat = ad["w"] / ad["n"] * 100.0
            roi = ad["pnl"] / (ad["n"] * 100.0) * 100.0
            print(f"  {stat:<6} {k:<10} n={ad['n']:>6,d}  beat={beat:>6.2f}%  ROI={roi:>+6.2f}%")

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump({
        "n_total": grand_n, "beat_pct": grand_w/grand_n*100 if grand_n else 0,
        "roi_pct": grand_pnl/grand_stake*100 if grand_stake else 0,
        "pnl": grand_pnl, "stake": grand_stake,
        "per_stat": out_per_stat,
        "source": "benashkar/nba_gambling DK/FD/MGM mainline+alt, L10 baseline, Jan 29 - May 10, 2026",
    }, open(_OUT, "w", encoding="utf-8"), indent=2)
    print(f"\nResults: {_OUT.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
