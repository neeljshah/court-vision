"""Daily operator briefing for the prediction-markets dry-run system.

Single command runs the full daily cycle and prints a markdown report:

    1. settle    — grade yesterday's pending rows (PM + Kalshi)
    2. snapshot  — write today's market snapshot for both venues
    3. scan      — run all forecasters against today's open markets
    4. place     — append new dry-run rows to the ledger
    5. summary   — career + last-7-day PnL/ROI/hit-rate

Mirrors scripts/morning_briefing.py from the NBA stack: clean stdout
markdown, optional save to vault/Reports/predmarkets_briefing_<date>.md.

Usage:
    python -m predmarkets.morning_briefing
    python -m predmarkets.morning_briefing --date 2026-05-27 --bankroll 1000
    python -m predmarkets.morning_briefing --skip-snapshot   # rerun with existing snapshot
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date as _date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from predmarkets.dry_run_placer import (
    DEFAULT_LEDGER_DIR,
    _read_rows,
    place_dry_run_batch,
    settle_ledger,
    summarize_ledger,
)
from predmarkets.edge_scanner import EdgeScanner, EdgeScannerConfig, load_snapshot
from predmarkets.forecasters import CryptoThresholdForecaster, LLMForecaster

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT_REPORTS = os.path.join(PROJECT_DIR, "vault", "Strategy", "PredictionMarkets", "Briefings")
PM_SNAPSHOT_FMT = "data/pm/markets_{date}.parquet"
KALSHI_SNAPSHOT_FMT = "data/kalshi/markets_{date}.parquet"
DEFAULT_LEDGER = os.path.join(DEFAULT_LEDGER_DIR, "ledger.csv")


def _today() -> _date:
    return datetime.now(timezone.utc).date()


def _section_settle(ledger_path: str) -> Dict[str, Any]:
    from predmarkets import KalshiClient, PMClient
    clients = {"polymarket": PMClient(), "kalshi": KalshiClient()}
    return settle_ledger(ledger_path, clients)


def _section_snapshot(snap_date: _date, skip: bool) -> Dict[str, Any]:
    if skip:
        return {"skipped": True}
    from predmarkets.snapshot import snapshot_kalshi, snapshot_polymarket
    out: Dict[str, Any] = {"skipped": False}
    try:
        out["polymarket"] = snapshot_polymarket(snap_date)
    except Exception as exc:
        out["polymarket_error"] = f"{type(exc).__name__}: {exc}"
    try:
        out["kalshi"] = snapshot_kalshi(snap_date)
    except Exception as exc:
        out["kalshi_error"] = f"{type(exc).__name__}: {exc}"
    return out


def _section_scan_and_place(snap_date: _date, ledger_path: str, bankroll: float,
                            threshold: float) -> Dict[str, Any]:
    forecasters = [CryptoThresholdForecaster(), LLMForecaster()]
    cfg = EdgeScannerConfig(bankroll=bankroll, edge_threshold=threshold)
    scanner = EdgeScanner(forecasters, cfg)
    result: Dict[str, Any] = {"venues": {}}
    venue_files = [
        ("polymarket", PM_SNAPSHOT_FMT.format(date=snap_date.isoformat())),
        ("kalshi",     KALSHI_SNAPSHOT_FMT.format(date=snap_date.isoformat())),
    ]
    for venue, path in venue_files:
        if not os.path.exists(os.path.join(PROJECT_DIR, path)):
            result["venues"][venue] = {"error": f"snapshot not found: {path}"}
            continue
        markets = load_snapshot(os.path.join(PROJECT_DIR, path), status="open")
        scan = scanner.scan(markets)
        report = place_dry_run_batch(scan["edges"], ledger_path)
        result["venues"][venue] = {
            "scanned": scan["n_markets"],
            "edges": scan["n_edges"],
            "placed": report["placed"],
            "skipped_zero_stake": report["skipped_zero_stake"],
            "skipped_duplicate": report["skipped_duplicate"],
            "top_edges": scan["edges"][:5],
        }
    return result


def _section_pnl(ledger_path: str) -> Dict[str, Any]:
    overall = summarize_ledger(ledger_path)
    # 7-day rolling
    rows = _read_rows(ledger_path)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
    recent = [r for r in rows if (r.get("placed_at") or "") >= cutoff
              and (r.get("status") or "") in {"WIN", "LOSS", "PUSH", "VOID"}]
    pnl_7d = 0.0
    staked_7d = 0.0
    wins_7d = sum(1 for r in recent if (r.get("status") or "") == "WIN")
    losses_7d = sum(1 for r in recent if (r.get("status") or "") == "LOSS")
    for r in recent:
        try:
            pnl_7d += float(r.get("profit") or 0.0)
            staked_7d += float(r.get("stake_dollars") or 0.0)
        except (TypeError, ValueError):
            pass
    overall["last_7d"] = {
        "graded": len(recent),
        "wins": wins_7d,
        "losses": losses_7d,
        "pnl_dollars": round(pnl_7d, 2),
        "staked_dollars": round(staked_7d, 2),
        "roi": (pnl_7d / staked_7d) if staked_7d else None,
    }
    return overall


def _render_markdown(snap_date: _date, settle: Dict[str, Any], snapshot: Dict[str, Any],
                      scan: Dict[str, Any], pnl: Dict[str, Any], ledger_path: str) -> str:
    lines: List[str] = []
    lines.append(f"# Predmarkets Morning Briefing — {snap_date.isoformat()}")
    lines.append("")
    lines.append(f"_ledger: `{ledger_path}`_")
    lines.append("")

    lines.append("## 1. Settlement")
    if settle.get("checked", 0) == 0:
        lines.append("No pending rows.")
    else:
        lines.append(f"- Checked: **{settle['checked']}** pending rows")
        lines.append(f"- Graded:  **{settle['graded']}**")
        lines.append(f"- Still pending: **{settle['still_pending']}**")
    lines.append("")

    lines.append("## 2. Snapshot")
    if snapshot.get("skipped"):
        lines.append("_Skipped (--skip-snapshot)._")
    else:
        for venue in ("polymarket", "kalshi"):
            if path := snapshot.get(venue):
                try:
                    import pandas as pd
                    n = len(pd.read_parquet(path))
                    lines.append(f"- **{venue}**: {n} rows -> `{path}`")
                except Exception:
                    lines.append(f"- **{venue}**: `{path}` (size unknown)")
            elif err := snapshot.get(f"{venue}_error"):
                lines.append(f"- **{venue}**: FAILED — {err}")
    lines.append("")

    lines.append("## 3. Today's Edges")
    for venue, info in scan.get("venues", {}).items():
        if "error" in info:
            lines.append(f"### {venue}: error — {info['error']}")
            continue
        lines.append(f"### {venue}")
        lines.append(f"- Scanned: {info['scanned']} open markets")
        lines.append(f"- Edges found: **{info['edges']}**")
        lines.append(f"- Placed (new dry-run rows): {info['placed']} "
                     f"(skipped {info['skipped_zero_stake']} zero-stake, "
                     f"{info['skipped_duplicate']} duplicates)")
        if info.get("top_edges"):
            lines.append("")
            lines.append("| side | price | model | edge pp | stake$ | EV$ | category | question |")
            lines.append("|---|---|---|---|---|---|---|---|")
            for e in info["top_edges"]:
                q = (e.get("question") or "")[:60].replace("|", "/")
                cat = e.get("category") or ""
                lines.append(
                    f"| {e['side']} | {e['price']:.4f} | {e['model_prob']:.4f} | "
                    f"{e['edge_pp']:+.4f} | ${e['stake_dollars']:.2f} | "
                    f"${e['expected_value_dollars']:.2f} | {cat} | {q} |"
                )
        lines.append("")

    def _fmt_pct(v: Any) -> str:
        if v is None:
            return "n/a"
        try:
            return f"{float(v):.1%}"
        except (TypeError, ValueError):
            return "n/a"

    lines.append("## 4. PnL")
    career_hit = _fmt_pct(pnl.get("hit_rate"))
    career_roi = _fmt_pct(pnl.get("roi"))
    lines.append(
        f"- **Career**: {pnl['graded']} graded ({pnl['wins']}W / {pnl['losses']}L), "
        f"hit_rate={career_hit}, PnL=${pnl['pnl_dollars']:+.2f}, ROI={career_roi}"
    )
    seven = pnl.get("last_7d") or {}
    seven_roi = _fmt_pct(seven.get("roi"))
    lines.append(
        f"- **Last 7d**: {seven.get('graded', 0)} graded "
        f"({seven.get('wins', 0)}W / {seven.get('losses', 0)}L), "
        f"PnL=${seven.get('pnl_dollars', 0):+.2f}, ROI={seven_roi}"
    )
    lines.append(f"- Pending: {pnl['pending']}")
    lines.append("")
    return "\n".join(lines)


def run(snap_date: Optional[_date] = None, bankroll: float = 1000.0,
        threshold: float = 0.05, ledger_path: str = DEFAULT_LEDGER,
        skip_snapshot: bool = False, save_to_vault: bool = True) -> str:
    snap_date = snap_date or _today()
    settle = _section_settle(ledger_path)
    snapshot = _section_snapshot(snap_date, skip_snapshot)
    scan = _section_scan_and_place(snap_date, ledger_path, bankroll, threshold)
    pnl = _section_pnl(ledger_path)
    md = _render_markdown(snap_date, settle, snapshot, scan, pnl, ledger_path)
    if save_to_vault:
        os.makedirs(VAULT_REPORTS, exist_ok=True)
        path = os.path.join(VAULT_REPORTS, f"briefing_{snap_date.isoformat()}.md")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(md)
        except OSError:
            pass
    return md


def _cli(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Daily predmarkets briefing")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default: today UTC)")
    parser.add_argument("--bankroll", type=float, default=1000.0)
    parser.add_argument("--threshold", type=float, default=0.05)
    parser.add_argument("--ledger", default=DEFAULT_LEDGER)
    parser.add_argument("--skip-snapshot", action="store_true")
    parser.add_argument("--no-save", action="store_true", help="Don't save to vault")
    args = parser.parse_args(argv)
    snap_date = (
        datetime.strptime(args.date, "%Y-%m-%d").date() if args.date
        else _today()
    )
    md = run(snap_date=snap_date, bankroll=args.bankroll, threshold=args.threshold,
             ledger_path=args.ledger, skip_snapshot=args.skip_snapshot,
             save_to_vault=not args.no_save)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
