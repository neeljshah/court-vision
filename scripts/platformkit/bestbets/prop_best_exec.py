"""scripts.platformkit.bestbets.prop_best_exec -- best-execution layer for paper props.

THE GAP: props are our worst execution channel (mean CLV -7.1%) -- a candidate is
priced against ONE book (edge["source"]) and placed at that single price, never
shopped, never devig-gated, never volume-limited. This module sits between a
priced prop_edge board edge and the paper ledger write:

  shop_prop   -- cross-book (build_prop_matrix) best price for the taken side +
                 the opposite side's best price (needed to devig) + an audit
                 trail of every book quoted.
  fair_and_gate -- devig the two-way pair (odds_shop.devig_twoway, the SAME
                 solver clv_ledger.compute_clv uses) -> fair prob for the taken
                 side -> execution.expected_clv_gate at the pre-registered
                 PROP_EXPECTED_CLV_MIN_PCT floor. One-sided market (no opposite
                 price) FAILS CLOSED -- never fabricates a devig off one leg.
  decide      -- shop -> gate -> execution.circuit_breaker.allow_placement.

SUPPRESS-ONLY: this layer can only BLOCK a placement or improve its taken price
vs. the old single-book path; it can never place something the old path would
have skipped. Callers gate this whole module behind CV_PROP_BEST_EXEC (default
ON) so it can be disabled without a code edit.

PAPER / UNITS only. No $ field anywhere. Public fns never raise.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/bestbets/test_prop_best_exec.py -q
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from scripts.platformkit.execution import circuit_breaker as _breaker
from scripts.platformkit.execution.expected_clv_gate import gate as _gate
from scripts.platformkit.execution.thresholds import PROP_EXPECTED_CLV_MIN_PCT
from scripts.platformkit.odds_shop import devig_twoway as _devig_twoway
from scripts.platformkit.prop_line_matrix import MatrixRow, build_prop_matrix

logger = logging.getLogger(__name__)

MAX_AUDIT_BOOKS = 8


def load_ledger_rows(ledger_path: Any) -> List[Dict[str, Any]]:
    """All rows currently in the units ledger; [] on any read failure.

    Shared by callers needing both the dedup bet_id set AND the circuit-breaker
    rolling-CLV window off the SAME read (avoids reading the ledger twice)."""
    try:
        from scripts.platformkit import clv_ledger as _clv
        return list(_clv.load_ledger(ledger_path))
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_best_exec: ledger read failed: %s", exc)
        return []


def _match_row(edge: Dict[str, Any], matrix: List[MatrixRow]) -> Optional[MatrixRow]:
    player = str(edge.get("player") or edge.get("matched_name") or "").strip().lower()
    stat = str(edge.get("stat") or "").strip().lower()
    try:
        line = float(edge.get("line"))
    except (TypeError, ValueError):
        return None
    for row in matrix:
        if (row.player.strip().lower() == player and row.stat.strip().lower() == stat
                and float(row.line) == line):
            return row
    return None


def shop_prop(edge: Dict[str, Any], sport: str,
              providers: Optional[List[Any]] = None) -> Optional[Dict[str, Any]]:
    """Cross-book shop for one candidate prop edge (player/stat/line/side).

    Returns None (skip, honest reason logged) when providers are unavailable or
    no book quotes the taken side. Otherwise a dict: side, taken_price,
    taken_book, opp_price, opp_book (side's price/book absent -> None, never
    fabricated), payout_type, as_of, all_books (per-book over/under, capped at
    MAX_AUDIT_BOOKS for the ledger audit log).
    """
    side = str(edge.get("best_side") or edge.get("side") or "").strip().lower()
    if side not in ("over", "under"):
        return None
    if providers is None:
        try:
            from scripts.platformkit.prop_edge_config import providers_for_sport
            providers = providers_for_sport(sport)
        except Exception as exc:  # noqa: BLE001
            logger.debug("prop_best_exec: providers_for_sport(%s) failed: %s", sport, exc)
            providers = []
    if not providers:
        return None
    try:
        from scripts.platformkit.odds_provider.prop_aggregate import gather_props
        raw_rows = gather_props(providers, sport)
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_best_exec: gather_props(%s) failed: %s", sport, exc)
        return None
    if not raw_rows:
        return None
    matrix = build_prop_matrix(providers, sport, raw_rows=raw_rows)
    row = _match_row(edge, matrix)
    if row is None:
        return None
    taken_price = row.best_over_price if side == "over" else row.best_under_price
    taken_book = row.best_over_book if side == "over" else row.best_under_book
    if taken_price is None or taken_book is None:
        return None  # no book quotes the taken side -- honest skip
    opp_price = row.best_under_price if side == "over" else row.best_over_price
    opp_book = row.best_under_book if side == "over" else row.best_over_book
    player_l, stat_l = row.player.strip().lower(), row.stat.strip().lower()
    all_books = []
    for r in raw_rows:
        if str(r.player).strip().lower() != player_l or str(r.stat).strip().lower() != stat_l:
            continue
        try:
            if float(r.line) != float(row.line):
                continue
        except (TypeError, ValueError):
            continue
        all_books.append({"book": r.source, "over": r.over_price, "under": r.under_price})
    return {
        "side": side,
        "taken_price": taken_price, "taken_book": taken_book,
        "opp_price": opp_price, "opp_book": opp_book,
        "payout_type": row.payout_type, "as_of": row.as_of,
        "all_books": all_books[:MAX_AUDIT_BOOKS],
    }


def fair_and_gate(taken_decimal: Optional[float], opp_decimal: Optional[float],
                   threshold_pct: float = PROP_EXPECTED_CLV_MIN_PCT) -> Dict[str, Any]:
    """Devig the two-way pair -> fair prob for the taken side -> expected-CLV gate.

    Fails closed (passed=False, reason="no_two_way") when the opposite side has
    no price -- a one-sided market cannot be honestly devigged off one leg.
    """
    if taken_decimal is None or opp_decimal is None:
        return {"passed": False, "expected_clv_pct": None, "threshold_pct": threshold_pct,
                "fair_prob": None, "taken_decimal": taken_decimal, "reason": "no_two_way"}
    try:
        fair_taken, _fair_opp = _devig_twoway(float(taken_decimal), float(opp_decimal))
    except (TypeError, ValueError, ArithmeticError) as exc:
        logger.debug("prop_best_exec: devig failed: %s", exc)
        return {"passed": False, "expected_clv_pct": None, "threshold_pct": threshold_pct,
                "fair_prob": None, "taken_decimal": taken_decimal, "reason": "degenerate"}
    return _gate(taken_decimal, fair_taken, threshold_pct)


def decide(edge: Dict[str, Any], sport: str, ledger_rows: List[Dict[str, Any]],
           now_iso: str, *, providers: Optional[List[Any]] = None,
           threshold_pct: float = PROP_EXPECTED_CLV_MIN_PCT) -> Dict[str, Any]:
    """Compose shop -> devig+gate -> circuit breaker for one candidate prop.

    Returns {"place": bool, "reason": str, "exec_log": dict|None}. Never raises.
    """
    shopped = shop_prop(edge, sport, providers=providers)
    if shopped is None:
        return {"place": False, "reason": "unavailable", "exec_log": None}
    g = fair_and_gate(shopped["taken_price"], shopped["opp_price"], threshold_pct)
    if not g.get("passed"):
        return {"place": False, "reason": g.get("reason") or "below_threshold",
                "exec_log": {**shopped, **g}}
    breaker = _breaker.allow_placement(ledger_rows, "prop", now_iso)
    if not breaker.get("allowed"):
        return {"place": False, "reason": breaker.get("reason") or "breaker_capped",
                "exec_log": {**shopped, **g, "breaker_state": breaker.get("state")}}
    exec_log = {
        "book": shopped["taken_book"],
        "taken_decimal": shopped["taken_price"],
        "opp_decimal": shopped["opp_price"],
        "fair_prob": g.get("fair_prob"),
        "expected_clv_pct": g.get("expected_clv_pct"),
        "threshold_pct": g.get("threshold_pct"),
        "all_books": shopped["all_books"],
        "as_of": shopped["as_of"],
        "breaker_state": breaker.get("state"),
    }
    return {"place": True, "reason": "ok", "exec_log": exec_log}


def gate_and_stamp(p: Dict[str, Any], edge: Dict[str, Any], sport: str,
                    ledger_rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Best-exec gate one props_paper_placer placement dict *p*.

    Suppress-only: returns None to skip (never places what the legacy path
    would reject) or *p* (copied) with its taken price shopped to the best
    book + an exec_gate audit trail + signal_ts + placement_latency_ms +
    quote_age_s (LEVER 1 prop-side stamp, EXECUTION_BACKLOG.md #1/#5: seconds
    between the shopped quote's as_of and now -- honest None if either
    timestamp is unparseable). ledger_rows is a caller-supplied snapshot --
    ponytail: the breaker cap can under-count placements made earlier in the
    same run; refresh from disk if within-run precision ever matters."""
    import time as _time
    t0 = _time.monotonic()
    now_iso = _now_iso_utc()
    dec = decide(edge, sport, ledger_rows, now_iso)
    latency_ms = round((_time.monotonic() - t0) * 1000.0, 2)
    if not dec["place"]:
        logger.info("prop_best_exec: skip %s reason=%s", p.get("market"), dec["reason"])
        return None
    log = dec["exec_log"]
    out = dict(p)
    out["taken_book"] = str(log["book"])
    out["taken_decimal"] = float(log["taken_decimal"])
    out["exec_gate"] = log
    out["signal_ts"] = edge.get("as_of")
    out["placement_latency_ms"] = latency_ms
    out["quote_age_s"] = _quote_age_s(log.get("as_of"), now_iso)
    return out


