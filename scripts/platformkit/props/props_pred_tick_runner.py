"""scripts.platformkit.props.props_pred_tick_runner -- supervised M13 entry.

MEASUREMENT-ONLY daemon: every 300 s re-scores available prop lines against
the calibrated domain pricer and atomically writes
data/frontend/props_snapshot.json.

HONEST RAILS:
  - UNITS not $: output rows carry p_over/p_under + proj_mean + proj_sigma +
    tier + confidence. NEVER a dollar P&L field.
  - UNAVAILABLE when no prop lines are available (NBA offseason, no keyless
    DK/FD NBA prop feed, PrizePicks/Underdog empty). The snapshot degrades
    to card_count=0 + overall=UNAVAILABLE rather than fabricating cards.
  - CALIBRATION not edge: cards are P(over/under) from the leak-free domain
    pricer. No fabricated ROI or profit claim.
  - No flag flip; no data/registry/ write; no real-money action.
  - Stale-never-green: a pricer failure degrades to UNAVAILABLE envelope;
    heartbeat still advances.
  - Injectable clock/sleep/score_fn/max_ticks for offline tests.

Heartbeat component: m13_props_pred_tick ->
  data/cache/daemon_heartbeats/m13_props_pred_tick.txt

Cadence: DEFAULT_INTERVAL_SEC = 300 s.
Output : data/frontend/props_snapshot.json (atomic tmp+replace).

stdlib + repo-internal; ASCII only; <=300 LOC.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("props_pred_tick_runner")

HEARTBEAT_COMPONENT = "m13_props_pred_tick"

_REPO = pathlib.Path(__file__).resolve().parents[3]
_OUTPUT_PATH = _REPO / "data" / "frontend" / "props_snapshot.json"

DEFAULT_INTERVAL_SEC = 300.0


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M13 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("props_pred_tick heartbeat skipped: %s", exc)


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------

def _score_props(now: float) -> List[Dict[str, Any]]:
    """Re-score available prop lines via the W2 prop_surface module.

    Returns [] (UNAVAILABLE) when no lines are available (offseason) or
    when the prop_surface module is not yet built. Never raises.
    Each row must NOT carry a dollar P&L field.
    """
    try:
        from predict_service.prop_surface import build_prop_rows  # type: ignore
        rows = list(build_prop_rows(now=now))
        # Safety: strip any dollar P&L field
        return [{k: v for k, v in r.items()
                 if k not in ("dollar_pnl", "pnl_usd")} for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.debug("props_pred_tick build_prop_rows unavailable: %s", exc)
        return []


def _make_envelope(rows: List[Dict[str, Any]], now: float, *,
                   ok: bool) -> Dict[str, Any]:
    """Wrap prop rows in a standard output envelope."""
    overall = "ok" if (ok and rows) else ("UNAVAILABLE" if not rows else "degraded")
    return {
        "generated_at": now,
        "overall": overall,
        "card_count": len(rows),
        "rows": rows,
        "honest_note": (
            "MEASUREMENT-ONLY props_pred_tick M13. "
            "Rows = calibrated P(over/under) from leak-free domain pricer; "
            "UNITS not $; UNAVAILABLE when no prop lines (offseason). "
            "calibration not edge."
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
        logger.debug("props_pred_tick atomic write failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Tick
# ---------------------------------------------------------------------------

def tick(*, now: float,
         score_fn: Optional[Callable[[float], List[Dict[str, Any]]]] = None,
         output_path: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    """One props tick: score lines -> atomic write -> heartbeat. Never raises.

    Returns the envelope that was written. UNAVAILABLE when no prop lines.
    Heartbeat advances regardless of score success/failure.
    """
    _score = score_fn if score_fn is not None else _score_props
    path = output_path if output_path is not None else _OUTPUT_PATH

    try:
        rows = _score(now)
        ok = True
    except Exception as exc:  # noqa: BLE001
        logger.debug("props_pred_tick score raised: %s", exc)
        rows = []
        ok = False

    envelope = _make_envelope(rows, now, ok=ok)
    _atomic_write(path, envelope)
    _beat(now)
    return envelope


# ---------------------------------------------------------------------------
# Run loop
# ---------------------------------------------------------------------------

def run(*, score_fn: Optional[Callable[[float], List[Dict[str, Any]]]] = None,
        output_path: Optional[pathlib.Path] = None,
        interval_sec: float = DEFAULT_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the props prediction tick loop forever (or max_ticks). Never raises out.

    Everything injectable for offline tests. Returns number of ticks executed.

    MEASUREMENT-ONLY: writes props_snapshot.json + heartbeat ONLY.
    No flag flip, no data/registry/ write, no $ field, no real-money action.
    """
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
        tick(now=now, score_fn=score_fn, output_path=output_path)
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
        description="Supervised props prediction tick daemon (M13): every "
                    "300 s re-scores prop lines and writes "
                    "data/frontend/props_snapshot.json. MEASUREMENT-ONLY -- "
                    "UNAVAILABLE in offseason, UNITS not $, no flag flip.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC,
                   help="Seconds between ticks (default: %(default)s).")
    a = p.parse_args()
    print("props_pred_tick_runner | started interval=%ss component=%s out=%s"
          % (a.interval, HEARTBEAT_COMPONENT, _OUTPUT_PATH), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("props_pred_tick_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC", "tick", "run"]
