"""scripts.platformkit.bestbets.bestbets_compute_runner -- supervised M10 entry.

MEASUREMENT-ONLY daemon: every 120 s re-ranks calibrated model-vs-market
divergence cards across sports and atomically writes
data/frontend/best_bets.json so the UI / W3 bestbets board can serve them
without recomputing on each request.

HONEST RAILS:
  - UNITS not $: the output JSON carries units + tier + confidence + clv;
    it NEVER carries a dollar P&L field.
  - CALIBRATION not edge: cards are ranked calibrated divergence; no
    fabricated ROI or profit claim.
  - real-money stays default-DENY; no flag flip; no data/registry/ write.
  - Stale-never-green: a compute failure degrades to an explicit
    overall=degraded envelope; the heartbeat still advances so the
    supervisor can distinguish "alive but compute unhappy" from "dead".
  - Injectable clock/sleep/max_ticks for offline tests -- no network, no
    real sleep, bounded run.

Heartbeat component: m10_best_bets_compute ->
  data/cache/daemon_heartbeats/m10_best_bets_compute.txt

Cadence: DEFAULT_INTERVAL_SEC = 120 s.
Output : data/frontend/best_bets.json (atomic tmp+replace).

stdlib + repo-internal; ASCII only; <=300 LOC.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("bestbets_compute_runner")

HEARTBEAT_COMPONENT = "m10_best_bets_compute"

_REPO = pathlib.Path(__file__).resolve().parents[3]
_OUTPUT_PATH = _REPO / "data" / "frontend" / "best_bets.json"

DEFAULT_INTERVAL_SEC = 120.0


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the liveness heartbeat for this daemon. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("bestbets_compute_runner heartbeat skipped: %s", exc)


# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------

def _compute_cards(now: float) -> List[Dict[str, Any]]:
    """Pull best-bets cards from the W3 compute module. Returns [] on any error.

    Imports build_cards from the platformkit adapter (scripts/platformkit/bestbets/
    build_cards.py) which fans out over all sports, runs board_sanitizer and
    degenerate_guard, and returns a pre-sanitized list.  Falls back to [] on any
    failure so the daemon always degrades gracefully rather than raising.
    """
    try:
        from scripts.platformkit.bestbets.build_cards import (  # noqa: PLC0415
            build_cards,
        )
        return list(build_cards(now=now))
    except Exception as exc:  # noqa: BLE001
        logger.debug("bestbets build_cards unavailable: %s", exc)
        return []


def _make_envelope(cards: List[Dict[str, Any]], now: float, *,
                   ok: bool, note: str = "") -> Dict[str, Any]:
    """Wrap cards in a standard output envelope (never green on failure)."""
    return {
        "generated_at": now,
        "overall": "ok" if ok else "degraded",
        "honest_note": (
            "MEASUREMENT-ONLY bestbets daemon m10. "
            "Cards = ranked calibrated divergence; UNITS not $; "
            "real-money default-DENY; calibration not edge."
        ),
        "card_count": len(cards),
        "cards": cards,
        "note": note,
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
        logger.debug("bestbets_compute_runner atomic write failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Tick
# ---------------------------------------------------------------------------

# ponytail: slow ticks (offseason feeds waiting out timeouts) can exceed the
# supervisor's 300s heartbeat window, so the daemon was killed MID-TICK forever
# (observed 2026-07-15: restart #24, zero completed ticks all day). Run the
# compute in a worker thread and beat with a FRESH stamp every slice while it
# runs; past the deadline stop beating (hang detection stays honest -- the
# supervisor reaps us within its window) and publish a degraded envelope. The
# abandoned thread is daemonized/leaked; upgrade path = cancellable compute.
_BEAT_SLICE_SEC = 30.0
_COMPUTE_DEADLINE_SEC = 900.0


def tick(*, now: float,
         compute_fn: Optional[Callable[[float], List[Dict[str, Any]]]] = None,
         output_path: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    """One compute cycle: build cards -> atomic write -> heartbeat. Never raises.

    Returns the envelope that was written (degraded on compute failure or
    deadline). Beats a fresh heartbeat every _BEAT_SLICE_SEC while the compute
    runs so a slow-but-alive tick is not reaped as hung.
    """
    _compute = compute_fn if compute_fn is not None else _compute_cards
    path = output_path if output_path is not None else _OUTPUT_PATH

    result: Dict[str, Any] = {}

    def _work() -> None:
        try:
            result["cards"] = _compute(now)
        except Exception as exc:  # noqa: BLE001
            result["exc"] = exc

    worker = threading.Thread(target=_work, daemon=True,
                              name="bestbets-compute")
    worker.start()
    waited = 0.0
    while worker.is_alive() and waited < _COMPUTE_DEADLINE_SEC:
        worker.join(_BEAT_SLICE_SEC)
        waited += _BEAT_SLICE_SEC
        if worker.is_alive():
            _beat()  # fresh stamp: alive, tick still in flight

    if worker.is_alive():
        logger.debug("bestbets tick compute exceeded %ss deadline",
                     _COMPUTE_DEADLINE_SEC)
        cards: List[Dict[str, Any]] = []
        ok = False
        note = "compute_deadline"
    elif "exc" in result:
        logger.debug("bestbets tick compute raised: %s", result["exc"])
        cards = []
        ok = False
        note = type(result["exc"]).__name__
    else:
        cards = result.get("cards", [])
        ok = True
        note = ""

    envelope = _make_envelope(cards, now, ok=ok, note=note)
    _atomic_write(path, envelope)
    # Fresh stamp, NOT tick-start `now`: stamping start time made every slow
    # tick's heartbeat instantly stale on completion -> reap loop.
    _beat()
    return envelope


# ---------------------------------------------------------------------------
# Run loop
# ---------------------------------------------------------------------------

def run(*, compute_fn: Optional[Callable[[float], List[Dict[str, Any]]]] = None,
        output_path: Optional[pathlib.Path] = None,
        interval_sec: float = DEFAULT_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the best-bets compute loop forever (or max_ticks). Never raises out.

    Everything is injectable: offline tests pass a fake clock, sleep stub,
    stub compute_fn, bounded max_ticks and isolated output_path.
    Returns the number of ticks executed.

    MEASUREMENT-ONLY: writes data/frontend/best_bets.json + heartbeat ONLY.
    No flag flip, no data/registry/ write, no $ field, no real-money action.
    """
    import time as _time
    _clock = clock if clock is not None else _time.time
    _sleep = sleep if sleep is not None else _time.sleep
    ticks = 0
    # Beat at boot so the service is "live" before the first tick finishes.
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
        tick(now=now, compute_fn=compute_fn, output_path=output_path)
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
        description="Supervised best-bets compute daemon (M10): every 120 s "
                    "re-ranks calibrated model-vs-market divergence cards and "
                    "writes data/frontend/best_bets.json. MEASUREMENT-ONLY -- "
                    "UNITS not $, calibration not edge, no flag flip.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC,
                   help="Seconds between compute cycles (default: %(default)s).")
    a = p.parse_args()
    print("bestbets_compute_runner | started interval=%ss component=%s out=%s"
          % (a.interval, HEARTBEAT_COMPONENT, _OUTPUT_PATH), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("bestbets_compute_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC", "tick", "run"]
