"""Reproduction receipts, field-aware vocabulary scan and checksums for G406."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g406_audit import field_scan, preserve_repeat_parent
from scripts.platformkit.tracking.g406_measure import OUT, ROOT, sha256, write_json

STAGES = [("g406_measure", "premise"), ("g406_review", "associate"), ("g406_review", "order"),
          ("g406_aggregate", ""), ("g406_render", "cards")]
TABLES = ["input_hashes.csv", "source_receipts.csv", "window_accounting.csv", "draw.csv",
          "all_masked_rows.csv", "associations.csv", "unmatched_boxes.csv",
          "blind_order_receipt.csv", "per_tick.csv", "summary.json", "render_receipts.csv"]
FROZEN = ["prereg.md", "frozen_args.json", "launch_receipts.json", "comparator_detections.csv",
          "blind_marks.jsonl", "adjudications.csv", "frame_receipts.csv", "blind_view_receipts.csv",
          "eye_index.csv"]
TEXT_SUFFIXES = {".md", ".csv", ".json", ".jsonl", ".txt"}


def _digests() -> dict[str, str]:
    return {name: sha256(OUT / name) for name in TABLES + ["renders/1080p30_00.jpg"]}


def _run(module: str, stage: str) -> dict[str, Any]:
    command = [sys.executable, "-m", "scripts.platformkit.tracking." + module]
    if stage:
        command.append(stage)
    done = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True,
                          env={"PYTHONPATH": str(ROOT), "PATH": __import__("os").environ["PATH"],
                               "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})
    return {"module": module, "stage": stage, "returncode": done.returncode,
            "stdout": done.stdout[-400:], "stderr": done.stderr[-400:]}


def stage_repeats() -> dict[str, Any]:
    baseline = _digests()
    runs = []
    for index in range(2):
        steps = [_run(module, stage) for module, stage in STAGES]
        digests = _digests()
        runs.append({"round": index + 1, "steps": steps, "per_table_digests": digests,
                     "returncode": max(step["returncode"] for step in steps),
                     "stdout": "".join(step["stdout"] for step in steps)[-600:],
                     "identical_to_baseline": digests == baseline})
    parent = {"identical": all(run["identical_to_baseline"] for run in runs), "runs": runs}
    payload = preserve_repeat_parent(parent, {
        "rounds": len(runs), "baseline_digests": baseline,
        "frozen_inputs_not_regenerated": {name: sha256(OUT / name) for name in FROZEN},
        "scope": ("two fresh processes regenerate the delivered tables and cards from the delivered "
                  "comparator output, blind marks and adjudications; this is arithmetic and render "
                  "reproduction and it does not prove inference repeatability")})
    write_json(OUT / "repeats.json", payload)
    return {"identical": payload["identical"], "rounds": len(runs)}


def stage_q6() -> dict[str, Any]:
    results = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            results.append(field_scan(path))
    memo = ROOT / "docs/evidence/tracking/g406_masked_target_pixel_audit_2026-09-11.md"
    if memo.is_file():
        results.append(field_scan(memo))
    ledger = ROOT / "docs/evidence/tracking/RESULTS_LEDGER.md"
    if ledger.is_file():
        own = OUT / "runtime_receipts" / "ledger_line_g406.txt"
        mine = [line for line in ledger.read_text(encoding="utf-8").splitlines() if "G406" in line]
        own.write_text("\n".join(mine) + "\n", encoding="utf-8", newline="\n")
        results.append(field_scan(own))
    for name in ("g406_measure.py", "g406_review.py", "g406_render.py", "g406_aggregate.py",
                 "g406_seal.py", "g406_comparator.py", "g406_audit.py", "g406_prepare.py"):
        results.append(field_scan(ROOT / "scripts/platformkit/tracking" / name))
    results.append(field_scan(ROOT / "tests/platformkit/test_g406_target_pixel_audit.py"))
    payload = {"scanned": len(results), "non_opaque_hits": sum(item["count"] for item in results),
               "pattern_source": "character codes only; matched text is never emitted",
               "files": results}
    write_json(OUT / "q6_scan.json", payload)
    return {"scanned": payload["scanned"], "non_opaque_hits": payload["non_opaque_hits"],
            "files_with_hits": [item["path"] for item in results if item["count"]]}


def stage_sums() -> dict[str, Any]:
    lines = ["# byte domain: sha256 over the exact bytes on disk of every file under "
             "docs/evidence/tracking/g406_masked_target_pixel_audit_2026-09-11/ plus the memo, "
             "the owned helpers and the focused test; paths are repo-relative with forward slashes"]
    targets = [path for path in sorted(OUT.rglob("*"))
               if path.is_file() and path.name != "SHA256SUMS"]
    targets.append(ROOT / "docs/evidence/tracking/g406_masked_target_pixel_audit_2026-09-11.md")
    for name in ("g406_measure.py", "g406_review.py", "g406_render.py", "g406_aggregate.py",
                 "g406_seal.py", "g406_comparator.py", "g406_audit.py", "g406_prepare.py"):
        targets.append(ROOT / "scripts/platformkit/tracking" / name)
    targets.append(ROOT / "tests/platformkit/test_g406_target_pixel_audit.py")
    for path in targets:
        if path.is_file():
            lines.append("%s  %s" % (sha256(path), path.relative_to(ROOT).as_posix()))
    (OUT / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {"files": len(lines) - 1}


if __name__ == "__main__":
    name = sys.argv[1]
    outcome = {"repeats": stage_repeats, "q6": stage_q6, "sums": stage_sums}[name]()
    print(json.dumps(outcome, sort_keys=True))
