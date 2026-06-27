"""scripts.platformkit.pm_trading.kalshi_scan_runner -- supervised M17 entry.

DISCOVERY-ONLY daemon: every 1800 s it scans the LIQUID, actually-tradeable Kalshi
sports surface (kalshi_market_scan.run) and atomically writes the report, so we learn
which market types (player props / totals / spreads / game-winners) genuinely develop
takeable two-way liquidity DURING the live slate -- vs the thousands that stay
listed-not-traded. It also keeps a per-type daily HIGH-WATER mark of the most liquid
markets ever seen, so a peak during a marquee game is captured even between scans.

HONEST RAILS: read-only discovery -- NO placement, NO $ field, NO edge claim, NO flag
flip, NO real-money action. A market with no live two-way is EXCLUDED, never fabricated.
Heartbeat advances every tick. Injectable clock/sleep/scan_fn/max_ticks for tests.

Heartbeat: m17_kalshi_scan -> data/cache/daemon_heartbeats/m17_kalshi_scan.txt
Cadence: DEFAULT_INTERVAL_SEC = 1800 s. Report: data/frontend/ops/kalshi_market_scan.json.
stdlib + repo-internal; ASCII only; <=300 LOC.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("kalshi_scan_runner")

HEARTBEAT_COMPONENT = "m17_kalshi_scan"

_REPO = pathlib.Path(__file__).resolve().parents[3]
_HWM_PATH = _REPO / "data" / "frontend" / "ops" / "kalshi_scan_highwater.json"

DEFAULT_INTERVAL_SEC = 1800.0
DEFAULT_LEAGUES = ("MLB", "WC", "EPL", "WNBA")


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M17 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("kalshi_scan heartbeat skipped: %s", exc)


def _default_scan(leagues) -> Dict[str, Any]:
    """Run the real liquid-surface scan. Never raises."""
    try:
        from scripts.platformkit.pm_trading.kalshi_market_scan import run as _run
        return dict(_run(tuple(leagues)) or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("kalshi_scan sweep raised: %s", exc)
        return {"by_type": {}, "n_liquid_total": 0, "error": str(exc)}


def _update_highwater(report: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the per-type MAX liquid count ever seen + the peak total. Never raises."""
    hwm: Dict[str, Any] = {"by_type_max_liquid": {}, "peak_liquid_total": 0}
    try:
        if _HWM_PATH.exists():
            hwm = json.loads(_HWM_PATH.read_text(encoding="ascii"))
    except Exception:  # noqa: BLE001
        hwm = {"by_type_max_liquid": {}, "peak_liquid_total": 0}
    bt = hwm.setdefault("by_type_max_liquid", {})
    for mt, d in (report.get("by_type", {}) or {}).items():
        liq = int((d or {}).get("n_liquid", 0) or 0)
        if liq > int(bt.get(mt, 0) or 0):
            bt[mt] = liq
    total = int(report.get("n_liquid_total", 0) or 0)
    if total > int(hwm.get("peak_liquid_total", 0) or 0):
        hwm["peak_liquid_total"] = total
    hwm["honest_note"] = ("Per-type MAX liquid Kalshi markets ever observed across scans "
                          "(peak during the live slate). Discovery only; no $ / edge.")
    try:
        _HWM_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _HWM_PATH.with_suffix(_HWM_PATH.suffix + ".tmp")
        tmp.write_text(json.dumps(hwm, ensure_ascii=True, indent=2, sort_keys=True),
                       encoding="ascii")
        os.replace(str(tmp), str(_HWM_PATH))
    except Exception as exc:  # noqa: BLE001
        logger.debug("kalshi_scan highwater write failed: %s", exc)
    return hwm


def tick(*, now: float, leagues=DEFAULT_LEAGUES,
         scan_fn: Optional[Callable[[Any], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """One scan tick: scan liquid surface -> update high-water -> heartbeat. Never raises."""
    _scan = scan_fn if scan_fn is not None else _default_scan
    try:
        report = dict(_scan(leagues) or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("kalshi_scan tick raised: %s", exc)
        report = {"by_type": {}, "n_liquid_total": 0}
    _update_highwater(report)
    _beat(now)
    return report


def run(*, leagues=DEFAULT_LEAGUES,
        scan_fn: Optional[Callable[[Any], Dict[str, Any]]] = None,
        interval_sec: float = DEFAULT_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the Kalshi scan loop forever (or max_ticks). Never raises out. Everything
    injectable for offline tests. Returns ticks executed. DISCOVERY-ONLY: report +
    high-water + heartbeat; no placement, no $ field, no real-money action."""
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
        tick(now=now, leagues=leagues, scan_fn=scan_fn)
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
        description="Supervised Kalshi liquid-surface scanner (M17): every 1800 s "
                    "discovers the takeable Kalshi sports surface. DISCOVERY-only; no $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    p.add_argument("--leagues", default=",".join(DEFAULT_LEAGUES))
    a = p.parse_args()
    leagues = tuple(t.strip() for t in a.leagues.split(",") if t.strip()) or DEFAULT_LEAGUES
    print("kalshi_scan_runner | started interval=%ss leagues=%s component=%s"
          % (a.interval, ",".join(leagues), HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval, leagues=leagues)
    except KeyboardInterrupt:
        print("kalshi_scan_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC", "tick", "run"]
