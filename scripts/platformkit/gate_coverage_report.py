"""gate_coverage_report.py — Prediction-surface inventory vs ledger verdicts (N-GATE-001).
Output: .planning/platform/GATE_COVERAGE.md — descriptive only, no edge claims.
Pure stdlib + light text parsing. No app boot. No torch. Runtime < 5 s.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

from gate_surface_catalog import VERDICT_LABEL

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
# Inject REPO_ROOT into the compute module before any of its functions run
# ---------------------------------------------------------------------------

import gate_coverage_report_compute as _compute  # noqa: E402
_compute.REPO_ROOT = REPO_ROOT

# ---------------------------------------------------------------------------
# Re-export every public name so all import paths still resolve
# ---------------------------------------------------------------------------

from gate_coverage_report_compute import (  # noqa: E402,F401
    _load_ledger,
    _parse_flags_from_source,
    _verdict_from_ledger,
    _build_flag_rows,
    _build_surface_rows,
    _gap,
    _build_gaps,
    build_coverage_map,
)

# Backward-compatible alias for tests that import the private name directly.
from gate_surface_catalog import enumerate_prediction_surfaces  # noqa: E402,F401
_enumerate_prediction_surfaces = enumerate_prediction_surfaces

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
    a("> Source: `scripts/platformkit/gate_coverage_report.py` (N-GATE-001)  ")
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
