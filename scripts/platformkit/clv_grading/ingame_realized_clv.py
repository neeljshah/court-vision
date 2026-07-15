"""scripts.platformkit.clv_grading.ingame_realized_clv -- in-game realized-CLV grader.

MEASUREMENT ONLY, no $/ROI/edge claim. Paper in-game bets settle with
clv_is_proxy=True (clv_ledger has no true two-way close for a live in-game
market) so we cannot say a placement "beat the close". This module adds an
HONEST, ADDITIONAL measurement instead: mark the taken price to the market a
fixed horizon later (30s/120s/300s) and report the move in probability
points. Positive = market moved toward our side after we took it. This is
NOT closing-line value and does not touch clv_is_proxy -- results go to a
separate sidecar (data/frontend/ingame_realized_clv.jsonl); clv_ledger.jsonl
is never mutated.

Reuses (never reimplements) scripts.platformkit.execution.book_replay's
tick-archive primitives: load_dense_rows/load_ladder_rows for the two
archives, mid_at_or_after for slack-bounded mid lookup, _group_by_ticker_sorted
+ _epoch for the (t, bid, ask) tuple shape mid_at_or_after expects.

Coverage: dense (book_depth/kalshi, ~40s median cadence) is mlb+wnba only,
from 2026-07-04. Every other sport falls back to the coarser depth_history
archive (~26min median cadence) -- most of its ticks will miss the short
30s/120s/300s horizons, correctly reported INSUFFICIENT_DATA rather than
interpolated. Bets before dense coverage existed are INSUFFICIENT_DATA too
(counted, never dropped silently).

Ticker resolution: a paper_ingame ledger row's game_id is the Kalshi event-key
prefix (e.g. KXMLBGAME-26JUN281920NYYBOS); the tick archive keys on the FULL
per-side ticker (prefix + "-" + team suffix, e.g. "...-NYY"). There is no
reliable offline home/away -> team-abbreviation map, so the side ticker is
resolved by nearest-mid: of the candidate tickers sharing the event-key
prefix, the one whose mid at placement is closest to the taken price
(1/taken_decimal) is the bet's side -- the wrong side's mid is ~(1 - taken_p).

INVARIANTS: scripts/platformkit/clv_grading/ only; <=300 LOC; ASCII; stdlib +
book_replay only; local-only sidecar output; never writes data/registry/;
never mutates clv_ledger.jsonl; never flips a flag.
Test: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/clv_grading/test_ingame_realized_clv.py -q
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.clv_ledger import load_ledger
from scripts.platformkit.execution.book_replay import (
    _epoch,
    _group_by_ticker_sorted,
    load_dense_rows,
    load_ladder_rows,
    mid_at_or_after,
)

ROOT = Path(__file__).resolve().parents[3]
SIDECAR = ROOT / "data" / "frontend" / "ingame_realized_clv.jsonl"
DENSE_SPORTS = ("mlb", "wnba")
LADDER_SPORTS = ("kbo", "mlb", "npb", "soccer_intl", "tennis", "wnba")
HORIZONS_S = (30, 120, 300)
SLACK_S = 120.0  # matches book_replay.mid_at_or_after's own default; a tick must
                 # land within this many seconds of the target instant

Snaps = List[Tuple[float, Optional[float], Optional[float]]]


def _snaps_by_ticker(rows: List[Dict[str, Any]]) -> Dict[str, Snaps]:
    return {tk: [(_epoch(r["ts"]), r.get("best_bid"), r.get("best_ask")) for r in trs]
            for tk, trs in _group_by_ticker_sorted(rows).items()}


def load_sport_snaps(sport: str) -> Tuple[Dict[str, Snaps], Optional[str]]:
    """{ticker: snaps} for one sport + the tier's source name (None if no coverage)."""
    if sport in DENSE_SPORTS:
        rows = [r for r in load_dense_rows() if r.get("sport") == sport]
        return (_snaps_by_ticker(rows), "book_depth") if rows else ({}, None)
    if sport in LADDER_SPORTS:
        rows = load_ladder_rows(sport)
        return (_snaps_by_ticker(rows), "depth_history") if rows else ({}, None)
    return {}, None


def _resolve_ticker(game_id: str, taken_p: float, placement_epoch: float,
                     snaps_by_ticker: Dict[str, Snaps]) -> Optional[str]:
    """Candidate ticker (event-key-prefix match) whose placement-time mid is nearest taken_p."""
    prefix = str(game_id) + "-"
    best_tk, best_diff = None, None
    for tk in snaps_by_ticker:
        if not tk.startswith(prefix):
            continue
        mid = mid_at_or_after(snaps_by_ticker[tk], placement_epoch, slack_s=SLACK_S)
        if mid is None:
            continue
        diff = abs(mid - taken_p)
        if best_diff is None or diff < best_diff:
            best_tk, best_diff = tk, diff
    return best_tk


