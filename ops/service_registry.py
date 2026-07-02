"""ops.service_registry -- the OBSERVABLE service inventory for the status page.

This is the single descriptor list the health aggregator iterates over to build
status.json. It DERIVES from ``supervisor.manifest`` (the supervised process
inventory) rather than re-listing the stack, so the two never drift: every
ProcSpec becomes a ServiceDescriptor carrying the liveness component name, the
freshness source name, and a ``critical`` flag (a critical service being down
makes the whole stack "down"; a non-critical one only "degraded").

A ServiceDescriptor is pure data -- no I/O. The aggregator resolves liveness via
``ops.liveness`` and freshness via ``ops.freshness_guard`` from these names.

Mapping from a ProcSpec to its liveness component / freshness source:
  * m1_producer    -> predict_service_scheduler heartbeat / source "predict_service"
  * m6_ingame_loop -> ingame_live_loop heartbeat / source "ingame_live_loop"
  * m1_line_daemon -> source "line_daemon"
  * m1_paper       -> source "paper_loop"
  * HTTP/TCP servers (api_paper, api_boards, ui) carry no heartbeat; their
    liveness is the supervisor probe (port reachability), surfaced as fresh=None.

CRITICAL services (down => overall "down"): the producer + the Auto-API :8099.
Everything else is non-critical (down => "degraded").

INVARIANTS: <=300 LOC; ASCII only; stdlib only; never raises; no I/O at import.
Build only under ops/. Reuses supervisor.manifest -- does not re-declare the stack.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath
from typing import Dict, List, Optional

try:
    from supervisor.manifest import HEARTBEAT, ProcSpec, manifest as _manifest
except Exception:  # pragma: no cover -- isolated import fallback
    HEARTBEAT = "heartbeat-file-fresh"
    ProcSpec = object  # type: ignore[assignment,misc]

    def _manifest(profile: str = "default"):  # type: ignore[misc]
        return []


# ---------------------------------------------------------------------------
# Per-spec wiring: ProcSpec.name -> (liveness component, freshness source).
#
# AUTO-DERIVATION (so a new daemon can never silently slip through invisible):
# any heartbeat-backed ProcSpec whose readiness carries a heartbeat_path gets a
# liveness component DERIVED from that file's stem (e.g.
# data/cache/daemon_heartbeats/m7_ingame_refresh.txt -> "m7_ingame_refresh").
# That stem is exactly the key ops.liveness.liveness_snapshot uses for a
# daemon-registry heartbeat, so the aggregator can resolve liveness with zero
# hand-maintenance. The dicts below are now OVERRIDES ONLY -- they remap the
# handful of specs whose component/source name differs from the stem
# (predict_service.scheduler -> predict_service_scheduler, etc.). A None value
# explicitly forces "no heartbeat" (port-probed server).
# ---------------------------------------------------------------------------
_LIVENESS_OVERRIDE: Dict[str, Optional[str]] = {
    "m1_producer": "predict_service_scheduler",
    "m6_ingame_loop": "ingame_live_loop",
    "m1_line_daemon": "line_daemon",
    "m1_paper": "paper_loop",
    "m1_api_paper": None,
    "m1_api_boards": None,
    "m1_ui": None,
}

_FRESHNESS_SOURCE: Dict[str, Optional[str]] = {
    "m1_producer": "predict_service",
    "m6_ingame_loop": "ingame_live_loop",
    "m1_line_daemon": "line_daemon",
    "m1_paper": "paper_loop",
    "m2_inplay": "inplay_history",
    "m4_selfimprove": None,
    "m1_api_paper": None,
    "m1_api_boards": None,
    "m1_ui": None,
}


def _hb_stem(hb_path: Optional[str]) -> Optional[str]:
    """The bare component name from a heartbeat filename (stem), or None.

    Handles both posix (data/cache/.../m7_ingame_refresh.txt) and Windows
    (data\\cache\\...\\m7.txt) separators; tolerates .txt and .json suffixes.
    """
    if not hb_path:
        return None
    raw = str(hb_path).strip()
    if not raw:
        return None
    try:
        name = PureWindowsPath(raw).name if "\\" in raw else PurePosixPath(raw).name
        stem = name.rsplit(".", 1)[0] if "." in name else name
        return stem or None
    except Exception:  # noqa: BLE001
        return None


def _liveness_component(name: str, hb_path: Optional[str]) -> Optional[str]:
    """Resolve the liveness component: explicit override wins, else hb-stem."""
    if name in _LIVENESS_OVERRIDE:
        return _LIVENESS_OVERRIDE[name]
    return _hb_stem(hb_path)

# A critical service being DOWN drives overall status to "down" (not "degraded").
_CRITICAL: frozenset = frozenset({"m1_producer", "m1_api_paper"})


@dataclass(frozen=True)
class ServiceDescriptor:
    """One observable service.

    name             -- supervisor ProcSpec name (e.g. "m1_api_paper").
    critical         -- True => down makes the whole stack "down".
    liveness_component -- ops.liveness component key, or None (port-probed).
    freshness_source -- ops.freshness_guard source key, or None.
    heartbeat_path   -- the readiness heartbeat_path (when kind==HEARTBEAT).
    fresh_sec        -- the heartbeat freshness window from the readiness spec.
    port             -- listen port (None for headless loops).
    """

    name: str
    critical: bool = False
    liveness_component: Optional[str] = None
    freshness_source: Optional[str] = None
    heartbeat_path: Optional[str] = None
    fresh_sec: Optional[float] = None
    port: Optional[int] = None
    depends_on: List[str] = field(default_factory=list)


def _from_spec(spec) -> ServiceDescriptor:
    """Project one ProcSpec into a ServiceDescriptor (pure)."""
    name = getattr(spec, "name", "")
    readiness = getattr(spec, "readiness", None)
    hb_path = None
    fresh_sec = None
    if readiness is not None and getattr(readiness, "kind", None) == HEARTBEAT:
        hb_path = getattr(readiness, "heartbeat_path", None)
        fresh_sec = getattr(readiness, "fresh_sec", None)
    # Auto-derive the liveness component from the heartbeat filename stem so a
    # newly-added heartbeat daemon is observable WITHOUT touching this file; an
    # explicit override in _LIVENESS_OVERRIDE still wins where the name differs.
    liveness_component = _liveness_component(name, hb_path)
    # Freshness source: explicit map wins; else fall back to the same component
    # name (so a heartbeat daemon's staleness can drive a "stale" verdict too).
    if name in _FRESHNESS_SOURCE:
        freshness_source = _FRESHNESS_SOURCE[name]
    else:
        freshness_source = liveness_component
    return ServiceDescriptor(
        name=name,
        critical=name in _CRITICAL,
        liveness_component=liveness_component,
        freshness_source=freshness_source,
        heartbeat_path=hb_path,
        fresh_sec=fresh_sec,
        port=getattr(spec, "port", None),
        depends_on=list(getattr(spec, "depends_on", []) or []),
    )


def service_descriptors(profile: str = "default") -> List[ServiceDescriptor]:
    """Return the observable services for *profile*, in supervisor (topo) order.

    Derived from ``supervisor.manifest(profile)`` so it always mirrors the real
    supervised stack. Never raises -- an unavailable manifest yields []."""
    try:
        specs = _manifest(profile)
    except Exception:  # noqa: BLE001
        return []
    out: List[ServiceDescriptor] = []
    for spec in specs:
        try:
            out.append(_from_spec(spec))
        except Exception:  # noqa: BLE001 -- one bad spec must not sink the list
            continue
    return out


def critical_names(profile: str = "default") -> List[str]:
    """Names of the critical services in *profile* (down => overall down)."""
    return [d.name for d in service_descriptors(profile) if d.critical]


__all__ = ["ServiceDescriptor", "service_descriptors", "critical_names"]
