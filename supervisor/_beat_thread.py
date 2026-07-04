"""supervisor._beat_thread -- background self-heartbeat thread (robustness fix).

ROOT CAUSE (docs/research, wave-17/wave-18 evidence, see
data/frontend/ops/api_crash_20260704_rootcause.json + logs/watchdog_autostart.log
36+ WEDGED events since 2026-06-23): Supervisor.run_forever()'s self-heartbeat
(_beat_self) only stamps ONCE PER TICK, serially AFTER supervise() returns.
supervise() probes every ProcSpec in the manifest (41 specs as of 2026-07-04);
each TCP/HTTP probe has its own _DEFAULT_TIMEOUT=2.0s (supervisor/health.py).
Under heavy fleet CPU load, several probes can each run close to their timeout
in the SAME tick, stacking serially with zero concurrency -- pushing one
supervise() pass close to or past the watchdog's staleness threshold. The
watchdog then declares the supervisor WEDGED, kills it, and reboots the WHOLE
fleet (reconcile_survivors() reaps + relaunches every spec), which is why
unrelated services (m1_api_paper, m1_api_boards, ...) appear to "crash" in
lockstep -- they are being restarted by a healthy supervisor's own reboot, not
failing independently.

PRECEDENT: this is the same class of bug fixed for m13_props_pred_tick on
2026-06-26 (see memory project_m13_flap_fix_2026_06_26): a single unit of work
(there: prop scoring; here: one supervise() tick of serial probes) can exceed
the staleness window even though the process is healthy. The fix there was a
background daemon thread that beats on a fixed cadence INDEPENDENT of the
work unit's duration. Same pattern applied here.

FIX: BeatThread stamps the supervisor's OWN liveness heartbeat on a fixed
wall-clock cadence (default 20s) via a daemon thread, decoupled from
supervise()'s duration. A slow tick (even one exceeding the watchdog's
staleness threshold) no longer starves the heartbeat -- the thread keeps
beating throughout. Combined with the raised watchdog threshold (90s -> 300s,
see watchdog_autostart.ps1), this removes the near-zero margin the rootcause
evidence identified (41 specs x up to 2.0s probe timeout = up to 82s of
serial probe time alone, before sleep/beat overhead, against a 90s cutoff).

Never spawns a NEW process, never touches data/registry/, never flips a flag.
Stdlib-only (threading), ASCII-only, <=150 LOC.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger("supervisor.supervisor")

# Cadence for the background beat. Must be comfortably below the SMALLEST
# defensible watchdog staleness threshold (300s, see watchdog_autostart.ps1)
# so a beat is never more than one interval late. 20s gives a >10x margin.
DEFAULT_BEAT_INTERVAL_SEC = 20.0


class BeatThread:
    """Daemon thread that calls *beat_fn* every *interval_sec*, forever.

    Decoupled from any caller's own work duration -- start() spawns ONE
    background thread that loops on a threading.Event.wait(timeout=interval)
    (interruptible, no busy-wait). stop() signals the event and joins with a
    bounded timeout so drain()/shutdown() never hangs on a wedged beat_fn.

    beat_fn must never raise for long-lived safety, but this thread also
    wraps each call in try/except so one bad beat never kills the thread.
    """

    def __init__(self, beat_fn: Callable[[], None],
                 interval_sec: float = DEFAULT_BEAT_INTERVAL_SEC) -> None:
        self._beat_fn = beat_fn
        self._interval = float(interval_sec)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _run(self) -> None:
        # Beat immediately on start (parity with the existing start-of-run
        # beat in run_forever) so a freshly-started thread doesn't wait a
        # full interval before the first stamp.
        while not self._stop_event.is_set():
            try:
                self._beat_fn()
            except Exception as exc:  # noqa: BLE001 -- one bad beat must not kill the thread
                logger.debug("supervisor: background beat raised %s",
                            type(exc).__name__)
            if self._stop_event.wait(timeout=self._interval):
                break

    def start(self) -> None:
        """Start the background beat loop. Idempotent (no-op if already running)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="supervisor-beat", daemon=True)
        self._thread.start()

    def stop(self, *, join_timeout: float = 2.0) -> None:
        """Signal the loop to stop and join with a bounded timeout.

        Never raises, never blocks longer than join_timeout even if beat_fn
        is (improbably) stuck -- the thread is daemon=True so a stuck join
        still lets the process exit cleanly.
        """
        self._stop_event.set()
        t = self._thread
        if t is not None:
            try:
                t.join(timeout=join_timeout)
            except Exception:  # noqa: BLE001
                pass

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


__all__ = ["BeatThread", "DEFAULT_BEAT_INTERVAL_SEC"]
