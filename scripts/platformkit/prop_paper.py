"""scripts.platformkit.prop_paper -- PAPER prop ledger + settlement/grade loop.

The honest proving loop for soccer player props: record the TRUSTWORTHY edges from
build_prop_board, grade them against realized post-match stats, and summarize
per-market performance. This is a SEPARATE append-only ledger from the team-bet
clv_ledger -- it does not touch it. PAPER ONLY: every row is executed=False,
channel="paper", market="prop".

HONESTY (binding):
  * The default bar (only_reliable=True) records ONLY edges that are reliable AND
    ev_flag=="ok". With today's thin World-Cup history this records ZERO bets --
    that is the CORRECT, honest behaviour, NOT a bug. We never lower the bar to
    manufacture a paper record.
  * Calibration is the yardstick. paper_roi (priced bets only) is small-N paper
    P&L, not a $-edge claim. CLV-vs-close requires capturing the CLOSING line,
    which is NOT built yet -> noted as a TODO in the summary, never faked.
  * Append-only + idempotent: re-running record/grade never mutates a row.

Public functions NEVER raise -- they degrade to a status dict.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_paper.py -q
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from domains.soccer.player_resolver import build_name_index, resolve_player
from domains.soccer.prop_settle import realized_stat, settle_prop
from scripts.platformkit import prop_line_history
from scripts.platformkit.prop_paper_store import (
    DEFAULT_LEDGER, append, identity, load_ledger, now_iso, paper_pnl,
    prop_summary,
)

logger = logging.getLogger(__name__)

_PARQUET = (
    Path(__file__).resolve().parents[2]
    / "data" / "domains" / "soccer" / "espn_player_stats.parquet"
)


def _passes_bar(edge: Dict[str, Any], only_reliable: bool) -> bool:
    if not only_reliable:
        return True
    return bool(edge.get("reliable")) and edge.get("ev_flag") == "ok"


def _taken_price(edge: Dict[str, Any]) -> Optional[float]:
    side = str(edge.get("side", "")).lower()
    price = edge.get("over_price") if side == "over" else edge.get("under_price")
    try:
        return float(price) if price is not None else None
    except (TypeError, ValueError):
        return None


def record_board(
    board: Dict[str, Any],
    *,
    only_reliable: bool = True,
    ledger_path: Optional[Path] = None,
    now: Optional[str] = None,
) -> Dict[str, Any]:
    """Record passing edges from a build_prop_board payload to the paper ledger.

    only_reliable=True (default) records only edges that are reliable AND
    ev_flag=="ok" -- with thin data this is correctly ZERO. Idempotent on the
    intrinsic (match, player, stat, line, side) identity -- as_of is NOT part of
    the key, so a cadence loop that rebuilds the board every cycle (each with a
    fresh as_of) re-records nothing: each distinct prop lands ONCE at first sight.
    Never raises.
    """
    target = Path(ledger_path) if ledger_path is not None else DEFAULT_LEDGER
    out = {"recorded": 0, "skipped_existing": 0, "below_bar": 0, "considered": 0}
    try:
        edges = (board or {}).get("edges") or []
        existing = {identity(r) for r in load_ledger(target)}
        for edge in edges:
            out["considered"] += 1
            if not _passes_bar(edge, only_reliable):
                out["below_bar"] += 1
                continue
            row = {
                "sport": board.get("sport"),
                "match": edge.get("match"),
                "player": edge.get("player"),
                "matched_name": edge.get("matched_name"),
                "team": edge.get("team"),
                "stat": edge.get("stat"),
                "line": edge.get("line"),
                "side": edge.get("side"),
                "taken_price": _taken_price(edge),
                "source": edge.get("source"),
                "model_p_over": edge.get("model_p_over"),
                "as_of": edge.get("as_of"),
                "recorded_at": now_iso(now),
                "executed": False,
                "channel": "paper",
                "market": "prop",
                "status": "open",
            }
            key = identity(row)
            if key in existing:
                out["skipped_existing"] += 1
                continue
            append(target, row)
            existing.add(key)
            out["recorded"] += 1
        out["status"] = "ok"
    except Exception as exc:  # noqa: BLE001 -- public fn must never raise
        logger.warning("record_board failed: %s", exc)
        out["status"] = "error: %s" % type(exc).__name__
    return out


def _load_parquet():
    try:
        import pandas as pd
    except Exception:  # noqa: BLE001
        return None
    if not _PARQUET.exists():
        return None
    try:
        return pd.read_parquet(_PARQUET)
    except Exception:  # noqa: BLE001
        return None


def _resolve_event_id(df, bet: Dict[str, Any], index) -> Optional[tuple]:
    """Map a bet to (player_id, event_id). A bet carries no event_id, so we
    resolve the player then pick their EARLIEST match on/after as_of (the match
    being bet). Returns None until such a final match exists. Never raises."""
    try:
        import pandas as pd

        res = resolve_player(
            df, bet.get("player"), team=bet.get("team"), index=index
        )
        if res.get("status") != "ok":
            return None
        pid = str(res["player_id"])
        rows = df.loc[df["player_id"].astype(str) == pid]
        if len(rows) == 0:
            return None
        as_of = pd.to_datetime(bet.get("as_of"), errors="coerce")
        dates = pd.to_datetime(rows["date"], errors="coerce")
        if as_of is not None and not pd.isna(as_of):
            rows = rows.loc[dates >= as_of]
        if len(rows) == 0:
            return None
        rows = rows.sort_values("date")
        return pid, str(rows.iloc[0]["event_id"])
    except Exception:  # noqa: BLE001
        return None


def _attach_clv(bet: Dict[str, Any], history_rows) -> Optional[float]:
    """CLV-vs-close for a PRICED settled bet, or None for a pick'em / unpriced bet.

    Looks up the bet's CLOSING-line snapshot (last logged line for the exact prop)
    in *history_rows* and devigs it against the taken price. None when the bet has no
    taken_price (pick'em -> calibration-only) or no priced snapshot was ever logged.
    Never raises (clv_vs_close is None-safe)."""
    taken = bet.get("taken_price")
    if taken is None:
        return None
    snap = prop_line_history.closing_snapshot(
        history_rows, bet.get("match"), bet.get("player"), bet.get("stat"),
        bet.get("line"), bet.get("source"),
    )
    if snap is None:
        return None
    return prop_line_history.clv_vs_close(
        bet.get("side"), taken, snap.get("over_price"), snap.get("under_price"),
    )


def grade_open(
    realized_df=None, ledger_path: Optional[Path] = None,
    history_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Settle every still-open prop bet against realized stats; append a settled
    twin per graded bet. Idempotent (an already-settled identity is skipped).
    Bets whose match is not yet final stay open. A PRICED settled bet also gets a
    clv_pct attached from its CLOSING-line snapshot in the line history (pick'em
    bets stay calibration-only, clv_pct None). Never raises."""
    target = Path(ledger_path) if ledger_path is not None else DEFAULT_LEDGER
    out = {"graded": 0, "still_open": 0, "already_settled": 0}
    try:
        df = realized_df if realized_df is not None else _load_parquet()
        if df is None:
            out["status"] = "no_realized_data"
            return out
        history_rows = prop_line_history.load_history(history_path)
        ledger = load_ledger(target)
        settled_keys = {
            identity(r) for r in ledger if r.get("status") == "settled"
        }
        opens = [r for r in ledger if r.get("status") == "open"]
        index = build_name_index(df)
        for bet in opens:
            key = identity(bet)
            if key in settled_keys:
                out["already_settled"] += 1
                continue
            ev = _resolve_event_id(df, bet, index)
            if ev is None:
                out["still_open"] += 1
                continue
            pid, eid = ev
            realized = realized_stat(df, pid, eid, bet.get("stat"))
            graded = settle_prop(realized, bet.get("line"), bet.get("side"))
            if graded["result"] == "pending":
                out["still_open"] += 1
                continue
            twin = dict(bet)
            twin["status"] = "settled"
            twin["settled_at"] = now_iso()
            twin["event_id"] = eid
            twin["player_id"] = pid
            twin["result"] = graded["result"]
            twin["realized"] = graded["realized"]
            twin["paper_pnl"] = paper_pnl(graded["result"], bet.get("taken_price"))
            twin["clv_pct"] = _attach_clv(bet, history_rows)
            append(target, twin)
            settled_keys.add(key)
            out["graded"] += 1
        out["status"] = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("grade_open failed: %s", exc)
        out["status"] = "error: %s" % type(exc).__name__
    return out


def main(argv: Optional[List[str]] = None) -> int:
    """CLI: --record | --grade | --summary --sport soccer_intl. Never raises."""
    ap = argparse.ArgumentParser(
        description="PAPER prop ledger loop (no real money)."
    )
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--grade", action="store_true")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--sport", default="soccer_intl")
    ap.add_argument("--all", action="store_true",
                    help="record_board with only_reliable=False (record thin too).")
    args = ap.parse_args(argv)
    try:
        if args.record:
            from scripts.platformkit.prop_edge import build_prop_board

            board = build_prop_board(args.sport)
            res = record_board(board, only_reliable=not args.all)
            print(json.dumps(res))
        if args.grade:
            print(json.dumps(grade_open()))
        if args.summary:
            print(json.dumps(prop_summary()))
        if not (args.record or args.grade or args.summary):
            ap.print_help()
    except Exception as exc:  # noqa: BLE001 -- CLI must never raise
        print(json.dumps({"status": "error: %s" % type(exc).__name__}))
        return 1
    return 0


__all__ = [
    "record_board", "grade_open", "prop_summary", "load_ledger", "main",
    "DEFAULT_LEDGER",
]


if __name__ == "__main__":
    raise SystemExit(main())
