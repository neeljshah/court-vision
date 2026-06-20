"""scripts.platformkit.autonomy.resource_governor -- fail-safe headroom gate.

A self-healing loop that keeps spawning work on a box already near its memory
ceiling is how the 15GB machine freezes (the documented pytest-freeze failure
mode: ~24 procs -> 94% RAM -> wedge). This governor is the brake: BEFORE a
heavy step (a retrain, a wide backtest, a fan-out), the loop asks the governor
``check()`` and only proceeds when there is honest headroom.

The decisive honesty property: when headroom is LOW *or UNKNOWN* the governor
returns a DISTINCT status ``DEFERRED_RESOURCE`` -- an explicit, labelled
UNDER-RUN. It is NEVER the string an honest-reject or a plateau uses, so a
deferral can never be silently misread as "the model has nothing left to learn"
or "the signal was rejected." A deferral means *we did not run*, not *we ran and
found nothing*. This keeps the calibration-not-edge rail clean: an under-run is
visible as an under-run.

Fail-safe direction: psutil is OPTIONAL. If psutil is missing, or the probe
raises, or any reading is unparseable, headroom is treated as UNKNOWN and the
governor DEFERS (under-runs) rather than charging ahead. It fails toward doing
LESS, never toward wedging the box.

Pure decision core (``decide``) is separated from the psutil probe so tests
drive every branch with synthetic readings and never touch real memory. NEVER
raises; stdlib + optional psutil; ASCII-only; <=300 LOC.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

# Status strings. PROCEED is the ONLY go-ahead. DEFERRED_RESOURCE is the
# distinct under-run -- deliberately unlike any reject/plateau verdict.
PROCEED = "PROCEED"
DEFERRED_RESOURCE = "DEFERRED_RESOURCE"

# Reason codes (for the status surface / logs).
R_OK = "headroom_ok"
R_LOW_MEM = "low_mem_headroom"
R_HIGH_CPU = "high_cpu_load"
R_UNKNOWN = "headroom_unknown"
R_PSUTIL_MISSING = "psutil_missing"

# Defaults tuned for the 15GB box: defer once free RAM drops under ~12% or the
# CPU is pinned. Conservative on purpose -- a self-healing loop must not be the
# process that pushes the box over the edge.
_DEFAULT_MIN_FREE_FRAC = 0.12
_DEFAULT_MAX_CPU_FRAC = 0.92


def decide(
    reading: Optional[Dict[str, Any]],
    *,
    min_free_frac: float = _DEFAULT_MIN_FREE_FRAC,
    max_cpu_frac: float = _DEFAULT_MAX_CPU_FRAC,
) -> Dict[str, Any]:
    """Pure decision: map a resource *reading* to PROCEED / DEFERRED_RESOURCE.

    ``reading`` keys (all optional; missing/None -> UNKNOWN -> defer):
      mem_free_frac : float in [0,1] -- fraction of RAM currently free.
      cpu_frac      : float in [0,1] -- recent CPU utilization (optional).

    Returns ``{"status", "reason", "detail"}``. UNKNOWN headroom DEFERS (fail
    safe). NEVER raises.
    """
    try:
        if not isinstance(reading, dict):
            return _defer(R_UNKNOWN, {"reading": "missing"})

        mem_free = reading.get("mem_free_frac")
        if not isinstance(mem_free, (int, float)):
            return _defer(R_UNKNOWN, {"mem_free_frac": "unparseable"})
        mem_free = float(mem_free)
        if not (0.0 <= mem_free <= 1.0):
            return _defer(R_UNKNOWN, {"mem_free_frac": mem_free})

        if mem_free < float(min_free_frac):
            return _defer(R_LOW_MEM,
                          {"mem_free_frac": round(mem_free, 4),
                           "min_free_frac": min_free_frac})

        # CPU is advisory: only gates if a valid reading is present.
        cpu = reading.get("cpu_frac")
        if isinstance(cpu, (int, float)) and 0.0 <= float(cpu) <= 1.0:
            if float(cpu) > float(max_cpu_frac):
                return _defer(R_HIGH_CPU,
                              {"cpu_frac": round(float(cpu), 4),
                               "max_cpu_frac": max_cpu_frac})

        return {"status": PROCEED, "reason": R_OK,
                "detail": {"mem_free_frac": round(mem_free, 4)}}
    except Exception:  # noqa: BLE001 -- a governor must fail safe, never crash
        return _defer(R_UNKNOWN, {"error": "decide_raised"})


def _defer(reason: str, detail: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": DEFERRED_RESOURCE, "reason": reason, "detail": detail}


def probe_reading(
    psutil_mod: Optional[Any] = None,
    *,
    cpu_interval: float = 0.0,
) -> Optional[Dict[str, Any]]:
    """Read live headroom via psutil. Returns a reading dict or None (UNKNOWN).

    psutil is OPTIONAL: pass it in (tests inject a fake), or let this import it.
    Any failure -> None so ``decide(None)`` DEFERS. ``cpu_interval`` 0.0 means a
    non-blocking CPU sample (uses the value since the last call).
    """
    mod = psutil_mod
    if mod is None:
        try:
            import psutil as mod  # type: ignore[no-redef]
        except Exception:  # noqa: BLE001 -- psutil absent -> UNKNOWN
            return None
    try:
        vm = mod.virtual_memory()
        total = float(getattr(vm, "total", 0) or 0)
        available = float(getattr(vm, "available", 0) or 0)
        if total <= 0:
            return None
        mem_free_frac = max(0.0, min(1.0, available / total))
        reading: Dict[str, Any] = {"mem_free_frac": mem_free_frac}
        try:
            cpu_pct = mod.cpu_percent(interval=cpu_interval)
            if isinstance(cpu_pct, (int, float)):
                reading["cpu_frac"] = max(0.0, min(1.0, float(cpu_pct) / 100.0))
        except Exception:  # noqa: BLE001 -- CPU optional; mem alone is enough
            pass
        return reading
    except Exception:  # noqa: BLE001
        return None


class ResourceGovernor:
    """Stateful convenience wrapper: probe + decide in one ``check()`` call."""

    def __init__(
        self,
        *,
        psutil_mod: Optional[Any] = None,
        min_free_frac: float = _DEFAULT_MIN_FREE_FRAC,
        max_cpu_frac: float = _DEFAULT_MAX_CPU_FRAC,
        probe: Optional[Callable[[], Optional[Dict[str, Any]]]] = None,
    ) -> None:
        self._min_free = float(min_free_frac)
        self._max_cpu = float(max_cpu_frac)
        if probe is not None:
            self._probe = probe
        else:
            self._probe = lambda: probe_reading(psutil_mod)
        # Surface whether psutil was even available, for honest status.
        self._psutil_seen = psutil_mod is not None

    def check(self) -> Dict[str, Any]:
        """Probe live headroom and decide. UNKNOWN -> DEFERRED_RESOURCE."""
        try:
            reading = self._probe()
        except Exception:  # noqa: BLE001
            reading = None
        if reading is None and not self._psutil_seen:
            d = _defer(R_PSUTIL_MISSING, {"psutil": "unavailable"})
            return d
        return decide(reading, min_free_frac=self._min_free,
                      max_cpu_frac=self._max_cpu)


__all__ = [
    "PROCEED",
    "DEFERRED_RESOURCE",
    "decide",
    "probe_reading",
    "ResourceGovernor",
    "R_OK",
    "R_LOW_MEM",
    "R_HIGH_CPU",
    "R_UNKNOWN",
    "R_PSUTIL_MISSING",
]
