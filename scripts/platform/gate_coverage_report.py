"""gate_coverage_report.py — Prediction-surface inventory vs ledger verdicts (N-GATE-001).
Output: .planning/platform/GATE_COVERAGE.md — descriptive only, no edge claims.
Pure stdlib + light text parsing. No app boot. No torch. Runtime < 5 s.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from _gate_surfaces import (
    ADHOC_FLAGS,
    PREEXISTING_FLAGS,
    VERDICT_LABEL,
    enumerate_prediction_surfaces,
)

# Backward-compatible alias for tests that import the private name directly.
_enumerate_prediction_surfaces = enumerate_prediction_surfaces

# ---------------------------------------------------------------------------
# Repo root resolution
# ---------------------------------------------------------------------------

def _find_repo_root() -> Path:
    candidate = Path(__file__).resolve()
    for _ in range(10):
        candidate = candidate.parent
        if (candidate / "CLAUDE.md").exists():
            return candidate
    return Path(__file__).resolve().parents[3]


REPO_ROOT: Path = _find_repo_root()

# ---------------------------------------------------------------------------
# Ledger loading (read-only JSONL parse — no src imports, no heavy deps)
# ---------------------------------------------------------------------------

_LEDGER_PATH: Path = REPO_ROOT / ".planning" / "loop" / "ledger.jsonl"


def _load_ledger() -> Dict[str, Dict[str, Any]]:
    if not _LEDGER_PATH.exists():
        return {}
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    with _LEDGER_PATH.open("r", encoding="utf-8") as fh:
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

_FLAGS_PATH: Path = REPO_ROOT / "src" / "brain" / "flags.py"


def _parse_flags_from_source() -> List[Dict[str, Any]]:
    """Parse FLAGS dict entries from flags.py via regex (no import needed)."""
    if not _FLAGS_PATH.exists():
        return []
    source = _FLAGS_PATH.read_text(encoding="utf-8")
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


# ---------------------------------------------------------------------------
# Markdown emitter
# ---------------------------------------------------------------------------

def _vd(verdict: str) -> str:
    return VERDICT_LABEL.get(verdict, verdict)


def _bullets(a, items: list, fmt_fn, empty_msg: str) -> None:
    [a(fmt_fn(x)) for x in items] if items else a(empty_msg)


def emit_report(data: Dict[str, Any], out_path: Path) -> None:
    """Write GATE_COVERAGE.md to out_path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ln: List[str] = []
    a = ln.append

    a("# Gate Coverage Map — Prediction Surfaces & Feature Flags")
    a("")
    a(f"> Generated: {data['generated_at']}  ")
    a("> Source: `scripts/platform/gate_coverage_report.py` (N-GATE-001)  ")
    a("> This document is descriptive only. It records coverage status, not performance claims.")
    a("")
    a("---")
    a("")

    # § 1: Feature Flags
    a("## 1. Feature Flags")
    a("")
    a("Every default-OFF feature flag in the codebase. Columns:")
    a("- **Registry**: `brain_flags` = in `src/brain/flags.py FLAGS`; "
      "`pre_existing` = documented but owned by another module; `adhoc` = found by grep only.")
    a("- **Has Gate Text**: whether gate criteria are written in the registry.")
    a("- **Verdict**: recorded outcome in the loop ledger (or classification).")
    a("")
    a("| Flag | Registry | Phase | Has Gate Text | Verdict | Verdict Date | Notes |")
    a("|------|----------|-------|--------------|---------|--------------|-------|")
    for f in sorted(data["flags"], key=lambda x: x["flag_name"]):
        a(f"| `{f['flag_name']}` | {f['registry']} | {f['phase']} "
          f"| {'YES' if f['has_gate_text'] else 'NO'} | {_vd(f['verdict'])} "
          f"| {f['verdict_date']} | {f['desc'][:80]} |")

    a("")
    a("### 1.1 Flags Without a Recorded Verdict")
    a("")
    _bullets(a, [f for f in data["flags"] if f["verdict"] == "NO_VERDICT"],
             lambda f: f"- **`{f['flag_name']}`** ({f['registry']}, {f['phase']}): {f['desc'][:120]}",
             "_All registered flags have a recorded verdict or are classified._")

    a("")
    a("### 1.2 Flags Missing Gate Text")
    a("")
    _bullets(a, [f for f in data["flags"] if not f["has_gate_text"] and f["registry"] == "brain_flags"],
             lambda f: f"- **`{f['flag_name']}`**: gate field is absent or empty in FLAGS dict",
             "_All brain-registered flags have gate text._")

    a("")
    a("### 1.3 Ad-Hoc Flags (Not in flags.py Registry)")
    a("")
    _bullets(a, [f for f in data["flags"] if f["registry"] == "adhoc"],
             lambda f: f"- **`{f['flag_name']}`**: {f['gate_note']}",
             "_No ad-hoc flags found._")

    a("")
    a("---")
    a("")

    # § 2: Prediction Surfaces
    a("## 2. Prediction Surfaces")
    a("")
    a("Every named prediction surface enumerated from route files and architecture docs.")
    a("")
    a("| Surface | Category | Verdict | Verdict Date | Source |")
    a("|---------|----------|---------|--------------|--------|")
    for sr in sorted(data["surfaces"], key=lambda x: (x["category"], x["surface_name"])):
        a(f"| `{sr['surface_name']}` | {sr['category']} "
          f"| {_vd(sr['verdict'])} | {sr['verdict_date']} "
          f"| {sr['source'][:80]} |")

    a("")
    a("### 2.1 Legacy-Shipped Surfaces (Pre-Gate Architecture)")
    a("")
    legacy = [sr for sr in data["surfaces"] if sr["verdict"] == "LEGACY_SHIPPED"]
    if legacy:
        a("These surfaces existed before the gate architecture was built. "
          "They require a retroactive evaluation to confirm continued fitness.")
        a("")
        for sr in legacy:
            a(f"- **`{sr['surface_name']}`** ({sr['category']}): {sr['notes'][:120]}")
    else:
        a("_No legacy-shipped surfaces identified._")

    a("")
    a("### 2.2 Surfaces With No Verdict")
    a("")
    _bullets(a, [sr for sr in data["surfaces"] if sr["verdict"] == "NO_VERDICT"],
             lambda sr: f"- **`{sr['surface_name']}`** ({sr['category']}): {sr['notes'][:120]}",
             "_All surfaces have a verdict or classification._")

    a("")
    a("---")
    a("")

    # § 3: Gap List
    a("## 3. Coverage Gaps — Candidate Future Tasks")
    a("")
    a("Each gap below is a candidate task for the build backlog. "
      "Gaps are listed, not prioritised. The orchestrator decides which to queue or waive.")
    a("")
    gap_by_type: Dict[str, List[Dict[str, Any]]] = {}
    for g in data["gaps"]:
        gap_by_type.setdefault(g["gap_type"], []).append(g)
    for idx, (gap_type, gap_list) in enumerate(sorted(gap_by_type.items()), 1):
        a(f"### 3.{idx} {gap_type}")
        a("")
        for g in gap_list:
            a(f"- **`{g['item']}`** ({g['kind']}): {g['candidate_action']}")
        a("")

    # § 4: Summary
    a("---")
    a("")
    a("## 4. Coverage Summary")
    a("")
    flags, surfaces = data["flags"], data["surfaces"]
    a("| Metric | Count |")
    a("|--------|-------|")
    a(f"| Total flags enumerated | {len(flags)} |")
    a(f"| Flags with a recorded verdict | {sum(1 for f in flags if f['verdict'] != 'NO_VERDICT')} |")
    a(f"| Brain-registered flags with gate text | {sum(1 for f in flags if f['has_gate_text'])} |")
    a(f"| Total prediction surfaces enumerated | {len(surfaces)} |")
    a(f"| Surfaces with a formal verdict | {sum(1 for s in surfaces if s['verdict'] not in ('NO_VERDICT', 'LEGACY_SHIPPED'))} |")
    a(f"| Total coverage gaps identified | {len(data['gaps'])} |")
    a("")
    a("---")
    a("")
    a("_End of GATE_COVERAGE.md_")

    out_path.write_text("\n".join(ln), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Build the coverage map and write GATE_COVERAGE.md."""
    import time as _time
    t0 = _time.perf_counter()
    data = build_coverage_map()
    out = REPO_ROOT / ".planning" / "platform" / "GATE_COVERAGE.md"
    emit_report(data, out)
    elapsed = _time.perf_counter() - t0
    print(
        f"GATE_COVERAGE.md written: {out}\n"
        f"  flags={len(data['flags'])}  surfaces={len(data['surfaces'])}  "
        f"gaps={len(data['gaps'])}  elapsed={elapsed:.2f}s"
    )


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT))
    main()
