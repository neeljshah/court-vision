"""scripts.platformkit.execution.executor.dryrun -- DRY-RUN order pass:
consume the composer's bestbets_composed.jsonl, drive each intended order
through the full OrderExecutor lifecycle against MockKalshiExchange seeded
with the freshest CAPTURED book_depth snapshots, and append intended orders +
simulated fills (as-of stamped) to data/frontend/ops/dryrun_orders.jsonl --
the forward paper-parity log that reconcile.py later scores against the tape.

NO real order path here: --live routes through lifecycle.resolve_exchange's
double gate and raises (the enabling env flag does not exist in this repo by
design). Idempotent across re-runs: a (ticker, side, price, day) intent
already in the output file is skipped, never duplicated.

If the composer input does not exist yet (it is a forward contract from the
compose lane), the run reports input_missing honestly and writes nothing.

TICKER RESOLUTION (M13 fix): composer rows never carry ticker/kalshi_ticker/
market_id -- collect_candidates() reuses the sport/book-agnostic best-bets
board (any book, not just Kalshi), so parse_intent() alone always returned
None. SEAM CHOICE: resolved HERE, not in composer -- dryrun is already the
sole Kalshi-specific IO boundary (MockKalshiExchange + book_depth/kalshi),
so ticker resolution belongs where Kalshi concerns already live, not leaked
into the book-agnostic composer. resolve_mlb_ticker() reuses ONLY what is
already loaded (this run's own book_depth snapshots, split into event/leg
ids) plus the settle path's existing team->Kalshi-code map
(ingame_id_resolver_mlb.KALSHI_ABBR) -- no new network join, no new team map.
MLB-only for now (KALSHI_ABBR's coverage); other sports/market_types stay an
honest unparseable when no local resolver covers them.

INVARIANTS: <=300 LOC; ASCII; stdlib only; order-time features only (the
freshest snapshot AT run time, never a later one); never writes
data/registry/; never flips a flag; price/probability language only.
Test: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/execution/executor/test_dryrun_reconcile.py -q
"""
from __future__ import annotations

import argparse
import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.execution.book_replay import load_jsonl
from scripts.platformkit.execution.executor.lifecycle import (
    ExecOrder, OrderExecutor, idem_key, resolve_exchange)
from scripts.platformkit.execution.executor.mock_exchange import MockKalshiExchange
from scripts.platformkit.ingame.ingame_id_resolver_mlb import KALSHI_ABBR

