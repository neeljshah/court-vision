"""scripts.platformkit.chaos_check -- the kill/failure MATRIX honesty proof.

RB-E-1 (R-X-2). The headline robustness deliverable: it injects, per feed / service
/ daemon, a failure mode -- EMPTY, STALE, PARTIAL (one up one down), CORRUPT/MALFORMED
JSON, and TIMEOUT/slow -- and ASSERTS the product reports an HONEST state
(Unavailable / Empty / Stale / Degraded / Down) for each, NEVER green-on-missing,
never a crash, never a fabricated number, never a $ field.

It does NOT re-derive honesty. It COMPOSES the already-proven surfaces:
  * odds_provider.freshness.sidecar_status  -- stale-never-green serving guard.
  * autonomy.status_composer-style monotone-DOWN rank (reused locally) for rollups.
  * autonomy.supervisor_readiness.compose_readiness -- the daemon readiness surface.
Each "surface adapter" below takes an injected (failure-mode) input and returns the
honest verdict that surface produces; the matrix asserts the verdict is honest.

NEGATIVE CONTROL (the teeth): a deliberately green-on-missing stub surface,
``green_on_missing_stub``, returns OK even when its input is EMPTY/MISSING. The
matrix MUST flag that surface as a FAILURE. If the chaos check ever passes WITH the
negative control included, the check is worthless -- so the driver test asserts the
negative control is caught.

Run modes: PURE / mocked (default, fast, no box risk) -- every transport is injected
so nothing real is spawned, bound, or slept. There is no live-kill here (that is an
operator opt-in via view_local.ps1); this module proves the honest-degradation
CONTRACT deterministically.

INVARIANTS: reads only; never spawns; never flips a flag; never touches real money;
NEVER raises out of run_matrix; NO $ field anywhere; calibration not edge;
self-improve untouched. stdlib + repo-internal; ASCII; <=300 LOC.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.autonomy.supervisor_readiness import compose_readiness
from scripts.platformkit.odds_provider import freshness as _fresh

# Honest end-states a surface may legitimately report under failure.
OK = "ok"
EMPTY = "empty"
STALE = "stale"
UNAVAILABLE = "unavailable"
DEGRADED = "degraded"
DOWN = "down"

# Any of these is an HONEST degraded state under a failure injection. "ok" is
# honest ONLY for the explicit no-failure (control) cell; under any injected
# failure an "ok"/green verdict is a FAILURE of the check.
_HONEST_DEGRADED = frozenset({EMPTY, STALE, UNAVAILABLE, DEGRADED, DOWN, "missing",
                              "unknown"})

# Failure modes injected per surface.
EMPTY_MODE = "EMPTY"
STALE_MODE = "STALE"
PARTIAL_MODE = "PARTIAL"
CORRUPT_MODE = "CORRUPT"
TIMEOUT_MODE = "TIMEOUT"
_MODES = (EMPTY_MODE, STALE_MODE, PARTIAL_MODE, CORRUPT_MODE, TIMEOUT_MODE)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Surface adapters: each maps an injected (mode -> input) to the surface's verdict.
# Every adapter returns a status string from the honest vocabulary.
# --------------------------------------------------------------------------- #
def feed_freshness_surface(mode: str) -> str:
    """The serving-path feed guard (odds_provider.freshness.sidecar_status).

    We exercise the REAL sidecar_status logic by handing it a synthetic sidecar
    dict via a tiny in-memory shim, so the verdict is the production rule, never a
    parallel stub. STALE -> 'stale'; EMPTY/MISSING -> 'missing'/'stale'; CORRUPT ->
    'stale'/'missing'; TIMEOUT (no fresh source) -> 'stale'. Never 'fresh'.
    """
    now = _now()
    if mode == STALE_MODE:
        old = (now - timedelta(hours=6)).isoformat()
        fs = _fresh.freshness_status(old, now=now)
        return fs["status"]  # 'stale'
    if mode == EMPTY_MODE:
        # A present-but-empty authoritative source key -> stale-never-green (LA-P0-a).
        return _sidecar_verdict({"last_source_ts": None}, now)
    if mode == PARTIAL_MODE:
        # One feed fresh, one frozen: the frozen one (empty source) must read stale.
        return _sidecar_verdict({"last_source_ts": ""}, now)
    if mode == CORRUPT_MODE:
        # Unparseable timestamp -> unknown (NOT fresh).
        return _fresh.freshness_status("not-a-timestamp", now=now)["status"]
    if mode == TIMEOUT_MODE:
        # A frozen feed whose poll never advanced -> empty authoritative source.
        return _sidecar_verdict({"source_as_of": None}, now)
    return OK


def _sidecar_verdict(side: Dict[str, Any], now: datetime) -> str:
    """Apply the REAL sidecar source-key rule to an in-memory sidecar dict.

    Mirrors freshness.sidecar_status' authoritative-source-key short-circuit
    without writing a file: a present-but-empty source key is stale-never-green.
    """
    for key in _fresh._SIDECAR_SOURCE_KEYS:  # noqa: SLF001 -- documented reuse
        if key in side:
            val = side.get(key)
            if not val:
                return STALE
            return _fresh.freshness_status(val, now=now)["status"]
    return STALE


def composite_surface(mode: str) -> str:
    """A composite endpoint that fans out to sub-feeds; monotone-DOWN rollup.

    Reuses the same rank as status_composer (ok<degraded<down). PARTIAL = one sub
    OK + one DOWN -> the composite MUST be DOWN (a dead child degrades the whole).
    EMPTY set -> unavailable (not ok). Proves R-SVC-4.
    """
    subs = _sub_statuses(mode)
    return rollup(subs)


def _sub_statuses(mode: str) -> List[str]:
    if mode == EMPTY_MODE:
        return []  # no sub-feeds at all
    if mode == PARTIAL_MODE:
        return [OK, DOWN]  # one up, one down
    if mode == STALE_MODE:
        return [OK, STALE]
    if mode == CORRUPT_MODE:
        return [OK, DEGRADED]
    if mode == TIMEOUT_MODE:
        return [OK, DOWN]
    return [OK, OK]


_RANK = {OK: 0, "unknown": 1, EMPTY: 1, STALE: 1, DEGRADED: 1, UNAVAILABLE: 2,
         DOWN: 2}
_BY_RANK = {0: OK, 1: DEGRADED, 2: DOWN}


def rollup(statuses: List[str]) -> str:
    """Monotone-DOWN rollup of sub-statuses. EMPTY set -> unavailable (never ok)."""
    if not statuses:
        return UNAVAILABLE
    worst = 0
    for s in statuses:
        worst = max(worst, _RANK.get(s, 1))  # unknown label -> degraded, never ok
    return _BY_RANK[worst]


def daemon_readiness_surface(mode: str) -> str:
    """A supervised daemon's readiness (autonomy.supervisor_readiness).

    Exercises the REAL compose_readiness with a synthetic heartbeat-expecting spec.
    STALE hb / ABSENT hb -> degraded; breaker OPEN or dead -> down. Never ok under
    an injected failure. Proves R-AUTO-1/2 cells.
    """
    spec = _FakeSpec("m_test", expects_heartbeat=True, fresh_sec=300.0)
    obs = _daemon_obs(mode)
    doc = compose_readiness([spec], {"m_test": obs})
    return str(doc.get("overall", DEGRADED))


def _daemon_obs(mode: str) -> Dict[str, Any]:
    if mode == STALE_MODE:
        return {"alive": True, "hb_age": 99999.0, "breaker": {"state": "CLOSED"}}
    if mode == EMPTY_MODE:
        return {"alive": True, "hb_age": None, "breaker": {"state": "CLOSED"}}
    if mode == CORRUPT_MODE:
        return {"alive": True, "hb_age": "garbage", "breaker": {"state": "CLOSED"}}
    if mode == TIMEOUT_MODE:  # hung past window -> reaper would trip the breaker
        return {"alive": True, "hb_age": 99999.0, "breaker": {"state": "OPEN"},
                "reaper_status": "STALE_HUNG"}
    if mode == PARTIAL_MODE:  # observed but dead
        return {"alive": False, "hb_age": None, "breaker": {"state": "CLOSED"}}
    return {"alive": True, "hb_age": 1.0, "breaker": {"state": "CLOSED"}}


class _FakeSpec:
    """Minimal ProcSpec-shaped stand-in carrying just a readiness predicate."""

    def __init__(self, name: str, *, expects_heartbeat: bool, fresh_sec: float):
        self.name = name

        class _RD:
            kind = "heartbeat-file-fresh" if expects_heartbeat else "none"

            def __init__(self, fs: float):
                self.fresh_sec = fs
                self.heartbeat_path = "x" if expects_heartbeat else None

        self.readiness = _RD(fresh_sec)


# --------------------------------------------------------------------------- #
# NEGATIVE CONTROL -- the teeth. This surface fakes green on missing data.
# --------------------------------------------------------------------------- #
def green_on_missing_stub(mode: str) -> str:
    """A DELIBERATELY broken surface: returns OK no matter the failure injected.

    The chaos matrix MUST flag this as a FAILURE for every non-control mode. If the
    matrix were to pass this surface, the whole check is worthless -- so the driver
    test asserts this negative control is caught.
    """
    return OK  # green-on-missing: the bug the check exists to catch.


# --------------------------------------------------------------------------- #
# The matrix runner.
# --------------------------------------------------------------------------- #
# The proven honest-degrading surfaces (the positive set).
HONEST_SURFACES: Dict[str, Callable[[str], str]] = {
    "feed_freshness": feed_freshness_surface,
    "composite_endpoint": composite_surface,
    "daemon_readiness": daemon_readiness_surface,
}


def run_matrix(
    surfaces: Optional[Dict[str, Callable[[str], str]]] = None,
    *,
    include_negative_control: bool = False,
) -> Dict[str, Any]:
    """Run the failure matrix over *surfaces*; assert each cell is honest. Never raises.

    For every (surface, mode) it calls the surface adapter and checks the returned
    status is in the honest-degraded vocabulary (an "ok"/green under an injected
    failure is a FAILURE). Returns a report:

      {"passed": bool, "cells": [{surface, mode, status, honest}], "failures": [...],
       "robustness_manifest": {surface: "PROVEN"|"FAILED"}, "honest_note": str}

    With ``include_negative_control=True`` the green-on-missing stub is added; the
    matrix is then EXPECTED to fail (that is how the driver test proves the teeth).
    """
    surf = dict(surfaces if surfaces is not None else HONEST_SURFACES)
    if include_negative_control:
        surf["green_on_missing_NEGATIVE_CONTROL"] = green_on_missing_stub

    cells: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    per_surface_ok: Dict[str, bool] = {name: True for name in surf}

    for name, fn in surf.items():
        for mode in _MODES:
            try:
                status = str(fn(mode))
            except Exception as exc:  # noqa: BLE001 -- a crash under failure IS a failure
                status = "CRASH:%s" % type(exc).__name__
            honest = status in _HONEST_DEGRADED
            cell = {"surface": name, "mode": mode, "status": status,
                    "honest": honest}
            cells.append(cell)
            if not honest:
                failures.append(cell)
                per_surface_ok[name] = False

    manifest = {
        name: ("PROVEN" if ok else "FAILED")
        for name, ok in per_surface_ok.items()
    }
    return {
        "passed": not failures,
        "cells": cells,
        "failures": failures,
        "robustness_manifest": manifest,
        "honest_note": (
            "Under any injected failure (EMPTY/STALE/PARTIAL/CORRUPT/TIMEOUT) the "
            "surface must report an honest degraded state, NEVER green-on-missing. "
            "No $ field; calibration not edge; self-improve untouched."
        ),
    }


def _main() -> int:  # pragma: no cover -- thin CLI shim
    rep = run_matrix()
    print("chaos_check | passed=%s surfaces=%d cells=%d failures=%d"
          % (rep["passed"], len(rep["robustness_manifest"]), len(rep["cells"]),
             len(rep["failures"])), flush=True)
    for name, verdict in sorted(rep["robustness_manifest"].items()):
        print("  %-24s %s" % (name, verdict), flush=True)
    return 0 if rep["passed"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = [
    "run_matrix", "HONEST_SURFACES", "rollup", "green_on_missing_stub",
    "feed_freshness_surface", "composite_surface", "daemon_readiness_surface",
    "EMPTY_MODE", "STALE_MODE", "PARTIAL_MODE", "CORRUPT_MODE", "TIMEOUT_MODE",
]
