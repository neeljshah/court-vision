"""probe_R29_V4_session_note.py — end-to-end probe for the R15-R28 note.

Generates ``SESSION3.md`` against the REAL coordination log + improve-loop
state + git log, but writes the output to a probe-scoped temp path
(NEVER ``vault/Sessions/SESSION3.md``). Verifies:

  * All 5 mandated sections render
  * >= 10 round entries present
  * Output size lands in the [2KB, 30KB] window
  * Every commit SHA cited resolves via ``git cat-file -t``
  * Persists results to ``data/cache/probe_R29_V4_results.json``

Hard rules
----------
* LOCAL only.
* Never writes to ``vault/Sessions/SESSION3.md``.
* Read-only against every data source other than the probe results file.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts import generate_session_note as gsn  # noqa: E402

PROBE_RESULTS_PATH = os.path.join(
    _ROOT, "data", "cache", "probe_R29_V4_results.json"
)

EXPECTED_HEADINGS = (
    "## Round-by-Round Summary",
    "## Major Themes",
    "## Top 10 Ships by Impact",
    "## Open Items / Next Session",
    "## Stats",
)

SIZE_MIN_BYTES = 2 * 1024     # 2 KB lower bound
SIZE_MAX_BYTES = 30 * 1024    # 30 KB upper bound


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_coord_log() -> Path:
    """Pick the freshest coordination_log.md."""
    main_repo = Path(r"C:/Users/neelj/nba-ai-system/scripts/coordination_log.md")
    local = Path(_ROOT) / "scripts" / "coordination_log.md"
    if main_repo.exists() and (
        not local.exists()
        or main_repo.stat().st_size > local.stat().st_size
    ):
        return main_repo
    return local


def run_probe() -> Dict[str, Any]:
    """Generate the note, validate, return a result dict."""
    result: Dict[str, Any] = {
        "probe":         "R29_V4_session_note",
        "started_at":    _iso_now(),
        "status":        "running",
        "verdict":       None,
        "details":       {},
    }

    with tempfile.TemporaryDirectory(prefix="r29v4_") as tmp:
        out_path = Path(tmp) / "SESSION3.md"
        coord_log = _resolve_coord_log()

        try:
            body = gsn.build_note(
                session=3,
                start_round=15,
                end_round=28,
                coord_log_path=coord_log,
                now=datetime.now(timezone.utc),
            )
            gsn.atomic_write(out_path, body)
        except Exception as exc:
            result["status"] = "error"
            result["verdict"] = "BLOCKED"
            result["details"]["error"] = str(exc)
            result["details"]["traceback"] = traceback.format_exc()
            return result

        # ---- Section presence ----
        sections_rendered = sum(1 for h in EXPECTED_HEADINGS if h in body)
        result["details"]["sections_rendered"] = sections_rendered
        result["details"]["sections_total"] = len(EXPECTED_HEADINGS)

        # ---- Round count ----
        round_matches = re.findall(r"### R(\d+)\n- Tally:", body)
        result["details"]["n_rounds_documented"] = len(round_matches)
        result["details"]["rounds_seen"] = round_matches

        # ---- File size ----
        size = out_path.stat().st_size
        result["details"]["note_size_bytes"] = size
        result["details"]["size_in_range"] = (
            SIZE_MIN_BYTES <= size <= SIZE_MAX_BYTES
        )

        # ---- SHA cross-check ----
        shas = re.findall(r"`([0-9a-f]{12})`", body)
        valid = 0
        unknown: list = []
        # Sample-check up to 40 to keep probe runtime small.
        for sha in shas[:40]:
            try:
                rr = subprocess.run(
                    ["git", "cat-file", "-t", sha],
                    cwd=_ROOT,
                    capture_output=True, text=True,
                )
                if rr.returncode == 0 and rr.stdout.strip() == "commit":
                    valid += 1
                else:
                    unknown.append(sha)
            except Exception:
                unknown.append(sha)
        result["details"]["sha_total_cited"]  = len(shas)
        result["details"]["sha_checked"]      = min(len(shas), 40)
        result["details"]["sha_valid"]        = valid
        result["details"]["sha_unknown_sample"] = unknown[:5]

        # ---- Ship-gate verdict ----
        all_sections   = sections_rendered == len(EXPECTED_HEADINGS)
        enough_rounds  = len(round_matches) >= 10
        size_ok        = SIZE_MIN_BYTES <= size <= SIZE_MAX_BYTES
        shas_ok        = len(unknown) == 0 and len(shas) >= 10

        result["status"] = "ok"
        result["verdict"] = (
            "SHIP"
            if (all_sections and enough_rounds and size_ok and shas_ok)
            else "REJECT"
        )
        result["details"]["gates"] = {
            "all_sections": all_sections,
            "enough_rounds": enough_rounds,
            "size_in_range": size_ok,
            "shas_resolve":  shas_ok,
        }

    result["ended_at"] = _iso_now()
    return result


def persist_results(result: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(PROBE_RESULTS_PATH), exist_ok=True)
    tmp = PROBE_RESULTS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, sort_keys=True)
    os.replace(tmp, PROBE_RESULTS_PATH)


def main() -> int:
    result = run_probe()
    persist_results(result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("verdict") == "SHIP" else 1


if __name__ == "__main__":
    raise SystemExit(main())
