"""scripts.platformkit.clv.prop_close_capture_runner -- supervised M16 entry.

CAPTURE-ONLY daemon: every 60 s it snapshots the CURRENT two-way (Over/Under)
price of every OPEN in-game player prop into prop_close_store, then beats a
heartbeat. The LAST snapshot before a prop's market suspends becomes its closing
line -- which is what finally makes in-game props CLV-measurable, and that
captured-close corpus is the SECOND independent corpus the recalibrator needs to
ship a calibration improvement. So a faster, supervised cadence here (vs the
auto_loop's 20-min tick) directly grows both CLV coverage AND the improve loop's
data fuel.

HONEST RAILS (inherited from prop_close_capture):
  - Non-fabricating: records ONLY a real two-way price the live book actually shows
    (both Over and Under present, each decimal > 1.0). A prop with no live two-way
    (one-sided / market suspended / no game live) is simply not snapshotted -> the
    settler keeps clv_status 'no_close'. NEVER an invented close.
  - Cheap-when-idle: capture_once skips the network entirely when no in-game props
    are open, so a 60s cadence costs nothing on an empty/quiet slate.
  - PRICES not bets: writes closing-line quotes only; no placement, no $ field, no
    flag flip, no data/registry/ write, no real-money action.
  - Stale-never-green: the heartbeat advances every tick regardless of capture count.
  - Injectable clock/sleep/capture_fn/max_ticks/should_stop for offline tests.

Heartbeat: m16_prop_close_capture -> data/cache/daemon_heartbeats/m16_prop_close_capture.txt
Cadence: DEFAULT_INTERVAL_SEC = 60 s. Status: data/frontend/ops/prop_close_capture_status.json.
stdlib + repo-internal; ASCII only; <=300 LOC.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import Any, Callable, Dict, Optional, Sequence

logger = logging.getLogger("prop_close_capture_runner")

HEARTBEAT_COMPONENT = "m16_prop_close_capture"

_REPO = pathlib.Path(__file__).resolve().parents[3]
_STATUS_PATH = _REPO / "data" / "frontend" / "ops" / "prop_close_capture_status.json"

DEFAULT_INTERVAL_SEC = 60.0
# In-game two-way prop pricing exists on MLB (DraftKings live O/U); other sports
# stay un-measurable until a real two-way live feed exists for them.
DEFAULT_SPORTS = ("mlb",)


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M16 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_close_capture heartbeat skipped: %s", exc)


# ---------------------------------------------------------------------------
# Capture sweep
# ---------------------------------------------------------------------------

def _default_capture(sports: Sequence[str]) -> Dict[str, Any]:
    """Run the real two-way close-capture sweep over open in-game props. Never raises."""
    try:
        from scripts.platformkit.clv.prop_close_capture import capture_all
        return dict(capture_all(sports=tuple(sports)) or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_close_capture sweep raised: %s", exc)
        return {"by_sport": {}, "captured": 0, "error": str(exc)}


def _status_doc(result: Dict[str, Any], now: float, sports: Sequence[str]) -> Dict[str, Any]:
    """Compact, $-free status envelope for the capture sweep."""
    by_sport = result.get("by_sport", {}) or {}
    open_props = sum(int((v or {}).get("open_props", 0) or 0) for v in by_sport.values())
    no_live = sum(int((v or {}).get("no_live_price", 0) or 0) for v in by_sport.values())
    return {
        "generated_at": now,
        "component": HEARTBEAT_COMPONENT,
        "sports": list(sports),
        "captured": int(result.get("captured", 0) or 0),
        "open_props": open_props,
        "no_live_price": no_live,
        "executed": False,
        "edge_claimed": False,
        "honest_note": (
            "CAPTURE-ONLY M16. Snapshots the REAL live two-way (Over/Under) price of "
            "open in-game props into prop_close_store so they become CLV-measurable; a "
            "prop with no live two-way is simply not snapshotted (never a fabricated "
            "close). PRICES not bets; no edge, no $ field, no flag flip."
        ),
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

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
        logger.debug("prop_close_capture atomic write failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Tick
# ---------------------------------------------------------------------------

def tick(*, now: float,
         sports: Sequence[str] = DEFAULT_SPORTS,
         capture_fn: Optional[Callable[[Sequence[str]], Dict[str, Any]]] = None,
         status_path: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    """One capture tick: snapshot open in-game props' two-way price -> store ->
    atomic status write -> heartbeat. Never raises. The heartbeat advances
    regardless of capture count. capture_fn injectable for offline tests."""
    path = status_path if status_path is not None else _STATUS_PATH
    _capture = capture_fn if capture_fn is not None else _default_capture
    try:
        result = dict(_capture(sports) or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_close_capture tick raised: %s", exc)
        result = {"by_sport": {}, "captured": 0}
    doc = _status_doc(result, now, sports)
    _atomic_write(path, doc)
    _beat(now)
    return doc


# ---------------------------------------------------------------------------
# Run loop
# ---------------------------------------------------------------------------

def run(*, sports: Sequence[str] = DEFAULT_SPORTS,
        capture_fn: Optional[Callable[[Sequence[str]], Dict[str, Any]]] = None,
        status_path: Optional[pathlib.Path] = None,
        interval_sec: float = DEFAULT_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the close-capture tick loop forever (or max_ticks). Never raises out.
    Everything injectable for offline tests. Returns ticks executed. CAPTURE-ONLY:
    closing-line quotes + status + heartbeat; no placement, no flag flip, no
    data/registry/ write, no $ field, no real-money action."""
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
        tick(now=now, sports=sports, capture_fn=capture_fn, status_path=status_path)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001
            break
    return ticks


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> int:  # pragma: no cover
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="Supervised prop-close-capture daemon (M16): every 60 s snapshots "
                    "the live two-way price of open in-game props -> prop_close_store. "
                    "CAPTURE-ONLY; non-fabricating; cheap-when-idle; PRICES not $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC,
                   help="Seconds between capture sweeps (default: %(default)s).")
    p.add_argument("--sports", type=str, default=",".join(DEFAULT_SPORTS),
                   help="Comma-separated sports to capture (default: %(default)s).")
    a = p.parse_args()
    sports = tuple(s.strip() for s in a.sports.split(",") if s.strip()) or DEFAULT_SPORTS
    print("prop_close_capture_runner | started interval=%ss sports=%s component=%s"
          % (a.interval, ",".join(sports), HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval, sports=sports)
    except KeyboardInterrupt:
        print("prop_close_capture_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC", "DEFAULT_SPORTS", "tick", "run"]
