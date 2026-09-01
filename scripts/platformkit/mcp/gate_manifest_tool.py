"""Read-only MCP loader for the eval-gate freshness manifest.

Truth source: ``data/cache/eval_gate/gate_manifest.json``, written by the
existing eval-gate producer. This module DERIVES NOTHING. It returns the
manifest's own ``summary`` block and its per-artifact rows (name, source_path,
mtime, staleness_days, status, verdict) verbatim, wrapped in the standard MCP
envelope (status / category / source_artifact / as_of), so an AI consumer can
answer "is the gate evidence fresh?" without reading files itself.

Fails closed: an absent or unparseable manifest returns ``no_data``. There is
deliberately NO staleness-refusal tier -- see ``gate_manifest``'s docstring.

Additive and inert: nothing imports this yet. The one-line wiring change into
``scripts/platformkit/mcp_server/tools.py`` is a PROPOSED diff in
``docs/research/organization-sprint/MCP_ADVANCE_2026-09-01.md``.

Run: python -m scripts.platformkit.mcp.gate_manifest_tool
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ponytail: reuse mcp_server.artifact_tools' loader/envelope helpers instead of
# re-implementing them -- same package family, same contract, same envelope
# shape. They are underscore-private only because nothing outside that file
# needed them before; make them public there if a third module ever wants them.
from scripts.platformkit.mcp_server.artifact_tools import _as_of, _load, _no_data

_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST = "data/cache/eval_gate/gate_manifest.json"

_NOTE = (
    "Rows are returned verbatim from the manifest. No staleness-refusal tier: a "
    "freshness report that refuses when stale cannot report its own staleness. "
    "Read manifest_staleness_days and each row's staleness_days instead."
)


def _staleness_days(as_of: Any) -> Optional[float]:
    """Age of an ISO timestamp in days, or None if it is not parseable."""
    try:
        stamp = datetime.fromisoformat(str(as_of))
    except (TypeError, ValueError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - stamp).total_seconds() / 86400.0, 4)


def gate_manifest(args: Dict[str, Any], root: Path = _ROOT) -> Dict[str, Any]:
    """Truth source: data/cache/eval_gate/gate_manifest.json.

    ``args["status"]`` optionally filters rows by their own status field (case
    insensitive, e.g. "OK" / "EMPTY" / "UNREADABLE"). An absent or unreadable
    manifest -> ``no_data``. A filter that matches nothing still returns ``ok``
    with ``n_rows: 0`` -- the manifest was read, it simply has no such rows,
    which is a different fact from "no manifest".
    """
    loaded = _load(root, (_MANIFEST,))
    if loaded is None:
        return _no_data("gate_manifest", _MANIFEST, "gate manifest absent or unreadable")
    path, rel, value = loaded
    if not isinstance(value, dict):
        return _no_data("gate_manifest", rel, "gate manifest is not a JSON object")

    rows: List[Dict[str, Any]] = [r for r in (value.get("rows") or []) if isinstance(r, dict)]
    wanted = args.get("status")
    if wanted:
        rows = [r for r in rows if str(r.get("status", "")).upper() == str(wanted).upper()]

    as_of = _as_of(path, value)
    return {
        "status": "ok",
        "category": "gate_manifest",
        "source_artifact": rel,
        "as_of": as_of,
        "manifest_staleness_days": _staleness_days(as_of),
        "summary": value.get("summary"),
        "n_rows": len(rows),
        "rows": rows,
        "note": _NOTE,
    }


def tool_specs() -> List[Dict[str, Any]]:
    """MCP metadata; the description names the truth source, per house style."""
    return [{
        "name": "gate_manifest",
        "description": (
            "Truth source: data/cache/eval_gate/gate_manifest.json. Read-only freshness "
            "ledger for the gate's backing artifacts: per-row name, source_path, mtime, "
            "staleness_days, status, verdict, plus the manifest's own summary counts "
            "(ok / empty / unreadable / total). Answers 'is the evidence behind the gate "
            "fresh, and which rows are stale or unreadable'. Optional status filter. "
            "Missing manifest returns no_data. Descriptive freshness only -- no ratings, "
            "no calibration numbers, no edge or ROI claim."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string",
                           "description": "optional row filter, e.g. OK / EMPTY / UNREADABLE"},
            },
        },
        "handler": gate_manifest,
    }]


if __name__ == "__main__":
    print(json.dumps(gate_manifest({}), indent=2, default=str))
