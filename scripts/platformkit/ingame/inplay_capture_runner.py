"""scripts.platformkit.ingame.inplay_capture_runner -- supervised in-play CAPTURE entry (W4).

A thin, runnable wrapper around ``inplay_capture_loop.serve_forever`` so the M9
supervisor can spawn it as ``python -u -m
scripts.platformkit.ingame.inplay_capture_runner`` and keep the MEASUREMENT-ONLY
in-play capture daemon alive on a cadence.

WHY a wrapper instead of the daemon's own ``__main__``:
  * The supervisor's heartbeat-fresh readiness probe reads a standard liveness
    heartbeat at data/cache/daemon_heartbeats/<component>.txt (ops.liveness). The
    capture daemon writes its OWN per-cycle JSON heartbeat (``_capture_heartbeat.json``,
    a measurement readout) but NOT a process-liveness txt heartbeat. This wrapper beats
    ``ops.liveness`` component ``m2_inplay_capture`` on every poll boundary so a hung /
    dead loop ages out as NOT-READY -- stale-never-green -- exactly like the sibling
    ``inplay_runner`` (P2) does for the in-play SNAPSHOT daemon.
  * The CLI default (``--max-ticks 1``) is a single bounded tick so an accidental bare
    invocation can never leave a daemon running; a supervised forever-run needs an
    explicit unbounded loop, which this wrapper provides (max_ticks=None).

Per-game error isolation lives INSIDE serve_forever / poll_once (one bad game never
sinks the tick, one bad tick never stops the loop); this wrapper adds only the liveness
heartbeat + a runnable forever entry. It NEVER raises out of the loop, NEVER executes
real money, NEVER flips a flag, NEVER arms autostart, NEVER writes data/registry/.
PAPER / UNITS / probability only -- NO $ field. stdlib + repo-internal; ASCII; <=300 LOC.

Heartbeat component: ``m2_inplay_capture`` ->
data/cache/daemon_heartbeats/m2_inplay_capture.txt (consumed by ops.liveness /
the supervisor heartbeat-fresh readiness probe).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_inplay_capture_runner.py -q
"""
from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional

from scripts.platformkit.ingame.inplay_capture_loop import (
    DEFAULT_SPORTS,
    IDLE_INTERVAL_SEC,
    serve_forever,
)

logger = logging.getLogger("inplay_capture_runner")

HEARTBEAT_COMPONENT = "m2_inplay_capture"

# LANE 4b (depth capture arming, follow-up wire): the REAL order-book depth
# capture callable, reusing scripts.platformkit.odds_provider.depth_capture.
# run_capture_pass AS-IS (no rewrite). Constructed here (not merely
# depth_capture=True) so this production entry point owns the exact call
# shape it wants (max_tickers_per_sport bound) independent of the loop
# module's own internal default. FAIL-OPEN: any exception -- import error,
# network failure, malformed return -- is caught by the loop's own
# _maybe_capture_depth wrapper (scripts/platformkit/ingame/
# inplay_capture_loop.py) before it can reach poll_once/serve_forever; this
# function adds no additional try/except because the hook already guarantees
# the host cycle is unaffected. DATA CAPTURE ONLY: no model, no gate, no edge
# framing -- an accrual asset for future liquidity/venue-calibration studies.
def _depth_capture_fn(sports: List[str]) -> Any:
    """The real depth-capture callable: odds_provider.depth_capture.run_capture_pass.

    Bounded per-sport (max_tickers_per_sport) so one slate can never balloon a
    tick's cost. Any failure surfaces to the loop's fail-open hook, not here.
    """
    from scripts.platformkit.odds_provider import depth_capture as _dc
    return _dc.run_capture_pass(list(sports), max_tickers_per_sport=50)


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the liveness heartbeat for this service. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001 -- liveness write must never sink loop
        logger.debug("inplay_capture_runner heartbeat skipped: %s", exc)


def _heartbeat_sleep(
    base_sleep: Callable[[float], None],
    *,
    clock: Optional[Callable[[], float]] = None,
) -> Callable[[float], None]:
    """Wrap a sleep callable so a heartbeat is written on every wake boundary.

    serve_forever calls ``sleep(wait)`` once per poll tick; beating right before the
    sleep refreshes the heartbeat at the poll cadence (fast while live, idle otherwise).
    Beating never raises and never blocks the real sleep.
    """
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