_REPO = Path(__file__).resolve().parents[4]
DEFAULT_INPUT = _REPO / "data" / "frontend" / "ops" / "bestbets_composed.jsonl"
DEFAULT_OUT = _REPO / "data" / "frontend" / "ops" / "dryrun_orders.jsonl"
BOOK_DEPTH_DIR = _REPO / "data" / "cache" / "book_depth" / "kalshi"
_PROB_FIELDS = ("limit_prob", "taken_prob", "market_prob", "model_prob", "price")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_intent(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Tolerant extraction of one order intent from a composed row.
    None if the row lacks a ticker or a usable 0-1 price."""
    ticker = row.get("ticker") or row.get("kalshi_ticker") or row.get("market_id")
    if not ticker:
        return None
    prob = None
    for f in _PROB_FIELDS:
        try:
            v = float(row[f])
        except (KeyError, TypeError, ValueError):
            continue
        if 0.0 < v < 1.0:
            prob = v
            break
    if prob is None:
        return None
    side = row.get("side") if row.get("side") in ("yes", "no") else "yes"
    try:
        qty = max(1, int(row.get("contracts", 10)))
    except (TypeError, ValueError):
        qty = 10  # ponytail: default 10 contracts per intent; size policy is the composer's job
    return {"ticker": str(ticker), "side": side, "qty": qty,
            "price_cents": min(99, max(1, int(round(prob * 100.0)))),
            "sport": str(row.get("sport", "unknown"))}


def _norm_team(name: Any) -> str:
    return " ".join(str(name or "").lower().split())


def _kalshi_code_for(team: str) -> Optional[str]:
    """Team name -> Kalshi 2-3 letter code via the settle path's existing
    KALSHI_ABBR map (statsapi full names). Kalshi-sourced board rows carry a
    TRUNCATED dialect (e.g. 'Los Angeles D' for 'Los Angeles Dodgers'), so an
    exact-key miss falls back to substring match -- the SAME loose-matching
    technique pm_game_placer._name_matches already uses for this exact
    cross-source divergence. >1 candidate match (e.g. bare 'Chicago', which
    fits both Cubs and White Sox) is an honest skip, never a guess."""
    t = _norm_team(team)
    if not t:
        return None
    exact = KALSHI_ABBR.get(t)
    if exact:
        return exact
    hits = {code for full, code in KALSHI_ABBR.items() if t in full or full in t}
    return hits.pop() if len(hits) == 1 else None


def leg_index(depth_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """{event_id: {team_code: leg_ticker}} from CAPTURED book_depth rows this
    run already loads for fills (no new IO). A Kalshi leg ticker is
    "<event_id>-<TEAMCODE>" -- this only splits that existing string, never
    guesses. Never raises."""
    idx: Dict[str, Dict[str, str]] = {}
    for r in depth_rows:
        event_id, sep, code = str(r.get("ticker") or "").rpartition("-")
        if sep and event_id and code:
            idx.setdefault(event_id, {})[code] = event_id + sep + code
    return idx


def resolve_mlb_ticker(row: Dict[str, Any], legs: Dict[str, Dict[str, str]]
                       ) -> Optional[str]:
    """MLB-only ticker resolution for a composed row that lacks one: if
    row['game_id'] is already a captured Kalshi event id and row['side'] is
    home/away, look up that side's leg ticker via the SAME team-name ->
    Kalshi-code map the settle path already uses (KALSHI_ABBR) -- no new
    team map. None on any miss (honest skip, never a guessed leg)."""
    if str(row.get("sport") or "").lower() != "mlb":
        return None
    per_event = legs.get(str(row.get("game_id") or ""))
    if not per_event:
        return None
    side = row.get("side")
    matchup = str(row.get("matchup") or "")
    if side not in ("home", "away") or " vs " not in matchup:
        return None
    home, _, away = matchup.partition(" vs ")
    code = _kalshi_code_for(home.strip() if side == "home" else away.strip())
    return per_event.get(code) if code else None


def load_latest_books(depth_dir: Path = BOOK_DEPTH_DIR, n_files: int = 2
                      ) -> List[Dict[str, Any]]:
    """Freshest snapshot row per ticker from the last *n_files* capture days
    (order-time features: everything here was captured BEFORE this run)."""
    latest: Dict[str, Dict[str, Any]] = {}
    for p in sorted(glob.glob(str(depth_dir / "*.jsonl")))[-n_files:]:
        for r in load_jsonl(Path(p)):
            tk = r.get("ticker")
            if tk and str(r.get("ts", "")) >= str(latest.get(tk, {}).get("ts", "")):
                latest[tk] = r
    return list(latest.values())


def _existing_keys(out_path: Path) -> set:
    return {r.get("idempotency_key") for r in load_jsonl(out_path)}


def run_dryrun(input_path: Path = DEFAULT_INPUT, out_path: Path = DEFAULT_OUT,
               depth_dir: Path = BOOK_DEPTH_DIR, max_rows: int = 500,
               exchange: Optional[MockKalshiExchange] = None) -> Dict[str, Any]:
    asof = _now_iso()
    day = asof[:10]
    rows = load_jsonl(input_path)
    report: Dict[str, Any] = {
        "asof_ts": asof, "input": str(input_path), "out": str(out_path),
        "input_missing": not input_path.exists(), "edge_claimed": False,
        "n_input_rows": len(rows), "n_intents": 0, "n_written": 0,
        "n_skipped_idempotent": 0, "n_unparseable": 0, "n_ticker_resolved": 0,
        "states": {},
    }
    if not rows:
        return report
    books = load_latest_books(depth_dir)
    if exchange is None:
        exchange = MockKalshiExchange(books)
    legs = leg_index(books)
    executor = OrderExecutor(exchange, governor=None, sleep_fn=lambda _s: None)
    seen = _existing_keys(out_path)
    out_lines: List[str] = []
    for row in rows[:max_rows]:
        if not (row.get("ticker") or row.get("kalshi_ticker") or row.get("market_id")):
            resolved = resolve_mlb_ticker(row, legs)
            if resolved:
                row = dict(row, ticker=resolved)
                report["n_ticker_resolved"] += 1
        intent = parse_intent(row)
        if intent is None:
            report["n_unparseable"] += 1
            continue
        report["n_intents"] += 1
        key = idem_key(intent["ticker"], intent["side"], intent["price_cents"], day)
        if key in seen:
            report["n_skipped_idempotent"] += 1
            continue
        seen.add(key)
        order = ExecOrder(idempotency_key=key, **intent)
        executor.execute(order, timeout_s=0.0)  # immediate-or-cancel parity pass
        book = exchange.book(intent["ticker"]) or {}
        rec = {
            "asof_ts": asof, "idempotency_key": key, "source": str(input_path.name),
            "ticker": intent["ticker"], "side": intent["side"], "qty": intent["qty"],
            "limit_price_cents": intent["price_cents"], "sport": intent["sport"],
            "book_ts": book.get("ts", ""), "book_best_bid_cents": book.get("bid"),
            "book_best_ask_cents": book.get("ask"),
            "state": order.state.value, "filled_qty": order.filled_qty,
            "avg_fill_price_cents": order.avg_fill_price_cents,
            "slippage_cents": (round(order.avg_fill_price_cents
                                     - intent["price_cents"], 4)
                               if order.filled_qty > 0 else None),
            "reason": order.reason,
            "history": [s for _t, s in order.history],
        }
        out_lines.append(json.dumps(rec, ensure_ascii=True))
        report["n_written"] += 1
        report["states"][order.state.value] = report["states"].get(order.state.value, 0) + 1
    if out_lines:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(out_lines) + "\n")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Dry-run Kalshi order pass (mock fills from captured "
                    "books; no real order path -- see --live gate)")
    ap.add_argument("--input", default=str(DEFAULT_INPUT))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--depth-dir", default=str(BOOK_DEPTH_DIR))
    ap.add_argument("--max-rows", type=int, default=500)
    ap.add_argument("--live", action="store_true",
                    help="explicit per-run live gate (gate b). Refused unless "
                         "the nonexistent env flag (gate a) is also set -- and "
                         "even then the live client is not wired.")
    args = ap.parse_args()
    # Gate check FIRST: --live must raise before any work is attempted.
    resolve_exchange(live=args.live)
    report = run_dryrun(Path(args.input), Path(args.out), Path(args.depth_dir),
                        max_rows=args.max_rows)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0


__all__ = ["parse_intent", "load_latest_books", "run_dryrun", "leg_index",
           "resolve_mlb_ticker", "DEFAULT_INPUT", "DEFAULT_OUT", "BOOK_DEPTH_DIR"]

if __name__ == "__main__":
    raise SystemExit(main())
