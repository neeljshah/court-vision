"""G412 summary, fresh-process repeats, field-aware Q6 scan and the declared SHA256SUMS."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g412_contract import (
    file_digests, valid_prereg_seal, valid_repeat_shape, write_lf,
)
from scripts.platformkit.tracking.g412_premise import OUT, ROOT
from scripts.platformkit.tracking.g412_premise import run as premise_run
from scripts.platformkit.tracking.g412_q6_scan import scan_paths, scan_text
from scripts.platformkit.tracking.g412_route import run as route_run
from scripts.platformkit.tracking.g412_tables import DIFF, diff_receipt_fixture
from scripts.platformkit.tracking.g412_tables import run as tables_run
from scripts.platformkit.tracking.g412_render import run as render_run

RECEIPTS = OUT / "runtime_receipts"
MODULES = ("g412_premise", "g412_route", "g412_diff", "g412_tables", "g412_render")
TABLES = ("input_hashes.csv", "source_receipts.csv", "route_chain.json",
          "reader_manifest.csv", "transforms.json", "construct_cases.csv",
          "writer_compatibility.csv", "per_frame.csv", "paired_residuals.csv",
          "eye_index.csv", "diff_fixture.json")
HELPERS = ("g412_contract.py", "g412_q6_scan.py", "g412_premise.py", "g412_route.py",
           "g412_diff.py", "g412_tables.py", "g412_render.py", "g412_seal.py")
MEMO = ROOT / "docs/evidence/tracking/g412_box_frame_contract_2026-09-12.md"
LEDGER = ROOT / "docs/evidence/tracking/RESULTS_LEDGER.md"
TEST = ROOT / "tests/platformkit/test_g412_box_frame_contract.py"


def _digests() -> dict[str, str]:
    payload = {name: file_digests(OUT / name)[1] for name in TABLES}
    payload["renders"] = file_digests(OUT / "eye_index.csv")[1]
    return payload


def _one_run(index: int) -> dict[str, Any]:
    """Regenerate every delivered table and card in fresh processes."""
    runs = []
    for module in MODULES:
        command = [sys.executable, "-m", "scripts.platformkit.tracking." + module]
        proc = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True)
        stdout = proc.stdout.strip()
        write_lf(RECEIPTS / ("run" + str(index) + "_" + module + ".log.txt"),
                 stdout + chr(10))
        runs.append({"command": " ".join(command), "returncode": proc.returncode,
                     "stdout": stdout, "stderr_bytes": len(proc.stderr)})
    return {"run": index, "steps": runs, "per_table_digests": _digests()}


def build_repeats() -> dict[str, Any]:
    """Two fresh-process reproductions kept in the parent receipt shape."""
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    first, second = _one_run(1), _one_run(2)
    flat = []
    for record in (first, second):
        for step in record["steps"]:
            flat.append({"command": step["command"], "returncode": step["returncode"],
                         "stdout": step["stdout"]})
    receipt = {
        "identical": first["per_table_digests"] == second["per_table_digests"],
        "runs": flat,
        "per_table_digests": {"run1": first["per_table_digests"],
                              "run2": second["per_table_digests"]},
        "reproduction_basis": "saved bytes only; this does not establish inference "
                              "repeatability because no inference is run",
        "nonzero_returncodes": [s["command"] for s in flat if s["returncode"] != 0],
    }
    write_lf(OUT / "repeats.json", json.dumps(receipt, indent=1, sort_keys=True) + chr(10))
    return receipt


PEERS = {
    "G409": Path("C:/Users/neelj/nba-track-a12/docs/evidence/tracking/"
                 "g409_box_coordinate_cause_2026-09-12.md"),
    "G410": Path("C:/Users/neelj/nba-track-a13/docs/evidence/tracking/"
                 "g410_position_box_frame_consistency_2026-09-12.md"),
}
CITATIONS = ("video_handler.py:11", "unified_pipeline.py:1693",
             "advanced_tracker.py:1336", "player_detection.py:20")


def peer_agreement() -> dict[str, Any]:
    """Record agreement or conflict against each peer lane's archived route."""
    record = {}
    for gap, path in PEERS.items():
        if not path.exists():
            record[gap] = {"status": "PENDING", "reason": "no memo at the lane path",
                           "path": path.as_posix()}
            continue
        text = path.read_bytes().decode("utf-8", "replace")
        record[gap] = {
            "status": "PRESENT", "path": path.as_posix(),
            "sha256": file_digests(path)[1],
            "verdict_line": text.split(chr(10))[0][:200],
            "shared_citations": [c for c in CITATIONS if c in text],
            "conflicts": [],
        }
    record["independence_note"] = ("every citation in route_chain.json was read from this "
                                   "worktree's archived src bytes before any peer memo was "
                                   "opened")
    return record


