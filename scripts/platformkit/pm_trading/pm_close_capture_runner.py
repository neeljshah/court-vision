"""scripts.platformkit.pm_trading.pm_close_capture_runner -- supervised M18 entry.

CLOSE-CAPTURE-ONLY daemon: every 900 s it resolves + applies confirmed Kalshi closing
lines to settled paper_pm bets (pm_close_capture.sweep_closes), making our best-realized
channel (Kalshi game moneyline) finally CLV-MEASURABLE -- it carried clv_pct=None on every
row because the resolver was never run. Then beats a heartbeat.

HONEST RAILS: PAPER measurement only -- NO placement, NO $ field, NO edge claim, NO flag
flip, NO real-money action. ONLY a confirmed (settled) Kalshi close is stamped (true_close);
an open/inferred market is never written. Idempotent. Injectable clock/sleep/sweep_fn/
max_ticks/should_stop for offline tests.

Heartbeat: m18_pm_close_capture -> data/cache/daemon_heartbeats/m18_pm_close_capture.txt
Cadence: DEFAULT_INTERVAL_SEC = 900 s. Status: data/frontend/ops/pm_close_capture_status.json.
stdlib + repo-internal; ASCII only; <=300 LOC.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("pm_close_capture_runner")

HEARTBEAT_COMPONENT = "m18_pm_close_capture"

_REPO = pathlib.Path(__file__).resolve().parents[3]
_STATUS_PATH = _REPO / "data" / "frontend" / "ops" / "pm_close_capture_status.json"

DEFAULT_INTERVAL_SEC = 900.0


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M18 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("pm_close_capture heartbeat skipped: %s", exc)


def _default_sweep() -> Dict[str, Any]:
    """Run the real PM close-capture sweep over clv_ledger. Never raises."""
    try:
        from scripts.platformkit.pm_trading.pm_close_capture import sweep_closes
        return dict(sweep_closes() or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("pm_close_capture sweep raised: %s", exc)
        return {"n_targets": 0, "n_captured": 0, "n_no_close": 0, "n_proxy": 0,
                "error": str(exc)}


def _status_doc(result: Dict[str, Any], now: float) -> Dict[str, Any]:
    """Compact, $-free status envelope."""
    return {
        "generated_at": now,
        "component": HEARTBEAT_COMPONENT,
        "n_targets": int(result.get("n_targets", 0) or 0),
        "n_captured": int(result.get("n_captured", 0) or 0),
        "n_no_close": int(result.get("n_no_close", 0) or 0),
        "n_proxy": int(result.get("n_proxy", 0) or 0),
        "executed": False,
        "edge_claimed": False,
        "honest_note": (
            "CLOSE-CAPTURE-ONLY M18. Stamps CONFIRMED (settled) Kalshi closes onto "
            "settled paper_pm bets so the channel is CLV-measurable; open/inferred "
            "markets are never written (no fabricated close). PAPER; no $ field, no edge."
        ),
    }


def _atomic_write(path: pathlib.Path, doc: Dict[str, Any]) -> bool:
    """Atomically write JSON to path. Returns True on success. Never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(raw, encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("pm_close_capture atomic write failed: %s", exc)
        return False


def tick(*, now: float,
         sweep_fn: Optional[Callable[[], Dict[str, Any]]] = None,
         status_path: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    """One close-capture tick: sweep settled PM rows -> stamp confirmed closes -> atomic
    status write -> heartbeat. Never raises. Heartbeat advances regardless of count."""
    path = status_path if status_path is not None else _STATUS_PATH
    _sweep = sweep_fn if sweep_fn is not None else _default_sweep
    try:
        result = dict(_sweep() or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("pm_close_capture tick sweep raised: %s", exc)
        result = {"n_targets": 0, "n_captured": 0, "n_no_close": 0, "n_proxy": 0}
    doc = _status_doc(result, now)
    _atomic_write(path, doc)
    _beat(now)
    return doc


def run(*, sweep_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        status_path: Optional[pathlib.Path] = None,
        interval_sec: float = DEFAULT_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the PM close-capture loop forever (or max_ticks). Never raises out.
    Everything injectable for offline tests. Returns ticks executed."""
    import time as _time
    _clock = clock if clock is not None else _time.time
    _sleep = sleep if sleep is not None else _time.sleep
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
            now = _time.time()
        tick(now=now, sweep_fn=sweep_fn, status_path=status_path)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001
            break
    return ticks


def _main() -> int:  # pragma: no cover
    import argparse
    p = argparse.ArgumentParser(
        description="Supervised PM close-capture daemon (M18): every 900 s stamps "
                    "confirmed Kalshi closes onto settled paper_pm bets. PAPER; no $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    a = p.parse_args()
    print("pm_close_capture_runner | started interval=%ss component=%s"
          % (a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("pm_close_capture_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC", "tick", "run"]