def _now_iso_utc() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _quote_age_s(as_of: Optional[str], now_iso: str) -> Optional[float]:
    """Seconds between the shopped quote's as_of and *now_iso* (LEVER 1,
    EXECUTION_BACKLOG.md #1/#5 prop-side stamp). None if either timestamp is
    missing/unparseable -- never fabricated."""
    from datetime import datetime

    def _parse(v: Optional[str]):
        if not v:
            return None
        try:
            return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None

    a, n = _parse(as_of), _parse(now_iso)
    if a is None or n is None:
        return None
    return round((n - a).total_seconds(), 2)


def _demo() -> None:
    """Smallest runnable self-check (assert-based); not a test framework."""
    edge = {"side": "over", "player": "A B", "stat": "Hits", "line": 1.5}
    from scripts.platformkit.odds_provider.prop_base import PropLine
    rows = [
        PropLine(sport="mlb", event_id="1", match="X @ Y", player="A B", team=None,
                 stat="Hits", line=1.5, over_price=1.80, under_price=1.95,
                 payout_type="sportsbook", source="dk", as_of="2026-07-15T00:00:00Z"),
        PropLine(sport="mlb", event_id="1", match="X @ Y", player="A B", team=None,
                 stat="Hits", line=1.5, over_price=2.05, under_price=1.85,
                 payout_type="sportsbook", source="mgm", as_of="2026-07-15T00:05:00Z"),
    ]
    shopped = shop_prop(edge, "mlb", providers=[])
    assert shopped is None  # no providers -> unavailable
    matrix = build_prop_matrix([], "mlb", raw_rows=rows)
    row = _match_row(edge, matrix)
    assert row.best_over_price == 2.05 and row.best_over_book == "mgm"  # shopped best
    g = fair_and_gate(2.05, None)
    assert g["passed"] is False and g["reason"] == "no_two_way"  # fails closed
    print("prop_best_exec self-check OK")


if __name__ == "__main__":
    _demo()


__all__ = ["load_ledger_rows", "shop_prop", "fair_and_gate", "decide",
           "gate_and_stamp", "MAX_AUDIT_BOOKS"]
