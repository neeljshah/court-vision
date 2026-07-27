"""supervisor.manifest -- the supervised process INVENTORY + readiness probes.

Describes (does NOT spawn) the real always-on stack that boot.ps1 launches:
producer/scheduler, Auto-API :8099, boards API :8098, UI :3000, paper loop,
line daemon, and the in-game live_loop. Each process is a ``ProcSpec`` carrying
its launch shape, an optional listen port, its ``depends_on`` edges, a readiness
probe spec, a restart policy, and env.

``manifest(profile="default")`` returns an ordered, DAG-validated list. The
ordering is a topological sort of ``depends_on`` (so a dependency always boots
before its dependents). A cyclic ``depends_on`` graph is a CONFIG error and
raises :class:`CycleError` -- this is intentional and tested.

Sport-blind: nothing here imports a sport adapter. Readiness paths reuse the
real on-disk heartbeats (predict_service / ingame ``_heartbeat.json``).

Design rules: stdlib-only, ASCII-only, <=300 LOC, no process is spawned, no
flag is flipped, ``data/registry/`` is never written.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

# Readiness probe kinds.
TCP = "tcp-port-open"
HTTP = "http-200"
HEARTBEAT = "heartbeat-file-fresh"
NONE = "none"
_PROBE_KINDS = frozenset({TCP, HTTP, HEARTBEAT, NONE})


class CycleError(ValueError):
    """Raised when a manifest's depends_on graph contains a cycle (config error)."""


@dataclass(frozen=True)
class RestartPolicy:
    """Auto-restart envelope: capped exponential backoff between relaunches.

    backoff(attempt) = min(cap, base * 2**(attempt-1)); attempt is 1-based.
    A ``max_retries`` of None means "retry forever" (the always-on default for
    long-lived loops); a positive int caps relaunch attempts before giving up.
    """

    max_retries: Optional[int] = None
    backoff_base_sec: float = 2.0
    backoff_cap_sec: float = 60.0

    def backoff_for(self, attempt: int) -> float:
        """Backoff (seconds) before the *attempt*-th relaunch (1-based)."""
        if attempt < 1:
            return 0.0
        delay = self.backoff_base_sec * (2.0 ** (attempt - 1))
        return float(min(self.backoff_cap_sec, delay))

    def exhausted(self, attempts: int) -> bool:
        """True if *attempts* relaunches have hit the retry cap."""
        return self.max_retries is not None and attempts >= self.max_retries


@dataclass(frozen=True)
class ReadinessSpec:
    """How to decide a process is READY (not merely alive).

    kind == TCP        -> port must accept a connection.
    kind == HTTP       -> http_path must return 200 (on ``port``).
    kind == HEARTBEAT  -> heartbeat_path mtime/updated_at within fresh_sec.
    kind == NONE       -> ready as soon as the process is alive.
    """

    kind: str = NONE
    http_path: Optional[str] = None
    heartbeat_path: Optional[str] = None
    fresh_sec: float = 120.0

    def __post_init__(self) -> None:
        if self.kind not in _PROBE_KINDS:
            raise ValueError(
                "unknown readiness kind %r (expected one of %s)"
                % (self.kind, sorted(_PROBE_KINDS))
            )


@dataclass(frozen=True)
class ProcSpec:
    """One supervised process.

    kind        -- "py" (python -u -m module) or "node" (npm run dev in cwd).
    module      -- python module for kind=="py" (e.g. predict_service.app).
    cmd         -- raw command for kind=="node" (e.g. "npm run dev").
    argv        -- extra CLI args.
    port        -- listen port (None for headless loops).
    depends_on  -- names that must be READY before this one boots.
    readiness   -- ReadinessSpec.
    restart_policy -- RestartPolicy.
    env         -- extra environment for the child.
    cwd         -- working dir override (UI runs in court-visions).
    """

    name: str
    kind: str
    module: Optional[str] = None
    cmd: Optional[str] = None
    argv: List[str] = field(default_factory=list)
    port: Optional[int] = None
    depends_on: List[str] = field(default_factory=list)
    readiness: ReadinessSpec = field(default_factory=ReadinessSpec)
    restart_policy: RestartPolicy = field(default_factory=RestartPolicy)
    env: Dict[str, str] = field(default_factory=dict)
    cwd: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind not in ("py", "node"):
            raise ValueError("ProcSpec.kind must be 'py' or 'node', got %r" % self.kind)
        if self.kind == "py" and not self.module:
            raise ValueError("py ProcSpec %r requires a module" % self.name)
        if self.kind == "node" and not self.cmd:
            raise ValueError("node ProcSpec %r requires a cmd" % self.name)


