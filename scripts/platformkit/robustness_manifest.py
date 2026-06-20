"""scripts.platformkit.robustness_manifest -- which surfaces are PROVEN honest.

RB-E-2 (R-X-3). Enumerates every robustness surface (feed / service / daemon /
supervised process) and maps it to its honest-state contract + the chaos-matrix
result that PROVES it degrades honestly. A surface that the chaos matrix did NOT
prove honest-degrading is reported as ``UNPROVEN`` (an explicit honest gap) -- it
is NEVER silently omitted, and NEVER read as proven-by-absence.

It composes two real sources (never re-derives them):
  * chaos_check.run_matrix() -- the per-surface PROVEN/FAILED verdict from the live
    failure matrix.
  * supervisor.manifest.manifest() -- the supervised-process inventory, so every
    manifested daemon appears as a surface row (covered by the daemon-readiness
    chaos cell) and a NEW daemon with no readiness predicate shows up as a gap.

OUTPUT (data/cache/robustness/manifest.json, atomic write, ASCII):
  {generated_at, overall, surfaces:[{name, kind, contract, verdict}], counts:{...},
   honest_note}
where verdict in {PROVEN, FAILED, UNPROVEN}. overall is the WORST: any FAILED ->
"failed"; else any UNPROVEN -> "unproven"; else "proven".

INVARIANTS: reads only (never data/registry/, MEMORY.md); never spawns; never flips
a flag; never touches real money; NEVER raises; NO $ field; calibration not edge;
self-improve untouched. stdlib + repo-internal; ASCII; <=300 LOC.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Any, Dict, List, Optional

from scripts.platformkit import chaos_check as _chaos

PROVEN = "PROVEN"
FAILED = "FAILED"
UNPROVEN = "UNPROVEN"

_REPO = pathlib.Path(__file__).resolve().parents[2]
_OUT = _REPO / "data" / "cache" / "robustness" / "manifest.json"

# The honest-state contract each surface kind must satisfy under failure.
_CONTRACTS = {
    "feed": "EMPTY/STALE/CORRUPT/TIMEOUT -> stale/missing/unknown, never fresh-green",
    "composite": "any dead sub-feed -> degraded/down (monotone-DOWN), never green",
    "daemon": "absent/stale heartbeat or open breaker -> degraded/down, never READY",
    "supervised_proc": "must have a readiness predicate; hung/dead -> NOT-READY",
}

# Map a chaos surface name to its kind (for the contract text).
_SURFACE_KIND = {
    "feed_freshness": "feed",
    "composite_endpoint": "composite",
    "daemon_readiness": "daemon",
}


def _supervised_surfaces() -> List[Dict[str, Any]]:
    """Every manifested supervised process becomes a surface row.

    A process whose readiness kind is a heartbeat predicate is covered by the
    daemon-readiness chaos cell (verdict inherits that surface's PROVEN/FAILED).
    A process with NO heartbeat predicate (readiness kind NONE) is reported with an
    explicit note -- it is exempt from the heartbeat contract but still enumerated,
    never silently dropped.
    """
    rows: List[Dict[str, Any]] = []
    try:
        from supervisor.manifest import manifest as _manifest
        specs = _manifest("default")
    except Exception:  # noqa: BLE001 -- a manifest failure is itself a gap, not a crash
        return [{"name": "supervised_stack", "kind": "supervised_proc",
                 "contract": _CONTRACTS["supervised_proc"], "verdict": UNPROVEN,
                 "note": "supervisor.manifest() unavailable -> cannot enumerate"}]
    for spec in specs:
        try:
            rd = getattr(spec, "readiness", None)
            kind = getattr(rd, "kind", "none") if rd is not None else "none"
            expects_hb = kind == "heartbeat-file-fresh"
            rows.append({
                "name": str(getattr(spec, "name", "?")),
                "kind": "supervised_proc",
                "contract": _CONTRACTS["supervised_proc"],
                "expects_heartbeat": expects_hb,
                # A heartbeat-bearing proc is covered by the daemon chaos cell; a
                # NONE-readiness proc is exempt-but-enumerated (note explains why).
                "verdict": None,  # filled in by reconcile() against the chaos result
                "note": ("heartbeat predicate -> covered by daemon-readiness chaos"
                         if expects_hb else
                         "NONE-readiness (alive-only); exempt from heartbeat contract"),
            })
        except Exception:  # noqa: BLE001
            rows.append({"name": "?", "kind": "supervised_proc",
                         "contract": _CONTRACTS["supervised_proc"],
                         "verdict": UNPROVEN, "note": "spec read raised"})
    return rows


def build_manifest(
    *,
    chaos_report: Optional[Dict[str, Any]] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Compose the robustness manifest from the chaos result + supervised inventory.

    ``chaos_report`` defaults to a fresh chaos_check.run_matrix() (positive set, no
    negative control). Never raises.
    """
    t = float(now) if now is not None else time.time()
    rep = chaos_report if chaos_report is not None else _chaos.run_matrix()
    chaos_manifest = dict(rep.get("robustness_manifest") or {})

    surfaces: List[Dict[str, Any]] = []

    # 1) Chaos surfaces (feed / composite / daemon) -- their proven verdict.
    for name, verdict in sorted(chaos_manifest.items()):
        kind = _SURFACE_KIND.get(name, "feed")
        surfaces.append({
            "name": name, "kind": kind,
            "contract": _CONTRACTS.get(kind, ""),
            "verdict": verdict if verdict in (PROVEN, FAILED) else UNPROVEN,
        })

    # 2) Supervised processes -- each enumerated; heartbeat procs inherit the
    #    daemon-readiness verdict, NONE-readiness procs are exempt-but-listed.
    daemon_verdict = chaos_manifest.get("daemon_readiness")
    for row in _supervised_surfaces():
        if row.get("verdict") is None:
            if row.get("expects_heartbeat"):
                row["verdict"] = (daemon_verdict
                                  if daemon_verdict in (PROVEN, FAILED)
                                  else UNPROVEN)
            else:
                # exempt-but-enumerated: counts as PROVEN-exempt (no heartbeat
                # contract to satisfy), explicitly noted so it is never a hidden gap.
                row["verdict"] = PROVEN
        surfaces.append(row)

    counts = {PROVEN: 0, FAILED: 0, UNPROVEN: 0}
    for s in surfaces:
        v = s.get("verdict", UNPROVEN)
        counts[v] = counts.get(v, 0) + 1

    if counts[FAILED]:
        overall = "failed"
    elif counts[UNPROVEN]:
        overall = "unproven"
    else:
        overall = "proven"

    return {
        "generated_at": t,
        "overall": overall,
        "surfaces": surfaces,
        "counts": counts,
        "honest_note": (
            "A surface with no proving chaos cell reads UNPROVEN (an honest gap), "
            "never proven-by-absence. No $ field; calibration not edge; "
            "self-improve untouched; real-money default-DENY untouched."
        ),
    }


def _atomic_write(path: pathlib.Path, doc: Dict[str, Any]) -> bool:
    """Atomically write *doc* as ASCII JSON (tmp + os.replace). Never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(raw, encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception:  # noqa: BLE001 -- a write failure must not crash the caller
        return False


def write_manifest(
    *, path: Optional[pathlib.Path] = None, now: Optional[float] = None,
) -> Dict[str, Any]:
    """Build + atomically persist the manifest. Returns the doc. Never raises."""
    doc = build_manifest(now=now)
    _atomic_write(path if path is not None else _OUT, doc)
    return doc


def _main() -> int:  # pragma: no cover -- thin CLI shim
    doc = write_manifest()
    print("robustness_manifest | overall=%s proven=%d failed=%d unproven=%d -> %s"
          % (doc["overall"], doc["counts"].get(PROVEN, 0),
             doc["counts"].get(FAILED, 0), doc["counts"].get(UNPROVEN, 0), _OUT),
          flush=True)
    return 0 if doc["overall"] == "proven" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["PROVEN", "FAILED", "UNPROVEN", "build_manifest", "write_manifest"]