def run(*, sports: Optional[List[str]] = None,
        interval: Optional[float] = None,
        sleep: Optional[Callable[[float], None]] = None,
        clock: Optional[Callable[[], float]] = None,
        max_ticks: Optional[int] = None,
        **kwargs: Any) -> int:
    """Run the in-play CAPTURE loop with a liveness heartbeat. Never raises out.

    All daemon knobs (``live_state_fn`` / ``model_fn`` / ``inplay_fetch_fn`` /
    ``finals_fn`` / ``grade_dir`` / ``ledger_path`` / ``heartbeat_path``) pass straight
    through via **kwargs so an offline test drives it with fakes + a bounded ``max_ticks``
    and NO network / NO real sleep. Returns the number of ticks run.

    MEASUREMENT-ONLY: each tick captures (model, devigged-price) pairs, paper-decides in
    UNITS (executed=False), and stamps held-out FINAL labels. It flips no flag, registers
    no autostart, writes no registry, touches no real money.
    """
    import time as _time
    base_sleep = sleep if sleep is not None else _time.sleep
    # Beat once at boot so the service is "live" before the first poll completes.
    _beat()
    wrapped_sleep = _heartbeat_sleep(base_sleep, clock=clock)
    # PRODUCTION default: enrich the captured MLB series with the authoritative statsapi
    # base-out state (resolver maps the Kalshi ticker -> gamePk -> linescore).  LAZY, so a
    # dead-feed / offline test tick makes NO network call; a test can still inject
    # mlb_deep=False or an offline deep_state_fn via **kwargs to override.
    kwargs.setdefault("mlb_deep", True)
    # PRODUCTION default (mirrors mlb_deep): enrich the captured KBO series with the
    # capture-only relay state row (kbo_capture_wire ticker->alias->matcher->relay chain).
    # LAZY + fail-open, same discipline as mlb_deep -- a test can still inject
    # kbo_deep=False or an offline kbo_deep_state_fn via **kwargs to override.
    kwargs.setdefault("kbo_deep", True)
    # PRODUCTION default (LANE 4b arming): thread the REAL order-book depth
    # capture callable through to serve_forever/poll_once at its own slower
    # cadence (DEPTH_CAPTURE_EVERY_N_TICKS). setdefault so a test/offline
    # caller can still inject depth_capture_fn=None (or its own stub) via
    # **kwargs to opt out -- exactly the mlb_deep/kbo_deep pattern above.
    # FAIL-OPEN is guaranteed inside the loop's own _maybe_capture_depth
    # wrapper, not here.
    kwargs.setdefault("depth_capture_fn", _depth_capture_fn)
    return serve_forever(
        interval=interval,
        clock=wrapped_sleep,
        max_ticks=max_ticks,
        sports=list(sports) if sports else None,
        **kwargs)


def _main() -> int:  # pragma: no cover -- thin CLI shim
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="Supervised in-play CAPTURE runner (W4): per live game per tick "
                    "captures (model,devigged-price) pairs + paper UNIT decisions + "
                    "settle labels, and beats a liveness heartbeat. MEASUREMENT-ONLY -- "
                    "paper, no $, no flag flip, no autostart.")
    p.add_argument("--sports", default=",".join(DEFAULT_SPORTS),
                   help="Comma-separated sport ids (default: %s)." % ",".join(DEFAULT_SPORTS))
    p.add_argument("--interval", type=float, default=None,
                   help="Poll interval (s); default = phase-aware (live/idle).")
    a = p.parse_args()
    sport_list = [s.strip() for s in a.sports.split(",") if s.strip()]
    print("inplay_capture_runner | started sports=%s component=%s idle_interval=%ss "
          "(measurement-only, paper, no $/flag/autostart)"
          % (",".join(sport_list), HEARTBEAT_COMPONENT, IDLE_INTERVAL_SEC), flush=True)
    try:
        run(sports=sport_list, interval=a.interval)
    except KeyboardInterrupt:
        print("inplay_capture_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "run"]
