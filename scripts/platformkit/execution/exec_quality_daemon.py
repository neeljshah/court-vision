"""scripts.platformkit.execution.exec_quality_daemon -- supervised M42 tick.

Closes the last manual-only hop in the execution-quality loop: measured CLV ->
breaker states -> digest -> webapp. Every ~120s this:

  (a) REALIZED-CLV SWEEP: ingame_realized_clv.backfill(write=True, min_age_s=...)
      -- ONE-SHOT per bet, only once its placement is old enough for every
      configured horizon (HORIZONS_S[-1]=300s) + book_replay's own lookup slack
      (SLACK_S=120s) to have had a tick land. Grading a bet earlier would
      permanently lock a sidecar row missing its longest horizon (write=True
      dedups by bet_id forever -- no second chance), so this daemon always
      passes min_age_s/now_epoch rather than calling backfill unfiltered.
  (b) DIGEST REFRESH: paper_today.build_today() -> data/frontend/paper_today.json,
      so the per-market circuit-breaker states + execution-quality block
      (paper_exec_summary.build_execution_block, reached via build_today's
      "execution" key) the webapp reads stay fresh on this daemon's faster
      cadence, between m1_bankroll's own ~600s digest writes.

PER-STEP FAILURE ISOLATION (mirrors ingame_enrichment_runner/m37): one step's
exception degrades to an {"error": str} entry for THAT step only -- it never
sinks the tick or blocks the sibling step.

MEASUREMENT ONLY: no bet/decision path touched, no flag flipped, no
data/registry/ write, no $ field, no edge claim.

Heartbeat: m42_exec_quality -> data/cache/daemon_heartbeats/m42_exec_quality.txt
Cadence: DEFAULT_INTERVAL_SEC = 120 s.
Repo-internal only; ASCII only; <=300 LOC.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      tests/platformkit/execution/test_exec_quality_daemon.py -q
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from scripts.platformkit.io_atomic import write_json_atomic

logger = logging.getLogger("exec_quality_daemon")

HEARTBEAT_COMPONENT = "m42_exec_quality"
DEFAULT_INTERVAL_SEC = 120.0

_REPO_ROOT = Path(__file__).resolve().parents[3]
TODAY_PATH = _REPO_ROOT / "data" / "frontend" / "paper_today.json"


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M42 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("exec_quality heartbeat skipped: %s", exc)


def _min_age_s() -> float:
    """Longest realized-CLV horizon + book_replay's own lookup slack -- the age
    a bet must reach before grading it can be a one-shot (see module docstring)."""
    from scripts.platformkit.clv_grading import ingame_realized_clv as CLV
    return float(max(CLV.HORIZONS_S) + CLV.SLACK_S)


def _sidecar_line_count(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return sum(1 for _ in fh)
    except (FileNotFoundError, OSError):
        return 0


def _default_grade(now_epoch: float) -> Dict[str, Any]:
    """One min-age-filtered realized-CLV grading pass. n_newly_graded is the
    sidecar line-count delta (backfill's own summary re-grades every eligible
    bet each call; only the delta reflects bets ACTUALLY new to the sidecar
    this tick). Never raises."""
    from scripts.platformkit.clv_grading import ingame_realized_clv as CLV
    before = _sidecar_line_count(CLV.SIDECAR)
    summary = CLV.backfill(write=True, min_age_s=_min_age_s(), now_epoch=now_epoch)
    summary["n_newly_graded"] = _sidecar_line_count(CLV.SIDECAR) - before
    return summary


def _default_digest() -> Dict[str, Any]:
    """Rebuild + publish the paper_today digest (placed bets + breaker states)."""
    from scripts.platformkit.paper import paper_today as _today
    doc = _today.build_today()
    write_json_atomic(TODAY_PATH, doc, encoding="ascii", sort_keys=False,
                      indent=2, default=str, trailing_newline=True)
    return doc


def _breaker_states(digest: Dict[str, Any]) -> Dict[str, str]:
    by_market = (digest.get("execution") or {}).get("by_market_type") or {}
    return {mt: d.get("state", "UNKNOWN") for mt, d in by_market.items()}


def tick(*, now: float,
        grade_fn: Optional[Callable[[float], Dict[str, Any]]] = None,
        digest_fn: Optional[Callable[[], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """One exec-quality tick: realized-CLV sweep -> digest refresh -> heartbeat.
    Never raises; each step is isolated (see module docstring)."""
    _grade = grade_fn if grade_fn is not None else _default_grade
    _digest = digest_fn if digest_fn is not None else _default_digest

    try:
        grading = _grade(now)
    except Exception as exc:  # noqa: BLE001
        logger.warning("exec_quality grading step raised: %s", exc)
        grading = {"error": str(exc), "n_newly_graded": 0}

    try:
        digest = _digest()
    except Exception as exc:  # noqa: BLE001
        logger.warning("exec_quality digest step raised: %s", exc)
        digest = {"error": str(exc)}

    _beat(now)
    return {
        "component": "exec_quality",
        "grading": grading,
        "breaker_states": _breaker_states(digest),
        "honest_note": ("measurement only; realized-CLV is a probability-point "
                        "market move, not closing-line value; no bet/decision "
                        "path touched, no flag flipped, no data/registry/ write"),
        "edge_claimed": False,
    }


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the exec-quality loop forever (or max_ticks). Never raises out.
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
        print("%s | tick=%d n_graded=%d breakers=%s" % (
            HEARTBEAT_COMPONENT, ticks, doc["grading"].get("n_newly_graded", 0),
            doc["breaker_states"]), flush=True)
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
        description="Supervised execution-quality tick (M42): one-shot "
                    "min-age-filtered realized-CLV backfill + paper_today "
                    "digest refresh, every --interval seconds. Measurement "
                    "only, no $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    a = p.parse_args()
    print("exec_quality_daemon | started interval=%ss component=%s"
          % (a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("exec_quality_daemon | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC", "TODAY_PATH", "tick", "run"]
