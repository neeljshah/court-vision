"""scripts.platformkit.improve.selfimprove_runner -- supervised P4 entry.

A thin, runnable wrapper around ``selfimprove_daemon.run_forever`` so the M9
supervisor can spawn it as ``python -u -m
scripts.platformkit.improve.selfimprove_runner`` and keep it alive,
checkpoint-resumable across restarts.

WHY a wrapper:
  * ``run_forever`` is pure glue: it REQUIRES injected ``settled_games_fn`` /
    ``recalibrate_fn`` (no real defaults, by design -- the math lives elsewhere).
    A bare ``python -m selfimprove_daemon`` is therefore not runnable. This
    runner supplies the wiring + a liveness heartbeat + a clean CLI.
  * It resumes LOSSLESSLY from data/cache/improve/checkpoint.json: the cursor
    only ever advances, so a restart never reprocesses settled games.

SAFETY: the DEFAULT wiring is MEASUREMENT-ONLY. ``_default_settled_games_fn``
returns the new-settled games discovered by the existing self-improve plumbing
when available, else an EMPTY list; ``_default_recalibrate_fn`` returns None
(NO_CANDIDATE) unless a real recalibrator module is present. With no candidate
nothing is ever shipped, no flag is flipped, no registry is written -- the loop
just advances its cycle counter + heartbeat. The real recalibrator is injected
by a caller/test (or a future wiring module) WITHOUT touching this file.

Heartbeat component: ``m4_selfimprove`` ->
data/cache/daemon_heartbeats/m4_selfimprove.txt (consumed by ops.liveness via
service_registry, so it lands in the single status.json).

INVARIANTS: never edits MEMORY.md, never writes data/registry/, never flips a
flag, calibration not edge. Stdlib + repo-internal; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence

from scripts.platformkit.improve.selfimprove_daemon import run_forever

logger = logging.getLogger("selfimprove_runner")

HEARTBEAT_COMPONENT = "m4_selfimprove"
DEFAULT_NAMES = ("nba", "mlb", "soccer", "tennis")


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the liveness heartbeat for this service. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001 -- liveness write must never sink loop
        logger.debug("selfimprove_runner heartbeat skipped: %s", exc)


def _default_settled_games_fn(name: str, *, since: Any = "",
                              seen_ids: Optional[Sequence[str]] = None,
                              **_kw) -> List[Dict[str, Any]]:
    """New settled games for ``name`` not yet folded -- AUDITED + STATE-BEARING (FIX A).

    Wired to scripts.platformkit.improve.settled_ingest.settled_games_fn (the richer
    provider that fetches+classifies the keyless-ESPN boards, runs the MF3 anti-0-fill
    audit, AND reconstructs leak-free {p0, outcome} state rows per final via
    settled_ingest.states_for_game). The earlier default delegated to the bare
    settled_finals.settled_since, which returned STATELESS game dicts -> the audit
    quarantined every one as empty_states -> FeedDegradedError -> recalibrator None ->
    perpetual NO_CANDIDATE (the gate never ran). This provider hands the recalibrator
    state-bearing games so build_candidate + the 5-gate ratchet actually RUN (ship OR
    honest reject). DEDUP is by game_id via ``seen_ids`` (the primary guard the daemon
    threads through). A dead feed / degraded batch / offseason -> [] (NO_CANDIDATE).
    NEVER raises.
    """
    try:  # the richer, state-bearing, MF3-audited provider
        from scripts.platformkit.improve import settled_ingest as _si  # type: ignore
    except Exception:  # noqa: BLE001 -- provider import failed -> safe empty
        return []
    try:
        return list(_si.settled_games_fn(name, since=str(since or ""), seen_ids=seen_ids))
    except Exception as exc:  # noqa: BLE001
        logger.debug("settled_games_fn(%s) unavailable: %s", name, exc)
        return []


def _default_recalibrate_fn(name: str, settled: Sequence[Dict[str, Any]],
                            *_a, report: Optional[Dict[str, Any]] = None,
                            **_kw) -> Optional[Dict[str, Any]]:
    """Build a gate CANDIDATE from newly settled games, or None (NO_CANDIDATE).

    Default is None: with no real recalibrator wired the loop ships nothing and
    flips no flag (measurement-only). A real recalibrator is injected by a caller
    WITHOUT editing this runner. NEVER raises.

    ``report`` (optional, threaded by the daemon): records {reason, transient} so the
    daemon advances the cursor ONLY on a GENUINE evaluated decline, never on a TRANSIENT
    failure (an import error / a recalibrator raise -> transient -> games retried).
    """
    def _mark(reason: str, transient: bool) -> None:
        if isinstance(report, dict):
            report["reason"], report["transient"] = reason, transient

    if not settled:
        _mark("empty_batch", False)
        return None
    # MF1 defense-in-depth (layer B): stay inert even if recalibrator.py is importable.
    # With the human-only PIPELINE_ENABLED sentinel absent the runner returns None BEFORE
    # the recalibrator import, so the cycle is byte-identical to the NO_CANDIDATE baseline.
    try:
        from scripts.platformkit.improve.pipeline_flag import pipeline_enabled
        if not pipeline_enabled():
            _mark("inert", False)  # inert (flag-off): daemon preserves via the inert branch
            return None
    except Exception:  # noqa: BLE001 -- flag helper missing -> fail safe (inert)
        _mark("inert", False)
        return None
    try:  # optional real recalibrator + the CLV-corpus compose bridge
        from scripts.platformkit.improve import recalibrator as _rc  # type: ignore
        from scripts.platformkit.improve.clv_corpus_inject import inject_corpus as _inject
        from scripts.platformkit.improve.recalibrate_with_corpus import (
            recalibrate_with_corpus as _rwc,
        )
    except Exception:  # noqa: BLE001 -- import failed -> TRANSIENT (retry, never skip)
        _mark("recalibrator_import_failed", True)
        return None
    try:
        # base_build closes over `report` so build_candidate's own {reason, transient}
        # notes still win (recalibrate_with_corpus itself takes no report kwarg).
        # This appends the settled-CLV close corpus (FIX SI-CLV-CORPUS-WIRE) so a
        # genuine model-beats-close window can clear the >=2-corpora rule instead of
        # every candidate staying REPLICATION_PENDING forever with corpora==[].
        return _rwc(
            name, settled,
            base_build=lambda n, s: _rc.build_candidate(n, s, report=report),
            inject=_inject,
        )
    except Exception as exc:  # noqa: BLE001 -- a raise here is TRANSIENT
        logger.debug("recalibrate_fn(%s) unavailable: %s", name, exc)
        _mark("recalibrate_exception", True)
        return None


def _beating_sleep(base_sleep: Callable[[float], None],
                   clock: Optional[Callable[[], float]]) -> Callable[[float], None]:
    """Wrap sleep so a heartbeat lands on every cycle boundary. Never raises."""
    def _sleep(seconds: float) -> None:
        now = None
        if clock is not None:
            try:
                now = float(clock())
            except Exception:  # noqa: BLE001
                now = None
        _beat(now)
        base_sleep(seconds)
    return _sleep


def run(*, names: Sequence[str] = DEFAULT_NAMES,
        settled_games_fn: Optional[Callable[..., Sequence[Dict[str, Any]]]] = None,
        recalibrate_fn: Optional[Callable[..., Optional[Dict[str, Any]]]] = None,
        interval_sec: float = 60.0,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_cycles: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None,
        ckpt_path: Optional[str] = None,
        **kwargs) -> List[Any]:
    """Run the checkpoint-resumable self-improve loop + a liveness heartbeat.

    Defaults are measurement-only (no candidate -> nothing ships). Everything is
    injectable so an offline test drives it with a fake clock/sleep, a seeded
    settled-games fn, a bounded ``max_cycles`` and an isolated ``ckpt_path``.
    Returns the list of CycleResult. NEVER raises out.
    """
    import time as _time
    base_sleep = sleep if sleep is not None else _time.sleep
    _beat()  # live before the first cycle completes
    return run_forever(
        names=tuple(names),
        settled_games_fn=settled_games_fn or _default_settled_games_fn,
        recalibrate_fn=recalibrate_fn or _default_recalibrate_fn,
        clock=clock, sleep=_beating_sleep(base_sleep, clock),
        interval_sec=float(interval_sec), max_cycles=max_cycles,
        should_stop=should_stop, ckpt_path=ckpt_path, **kwargs)


def _main() -> int:  # pragma: no cover -- thin CLI shim
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="Supervised self-improve runner (P4): checkpoint-resumable "
                    "recalibration ratchet + liveness heartbeat. Paper/measure "
                    "only -- never ships without a real recalibrator + the gate.")
    p.add_argument("--names", default=",".join(DEFAULT_NAMES),
                   help="Comma-separated sport names (default: %s)."
                        % ",".join(DEFAULT_NAMES))
    p.add_argument("--interval", type=float, default=60.0,
                   help="Seconds between cycles.")
    a = p.parse_args()
    name_list = tuple(s.strip() for s in a.names.split(",") if s.strip())
    print("selfimprove_runner | started names=%s interval=%ss component=%s"
          % (",".join(name_list), a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(names=name_list, interval_sec=a.interval)
    except KeyboardInterrupt:
        print("selfimprove_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_NAMES", "run"]
