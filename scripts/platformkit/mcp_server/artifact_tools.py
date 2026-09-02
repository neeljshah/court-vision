"""Read-only artifact resolvers for the CourtVision MCP front door.

These tools never derive ratings, gates, or execution figures. They merely
return the contents that existing producers wrote, under the MCP envelope.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


_ROOT = Path(__file__).resolve().parents[3]
_ATLAS = "scripts/platformkit/analytics_showcase/out/market_strength_atlas.json"
_MECHANISM = (
    "scripts/platformkit/analytics_showcase/out/mechanism_exposure.json",
    "data/frontend/analytics/mechanism_exposure.json",
)
_HEALTH = (
    "data/frontend/analytics/harness_health.json",
    "data/cache/analytics_verify/harness_health.json",
    "scripts/platformkit/analytics_showcase/out/harness_health.json",
)
_EXECUTION = (
    "data/frontend/analytics/execution_status.json",
    "scripts/platformkit/analytics_showcase/out/execution_status.json",
    "scripts/platformkit/analytics_showcase/out/paper_execution_audit.json",
)


def _as_of(path: Path, value: Any) -> str:
    if isinstance(value, dict):
        for key in ("as_of", "generated_at", "updated_at", "created_at"):
            if value.get(key):
                return str(value[key])
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def _parse_iso(stamp: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def finalize(env: Dict[str, Any], root: Path = _ROOT) -> Dict[str, Any]:
    """S71/F1: age every `ok` envelope that names a real file on disk.

    The single point every MCP handler passes through (tools.handler_for), so
    `staleness_days` cannot be forgotten by a new tool. `as_of` is preferred
    over the file mtime when it parses -- it is the artifact's own measurement
    time -- and `staleness_days_source` says which was used. Envelopes that are
    not `ok` (no_data / not_supported / refused / ambiguous) carry no number and
    are returned untouched.
    """
    if not isinstance(env, dict) or env.get("status") != "ok":
        return env
    if env.get("staleness_days") is not None:
        return env
    sources = env.get("source_artifact")
    paths = [root / str(s).replace("\\", "/")
             for s in (sources if isinstance(sources, list) else [sources]) if isinstance(s, str)]
    paths = [p for p in paths if p.is_file()]
    if not paths:
        return env
    stamp, source = _parse_iso(env.get("as_of")), "as_of"
    if stamp is None:
        stamp = datetime.fromtimestamp(max(p.stat().st_mtime for p in paths), timezone.utc)
        source = "source_artifact_mtime"
    env["staleness_days"] = round(
        (datetime.now(timezone.utc) - stamp).total_seconds() / 86400.0, 4)
    env["staleness_days_source"] = source
    return env


def _no_data(category: str, source: str, note: str) -> Dict[str, Any]:
    return {"status": "no_data", "category": category, "source_artifact": source,
            "as_of": None, "note": note}


def _load(root: Path, rels: Iterable[str]) -> tuple[Path, str, Any] | None:
    for rel in rels:
        path = root / rel
        if not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        return path, rel.replace("\\", "/"), value
    return None


def _field(value: Any, *names: str) -> Any:
    if isinstance(value, dict):
        for name in names:
            if name in value:
                return value[name]
    return None


def strength_atlas(args: Dict[str, Any], root: Path = _ROOT) -> Dict[str, Any]:
    """Truth source: market_strength_atlas.json written by analytics_showcase.

    The writer nests ratings per sport under "sports": {sport: {top_5, bottom_5,
    eval_scores.mean_absolute_tracking_error}} -- there are no top-level
    top_ratings/bottom_ratings/tracking_mae keys. Reshape per-sport here instead
    of reading absent top-level keys (which silently produced ok+null).
    """
    loaded = _load(root, (_ATLAS,))
    if loaded is None:
        return _no_data("strength_atlas", _ATLAS, "artifact absent or unreadable")
    path, rel, value = loaded
    sports = value.get("sports") if isinstance(value, dict) else None
    if not isinstance(sports, dict) or not sports:
        return _no_data("strength_atlas", rel, "artifact has no per-sport 'sports' data")
    top_ratings = {s: v["top_5"] for s, v in sports.items() if isinstance(v, dict) and v.get("top_5")}
    bottom_ratings = {s: v["bottom_5"] for s, v in sports.items() if isinstance(v, dict) and v.get("bottom_5")}
    tracking_mae = {
        s: v["eval_scores"]["mean_absolute_tracking_error"]
        for s, v in sports.items()
        if isinstance(v, dict) and isinstance(v.get("eval_scores"), dict)
        and "mean_absolute_tracking_error" in v["eval_scores"]
    }
    if not top_ratings and not bottom_ratings and not tracking_mae:
        return _no_data("strength_atlas", rel, "no sport had ratings or tracking-MAE fields")
    return {"status": "ok", "category": "strength_atlas", "source_artifact": rel,
            "as_of": _as_of(path, value),
            "top_ratings": top_ratings or None,
            "bottom_ratings": bottom_ratings or None,
            "tracking_mae": tracking_mae or None,
            "DESCRIPTIVE_ONLY": _field(value, "label", "DESCRIPTIVE_ONLY", "descriptive_only")}


def mechanism_exposure(args: Dict[str, Any], root: Path = _ROOT) -> Dict[str, Any]:
    """Truth source: mechanism_exposure.py JSON output and its verbatim ledger fields."""
    loaded = _load(root, _MECHANISM)
    if loaded is None:
        return _no_data("mechanism_exposure", _MECHANISM[0], "exposure artifact absent or unreadable")
    path, rel, value = loaded
    game_id = args.get("game_id")
    if game_id is None:
        payload = value
    else:
        # S71/F2: the producer writes the per-game list under "game_sheets";
        # games/rows stay as fallbacks for any older artifact on disk.
        rows = (value.get("game_sheets", value.get("games", value.get("rows", [])))
                if isinstance(value, dict) else [])
        payload = [row for row in rows if str(row.get("game_id")) == str(game_id)]
        if not payload:
            return _no_data("mechanism_exposure", rel, "no exposure sheet for requested game_id")
    return {"status": "ok", "category": "mechanism_exposure", "source_artifact": rel,
            "as_of": _as_of(path, value), "exposure_sheets": payload,
            "note": "Ledger effect, n, and p fields are returned verbatim from the artifact."}


def tracking_program_status(args: Dict[str, Any], root: Path = _ROOT) -> Dict[str, Any]:
    """Truth source: docs/evidence/tracking packets and data/tracking_reports JSON files."""
    files = list((root / "docs/evidence/tracking").glob("*.json"))
    files += list((root / "docs/evidence/tracking").glob("*.md"))
    files += list((root / "data/tracking_reports").rglob("*.json"))
    if not files:
        return _no_data("tracking_program_status", "docs/evidence/tracking/; data/tracking_reports/",
                        "no tracking packet or report JSON artifacts present")
    artifacts: List[Dict[str, Any]] = []
    for path in sorted(files):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            value = json.loads(text) if path.suffix == ".json" else {"packet_text": text}
        except (OSError, json.JSONDecodeError):
            continue
        artifacts.append({"source_artifact": path.relative_to(root).as_posix(),
                          "as_of": _as_of(path, value), "sport": _field(value, "sport"),
                          "stage_table": _field(value, "stage_table", "stages"),
                          "latest_harness_verdicts": _field(value, "latest_harness_verdicts", "verdict"),
                          "artifact": value})
    if not artifacts:
        return _no_data("tracking_program_status", "docs/evidence/tracking/; data/tracking_reports/",
                        "tracking artifacts were unreadable")
    return {"status": "ok", "category": "tracking_program_status",
            "source_artifact": [row["source_artifact"] for row in artifacts],
            "as_of": max(row["as_of"] for row in artifacts), "artifacts": artifacts,
            "honest_headline": "0 passes"}


def harness_health(args: Dict[str, Any], root: Path = _ROOT) -> Dict[str, Any]:
    """Truth source: existing harness-health scoreboard JSON written by validation producers."""
    loaded = _load(root, _HEALTH)
    if loaded is None:
        return _no_data("harness_health", _HEALTH[0], "harness-health artifact absent or unreadable")
    path, rel, value = loaded
    return {"status": "ok", "category": "harness_health", "source_artifact": rel,
            "as_of": _as_of(path, value),
            "golden_verdicts": _field(value, "golden_verdicts", "golden"),
            "null_ship_calibration": _field(value, "null_ship_calibration", "null_ship"),
            "retro_correction_survivors": _field(value, "retro_correction_survivors"),
            "multiplicity_ledger_K": _field(value, "multiplicity_ledger_K", "K")}


def execution_status(args: Dict[str, Any], root: Path = _ROOT) -> Dict[str, Any]:
    """Truth source: execution-status or paper-execution-audit JSON written by existing ledgers."""
    loaded = _load(root, _EXECUTION)
    if loaded is None:
        return _no_data("execution_status", _EXECUTION[0], "execution artifact absent or unreadable")
    path, rel, value = loaded
    # S71/F3: the artifact states its own status -- an execution readout over an
    # empty ledger writes status "no_data" / verdict "INSUFFICIENT". Serving that
    # as `ok` invented a health the ledger does not have.
    own = _field(value, "status")
    if own in ("no_data", "not_supported", "refused", "ambiguous"):
        return {"status": own, "category": "execution_status", "source_artifact": rel,
                "as_of": _as_of(path, value),
                "note": "artifact reports status=%s, verdict=%s -- passed through verbatim" % (
                    own, _field(value, "verdict")),
                "units_only": True}
    return {"status": "ok", "category": "execution_status", "source_artifact": rel,
            "as_of": _as_of(path, value),
            "mlb_event_reactive_latency": _field(value, "mlb_event_reactive_latency", "mlb_event_reactive"),
            "maker_mode_config": _field(value, "maker_mode_config", "maker_mode"),
            "paper_ledger_counts": {key: _field(value, key) for key in
                                    ("n_records", "n_placed", "n_executed_filled", "n_open", "n_settled", "paper_units")
                                    if _field(value, key) is not None},
            "units_only": True}


def tool_specs() -> List[Dict[str, Any]]:
    """MCP metadata whose descriptions identify each tool's truth source."""
    return [
        {"name": "strength_atlas", "description": "Truth source: scripts/platformkit/analytics_showcase/out/market_strength_atlas.json. Read-only top/bottom ratings and tracking MAE; passes DESCRIPTIVE_ONLY through verbatim. Missing artifact returns no_data.", "inputSchema": {"type": "object", "properties": {}}, "handler": strength_atlas},
        {"name": "mechanism_exposure", "description": "Truth source: mechanism_exposure.py JSON output. Read-only per-game exposure sheets; ledger effect, n, and p are quoted verbatim. Missing artifact or game returns no_data.", "inputSchema": {"type": "object", "properties": {"game_id": {"type": "string"}}}, "handler": mechanism_exposure},
        {"name": "tracking_program_status", "description": "Truth source: docs/evidence/tracking packet JSON and data/tracking_reports JSON. Read-only stage and harness artifacts with the honest zero-passes headline. Missing artifacts return no_data.", "inputSchema": {"type": "object", "properties": {}}, "handler": tracking_program_status},
        {"name": "harness_health", "description": "Truth source: existing harness-health scoreboard JSON from validation producers. Read-only golden, null-ship, retro-correction, and multiplicity ledger values. Missing artifact returns no_data.", "inputSchema": {"type": "object", "properties": {}}, "handler": harness_health},
        {"name": "execution_status", "description": "Truth source: execution-status or paper-execution-audit JSON. Read-only latency, maker-mode, and paper-ledger scoreboard in units only. Missing artifact returns no_data.", "inputSchema": {"type": "object", "properties": {}}, "handler": execution_status},
    ]