# --------------------------------------------------------------------------- #
# DAG validation + topological order
# --------------------------------------------------------------------------- #
def topo_order(specs: List[ProcSpec]) -> List[ProcSpec]:
    """Return *specs* in dependency order (deps first). Stable on insertion order.

    Raises :class:`CycleError` if depends_on forms a cycle, or if a depends_on
    name is unknown (also a config error). Uses Kahn's algorithm; ties broken by
    the original manifest order so boot output is deterministic.
    """
    by_name: Dict[str, ProcSpec] = {}
    for s in specs:
        if s.name in by_name:
            raise CycleError("duplicate ProcSpec name %r" % s.name)
        by_name[s.name] = s

    indeg: Dict[str, int] = {s.name: 0 for s in specs}
    deps_of: Dict[str, List[str]] = {}
    for s in specs:
        deps = list(s.depends_on)
        for d in deps:
            if d not in by_name:
                raise CycleError(
                    "ProcSpec %r depends_on unknown %r" % (s.name, d)
                )
        deps_of[s.name] = deps
        indeg[s.name] = len(deps)

    order_index = {s.name: i for i, s in enumerate(specs)}
    ready = sorted((n for n, d in indeg.items() if d == 0), key=order_index.get)
    out: List[str] = []
    while ready:
        n = ready.pop(0)
        out.append(n)
        for s in specs:  # any spec that depended on n
            if n in deps_of[s.name]:
                indeg[s.name] -= 1
                if indeg[s.name] == 0:
                    # insert keeping original order among the newly-ready
                    ins = order_index[s.name]
                    lo, hi = 0, len(ready)
                    while lo < hi:
                        mid = (lo + hi) // 2
                        if order_index[ready[mid]] < ins:
                            lo = mid + 1
                        else:
                            hi = mid
                    ready.insert(lo, s.name)

    if len(out) != len(specs):
        cyclic = sorted(set(by_name) - set(out))
        raise CycleError("depends_on cycle among: %s" % ", ".join(cyclic))
    return [by_name[n] for n in out]


# --------------------------------------------------------------------------- #
# The real stack inventory (the DATA table) now lives in supervisor.stack_specs;
# importing base_specs() keeps this file under the <=300 LOC rail. Imported lazily
# inside manifest() to avoid an import cycle (stack_specs imports ProcSpec etc.
# from here).
# --------------------------------------------------------------------------- #
def manifest(
    profile: str = "default",
    services: Optional[List[str]] = None,
) -> List[ProcSpec]:
    """Ordered, DAG-validated ProcSpec list for *profile*.

    Profiles:
      "default" -- the full stack (with the Next.js UI).
      "backend" -- the same stack MINUS the UI node process (headless servers).
      "paper"   -- headless like "backend", and normally paired with a
                   *services* allowlist (see config/boot/paper.json).

    *services*, when given, is a NAME ALLOWLIST: only those ProcSpecs survive.
    An unknown name, or a kept spec whose depends_on names a DROPPED spec, is a
    CONFIG error and raises ValueError -- silently stripping the edge would boot
    a dependent without its dependency (e.g. m1_paper without m1_api_paper).

    An unknown profile falls back to "default" (never crashes). The returned
    list is topologically ordered; a cyclic config raises :class:`CycleError`.
    """
    from supervisor.stack_specs import base_specs  # local import: avoid cycle

    specs = base_specs()
    prof = (profile or "default").strip().lower()
    if prof in ("backend", "paper"):
        specs = [s for s in specs if s.kind != "node"]
        # drop the UI from any depends_on edge so the DAG stays well-formed.
        specs = [
            replace(s, depends_on=[d for d in s.depends_on if d != "m1_ui"])
            for s in specs
        ]
    if services:
        keep = list(dict.fromkeys(services))  # de-dupe, keep order
        known = {s.name for s in specs}
        unknown = [n for n in keep if n not in known]
        if unknown:
            raise ValueError(
                "boot profile services names unknown spec(s): %s"
                % ", ".join(sorted(unknown))
            )
        kept = set(keep)
        specs = [s for s in specs if s.name in kept]
        for s in specs:
            missing = [d for d in s.depends_on if d not in kept]
            if missing:
                raise ValueError(
                    "boot profile services keeps %r but drops its depends_on: %s"
                    % (s.name, ", ".join(missing))
                )
    return topo_order(specs)
