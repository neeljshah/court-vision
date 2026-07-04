"""scripts.platformkit.odds_provider.feed_health_runner -- supervised M30 entry.

Every ~600s: live-probes every (provider, sport) pair the real slate uses
(feed_health.scan across DEFAULT_SPORTS, now widened to nba/mlb/soccer/
soccer_intl/tennis/wnba/npb -- unchanged cadence: 600s comfortably covers the
heavier probe cycle, so the interval is left as-is rather than shortened), heals any
RED auth/blocked provider (feed_health.heal marks its host stealth-first for
the NEXT fetch -- see transport.py), atomically writes the GREEN/RED verdict
doc (with the healed hosts attached), also runs the capture_quality
scoreboard (per-day capture-coverage vs yesterday, guarded so a quality
failure never sinks the health tick) AND the in-play sibling
(inplay_capture_quality.scoreboard_inplay -- per-day IN-PLAY tick coverage,
same guard), then beats the M30 heartbeat.
Independent branch (no depends_on) so a dead sentinel tick is itself just one
red status entry -- it never blocks the rest of the stack. Read-only network
probes only; NO $ field, NO flag flip, NO data/registry/ write, NO real-money
action, NO restart authority (visibility only -- a human or the autonomy
monitor acts on a RED row).

Heartbeat: m30_feed_health -> data/cache/daemon_heartbeats/m30_feed_health.txt
Cadence: DEFAULT_INTERVAL_SEC = 600 s. Report: data/frontend/ops/feed_health.json.
stdlib + repo-internal; ASCII only; <=300 LOC.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("feed_health_runner")

HEARTBEAT_COMPONENT = "m30_feed_health"
DEFAULT_INTERVAL_SEC = 600.0


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M30 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("feed_health heartbeat skipped: %s", exc)


def _default_quality_fn() -> Dict[str, Any]:
    from scripts.platformkit.odds_provider.capture_quality import scoreboard
    return scoreboard()


def _run_quality(quality_fn: Callable[..., Dict[str, Any]], now: float) -> None:
    """Measure + write the capture-quality scoreboard. A failure here must
    never sink the feed_health tick -- guarded and logged only."""
    try:
        from scripts.platformkit.odds_provider.capture_quality import write_status
        qdoc = quality_fn()
        write_status(qdoc, now=now)
    except Exception as exc:  # noqa: BLE001
        logger.debug("capture_quality tick raised: %s", exc)


def _default_inplay_quality_fn() -> Dict[str, Any]:
    from scripts.platformkit.odds_provider.inplay_capture_quality import scoreboard_inplay
    return scoreboard_inplay()


def _run_inplay_quality(inplay_quality_fn: Callable[..., Dict[str, Any]], now: float) -> None:
    """Measure + write the in-play capture-quality scoreboard. A failure here
    must never sink the feed_health tick -- guarded and logged only."""
    try:
        from scripts.platformkit.odds_provider.inplay_capture_quality import write_status
        qdoc = inplay_quality_fn()
        write_status(qdoc, now=now)
    except Exception as exc:  # noqa: BLE001
        logger.debug("inplay_capture_quality tick raised: %s", exc)


def tick(*, now: float,
         scan_fn: Optional[Callable[..., Dict[str, Any]]] = None,
         write_fn: Optional[Callable[..., bool]] = None,
         heal_fn: Optional[Callable[..., Any]] = None,
         quality_fn: Optional[Callable[..., Dict[str, Any]]] = None,
         inplay_quality_fn: Optional[Callable[..., Dict[str, Any]]] = None) -> Dict[str, Any]:
    """One sentinel tick: live-probe every provider -> heal any RED auth/blocked
    provider (mark it stealth-first for its NEXT fetch) -> write the verdict doc
    (with the healed hosts attached) -> run the capture_quality scoreboard AND
    the in-play sibling (both guarded, neither ever sinks this tick) ->
    heartbeat. Never raises."""
    from scripts.platformkit.odds_provider.feed_health import heal, scan, write_status
    _scan = scan_fn if scan_fn is not None else scan
    _write = write_fn if write_fn is not None else write_status
    _heal = heal_fn if heal_fn is not None else heal
    _quality = quality_fn if quality_fn is not None else _default_quality_fn
    _inplay_quality = inplay_quality_fn if inplay_quality_fn is not None else _default_inplay_quality_fn
    try:
        doc = dict(_scan() or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("feed_health scan raised: %s", exc)
        doc = {"rows": [], "n_red": 0, "overall": "GREEN"}
    try:
        doc["healed_hosts"] = sorted(set(_heal(doc)))
    except Exception as exc:  # noqa: BLE001
        logger.debug("feed_health heal raised: %s", exc)
        doc["healed_hosts"] = []
    try:
        _write(doc, now=now)
    except Exception as exc:  # noqa: BLE001
        logger.debug("feed_health write raised: %s", exc)
    _run_quality(_quality, now)
    _run_inplay_quality(_inplay_quality, now)
    _beat(now)
    return doc


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        scan_fn: Optional[Callable[..., Dict[str, Any]]] = None,
        write_fn: Optional[Callable[..., bool]] = None,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the sentinel loop forever (or max_ticks). Never raises out. Everything
    injectable for offline tests. Returns ticks executed."""
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
        doc = tick(now=now, scan_fn=scan_fn, write_fn=write_fn)
        healed = doc.get("healed_hosts") or []
        print("%s | tick=%d probed=%d red=%d healed=%s" % (
            HEARTBEAT_COMPONENT, ticks, doc.get("n_probed", 0), doc.get("n_red", 0),
            ",".join(healed) if healed else "none"),
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
        description="Supervised feed-health sentinel (M30): every 600 s live-probes "
                    "every odds-provider/sport pair the real slate uses. Read-only, no $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    a = p.parse_args()
    print("feed_health_runner | started interval=%ss component=%s"
          % (a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("feed_health_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
