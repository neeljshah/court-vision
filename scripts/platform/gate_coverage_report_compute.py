"""gate_coverage_report_compute.py — Data-loading and map-building helpers for gate_coverage_report.

Moved from gate_coverage_report.py (N-GATE-001) as part of the ≤300 LOC/file split.
All logic is verbatim — zero behaviour change.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from gate_surface_catalog import (
    ADHOC_FLAGS,
    PREEXISTING_FLAGS,
    enumerate_prediction_surfaces,
)

# ---------------------------------------------------------------------------
# Repo root (injected at module level by the entry file after import)
# ---------------------------------------------------------------------------

# Will be set by gate_coverage_report after _find_repo_root() runs.
REPO_ROOT: Path  # forward declaration — populated by the entry module


# ---------------------------------------------------------------------------
# Ledger loading (read-only JSONL parse — no src imports, no heavy deps)
# ---------------------------------------------------------------------------

def _get_ledger_path() -> Path:
    return REPO_ROOT / ".planning" / "loop" / "ledger.jsonl"


def _load_ledger() -> Dict[str, Dict[str, Any]]:
    ledger_path = _get_ledger_path()
    if not ledger_path.exists():
        return {}
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    with ledger_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = entry.get("name", "")
            if name:
                by_name.setdefault(name, []).append(entry)
    result: Dict[str, Dict[str, Any]] = {}
    for name, entries in by_name.items():
        non_defer = [e for e in entries if e.get("verdict") not in ("DEFER", None)]
        pool = non_defer if non_defer else entries
        result[name] = sorted(pool, key=lambda e: e.get("date", ""), reverse=True)[0]
    return result


# ---------------------------------------------------------------------------
# Flag registry loading (static text parse — avoids importing src.brain.flags)
# ---------------------------------------------------------------------------

def _get_flags_path() -> Path:
    return REPO_ROOT / "src" / "brain" / "flags.py"


def _parse_flags_from_source() -> List[Dict[str, Any]]:
    """Parse FLAGS dict entries from flags.py via regex (no import needed)."""
    flags_path = _get_flags_path()
    if not flags_path.exists():
        return []
    source = flags_path.read_text(encoding="utf-8")
    keys = re.compile(r'^\s{4}"(CV_[A-Z0-9_]+)"\s*:\s*\{', re.MULTILINE).findall(source)
    entries: List[Dict[str, Any]] = []
    for key in keys:
        start = source.find(f'"{key}"')
        end_candidates = [source.find(f'"{k}"', start + 1) for k in keys if k != key]
        end = min((e for e in end_candidates if e > start), default=len(source))
        block = source[start:end]
        phase_m = re.search(r'"phase"\s*:\s*"([^"]+)"', block)
        gate_m = re.search(r'"gate"\s*:\s*\(?\s*"([^"]{10,})', block, re.DOTALL)
        desc_m = re.search(r'"desc"\s*:\s*\(?\s*"([^"]{5,})', block, re.DOTALL)
        entries.append({
            "name": key,
            "phase": phase_m.group(1) if phase_m else "unknown",
            "has_gate_text": bool(gate_m),
            "gate_snippet": gate_m.group(1)[:120].replace("\n", " ").strip() if gate_m else "",
            "desc_snippet": desc_m.group(1)[:100].replace("\n", " ").strip() if desc_m else "",
            "source": "src/brain/flags.py",
            "registry": "brain_flags",
        })
    return entries


# ---------------------------------------------------------------------------
# Helpers for build_coverage_map
# ---------------------------------------------------------------------------

def _verdict_from_ledger(ledger: Dict[str, Dict[str, Any]], name: str):
    entry = ledger.get(name)
    if entry:
        return entry.get("verdict", "UNKNOWN"), entry.get("date", ""), "loop_ledger"
    return "NO_VERDICT", "", "none"


def _build_flag_rows(registered: List[Dict[str, Any]], ledger: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    # Brain-registered flags
    for f in registered:
        v, vd, vs = _verdict_from_ledger(ledger, f["name"])
        rows.append({
            "flag_name": f["name"], "registry": f["registry"],
            "phase": f["phase"], "has_gate_text": f["has_gate_text"],
            "verdict": v, "verdict_date": vd, "verdict_source": vs,
            "desc": f["desc_snippet"], "gate_note": f["gate_snippet"],
        })
    # Pre-existing flags
    for name, note in PREEXISTING_FLAGS:
        v, vd, vs = _verdict_from_ledger(ledger, name)
        rows.append({
            "flag_name": name, "registry": "pre_existing",
            "phase": "pre-gate", "has_gate_text": False,
            "verdict": v, "verdict_date": vd,
            "verdict_source": "loop_ledger" if ledger.get(name) else "none",
            "desc": note,
            "gate_note": "Pre-existing flag — canonical home is the owning module, not flags.py",
        })
    # Ad-hoc flags
    for name, owner, note in ADHOC_FLAGS:
        v, vd, _ = _verdict_from_ledger(ledger, name)
        rows.append({
            "flag_name": name, "registry": "adhoc",
            "phase": "ad-hoc", "has_gate_text": False,
            "verdict": v, "verdict_date": vd,
            "verdict_source": "loop_ledger" if ledger.get(name) else "memory_notes",
            "desc": note,
            "gate_note": f"Owner: {owner}. No entry in flags.py — consider migrating.",
        })
    return rows


def _build_surface_rows(surfaces: List[Dict[str, Any]], ledger: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for s in surfaces:
        entry = ledger.get(s["name"])
        if entry:
            v, vd, vs = entry.get("verdict", "UNKNOWN"), entry.get("date", ""), "loop_ledger"
        else:
            cat = s["category"]
            if cat in ("prop_quantile", "win_probability", "simulation", "cv_spatial"):
                v, vs = "LEGACY_SHIPPED", "pre_gate_architecture"
            elif cat in ("scouting_only", "narration", "auxiliary"):
                v, vs = "SCOUTING_ONLY", "architecture_decision"
            elif "CV_MIN_VAR" in s["notes"] or "VALIDATED" in s["notes"]:
                v, vs = "VALIDATED_NOT_IN_LEDGER", "memory_notes"
            else:
                v, vs = "NO_VERDICT", "none"
            vd = ""
        rows.append({
            "surface_name": s["name"], "category": s["category"],
            "source": s["source"], "verdict": v,
            "verdict_date": vd, "verdict_source": vs, "notes": s["notes"],
        })
    return rows


def _gap(item: str, kind: str, gap_type: str, action: str) -> Dict[str, Any]:
    return {"item": item, "kind": kind, "gap_type": gap_type, "candidate_action": action}


def _build_gaps(flag_rows: List[Dict[str, Any]], surface_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:  # noqa: E501
    gaps: List[Dict[str, Any]] = []
    for f in flag_rows:
        n = f["flag_name"]
        if f["verdict"] == "NO_VERDICT":
            gaps.append(_gap(n, "flag", "missing_ledger_verdict",
                             "Add gate criteria to flags.py and record verdict in loop ledger"))
        if not f["has_gate_text"] and f["registry"] == "brain_flags":
            gaps.append(_gap(n, "flag", "missing_gate_text",
                             "Write gate criteria in src/brain/flags.py FLAGS[gate] field"))
        if f["registry"] == "adhoc":
            gaps.append(_gap(n, "flag", "not_in_flags_registry",
                             "Migrate flag to src/brain/flags.py or document reason it lives ad-hoc"))
    for sr in surface_rows:
        if sr["verdict"] in ("NO_VERDICT", "LEGACY_SHIPPED"):
            gaps.append(_gap(sr["surface_name"], "surface", sr["verdict"],
                             "Record a formal gate evaluation in the loop ledger for this surface"
                             if sr["verdict"] == "NO_VERDICT"
                             else "Perform a retroactive gate evaluation; document as LEGACY_SHIPPED"))
    return gaps


# ---------------------------------------------------------------------------
# Coverage-map builder
# ---------------------------------------------------------------------------

def build_coverage_map() -> Dict[str, Any]:
    """Build and return the full coverage map as a structured dict."""
    ledger = _load_ledger()
    registered = _parse_flags_from_source()
    flag_rows = _build_flag_rows(registered, ledger)
    surface_rows = _build_surface_rows(enumerate_prediction_surfaces(), ledger)
    gaps = _build_gaps(flag_rows, surface_rows)
    return {
        "flags": flag_rows,
        "surfaces": surface_rows,
        "gaps": gaps,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
