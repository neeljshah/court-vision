"""scripts.platformkit.pm_trading.run_cross_venue_arb -- paper-place detected
cross-venue price discrepancies (cross_venue_arb.scan) into the CLV ledger, +
CLI/daemon entrypoint.

Split from cross_venue_arb.py purely for LOC discipline (<=300/file); the
detection math (matching/fees/staleness) lives there, this file only turns a
detected lock into two ledger rows and appends them (same idempotent bet_id-
dedup pattern as pm_game_placer.run / pm_paper_tick_runner.tick).

HONEST RAILS: every written row carries executed=False, channel="paper",
edge_claimed=False, market_type="arb". Never a dollar/pnl/roi field. Real
money stays denied -- this module has no path to a real order.

CLI:
    python -m scripts.platformkit.pm_trading.run_cross_venue_arb --sport mlb
    python -m scripts.platformkit.pm_trading.run_cross_venue_arb --sport mlb --place
    python -m scripts.platformkit.pm_trading.run_cross_venue_arb --daemon --place
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.pm_trading.cross_venue_arb import (
    DEFAULT_MAX_AGE_SEC, DEFAULT_MIN_LOCKED_PROB, DEFAULT_SPORTS,
    DEFAULT_STAKE_UNITS, HONEST_NOTE, scan,
)

_REPO = Path(__file__).resolve().parents[3]
_DEFAULT_LEDGER = _REPO / "data" / "frontend" / "clv_ledger.jsonl"

HEARTBEAT_COMPONENT = "cross_venue_arb"
DEFAULT_INTERVAL_SEC = 60.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _leg_row(arb: Dict[str, Any], leg_key: str, other_key: str,
            stake_units: float) -> Dict[str, Any]:
    leg, other = arb[leg_key], arb[other_key]
    matchup = "%s @ %s" % (arb["away"], arb["home"])
    bet_id = "arb|%s|%s|%s|%s" % (arb["sport"], matchup, leg["venue"], leg["side"])
    return {
        "ts": _now_iso(), "sport": str(arb.get("sport") or ""),
        "matchup": matchup, "side": leg["side"], "taken_book": leg["venue"],
        "venue": leg["venue"], "taken_decimal": float(leg["decimal"]),
        "stake_units": round(float(stake_units), 6),
        "status": "open", "executed": False, "channel": "paper",
        "is_pm": leg["venue"] in ("kalshi", "polymarket"),
        "is_arb": True, "market_type": "arb",
        "market_id": bet_id, "bet_id": bet_id,
        "locked_prob": arb["locked_prob"],
        "other_leg_venue": other["venue"], "other_leg_side": other["side"],
        "leg_age_sec": leg["age_sec"],
        "clv_status": "INSUFFICIENT_DATA", "clv_is_proxy": True,
        "edge_claimed": False, "honest_note": HONEST_NOTE,
    }


def arb_to_rows(arb: Dict[str, Any], stake_units: float = DEFAULT_STAKE_UNITS
                ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """One detected arb -> both leg rows, same schema style as
    pm_game_placer._ledger_row / row_schema.canonical_pm_row."""
    return (_leg_row(arb, "leg_a", "leg_b", stake_units),
            _leg_row(arb, "leg_b", "leg_a", stake_units))


def _existing_bet_ids(ledger_path: Path) -> set:
    try:
        from scripts.platformkit import clv_ledger as _clv
        return {str(r.get("bet_id")) for r in _clv.load_ledger(ledger_path) if r.get("bet_id")}
    except Exception:  # noqa: BLE001
        return set()


def _append(row: Dict[str, Any], ledger_path: Path) -> bool:
    try:
        from scripts.platformkit.clv_ledger_io import append_row as _ar
        _ar(row, path=ledger_path)
        return True
    except Exception:  # noqa: BLE001
        try:
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with ledger_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
            return True
        except Exception:  # noqa: BLE001
            return False


def place_arbs(arbs: Sequence[Dict[str, Any]], *, ledger_path: Optional[Path] = None,
               stake_units: float = DEFAULT_STAKE_UNITS,
               place: bool = True) -> Dict[str, Any]:
    """Write both legs of each detected arb to the paper ledger. Idempotent via
    bet_id dedup (same pattern as pm_game_placer.run). Never raises."""
    _ledger = ledger_path if ledger_path is not None else _DEFAULT_LEDGER
    seen = _existing_bet_ids(_ledger) if place else set()
    written: List[str] = []
    n_dup = 0
    for arb in arbs:
        row_a, row_b = arb_to_rows(arb, stake_units=stake_units)
        if row_a["bet_id"] in seen or row_b["bet_id"] in seen:
            n_dup += 1
            continue
        if not place:
            continue
        ok_a = _append(row_a, _ledger)
        ok_b = _append(row_b, _ledger)
        if ok_a and ok_b:
            written.extend([row_a["bet_id"], row_b["bet_id"]])
            seen.add(row_a["bet_id"]); seen.add(row_b["bet_id"])
    return {"n_detected": len(arbs), "n_pairs_written": len(written) // 2,
            "n_dup_skipped": n_dup, "bet_ids": written, "edge_claimed": False,
            "channel": "paper"}


def run(sports: Sequence[str] = DEFAULT_SPORTS, *, place: bool = True,
       ledger_path: Optional[Path] = None,
       max_age_sec: float = DEFAULT_MAX_AGE_SEC,
       min_locked_prob: float = DEFAULT_MIN_LOCKED_PROB,
       stake_units: float = DEFAULT_STAKE_UNITS) -> Dict[str, Any]:
    """Scan all *sports*, paper-place every detected lock. Never raises."""
    all_arbs: List[Dict[str, Any]] = []
    for sport in sports:
        try:
            all_arbs.extend(scan(sport, max_age_sec=max_age_sec,
                                 min_locked_prob=min_locked_prob))
        except Exception:  # noqa: BLE001
            continue
    result = place_arbs(all_arbs, ledger_path=ledger_path, stake_units=stake_units,
                        place=place)
    result["sports_scanned"] = list(sports)
    return result


def _beat(now_epoch: Optional[float] = None) -> None:
    try:
        from ops.liveness import heartbeat  # type: ignore
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception:  # noqa: BLE001
        pass


def daemon_loop(*, sports: Sequence[str] = DEFAULT_SPORTS, place: bool = True,
                interval_sec: float = DEFAULT_INTERVAL_SEC,
                sleep: Optional[Callable[[float], None]] = None,
                max_ticks: Optional[int] = None,
                should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Tick loop (injectable for tests): run() every interval_sec. Returns ticks
    executed. Never raises; survives any single-tick failure."""
    import time as _time
    _sleep = sleep if sleep is not None else _time.sleep
    ticks = 0
    _beat()
    while True:
        if should_stop is not None:
            try:
                if should_stop():
                    break
            except Exception:  # noqa: BLE001
                break
        try:
            out = run(sports, place=place)
            print("%s | tick=%d detected=%d written_pairs=%d dup=%d"
                  % (HEARTBEAT_COMPONENT, ticks, out["n_detected"],
                     out["n_pairs_written"], out["n_dup_skipped"]), flush=True)
        except Exception as exc:  # noqa: BLE001
            print("%s | tick=%d ERROR %s" % (HEARTBEAT_COMPONENT, ticks, str(exc)[:160]),
                  flush=True)
        _beat()
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
    p = _ap.ArgumentParser(description=(
        "Paper cross-venue price-discrepancy scan (fee-adjusted, staleness-gated). "
        "NO real money; edge_claimed=False."))
    p.add_argument("--sport", action="append", default=None,
                   help="Sport(s) to scan; repeatable. Default: %s" % (DEFAULT_SPORTS,))
    p.add_argument("--place", action="store_true", help="Write detected arbs to the paper ledger.")
    p.add_argument("--max-age-sec", type=float, default=DEFAULT_MAX_AGE_SEC)
    p.add_argument("--min-locked-prob", type=float, default=DEFAULT_MIN_LOCKED_PROB)
    p.add_argument("--daemon", action="store_true",
                   help="Run forever, ticking every --interval-sec (default one-shot).")
    p.add_argument("--interval-sec", type=float, default=DEFAULT_INTERVAL_SEC)
    a = p.parse_args()
    sports = a.sport or list(DEFAULT_SPORTS)
    if a.daemon:
        daemon_loop(sports=sports, place=a.place, interval_sec=a.interval_sec)
        return 0
    out = run(sports, place=a.place, max_age_sec=a.max_age_sec,
             min_locked_prob=a.min_locked_prob)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = [
    "DEFAULT_INTERVAL_SEC", "HEARTBEAT_COMPONENT",
    "arb_to_rows", "place_arbs", "run", "daemon_loop",
]
