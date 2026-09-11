"""Assemble every G401 evidence artifact from the immutable receipts.

Inputs: the off-repo receiver (retained sources, decoded PTS cache, pod
receipts) and the committed modules. Nothing here touches the pod or a
production path.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.platformkit.tracking.g393_parser_harness import extract_build_command
from scripts.platformkit.tracking.g401_prereg import q6_hit_counts, verify_prereg
from scripts.platformkit.tracking.g401_proposal import (
    build_fixtures, load_candidate, read_parser, reader_survey)
from scripts.platformkit.tracking.g401_render import render_all
from scripts.platformkit.tracking.g401_run import build_tables
from scripts.platformkit.tracking.g401_measure import LOSS_DECISION_SECONDS
from scripts.platformkit.tracking.g401_timebase import TARGET_DURATION_SECONDS

EVIDENCE = Path("docs/evidence/tracking/g401_fps_cap_duration_shadow_2026-09-11")
DIFF = Path("docs/research/organization-sprint/PROPOSED_g401_fps_cap.diff")
TEXT_SUFFIXES = (".csv", ".diff", ".json", ".jsonl", ".md", ".py", ".txt")
FLOAT_KEYS = ("arm_a_span_s", "arm_b_span_s", "arm_a_loss_s", "arm_b_loss_s",
              "native_frame_interval_s", "validated_fps",
              "arm_a_last_admitted_pts", "arm_a_first_excluded_pts",
              "arm_b_last_admitted_pts", "arm_b_first_excluded_pts")
INT_KEYS = ("draw_j", "arm_a_frame_cap", "arm_b_frame_cap", "arm_a_read_frames",
            "arm_b_read_frames", "source_frame_count",
            "declared_stride_opportunities")


from scripts.platformkit.tracking.g401_io import (  # noqa: E402
    read_csv, retype, sha256_file, write_csv)


def fixtures(root: Path, base_daemon: Path, candidate_daemon: Path) -> list[dict]:
    """The sealed construct-only argv cases against the real proposal text."""
    legacy = extract_build_command(base_daemon.read_text(encoding="utf-8"))
    candidate = load_candidate(candidate_daemon.read_text(encoding="utf-8"))
    parser = read_parser(root / "scripts/run_clip.py")
    return build_fixtures(candidate, legacy, parser)


def _proposal_receipt(cases: list[dict], survey: list[dict], diff_text: str,
                      pod: dict) -> dict:
    return {
        "proposed_diff_path": DIFF.as_posix(),
        "proposed_diff_sha256": hashlib.sha256(diff_text.encode("utf-8")).hexdigest(),
        "touches_files": ["scripts/platformkit/track_daemon.py"],
        "applies_clean_to_deploy_bytes": pod["diff_apply_check"],
        "deploy_track_daemon_sha256": pod["track_daemon_sha256"],
        "deploy_run_clip_sha256": pod["run_clip_sha256"],
        "deploy_unified_pipeline_sha256": pod["unified_pipeline_sha256"],
        "new_argv_flags": sorted({flag for case in cases
                                  for flag in case["flag_names_added"]}),
        "default_argv_matches_legacy": all(c["default_argv_matches_legacy"]
                                           for c in cases),
        "argv_parses_with_unchanged_run_clip": all(
            c["argv_parses_with_unchanged_run_clip"] for c in cases),
        "reader_rows": len(survey),
        "reader_rows_changed": sum(1 for r in survey if r["changed_by_proposal"]),
        "preserved_aliases": sorted({r["token"] for r in survey
                                     if not r["changed_by_proposal"]}),
        "vram_flush_interval_untouched": "_VRAM_FLUSH_INTERVAL" not in diff_text,
        "applied_anywhere": False,
        "not_verified": [
            "runtime cost of more than 3000 processed frames, which crosses "
            "_VRAM_FLUSH_INTERVAL=3000",
            "receipt retention and output quality across that flush boundary",
            "producer-emitted tick coverage under either cap",
            "any tracking-quality effect of a longer window"],
    }


def assemble(receiver: Path, root: Path, scratch: Path, pod: dict) -> dict:
    """Build every table, render, receipt and diff copy in the evidence dir."""
    evidence = root / EVIDENCE
    result = build_tables(receiver, evidence)

    shutil.copy2(receiver / "window_ledger.jsonl", evidence / "window_ledger.jsonl")
    write_csv(evidence / "source_receipts.csv",
              json.loads((receiver / "source_receipts.json").read_text()))

    spans = {r["source_name"]: float(r["available_span_s"])
             for r in read_csv(evidence / "pts.csv") if r["available_span_s"]}
    typed = [retype(row) for row in read_csv(evidence / "paired_caps.csv")]
    index = render_all(typed, spans, receiver / "sources",
                       evidence / "renders", scratch / "thumbs")
    write_csv(evidence / "eye_index.csv", index)

    cases = fixtures(root, scratch / "base/scripts/platformkit/track_daemon.py",
                     scratch / "cand/scripts/platformkit/track_daemon.py")
    (evidence / "argv_fixtures.json").write_text(
        json.dumps(cases, indent=1, sort_keys=True), encoding="ascii")
    survey = reader_survey(root)
    write_csv(evidence / "reader_survey.csv", survey)

    diff_text = (scratch / "proposed.diff").read_text(encoding="utf-8")
    (root / DIFF).parent.mkdir(parents=True, exist_ok=True)
    (root / DIFF).write_text(diff_text, encoding="utf-8", newline="\n")
    (evidence / "PROPOSED_g401_fps_cap.diff").write_text(
        diff_text, encoding="utf-8", newline="\n")
    (evidence / "proposal_receipt.json").write_text(
        json.dumps(_proposal_receipt(cases, survey, diff_text, pod),
                   indent=1, sort_keys=True), encoding="ascii")

    (evidence / "policy_receipt.json").write_text(json.dumps(dict(
        prereg_sha256_verified=verify_prereg(evidence / "prereg.md"),
        target_duration_seconds=TARGET_DURATION_SECONDS,
        loss_decision_seconds=LOSS_DECISION_SECONDS,
        **pod, **result), indent=1, sort_keys=True), encoding="ascii")
    return result


def q6_scan(evidence: Path) -> dict:
    """Counts only, over every landable text artifact including receipts."""
    paths = [p for p in sorted(evidence.rglob("*"))
             if p.is_file() and p.suffix in TEXT_SUFFIXES]
    return {"files_scanned": len(paths), "counts": q6_hit_counts(paths)}


def normalize_lf(evidence: Path) -> list[str]:
    """Rewrite every text artifact with LF endings so the sums match the blobs."""
    changed = []
    for path in sorted(evidence.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        raw = path.read_bytes()
        flat = raw.replace(b"\r\n", b"\n")
        if flat != raw:
            path.write_bytes(flat)
            changed.append(path.relative_to(evidence).as_posix())
    return changed


def checksums(evidence: Path) -> None:
    """SHA256SUMS with the byte-domain declaration on line 1."""
    normalize_lf(evidence)
    lines = ["# byte domain: sha256 over the exact committed bytes of each listed "
             "file, path relative to this directory, LF text as committed"]
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            lines.append("%s  %s" % (sha256_file(path),
                                     path.relative_to(evidence).as_posix()))
    (evidence / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii")


TABLES = ("census.csv", "draw.csv", "pts.csv", "policy_per_section.csv",
          "paired_caps.csv")


def repeat_once(receiver: Path, root: Path, out: Path) -> dict:
    """A fresh interpreter rebuilds the tables and re-renders the 30 cards."""
    code = (
        "import json,sys;"
        "sys.path.insert(0,%r);"
        "from pathlib import Path;"
        "from scripts.platformkit.tracking.g401_run import build_tables;"
        "from scripts.platformkit.tracking.g401_finish import "
        "read_csv, retype, sha256_file;"
        "from scripts.platformkit.tracking.g401_render import render_all;"
        "out=Path(%r);"
        "build_tables(Path(%r), out);"
        "spans={r['source_name']: float(r['available_span_s']) "
        "for r in read_csv(out/'pts.csv') if r['available_span_s']};"
        "rows=[retype(r) for r in read_csv(out/'paired_caps.csv')];"
        "render_all(rows, spans, Path(%r)/'sources', out/'renders', out/'thumbs');"
        "print(json.dumps({p.relative_to(out).as_posix(): sha256_file(p) "
        "for p in sorted(out.rglob('*')) if p.is_file() "
        "and p.parent.name != 'thumbs'}))"
        % (str(root.resolve()), str(out), str(receiver), str(receiver)))
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(root),
                          capture_output=True, text=True, check=True)
    return json.loads(proc.stdout.strip().splitlines()[-1])


def repeats(receiver: Path, root: Path, scratch: Path) -> dict:
    """Two fresh processes must reproduce every table and render digest."""
    evidence = root / EVIDENCE
    delivered = {name: sha256_file(evidence / name) for name in TABLES}
    delivered.update({"renders/" + p.name: sha256_file(p)
                      for p in sorted((evidence / "renders").iterdir())})
    runs = []
    for index in (1, 2):
        out = scratch / ("repeat_%d" % index)
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        produced = repeat_once(receiver, root, out)
        runs.append({"run": index,
                     "matches": {key: produced.get(key) == value
                                 for key, value in delivered.items()}})
    return {"delivered_sha256": delivered,
            "runs": runs,
            "all_tables_and_renders_reproduced": all(
                all(run["matches"].values()) for run in runs),
            "scope": "arithmetic and rendering only; a producer run is not repeated"}


def write_summary(root: Path) -> dict:
    """The single roll-up, built only from the delivered tables."""
    evidence = root / EVIDENCE
    policy = read_csv(evidence / "policy_per_section.csv")
    paired = read_csv(evidence / "paired_caps.csv")
    receipt = json.loads((evidence / "policy_receipt.json").read_text())
    proposal = json.loads((evidence / "proposal_receipt.json").read_text())
    repeat = json.loads((evidence / "repeats.json").read_text())
    valid = [r for r in paired if r["cap_basis"] == "VALIDATED_FPS"]
    reach = [r for r in valid if r["arm_b_reaches_target"] == "True"]
    fps_counts: dict[str, int] = {}
    for row in policy:
        key = "%.2f" % float(row["source_fps"]) if row["source_fps"] else "UNKNOWN"
        fps_counts[key] = fps_counts.get(key, 0) + 1
    summary = {
        "gap": "G401", "sport": "basketball", "worktree": "a11",
        "prereg_sha256": ("35133397a0d6ef07f71ebbb05b4248867acf49888"
                          "9056cf48e34b48bf12cd568"),
        "prereg_verified": receipt["prereg_sha256_verified"],
        "preference_activation_utc": receipt["preference_activation_utc"],
        "census_utc": receipt["census_utc"],
        "window_sections": receipt["policy"]["window_sections"],
        "window_sections_by_source_fps": fps_counts,
        "primary_metric_cap_loss_over_5s_fraction":
            receipt["policy"]["primary_metric"],
        "cap_loss_over_5s_count": receipt["policy"]["cap_loss_over_5s_count"],
        "unknown_sections": receipt["policy"]["unknown_sections"],
        "attribution_counts": receipt["policy"]["attribution_counts"],
        "policy_status": receipt["policy"]["policy_status"],
        "preference_alone_sufficient_for_this_window": False,
        "shadow_population_n": receipt["population_n"],
        "shadow_draw_n": receipt["draw_n"],
        "paired_valid_n": len(valid),
        "paired_arm_b_reaching_target_n": len(reach),
        "paired_arm_a_reaching_target_n":
            receipt["paired_arm_a_reaching_target_n"],
        "paired_mechanics_bar": "arm B extent within one native frame interval "
                                "of 100 s on all 30 valid sources",
        "paired_mechanics_pass": len(reach) == 30 and len(valid) == 30,
        "proposed_diff_sha256": proposal["proposed_diff_sha256"],
        "proposal_touches_files": proposal["touches_files"],
        "proposal_new_argv_flags": proposal["new_argv_flags"],
        "proposal_applied_anywhere": proposal["applied_anywhere"],
        "reproduced_by_two_fresh_processes":
            repeat["all_tables_and_renders_reproduced"],
        "not_verified": proposal["not_verified"] + [
            "tracking quality under either cap",
            "that any window section's producer-emitted ticks match the "
            "DECLARED stride opportunities"],
    }
    (evidence / "summary.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True), encoding="ascii")
    return summary


def main(argv: list[str]) -> int:
    receiver, root, scratch = Path(argv[1]), Path(argv[2]), Path(argv[3])
    pod = json.loads(Path(argv[4]).read_text(encoding="utf-8"))
    assemble(receiver, root, scratch, pod)
    if "repeat" in argv[5:]:
        repeat = repeats(receiver, root, scratch)
        (root / EVIDENCE / "repeats.json").write_text(
            json.dumps(repeat, indent=1, sort_keys=True), encoding="ascii")
    summary = write_summary(root)
    checksums(root / EVIDENCE)
    print(json.dumps(summary, indent=1, sort_keys=True))
    print(json.dumps(q6_scan(root / EVIDENCE), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