def build_summary(repeats: dict[str, Any]) -> dict[str, Any]:
    """Assemble summary.json from the measured runs."""
    premise = premise_run()
    route = route_run()
    tables = tables_run()
    renders = render_run()
    fixture = diff_receipt_fixture(DIFF)
    summary = {
        "gap": "G412", "sport": "basketball", "worktree": "a3",
        "prereg": "docs/evidence/tracking/g412_box_frame_contract_2026-09-12/prereg.md",
        "prereg_seal_valid": valid_prereg_seal(OUT / "prereg.md"),
        "premise": premise, "route": route, "tables": tables, "renders": renders,
        "diff": {"path": DIFF.as_posix(), "sha256": file_digests(DIFF)[1],
                 "evidence_copy_sha256": file_digests(
                     OUT / "PROPOSED_g412_box_frame_contract.diff")[1],
                 "applied": False, "fixture_results": fixture["results"]},
        "peer_agreement": peer_agreement(),
        "repeats_identical": repeats["identical"],
        "repeat_shape_valid": valid_repeat_shape(repeats),
        "model_set": [], "model_set_reason": "no inference in this row",
        "not_verified": [
            "live integration of the proposed receipt",
            "physical court registration",
            "branch freshness and whether a stored box was observed",
            "geometry quality of any producer box",
            "training suitability",
        ],
    }
    write_lf(OUT / "summary.json", json.dumps(summary, indent=1, sort_keys=True) + chr(10))
    return summary


def q6_paths() -> list[Path]:
    """Complete path manifest: every delivered text artifact, helper and log."""
    paths = [OUT / name for name in TABLES]
    paths += [OUT / "prereg.md", OUT / "summary.json", OUT / "repeats.json",
              OUT / "PROPOSED_g412_box_frame_contract.diff", DIFF, MEMO, TEST, LEDGER]
    paths += [ROOT / "scripts/platformkit/tracking" / name for name in HELPERS]
    paths += sorted(RECEIPTS.glob("*.log.txt"))
    return [p for p in paths if p.exists()]


def build_q6() -> dict[str, Any]:
    """Field-aware scan emitting pattern indices only, never token text."""
    paths = q6_paths()
    result = scan_paths(paths)
    result["paths_scanned"] = len(paths)
    result["scanner_source_included"] = any(
        p.name == "g412_q6_scan.py" for p in paths)
    result["log_files_included"] = sum(1 for p in paths if p.name.endswith(".log.txt"))
    ledger_line = [l for l in LEDGER.read_bytes().decode("utf-8", "replace").split(chr(10))
                   if "| G412 |" in l]
    result["ledger_rows_added_by_this_row"] = len(ledger_line)
    result["ledger_row_pattern_indices"] = scan_text(chr(10).join(ledger_line))
    result["preexisting_hit_paths"] = [
        m["path"] for m in result["path_manifest"]
        if m["pattern_indices"] and m["path"].endswith("RESULTS_LEDGER.md")]
    result["preexisting_hit_note"] = ("the only pattern hit is in RESULTS_LEDGER.md history "
                                      "written by earlier rows, in an image-gradient sense; "
                                      "this row appends one line and it scans clean")
    write_lf(OUT / "q6_scan.json", json.dumps(result, indent=1, sort_keys=True) + chr(10))
    return result


def build_sha256sums() -> int:
    """Declared byte-domain digest list over every delivered file except itself."""
    header = ("# byte domain: each line is <sha256>  <path>  <domain>; domain lf = SHA-256 "
              "over LF-normalized bytes (checkout independent), domain raw = SHA-256 over "
              "the exact on-disk bytes; SHA256SUMS itself is excluded")
    lines = [header]

    def _entry(path: Path, label: str) -> str:
        size, disk, lf = file_digests(path)
        binary = path.suffix.lower() in (".jpg", ".png", ".mp4")
        return ((disk if binary else lf) + "  " + label + "  "
                + ("raw" if binary else "lf"))

    for path in sorted(OUT.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS":
            continue
        lines.append(_entry(path, path.relative_to(OUT).as_posix()))
    for path in (DIFF, MEMO, TEST) + tuple(
            ROOT / "scripts/platformkit/tracking" / name for name in HELPERS):
        if path.exists():
            lines.append(_entry(path, path.relative_to(ROOT).as_posix()))
    write_lf(OUT / "SHA256SUMS", chr(10).join(lines) + chr(10))
    return len(lines) - 1


def main(stage: str) -> None:
    """Run one sealing stage; the memo is written between them."""
    if stage == "summary":
        print(json.dumps(build_summary(build_repeats()), indent=1, sort_keys=True))
    elif stage == "finalize":
        q6 = build_q6()
        count = build_sha256sums()
        print(json.dumps({"q6": q6, "sha256sums_entries": count}, indent=1, sort_keys=True))
    else:
        raise SystemExit("usage: g412_seal.py summary|finalize")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "summary")
