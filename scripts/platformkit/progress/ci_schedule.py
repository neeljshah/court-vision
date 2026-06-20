"""scripts.platformkit.progress.ci_schedule -- externally-triggered one-tick entrypoint.

A tiny declarative descriptor + a `main()` that runs ONE cadence tick
(`ci_cadence.run_once`) so the cadence can be driven by an EXTERNAL scheduler (cron /
Windows Task Scheduler / the supervisor) WITHOUT a self-spawning always-on daemon.

It DOES NOT self-arm autostart: it never installs itself into any OS scheduler, never
spawns a subprocess, never writes a registry/flag/sentinel. Turning the cadence on is
a documented HUMAN/ops step. The descriptor declares the INTENDED cadence as DATA:
  * NIGHTLY      -- full A->H (finder refresh + re-gate + survivor re-check)
  * HOURLY_LIGHT -- B->H (skip the heavy finder refresh; liveness + freshness only)
Each descriptor's kinds are a SUBSET of the cadence ALLOWED_KINDS (asserted in test).

RAILS: MEASUREMENT-ONLY; never ships, flips a flag, creates the sentinel, writes
data/registry/ or MEMORY.md, or arms autostart. NO $ field. stdlib-only; ASCII;
<=300 LOC.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit.progress.ci_cadence import ALLOWED_KINDS, run_once

# Declarative cadence descriptors (DATA only -- nothing self-installs).
NIGHTLY = "NIGHTLY"
HOURLY_LIGHT = "HOURLY_LIGHT"


@dataclass(frozen=True)
class CadenceDescriptor:
    """Declarative description of one cadence (no side effects)."""
    name: str
    steps: str
    period_sec: int
    description: str
    kinds: Tuple[str, ...] = field(default_factory=tuple)


# The intended cadences. period_sec is the DECLARED interval an external scheduler
# would honor; this module never sleeps/loops on it itself.
DESCRIPTORS: Dict[str, CadenceDescriptor] = {
    NIGHTLY: CadenceDescriptor(
        name=NIGHTLY, steps="A->H",
        period_sec=24 * 3600,
        description=("nightly full cadence: refresh backlog, choose+enqueue a "
                     "measurement kind, auto-gate (INERT), re-gate grown data, "
                     "survivor re-check at wider K, append ONE progress row"),
        kinds=tuple(sorted(ALLOWED_KINDS))),
    HOURLY_LIGHT: CadenceDescriptor(
        name=HOURLY_LIGHT, steps="B->H",
        period_sec=3600,
        description=("hourly light cadence: skip the heavy finder refresh; rebuild "
                     "durable state, enqueue if due, auto-gate (INERT), append ONE "
                     "progress row -- liveness + freshness, low churn"),
        kinds=tuple(sorted(ALLOWED_KINDS))),
}


def next_run(now: Optional[float] = None, *, cadence: str = NIGHTLY) -> float:
    """PURE: epoch seconds of the next scheduled measurement for the Progress view.

    Deterministic + monotonic: the next aligned boundary strictly AFTER `now` for the
    descriptor's period. Never raises; an unknown cadence falls back to NIGHTLY.
    """
    t = float(now) if now is not None else _dt.datetime.utcnow().timestamp()
    desc = DESCRIPTORS.get(cadence) or DESCRIPTORS[NIGHTLY]
    period = float(max(1, int(desc.period_sec)))
    n_periods = int(t // period) + 1
    return n_periods * period


def describe(cadence: str = NIGHTLY) -> Dict[str, Any]:
    """Return the descriptor as a plain dict (for the Progress view). NEVER raises."""
    desc = DESCRIPTORS.get(cadence) or DESCRIPTORS[NIGHTLY]
    return {
        "name": desc.name, "steps": desc.steps, "period_sec": desc.period_sec,
        "description": desc.description, "kinds": list(desc.kinds),
        "self_arms_autostart": False,
        "note": ("externally triggered; does NOT self-arm autostart; measurement-only; "
                 "no $ / flag / registry; vs_close UNPROVEN"),
    }


def run_tick(now: Optional[float] = None, *,
             run_fn: Optional[Callable[..., Any]] = None) -> Any:
    """Run ONE cadence tick (injectable run_fn for tests). NEVER raises out."""
    fn = run_fn or run_once
    try:
        return fn(now)
    except Exception:  # noqa: BLE001 -- a cadence failure degrades, never crashes main
        return None


def main(argv: Optional[List[str]] = None, *,
         run_fn: Optional[Callable[..., Any]] = None,
         now: Optional[float] = None) -> int:
    """Externally-triggered one-tick CLI. Returns 0 (degrade-isolated). NO autostart."""
    result = run_tick(now, run_fn=run_fn)
    overall = getattr(result, "overall", "degraded") if result is not None else "degraded"
    degraded = getattr(result, "degraded", []) if result is not None else ["no_result"]
    print("ci_schedule: one tick complete | overall=%s degraded=%s | "
          "measurement-only, no $/flag/registry/autostart"
          % (overall, ",".join(degraded) if degraded else "-"), flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover -- manual external trigger
    raise SystemExit(main())


__all__ = ["main", "run_tick", "next_run", "describe", "DESCRIPTORS",
           "CadenceDescriptor", "NIGHTLY", "HOURLY_LIGHT"]
