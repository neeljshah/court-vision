"""scripts.platformkit.execution.ingame_exec_gate -- in-game placement gate helper.

Composes the expected-CLV gate (execution.expected_clv_gate), an optional
adverse-price-drift check, and a max-spread placement gate into ONE
suppress-only decision for inplay_daytrader.on_tick's ENTER path. Also builds
the placement-time microstructure stamp (LEVER 1, EXECUTION_BACKLOG.md #1/#5)
that the caller threads verbatim into paper_ingame.record_ingame_bet's
exec_depth field. SUPPRESS-ONLY: it can only turn a would-be "bet" into
"no_bet", never manufacture a bet or loosen the edge/liquidity/freshness gates
already passed upstream. PAPER / UNITS only.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.platformkit.execution import expected_clv_gate as _gate
from scripts.platformkit.execution.thresholds import (
    INGAME_EXPECTED_CLV_MIN_PCT, INGAME_MAX_DRIFT_PCT, INGAME_MAX_SPREAD_BP,
)
from scripts.platformkit.ingame import ingame_book_depth as _bd

logger = logging.getLogger(__name__)

# Tick fields build_exec_depth prefers straight off the tick before falling
# back to a book_depth sidecar lookup -- see that function's docstring.
_DEPTH_TICK_FIELDS = ("spread_bp", "book_thinness", "best_bid", "best_ask")


def _drift_pct(signal_decimal: Optional[float], fresh_decimal: Optional[float]) -> Optional[float]:
    """Percent change in obtainable decimal from signal time to a fresher observation.

    Negative = the price got worse (adverse) since the signal was computed. None if
    no fresher observation was supplied (the common case: one tick, one price) --
    never fabricates a drift figure from a single observation.
    """
    if signal_decimal is None or fresh_decimal is None:
        return None
    try:
        sd, fd = float(signal_decimal), float(fresh_decimal)
    except (TypeError, ValueError):
        return None
    if sd <= 0.0:
        return None
    return (fd - sd) / sd * 100.0


def _spread_suppress_enabled() -> bool:
    """CV_INGAME_MAX_SPREAD env toggle, default ON."""
    return os.environ.get("CV_INGAME_MAX_SPREAD", "1").strip().lower() not in ("0", "false", "off")


def _parse_depth_ts(value: Optional[str]) -> Optional[datetime]:
    """Best-effort ISO-8601 parse (handles a trailing 'Z'). None on any failure."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _read_depth_sidecar_row(ticker: str, now_dt: datetime, *,
                            sidecar_dir: Optional[Path] = None,
                            max_age_sec: float = 120.0) -> Optional[Dict[str, Any]]:
    """Best-effort NEAREST kalshi book_depth sidecar row for *ticker* within
    max_age_sec of now_dt (today's date-sharded file only -- ponytail: a poll
    spanning UTC midnight can miss yesterday's tail, add a prev-day fallback if
    that gap ever bites). None on any read failure or no close-enough match --
    never fabricated."""
    base = Path(sidecar_dir) if sidecar_dir is not None else _bd.DEFAULT_SIDECAR_DIR
    path = base / "kalshi" / ("%s.jsonl" % now_dt.strftime("%Y-%m-%d"))
    if not path.exists():
        return None
    best_row, best_age = None, None
    try:
        for line in path.read_text(encoding="ascii", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("ticker") != ticker:
                continue
            ts = _parse_depth_ts(row.get("ts"))
            if ts is None:
                continue
            age = abs((now_dt - ts).total_seconds())
            if age <= max_age_sec and (best_age is None or age < best_age):
                best_row, best_age = row, age
    except Exception as exc:  # noqa: BLE001 -- a bad sidecar file never sinks placement
        logger.debug("ingame_exec_gate: depth sidecar read failed %s: %s", path, exc)
        return None
    return best_row


def build_exec_depth(tick: Optional[Dict[str, Any]] = None, *, ticker: Optional[str] = None,
                     now: Optional[datetime] = None, sidecar_dir: Optional[Path] = None,
                     max_age_sec: float = 120.0) -> Dict[str, Any]:
    """Placement-time microstructure stamp (LEVER 1, EXECUTION_BACKLOG.md #1/#5).

    Prefers spread_bp/book_thinness/best_bid/best_ask already present on *tick*
    (a live daemon that captured depth alongside its price pair); else looks up
    the freshest kalshi book_depth sidecar row (data/cache/book_depth/kalshi/
    <date>.jsonl, the row shape ingame_book_depth_kalshi.py writes) for
    *ticker* within max_age_sec (default 120s) of *now*. Never fabricates: no
    source at all -> every field None plus reason="no_depth_source". Never
    raises.
    """
    tick = tick or {}
    now_dt = now or datetime.now(timezone.utc)
    if any(tick.get(f) is not None for f in _DEPTH_TICK_FIELDS):
        src: Dict[str, Any] = tick
        depth_ts = tick.get("depth_ts") or tick.get("ts")
    else:
        row = (_read_depth_sidecar_row(ticker, now_dt, sidecar_dir=sidecar_dir,
                                       max_age_sec=max_age_sec) if ticker else None)
        if row is None:
            return {"spread_bp": None, "book_thinness": None, "best_bid": None,
                    "best_ask": None, "mid": None, "depth_ts": None,
                    "reason": "no_depth_source"}
        src, depth_ts = row, row.get("ts")
    bid, ask = src.get("best_bid"), src.get("best_ask")
    mid = ((bid + ask) / 2.0) if isinstance(bid, (int, float)) and isinstance(ask, (int, float)) else None
    return {"spread_bp": src.get("spread_bp"), "book_thinness": src.get("book_thinness"),
            "best_bid": bid, "best_ask": ask, "mid": mid, "depth_ts": depth_ts}


def evaluate_placement(ev: Dict[str, Any], tick: Dict[str, Any], *,
                       ticker: Optional[str] = None, now: Optional[datetime] = None,
                       sidecar_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Evaluate the expected-CLV + drift + max-spread gates for the chosen-side ENTER
    *ev* dict, and build its placement-time depth stamp.

    *ev* is inplay_edge_signal.evaluate's return dict. Mirrors clv.best_price's own
    expected_clv_pct convention (fair vs the price actually taken): here the FAIR
    estimate is the calibrated model probability (bet_model_prob) -- the model IS
    the fair-value estimate, the devigged market price is merely what it is
    compared against upstream -- and the TAKEN price is the obtainable decimal for
    the chosen side. This is mathematically ev*100 restated as a percent, gated
    against a pre-registered floor independent of the proxy-adjusted tier floor
    already applied upstream (never loosens it; only an additional, lower-set net).
    *tick* may optionally carry "fresh_obtainable_decimal": a fresher price
    observed for the same side at/near placement time; when absent (today's
    default -- no fresher-price source is wired), drift_pct is None and drift
    never suppresses. *tick* may also carry spread_bp/book_thinness/best_bid/
    best_ask directly (see build_exec_depth); *ticker* is the Kalshi market ref
    used to look those up from the book_depth sidecar when the tick doesn't.

    MAX-SPREAD GATE (LEVER 3, EXECUTION_BACKLOG.md #3, pre-registered
    2026-07-15): suppresses when spread_bp > INGAME_MAX_SPREAD_BP (800bp).
    Missing spread data NEVER suppresses (spread_unknown=True is logged on the
    gate dict instead) -- an absent depth source must not silently kill the
    channel. Toggle: CV_INGAME_MAX_SPREAD (default ON).

    Returns {"suppress": bool, "reason": Optional[str], "exec_gate": dict,
    "exec_depth": dict} where exec_gate is expected_clv_gate.gate()'s dict plus
    "drift_pct"/"spread_bp"/"spread_unknown"/"spread_flag", and exec_depth is
    build_exec_depth()'s placement-time microstructure stamp.
    """
    taken_decimal = ev.get("obtainable_decimal")
    fair_prob = ev.get("bet_model_prob")
    g = _gate.gate(taken_decimal=taken_decimal, fair_prob=fair_prob,
                   threshold_pct=INGAME_EXPECTED_CLV_MIN_PCT)
    drift = _drift_pct(taken_decimal, tick.get("fresh_obtainable_decimal"))
    g["drift_pct"] = drift
    depth = build_exec_depth(tick, ticker=ticker, now=now, sidecar_dir=sidecar_dir)
    spread_bp = depth.get("spread_bp")
    g["spread_bp"] = spread_bp
    g["spread_unknown"] = spread_bp is None
    g["spread_flag"] = bool(spread_bp is not None and spread_bp > INGAME_MAX_SPREAD_BP)
    if drift is not None and drift <= -INGAME_MAX_DRIFT_PCT:
        return {"suppress": True, "reason": "drift", "exec_gate": g, "exec_depth": depth}
    if not g.get("passed", False):
        return {"suppress": True, "reason": "expected_clv_below_floor", "exec_gate": g,
                "exec_depth": depth}
    if g["spread_flag"] and _spread_suppress_enabled():
        return {"suppress": True, "reason": "spread_too_wide", "exec_gate": g,
                "exec_depth": depth}
    return {"suppress": False, "reason": None, "exec_gate": g, "exec_depth": depth}


def _demo() -> None:
    """Smallest runnable self-check (assert-based); not a test framework."""
    ev_ok = {"obtainable_decimal": 1.818, "bet_model_prob": 0.80}  # big model edge
    r_ok = evaluate_placement(ev_ok, {})
    assert r_ok["suppress"] is False and r_ok["exec_gate"]["drift_pct"] is None
    assert r_ok["exec_depth"]["reason"] == "no_depth_source"

    ev_low = {"obtainable_decimal": 1.818, "bet_model_prob": 0.55}  # tiny model edge
    r_low = evaluate_placement(ev_low, {})
    assert r_low["suppress"] is True and r_low["reason"] == "expected_clv_below_floor"

    r_drift = evaluate_placement(ev_ok, {"fresh_obtainable_decimal": 1.60})
    assert r_drift["suppress"] is True and r_drift["reason"] == "drift"

    r_wide = evaluate_placement(ev_ok, {"spread_bp": 900.0})
    assert r_wide["suppress"] is True and r_wide["reason"] == "spread_too_wide"

    r_tight = evaluate_placement(ev_ok, {"spread_bp": 100.0})
    assert r_tight["suppress"] is False and r_tight["exec_gate"]["spread_flag"] is False
    print("ingame_exec_gate self-check OK")


if __name__ == "__main__":
    _demo()


__all__ = ["evaluate_placement", "build_exec_depth"]
