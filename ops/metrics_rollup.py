"""ops.metrics_rollup -- a small metrics object for the status page.

Rolls up two cheap, already-computed artifacts into one flat dict the UI can
render without any $ / ROI:

  * the paper-trading scoreboard (data/frontend/grade_summary.json, built by
    scripts.platformkit.pm_trading.scoreboard) -- CLV + counts ONLY.
  * a liveness count (how many observed services are live) from
    ops.liveness.liveness_snapshot.

HARD HONESTY: no dollars, no ROI, no profit. The ONLY performance numbers
surfaced are CLV % (beats-the-close yardstick), settled counts, and the
flat-unit win/loss record -- exactly the fields the gate already exposes.

Public API
----------
rollup(*, scoreboard_path=None, now=None) -> dict
    {
      "generated_at": "<ISO-8601 UTC>",
      "clv": {                     # null-safe pass-through of the scoreboard
        "n_settled":       <int>,
        "mean_clv_pct":    <float|null>,
        "pct_beat_close":  <float|null>,
        "flat_unit_wins":  <int>,
        "flat_unit_losses":<int>
      },
      "liveness": {"live": <int>, "total": <int>, "down": [<name>...]},
      "honest_note": "<string>"
    }
    Never raises -- a missing/corrupt scoreboard yields a zeroed clv block.

LIVENESS CONVENTION
-------------------
Port-bound servers (liveness_component is None, port set in the
ServiceDescriptor) are monitored via the supervisor port-probe, NOT via a
heartbeat file.  Their absence from daemon_heartbeats/ is EXPECTED and must
NOT be counted as "down" in the liveness rollup.  Only heartbeat-backed
daemons (liveness_component is not None) belong in the down list.

A snapshot entry is treated as heartbeat-monitored only when its key appears
as a liveness_component in some ServiceDescriptor.  Any entry NOT recognised
by the service_registry (e.g. a legacy daemon_registry alias for a port-bound
server such as predict_service_api) is also excluded from the down list to
align with health_aggregator's convention.

INVARIANTS: <=300 LOC; ASCII only; stdlib only; never raises; no $/ROI fields.
Build only under ops/.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Union

from ops import liveness as _liveness
from ops import service_registry as _registry

_HONEST_NOTE = (
    "Calibration / CLV only. No dollar figures. CLV %% is the beats-the-close "
    "yardstick; counts are settled paper bets."
)


def _find_repo_root() -> Path:
    candidate = Path(__file__).resolve()
    for _ in range(8):
        candidate = candidate.parent
        if (candidate / "CLAUDE.md").exists():
            return candidate
    return Path(__file__).resolve().parents[1]


_REPO_ROOT = _find_repo_root()
_DEFAULT_SCOREBOARD = _REPO_ROOT / "data" / "frontend" / "grade_summary.json"

# Only these scoreboard keys are surfaced (allowlist => no $/ROI can leak).
_CLV_KEYS = (
    "n_settled",
    "mean_clv_pct",
    "pct_beat_close",
    "flat_unit_wins",
    "flat_unit_losses",
)


def _utc_iso(ts: Optional[float] = None) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts is not None else datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _empty_clv() -> Dict[str, Any]:
    return {
        "n_settled": 0,
        "mean_clv_pct": None,
        "pct_beat_close": None,
        "flat_unit_wins": 0,
        "flat_unit_losses": 0,
    }


def _read_scoreboard(path: Path) -> Dict[str, Any]:
    """Read the grade_summary.json CLV block (allowlisted). Never raises."""
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return _empty_clv()
    except Exception:  # noqa: BLE001 -- missing/corrupt scoreboard -> zeros
        return _empty_clv()
    out = _empty_clv()
    for key in _CLV_KEYS:
        if key in data:
            out[key] = data[key]
    return out


def _port_probed_names() -> FrozenSet[str]:
    """Return service names that are port-probed, NOT heartbeat-backed.

    A port-probed ServiceDescriptor has liveness_component=None and a non-None
    port.  Their absence from daemon_heartbeats/ is expected and must NOT drive
    a false-positive "down" verdict in the liveness rollup.  Never raises.
    """
    try:
        descs = _registry.service_descriptors()
        return frozenset(
            d.name
            for d in descs
            if d.liveness_component is None and d.port is not None
        )
    except Exception:  # noqa: BLE001
        return frozenset()


def _liveness_counts(now: Optional[float]) -> Dict[str, Any]:
    """Count live vs total observed heartbeat-backed daemons; list the down ones.

    Alignment with health_aggregator convention:
      * Port-probed services (liveness_component=None / port set in
        ServiceDescriptor, e.g. m1_api_paper) are excluded from both total
        and down -- their liveness is the supervisor TCP probe, not a file.
      * Snapshot keys that are NOT recognised as a liveness_component by any
        ServiceDescriptor (e.g. the legacy daemon_registry entry
        predict_service_api) are also excluded -- they correspond to port-bound
        servers absent from the supervisor manifest and produce false-positive
        downs when their heartbeat file is missing.

    Only genuine heartbeat daemons with a stale or absent beat appear in down.
    Never raises.
    """
    try:
        snap = _liveness.liveness_snapshot(now=now)
    except Exception:  # noqa: BLE001
        return {"live": 0, "total": 0, "down": []}

    try:
        descs = _registry.service_descriptors()
        # Names of explicitly port-probed servers.
        port_bound_names: FrozenSet[str] = frozenset(
            d.name
            for d in descs
            if d.liveness_component is None and d.port is not None
        )
        # Recognised heartbeat-component keys (the keys liveness_snapshot emits
        # for genuine heartbeat-backed daemons).
        hb_components: FrozenSet[str] = frozenset(
            d.liveness_component
            for d in descs
            if d.liveness_component is not None
        )
    except Exception:  # noqa: BLE001
        port_bound_names = frozenset()
        hb_components = frozenset()

    total = 0
    live = 0
    down: List[str] = []
    for name, info in snap.items():
        # Explicitly port-probed server: skip.
        if name in port_bound_names:
            continue
        # Not a recognised heartbeat component (legacy alias or unrecognised
        # daemon_registry entry for a port-bound server): skip.
        if hb_components and name not in hb_components:
            continue
        total += 1
        if isinstance(info, dict) and info.get("live"):
            live += 1
        else:
            down.append(name)
    return {"live": live, "total": total, "down": sorted(down)}


def rollup(
    *,
    scoreboard_path: Optional[Union[str, Path]] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Build the status-page metrics object. Never raises."""
    sb_path = Path(scoreboard_path) if scoreboard_path is not None else _DEFAULT_SCOREBOARD
    return {
        "generated_at": _utc_iso(now),
        "clv": _read_scoreboard(sb_path),
        "liveness": _liveness_counts(now),
        "honest_note": _HONEST_NOTE,
    }


__all__ = ["rollup"]
