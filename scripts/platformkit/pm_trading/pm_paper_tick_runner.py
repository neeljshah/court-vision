"""scripts.platformkit.pm_trading.pm_paper_tick_runner -- M12 PM paper-trade daemon.

Captures PM pairs -> coerces to canonical rows -> appends to clv_ledger.jsonl.
0 markets coerced -> writes pm_last_capture.json honest-empty diagnostic.
RAILS: UNITS not $; is_pm=True; executed=False; clv_status=INSUFFICIENT_DATA;
real-money DENY; no flag flip; stale-never-green. bet_id=pm|venue|market_id
prevents paper_trail._collapse from folding N PM rows into one. <=300 LOC.
"""
from __future__ import annotations

import json
import logging
import pathlib
import time as _time_module
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("pm_paper_tick_runner")

HEARTBEAT_COMPONENT = "m12_pm_paper_tick"

_REPO = pathlib.Path(__file__).resolve().parents[3]
_DEFAULT_LEDGER = _REPO / "data" / "frontend" / "clv_ledger.jsonl"
_DEFAULT_DIAGNOSTIC = _REPO / "data" / "frontend" / "pm_last_capture.json"

DEFAULT_INTERVAL_SEC = 60.0

# Fields that must never appear in a PM paper row (units-not-$ rail).
_STRIP_KEYS = frozenset({"dollar_pnl", "pnl_usd", "dollar", "dollars",
                         "pnl", "roi", "profit", "dollar_stake",
                         "dollar_value", "net_pnl", "realized_pnl",
                         "unrealized_pnl"})

_PM_VENUES = frozenset({"kalshi", "polymarket"})


def _beat(now_epoch: Optional[float] = None) -> None:
    try:
        from ops.liveness import heartbeat  # type: ignore
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("pm_paper_tick heartbeat skipped: %s", exc)

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_row(raw: Dict[str, Any], now_iso: str) -> Optional[Dict[str, Any]]:
    """Coerce raw capture dict -> canonical PM ledger row, or None.

    Validates venue in {kalshi,polymarket} and non-empty market_id.
    Stamps is_pm=True, executed=False, clv_status=INSUFFICIENT_DATA.
    Sets taken_book=venue so enrich survives paper_trail collapse.
    """
    row: Dict[str, Any] = {k: v for k, v in raw.items() if k not in _STRIP_KEYS}

    # Venue: raw may supply "venue", "taken_book", or "channel".
    venue = str(row.get("venue") or row.get("taken_book") or
                row.get("channel") or "").strip().lower()
    if venue not in _PM_VENUES:
        for cand in _PM_VENUES:
            if cand in venue:
                venue = cand
                break
        else:
            # Last-resort: infer from market_id prefix.
            mid = str(row.get("market_id") or "").strip().lower()
            if mid.startswith(("kx", "kalshi")):
                venue = "kalshi"
            elif mid.startswith("poly"):
                venue = "polymarket"
            else:
                logger.debug("pm_paper_tick: skip non-PM venue %r mid=%r", venue, mid)
                return None

    market_id = str(row.get("market_id") or row.get("market") or "").strip()
    if not market_id:
        logger.debug("pm_paper_tick: skipping row with empty market_id")
        return None

    row["venue"] = venue
    row["market_id"] = market_id
    row["is_pm"] = True
    row["executed"] = False
    row["channel"] = "paper"
    row["status"] = str(row.get("status") or "open")
    row["clv_status"] = str(row.get("clv_status") or "INSUFFICIENT_DATA")
    row.setdefault("ts", now_iso)

    # taken_book must equal venue so enrich._infer_venue recovers is_pm=True.
    if not row.get("taken_book"):
        row["taken_book"] = venue

    # bet_id: stable per-contract key; prevents _collapse from folding N PM rows
    # that share the same sport/ts/taken_book into one (market_id is the diff).
    if not row.get("bet_id"):
        row["bet_id"] = "pm|%s|%s" % (venue, market_id)

    # stake_units alias resolution (default 1.0).
    if "stake_units" not in row:
        for alias in ("stake", "flat_unit", "units"):
            if alias in row:
                try:
                    row["stake_units"] = float(row[alias])
                except (TypeError, ValueError):
                    pass
                break
        row.setdefault("stake_units", 1.0)

    # model_prob alias resolution.
    if "model_prob" not in row:
        for alias in ("fair_prob", "calibrated_prob", "model_price"):
            if alias in row and row[alias] is not None:
                try:
                    row["model_prob"] = float(row[alias])
                except (TypeError, ValueError):
                    pass
                break

    # Final dollar-key guard.
    for k in list(_STRIP_KEYS & set(row.keys())):
        del row[k]

    return row


def _append_to_ledger(rows: List[Dict[str, Any]],
                      ledger_path: pathlib.Path) -> int:
    """Append rows to CLV ledger (lock-guarded, fallback direct). Never raises."""
    if not rows:
        return 0
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    for row in rows:
        try:
            from scripts.platformkit.clv_ledger_io import append_row as _ar
            _ar(row, path=ledger_path)
            written += 1
        except Exception:  # noqa: BLE001
            try:
                with ledger_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
                written += 1
            except Exception as exc2:  # noqa: BLE001
                logger.debug("pm_paper_tick ledger append failed: %s", exc2)
    return written


