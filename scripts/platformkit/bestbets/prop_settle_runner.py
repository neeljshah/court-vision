"""scripts.platformkit.bestbets.prop_settle_runner -- supervised M15 entry.

SETTLE-ONLY paper daemon: every 900 s it sweeps the OPEN player-prop rows in the
unified units ledger (clv_ledger.jsonl) and settles each one whose REAL post-game
stat is resolvable (MLB via statsapi, soccer via keyless ESPN), then beats a
heartbeat. This is the missing settle arm: m13 PLACES props, nothing SETTLED them,
so the CLV-yardstick ledger stalled with a growing open backlog.

HONEST RAILS (inherited from prop_settler.settle_open_props):
  - PAPER-only: executed=False on every settlement; no real-money action.
  - UNITS not $: a settled row carries unit_result at the taken price; NEVER a $/ROI field.
  - NEVER fabricated: a prop whose stat is unavailable (not final / player not found /
    network) stays PENDING. Idempotent -- an already-settled twin is skipped.
  - No edge claim, no flag flip, no data/registry/ write, no autostart.
  - Stale-never-green: the heartbeat advances every tick regardless of how many settled.
  - Injectable clock/sleep/settle_fn/max_ticks/should_stop for offline tests.

Heartbeat: m15_prop_settle -> data/cache/daemon_heartbeats/m15_prop_settle.txt
Cadence: DEFAULT_INTERVAL_SEC = 900 s. Status: data/frontend/ops/prop_settle_status.json.
stdlib + repo-internal; ASCII only; <=300 LOC.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("prop_settle_runner")

HEARTBEAT_COMPONENT = "m15_prop_settle"

_REPO = pathlib.Path(__file__).resolve().parents[3]
_STATUS_PATH = _REPO / "data" / "frontend" / "ops" / "prop_settle_status.json"

DEFAULT_INTERVAL_SEC = 900.0


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M15 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_settle heartbeat skipped: %s", exc)


# ---------------------------------------------------------------------------
# Settle sweep
# ---------------------------------------------------------------------------

def _default_settle() -> Dict[str, Any]:
    """Run the real OPEN-prop settlement sweep over clv_ledger.jsonl. Never raises."""
    try:
        from scripts.platformkit.bestbets.prop_settler import settle_open_props
        return dict(settle_open_props() or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_settle sweep raised: %s", exc)
        return {"n_open_props": 0, "n_settled_now": 0, "n_pending": 0,
                "settled": [], "pending": [], "error": str(exc)}


def _status_doc(result: Dict[str, Any], now: float) -> Dict[str, Any]:
    """Compact, $-free status envelope (the giant settled/pending lists are dropped)."""
    return {
        "generated_at": now,
        "component": HEARTBEAT_COMPONENT,
        "n_open_props": int(result.get("n_open_props", 0) or 0),
        "n_settled_now": int(result.get("n_settled_now", 0) or 0),
        "n_pending": int(result.get("n_pending", 0) or 0),
        "executed": False,
        "edge_claimed": False,
        "honest_note": (
            "SETTLE-ONLY M15. Settles OPEN player props on the REAL post-game stat "
            "(UNITS at the taken price) into clv_ledger.jsonl; unresolvable props stay "
            "PENDING (never fabricated). PAPER-only, executed=False; no edge, no $ field, "
            "no flag flip."
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
        logger.debug("prop_settle atomic write failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Tick
# ---------------------------------------------------------------------------

def tick(*, now: float,
         settle_fn: Optional[Callable[[], Dict[str, Any]]] = None,
         status_path: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    """One settle tick: sweep OPEN props -> settle the resolvable -> atomic status
    write -> heartbeat. Never raises. The heartbeat advances regardless of how many
    settled. settle_fn injectable for offline tests."""
    path = status_path if status_path is not None else _STATUS_PATH
    _settle = settle_fn if settle_fn is not None else _default_settle
    try:
        result = dict(_settle() or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_settle tick settle raised: %s", exc)
        result = {"n_open_props": 0, "n_settled_now": 0, "n_pending": 0}
    doc = _status_doc(result, now)
    _atomic_write(path, doc)
    _beat(now)
    return doc


# ---------------------------------------------------------------------------
# Run loop
# ---------------------------------------------------------------------------

def run(*, settle_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        status_path: Optional[pathlib.Path] = None,
        interval_sec: float = DEFAULT_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the prop-settle tick loop forever (or max_ticks). Never raises out.
    Everything injectable for offline tests. Returns ticks executed. SETTLE-ONLY,
    PAPER-only: clv_ledger settlements + status + heartbeat; no flag flip, no
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
        tick(now=now, settle_fn=settle_fn, status_path=status_path)
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
        description="Supervised prop-settle daemon (M15): every 900 s settles OPEN "
                    "player props on the REAL post-game stat -> clv_ledger.jsonl. "
                    "PAPER-only; unresolvable props stay PENDING; UNITS not $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC,
                   help="Seconds between settle sweeps (default: %(default)s).")
    a = p.parse_args()
    print("prop_settle_runner | started interval=%ss component=%s status=%s"
          % (a.interval, HEARTBEAT_COMPONENT, _STATUS_PATH), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("prop_settle_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC", "tick", "run"]
