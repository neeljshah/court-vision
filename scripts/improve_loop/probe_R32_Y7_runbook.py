"""probe_R32_Y7_runbook.py — verifies the operator runbook is shippable.

Procedure
---------
1. Verify docs/operator_runbook.md exists.
2. Count sections (must hit all 7 expected H2 headers).
3. Cross-check every referenced script exists on disk.
4. Count non-blank lines (must be >= 200).
5. Persist summary to data/cache/probe_R32_Y7_results.json.

Exit code 0 always — this is a reporter, not a gate. The ship gate is
the test suite + the live commit.

LOCAL ONLY. No SSH. No real-money side effect.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DOC_PATH = _ROOT / "docs" / "operator_runbook.md"
RESULTS_PATH = _ROOT / "data" / "cache" / "probe_R32_Y7_results.json"

REQUIRED_SECTIONS = (
    "TL;DR",
    "Architecture",
    "Daily timeline",
    "Files to open",
    "Cron setup",
    "Common operations",
    "Incident response",
)

REQUIRED_SCRIPTS = (
    "scripts/daily_workflow.py",
    "scripts/operator_dashboard.py",
    "scripts/mobile_html_server.py",
    "scripts/live_recommendation_engine.py",
    "scripts/ledger_insurance.py",
    "scripts/nightly_cleanup.py",
    "scripts/daemon_registry.json",
    "scripts/daemon_watchdog.py",
    "scripts/reconcile_settlements.py",
    "scripts/live_rec_tracker.py",
    "scripts/feature_drift_detector.py",
    "scripts/nba_injury_report_scraper.py",
    "scripts/recover_line_killed.py",
    "scripts/place_bet.py",
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_probe() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "probe": "R32_Y7",
        "ts": _iso_now(),
        "doc_path": str(DOC_PATH),
        "doc_exists": DOC_PATH.exists(),
    }
    if not DOC_PATH.exists():
        out["status"] = "FAIL"
        out["reason"] = "runbook missing"
        return out

    text = DOC_PATH.read_text(encoding="utf-8")
    lines_all = text.splitlines()
    lines_nb = [ln for ln in lines_all if ln.strip()]
    out["total_lines"] = len(lines_all)
    out["non_blank_lines"] = len(lines_nb)

    # Section coverage.
    sections_found = [s for s in REQUIRED_SECTIONS if s in text]
    out["sections_required"] = list(REQUIRED_SECTIONS)
    out["sections_found"] = sections_found
    out["sections_rendered"] = len(sections_found)
    out["sections_target"] = len(REQUIRED_SECTIONS)

    # Script cross-checks.
    cited: List[str] = []
    missing_on_disk: List[str] = []
    not_cited: List[str] = []
    for rel in REQUIRED_SCRIPTS:
        if rel in text:
            cited.append(rel)
            full = _ROOT / rel
            if not full.exists():
                missing_on_disk.append(rel)
        else:
            not_cited.append(rel)
    out["referenced_scripts_cited"] = cited
    out["referenced_scripts_count"] = len(cited)
    out["referenced_scripts_target"] = len(REQUIRED_SCRIPTS)
    out["referenced_scripts_missing_on_disk"] = missing_on_disk
    out["referenced_scripts_not_cited"] = not_cited

    # Status verdict.
    ok = (
        len(sections_found) == len(REQUIRED_SECTIONS)
        and not missing_on_disk
        and not not_cited
        and len(lines_nb) >= 200
    )
    out["status"] = "SHIP" if ok else "INCOMPLETE"
    return out


def main() -> int:
    result = run_probe()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(RESULTS_PATH) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, sort_keys=True)
    os.replace(tmp, RESULTS_PATH)
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"\n[probe_R32_Y7] wrote -> {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
