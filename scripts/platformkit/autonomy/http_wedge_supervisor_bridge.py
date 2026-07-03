"""scripts.platformkit.autonomy.http_wedge_supervisor_bridge -- WIRING NOTE.

supervisor.supervisor and supervisor._restart are BOTH already at the <=300 LOC
cap (300/300), so this reliability lane deliberately does NOT inline the
per-tick call into either file (that would violate the binding LOC rail).
Instead the m33_http_wedge_reaper ProcSpec (supervisor.stack_specs) runs the
reaper as its OWN independent supervised process --
scripts.platformkit.autonomy.http_wedge_reaper_runner -- exactly like m29
(output_freshness) and m30 (feed_health) run their sentinels as independent
branches rather than inline calls inside supervise().

This module exists only to document that decision for the next agent + hold a
tiny, OPTIONAL convenience function a future trim-and-wire pass can call from
inside supervise() once headroom is freed up in supervisor.py/_restart.py
(mirrors output_freshness.py's own documented FOLLOW-UP for
merge_freshness_into_services). NOT currently called from the live supervise()
tick. RESTART PENDING is not required for this file (it is additive-only and
imported by nothing at boot time); the NEW m33/m34 ProcSpecs DO need a
supervisor restart to pick up (see report: "restart pending").

Per-file test: covered by scripts/platformkit/autonomy/test_http_wedge_reaper.py
(the wiring-note function itself is trivial and exercised there).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


def run_one_tick_standalone(*, now: Optional[float] = None) -> List[Dict[str, Any]]:
    """Convenience: run exactly one http_wedge_reaper tick out-of-band (e.g.
    from an ad-hoc ops script or a future inline supervise() wire-up), using
    the real probes. Never raises; returns [] on any failure."""
    try:
        import time as _time
        from scripts.platformkit.autonomy.http_wedge_reaper_runner import tick
        return tick(now=float(now) if now is not None else _time.time())
    except Exception:  # noqa: BLE001
        return []


__all__ = ["run_one_tick_standalone"]
