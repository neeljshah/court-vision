"""scripts.platformkit.ingame.ingame_tail_multi_runner -- supervised entry point
for LANE C: cross-sport (tennis + soccer_intl / World Cup) in-play tail-band
scan + pre-registered gate + tick-latency scoreboard.

Every tick (default 21600s = 6h -- this corpus grows on daily/multi-day scales,
matching the MLB M32 cadence rationale):
  (a) ingame_tail_scan_multi.scan_all()  -> per-sport band scan, writes
      data/domains/<sport>/ingame_tail_scan.json.
  (b) ingame_tail_gate_multi.run_gate_all() -> per-sport PRE-REGISTERED forward
      gate, writes data/domains/<sport>/ingame_tail_verdict.json.
  (c) inplay_tick_latency.build_doc() -> cadence scoreboard, writes
      data/frontend/ops/inplay_tick_latency.json.
Then composes ONE ops summary doc, data/frontend/ops/ingame_tail_multi.json,
and beats the heartbeat. Each step is try/except-isolated so one failing
step never kills the tick or blocks the others from refreshing.

VERDICTS ONLY. Never wires, ships, or flips a flag for any candidate; a
CONFIRMED_FORWARD / SHIP_REVIEW verdict surfaces for a HUMAN to decide. No $
field, no flag flip, no data/registry/ write, no real-money action.

NOT YET REGISTERED IN THE SUPERVISOR STACK -- adding this ProcSpec requires a
supervisor restart to take effect; this lane only adds the entry (restart
pending, per the brief).

Heartbeat: m35_ingame_tail_multi -> data/cache/daemon_heartbeats/m35_ingame_tail_multi.txt
Cadence: DEFAULT_INTERVAL_SEC = 21600 s.
Repo-internal only; ASCII only; <=300 LOC.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_tail_multi_runner.py -q
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("ingame_tail_multi_runner")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SUMMARY_OUT = _REPO_ROOT / "data" / "frontend" / "ops" / "ingame_tail_multi.json"

HEARTBEAT_COMPONENT = "m35_ingame_tail_multi"
DEFAULT_INTERVAL_SEC = 21600.0

_SHIP_VERDICTS = frozenset({"SHIP_REVIEW", "SHIP-READY"})


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M35 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_tail_multi heartbeat skipped: %s", exc)


def _run_scan() -> Dict[str, Any]:
    """Re-run the multi-sport band scan; writes one artifact per sport.
    Returns {sport: {sport_verdict, n_games_graded, ...}}."""
    from scripts.platformkit.ingame.ingame_tail_scan_multi import scan_all, write_artifacts
    results = scan_all()
    write_artifacts(results)
    return {sport: {"sport_verdict": r.get("sport_verdict"),
                    "n_games_graded": r.get("n_games_graded", 0)}
            for sport, r in results.items()}


def _run_gate() -> List[Dict[str, Any]]:
    """Re-run the pre-registered cross-sport tail gate; each call writes its
    own data/domains/<sport>/ingame_tail_verdict.json."""
    from scripts.platformkit.ingame.ingame_tail_gate_multi import run_gate_all
    return run_gate_all()


def _run_latency() -> Dict[str, Any]:
    """Re-run the tick-latency scoreboard; writes data/frontend/ops/inplay_tick_latency.json."""
    from scripts.platformkit.ingame.inplay_tick_latency import build_doc, write_artifact
    doc = build_doc()
    write_artifact(doc)
    return {"overall_verdict": doc.get("overall_verdict"),
            "by_sport": {s: r.get("verdict") for s, r in doc.get("by_sport", {}).items()}}


def _compose(scan_summary: Dict[str, Any], gate_headlines: List[Dict[str, Any]],
            latency_summary: Dict[str, Any], now_iso: str) -> Dict[str, Any]:
    ship_review = [h["sport"] for h in gate_headlines if h.get("verdict") in _SHIP_VERDICTS]
    return {
        "component": "ingame_tail_multi", "generated_at": now_iso,
        "scan_summary": scan_summary,
        "gate_headlines": gate_headlines,
        "latency_summary": latency_summary,
        "ship_review": ship_review,
        "honest_note": ("verdicts only; wiring any winner is a human decision; no $ "
                        "edge claimed; tennis has no captured in-play ticks yet "
                        "(inplay_capture_loop.DEFAULT_SPORTS is mlb+soccer_intl only) "
                        "so its scan/gate honestly reads INSUFFICIENT_N/PENDING_FORWARD"),
        "edge_claimed": False,
    }


def tick(*, now: float,
         scan_fn: Optional[Callable[[], Dict[str, Any]]] = None,
         gate_fn: Optional[Callable[[], List[Dict[str, Any]]]] = None,
         latency_fn: Optional[Callable[[], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """One re-gating tick: scan -> gate -> latency -> composed doc -> heartbeat.
    Never raises. Each step isolated; a raising step degrades to an empty/ERROR
    entry, never kills the tick or blocks a sibling step."""
    _scan = scan_fn if scan_fn is not None else _run_scan
    _gate = gate_fn if gate_fn is not None else _run_gate
    _latency = latency_fn if latency_fn is not None else _run_latency

    try:
        scan_summary = _scan()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingame_tail_multi scan step raised: %s", exc)
        scan_summary = {"error": str(exc)}
    try:
        gate_headlines = _gate()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingame_tail_multi gate step raised: %s", exc)
        gate_headlines = [{"sport": "ALL", "verdict": "ERROR", "verdict_reason": str(exc)}]
    try:
        latency_summary = _latency()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingame_tail_multi latency step raised: %s", exc)
        latency_summary = {"overall_verdict": "ERROR", "error": str(exc)}

    now_iso = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
    doc = _compose(scan_summary, gate_headlines, latency_summary, now_iso)
    try:
        _SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
        tmp = _SUMMARY_OUT.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
        os.replace(str(tmp), str(_SUMMARY_OUT))
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingame_tail_multi summary write failed: %s", exc)
    _beat(now)
    return doc


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the re-gating loop forever (or max_ticks). Never raises out.
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
        doc = tick(now=now)
        print("%s | tick=%d ship_review=%s" % (
            HEARTBEAT_COMPONENT, ticks, ",".join(doc.get("ship_review", [])) or "none"),
            flush=True)
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
        description="Supervised cross-sport in-play tail-band scan+gate+latency (M35): "
                    "every 21600s re-runs the tennis/soccer_intl band scan, pre-registered "
                    "forward gate, and tick-latency scoreboard. Verdicts only, no $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    a = p.parse_args()
    print("ingame_tail_multi_runner | started interval=%ss component=%s"
          % (a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("ingame_tail_multi_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