def grade_row(row: Dict[str, Any], snaps_by_ticker: Dict[str, Snaps], *,
              tier: str = "dense", source: Optional[str] = "book_depth") -> Dict[str, Any]:
    """One graded record for a paper_ingame ledger *row*. Never raises; missing
    coverage -> every horizon None, tier 'insufficient', source None."""
    out: Dict[str, Any] = {
        "bet_id": row.get("bet_id"),
        "ingame_clv_cadence_tier": "insufficient",
        "ingame_clv_source": None,
    }
    for h in HORIZONS_S:
        out["ingame_realized_clv_%ds" % h] = None
    try:
        taken_p = 1.0 / float(row["taken_decimal"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return out
    placement_epoch = _epoch(row.get("ts"))
    if placement_epoch is None or not snaps_by_ticker:
        return out
    ticker = _resolve_ticker(str(row.get("game_id", "")), taken_p, placement_epoch, snaps_by_ticker)
    if ticker is None:
        return out
    snaps = snaps_by_ticker[ticker]
    graded_any = False
    for h in HORIZONS_S:
        mid_h = mid_at_or_after(snaps, placement_epoch + h, slack_s=SLACK_S)
        if mid_h is not None:
            out["ingame_realized_clv_%ds" % h] = round(mid_h - taken_p, 6)
            graded_any = True
    if graded_any:
        out["ingame_clv_cadence_tier"] = tier
        out["ingame_clv_source"] = source
    return out


def _dedup_by_bet_id(ledger: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Last row wins per bet_id (a settled twin is appended after the open row)."""
    out: Dict[str, Dict[str, Any]] = {}
    for row in ledger:
        bid = row.get("bet_id")
        if bid:
            out[bid] = row
    return out


def _existing_sidecar_bet_ids(path: Path) -> set:
    ids: set = set()
    if not path.exists():
        return ids
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ids.add(json.loads(line).get("bet_id"))
            except json.JSONDecodeError:
                continue
    return ids


def backfill(ledger_path: Optional[Path] = None, sports: Sequence[str] = DENSE_SPORTS,
             write: bool = False, sidecar_path: Path = SIDECAR) -> Dict[str, Any]:
    """Grade every paper_ingame ledger bet in *sports*; optionally append to the sidecar
    (additive, one line per bet_id -- re-running with write=True never duplicates)."""
    bets = [r for r in _dedup_by_bet_id(load_ledger(ledger_path)).values()
            if r.get("channel") == "paper_ingame" and r.get("sport") in sports]
    by_sport: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in bets:
        by_sport[r["sport"]].append(r)

    graded: List[Dict[str, Any]] = []
    for sport, rows in by_sport.items():
        snaps_by_ticker, source = load_sport_snaps(sport)
        tier = "dense" if sport in DENSE_SPORTS else "coarse"
        for row in rows:
            g = grade_row(row, snaps_by_ticker, tier=tier, source=source)
            g["sport"] = sport
            graded.append(g)

    n_gradeable = sum(1 for g in graded if g["ingame_clv_cadence_tier"] != "insufficient")
    horizon_stats: Dict[str, Any] = {}
    for h in HORIZONS_S:
        key = "ingame_realized_clv_%ds" % h
        vals = [g[key] for g in graded if g[key] is not None]
        horizon_stats["%ds" % h] = {
            "n": len(vals),
            "mean_pp": round(statistics.mean(vals), 6) if vals else None,
            "median_pp": round(statistics.median(vals), 6) if vals else None,
        }
    by_tier: Dict[str, int] = defaultdict(int)
    for g in graded:
        by_tier[g["ingame_clv_cadence_tier"]] += 1

    if write:
        existing = _existing_sidecar_bet_ids(sidecar_path)
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        with sidecar_path.open("a", encoding="utf-8") as fh:
            for g in graded:
                if g.get("bet_id") and g["bet_id"] not in existing:
                    fh.write(json.dumps(g, ensure_ascii=True) + "\n")
                    existing.add(g["bet_id"])

    return {
        "n_bets": len(graded),
        "n_gradeable": n_gradeable,
        "n_insufficient": len(graded) - n_gradeable,
        "by_cadence_tier": dict(by_tier),
        "horizons": horizon_stats,
    }


def summarize(sidecar_path: Path = SIDECAR) -> Dict[str, Any]:
    """Per-sport per-horizon {n, mean_pp, median_pp, pct_favorable} from the sidecar."""
    rows: List[Dict[str, Any]] = []
    if sidecar_path.exists():
        with sidecar_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    by_sport: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_sport[r.get("sport", "?")].append(r)
    out: Dict[str, Any] = {}
    for sport, rs in by_sport.items():
        out[sport] = {}
        for h in HORIZONS_S:
            key = "ingame_realized_clv_%ds" % h
            vals = [r[key] for r in rs if r.get(key) is not None]
            out[sport]["%ds" % h] = {
                "n": len(vals),
                "mean_pp": round(statistics.mean(vals), 6) if vals else None,
                "median_pp": round(statistics.median(vals), 6) if vals else None,
                "pct_favorable": (round(100.0 * sum(1 for v in vals if v > 0) / len(vals), 2)
                                  if vals else None),
            }
    return out


def _print_summary(summary: Dict[str, Any]) -> None:
    print("in-game realized CLV backfill (probability points; positive = market moved toward our side)")
    print("n_bets=%d gradeable=%d insufficient=%d" % (
        summary["n_bets"], summary["n_gradeable"], summary["n_insufficient"]))
    print("by cadence tier: %s" % summary["by_cadence_tier"])
    for h, stats in summary["horizons"].items():
        print("  %s: n=%d mean_pp=%s median_pp=%s" % (h, stats["n"], stats["mean_pp"], stats["median_pp"]))


def main() -> int:
    ap = argparse.ArgumentParser(description="In-game realized-CLV backfill grader (measurement only).")
    ap.add_argument("--backfill", action="store_true", help="grade paper_ingame ledger bets")
    ap.add_argument("--write", action="store_true", help="append graded rows to the sidecar")
    ap.add_argument("--sports", nargs="+", default=list(DENSE_SPORTS))
    args = ap.parse_args()
    if not args.backfill:
        ap.error("nothing to do -- pass --backfill")
    summary = backfill(sports=args.sports, write=args.write)
    _print_summary(summary)
    return 0


__all__ = ["grade_row", "backfill", "summarize", "load_sport_snaps", "SIDECAR",
           "HORIZONS_S", "DENSE_SPORTS", "LADDER_SPORTS"]

if __name__ == "__main__":
    raise SystemExit(main())