def _capture_pairs(now: float) -> List[Dict[str, Any]]:
    """Default capture: pull active PM pairs. Returns [] on any error."""
    try:
        from scripts.platformkit.pm_trading.live_feed import active_pairs  # type: ignore
        cleaned: List[Dict[str, Any]] = []
        for row in active_pairs(now=now):
            r = {k: v for k, v in row.items() if k not in _STRIP_KEYS}
            r.setdefault("captured_at", now)
            r.setdefault("clv_status", "INSUFFICIENT_DATA")
            cleaned.append(r)
        return cleaned
    except Exception as exc:  # noqa: BLE001
        logger.debug("pm_paper_tick active_pairs unavailable: %s", exc)
        return []


def _write_diagnostic(reason: str, now_iso: str, raw_count: int,
                      coerced_count: int,
                      diagnostic_path: Optional[pathlib.Path] = None) -> None:
    """Write ts/reason/counts diagnostic to pm_last_capture.json. Never raises."""
    _path = diagnostic_path if diagnostic_path is not None else _DEFAULT_DIAGNOSTIC
    try:
        _path.parent.mkdir(parents=True, exist_ok=True)
        diag: Dict[str, Any] = {
            "ts": now_iso, "reason": str(reason),
            "raw_count": int(raw_count), "coerced_count": int(coerced_count),
            "is_pm_active": coerced_count > 0,
        }
        with _path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(diag, ensure_ascii=True, sort_keys=True) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.debug("pm_paper_tick diagnostic write failed: %s", exc)


def tick(
    *,
    now: float,
    capture_fn: Optional[Callable[[float], List[Dict[str, Any]]]] = None,
    ledger_path: Optional[pathlib.Path] = None,
    diagnostic_path: Optional[pathlib.Path] = None,
    pm_dir: Optional[pathlib.Path] = None,  # backward-compat, ignored
) -> List[str]:
    """Capture pairs -> coerce -> append to clv_ledger. Returns written market_ids.
    Writes pm_last_capture.json diagnostic (injectable). Never raises.
    """
    _capture = capture_fn if capture_fn is not None else _capture_pairs
    _ledger = ledger_path if ledger_path is not None else _DEFAULT_LEDGER

    capture_error: Optional[str] = None
    try:
        raw_pairs = _capture(now)
    except Exception as exc:  # noqa: BLE001
        logger.debug("pm_paper_tick capture raised: %s", exc)
        capture_error = "%s: %s" % (type(exc).__name__, exc)
        raw_pairs = []

    now_iso = _now_iso()
    coerced: List[Dict[str, Any]] = []
    for raw in raw_pairs:
        row = _coerce_row(raw, now_iso)
        if row is not None:
            coerced.append(row)

    # Bug fix: use actual written count (return of _append_to_ledger), not
    # len(coerced), so diagnostic.coerced_count == rows on disk (invariant).
    written_ids: List[str] = []
    written_count = 0
    if coerced:
        written_count = _append_to_ledger(coerced, _ledger)
        written_ids = [str(r.get("market_id", "")) for r in coerced[:written_count]]

    raw_count = len(raw_pairs)
    if written_count > 0:
        _diag_reason = "ok:%d_markets_written" % written_count
    elif coerced and written_count == 0:
        _diag_reason = "write_error:coerced=%d_written=0" % len(coerced)
    elif capture_error:
        _diag_reason = "capture_error:%s" % capture_error
    elif raw_count > 0:
        _diag_reason = "coerce_gap:raw=%d_coerced=0" % raw_count
    else:
        _diag_reason = "no_liquid_pm_markets"
    _write_diagnostic(reason=_diag_reason, now_iso=now_iso,
                      raw_count=raw_count, coerced_count=written_count,
                      diagnostic_path=diagnostic_path)

    _beat(now)
    return written_ids


def run(
    *,
    capture_fn: Optional[Callable[[float], List[Dict[str, Any]]]] = None,
    ledger_path: Optional[pathlib.Path] = None,
    interval_sec: float = DEFAULT_INTERVAL_SEC,
    clock: Optional[Callable[[], float]] = None,
    sleep: Optional[Callable[[float], None]] = None,
    max_ticks: Optional[int] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    pm_dir: Optional[pathlib.Path] = None,  # backward-compat, ignored
) -> int:
    """Tick loop (injectable for tests). Returns ticks executed. Never raises."""
    _clock = clock if clock is not None else _time_module.time
    _sleep = sleep if sleep is not None else _time_module.sleep
    ticks = 0
    try:
        _beat(float(_clock()))
    except Exception:  # noqa: BLE001
        _beat()
    while True:
        if should_stop is not None:
            try:
                if should_stop():
                    break
            except Exception:  # noqa: BLE001
                break
        try:
            now = float(_clock())
        except Exception:  # noqa: BLE001
            now = _time_module.time()
        tick(now=now, capture_fn=capture_fn, ledger_path=ledger_path)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001
            break
    return ticks


def _main() -> int:  # pragma: no cover
    import argparse as _ap
    p = _ap.ArgumentParser(description="PM paper tick daemon (M12): UNITS not $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC,
                   help="Seconds between ticks (default: %(default)s).")
    a = p.parse_args()
    print("pm_paper_tick_runner | started interval=%ss component=%s out=%s"
          % (a.interval, HEARTBEAT_COMPONENT, _DEFAULT_LEDGER), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("pm_paper_tick_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC",
           "tick", "run", "_write_diagnostic"]
