"""Build every G403 evidence artifact from the landed G400 archives (no new rating)."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from scripts.platformkit.tracking import g403_package
from scripts.platformkit.tracking import g403_replay as replay

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/evidence/tracking/g403_ball_rater_failure_controls_2026-09-11"
G400_REL = ROOT / "docs/evidence/tracking/g400_ball_reference_growth_stage1_2026-09-11"
G400_MAIN = Path("C:/Users/neelj/nba-ai-system/docs/evidence/tracking/g400_ball_reference_growth_stage1_2026-09-11")
SHEETS = Path("C:/Users/neelj/g400_receiver/sheets")
EXPECTED = {"sealed_keys": 300, "raw_answers": 600, "archives": 20, "pooled_pairs": 299,
            "pooled_kappa": 0.7505, "round8_kappa": 0.3605, "round8_n": 30, "round1_n": 29,
            "both_visible_pairs": 125, "median_centre_gap_px": 24.021, "p90_centre_gap_px": 292.139,
            "gaps_over_100_px": 29, "valid_visible_diameters": 288, "conflicts": 115,
            "redaction_records": 8}


def digest(path: Path) -> str:
    """SHA-256 over LF-normalized bytes for text, exact bytes for images."""
    raw = path.read_bytes()
    if path.suffix.lower() in {".png", ".jpg"}:
        return hashlib.sha256(raw).hexdigest()
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Mapping[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(header), lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: ("" if row.get(key) is None else row.get(key)) for key in header})
    return path


def write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="ascii", newline="\n")
    return path


def g400_dir() -> Path:
    return G400_REL if G400_REL.is_dir() else G400_MAIN


def build() -> dict[str, object]:
    """Run the whole replay, diagnostic and control build; return the summary payload."""
    source = g400_dir()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    dims = replay.native_dims(source / "native_manifest.csv")
    order = replay.plan_order(source / "batch_plan.csv")
    answers = replay.load_all(source / "rater_raw", dims, order)
    index = replay.paired_labels(answers)
    binding = replay.archive_binding(answers, order)

    write_csv(EVIDENCE / "input_hashes.csv", ("path", "role", "sha256", "bytes"), [
        {"path": path.as_posix(), "role": role, "sha256": digest(path), "bytes": path.stat().st_size}
        for role, path in ([("g400_table", source / name) for name in
                            ("ratings.csv", "ratings_terra.csv", "ratings_sol.csv", "kappa.csv",
                             "batch_plan.csv", "native_manifest.csv", "conflict_index.csv",
                             "adjudications.csv", "resolutions.csv", "usability.json", "summary.json",
                             "box_audit.csv", "q6_redaction_manifest.csv")]
                           + [("g400_batch_receipt", source / "batch_receipts.csv")]
                           + [("g400_sheet_object", p) for p in sorted(SHEETS.glob("*.jpg"))]
                           + [("g400_raw_archive", p) for p in sorted((source / "rater_raw").glob("*.txt"))]
                           + [("g400_conflict_render", p) for p in sorted((source / "renders").glob("conflict_zoom_*.jpg"))]
                           + [("g389_baseline", ROOT / "docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/dev_boxes_v3.csv"),
                              ("g403_prereg", EVIDENCE / "prereg.md"),
                              ("g403_amendment", EVIDENCE / "amendment_A1.md")])])

    duplicates = sorted({key for rater in binding for key in binding[rater]["duplicate_ids"]})
    write_csv(EVIDENCE / "answer_binding.csv",
              ("archive", "line", "rater", "round", "position", "frame_key", "label", "label_status",
               "box_status", "in_native_frame", "box_x", "box_y", "box_w", "box_h", "cx", "cy",
               "diameter", "width", "height", "duplicate_id", "reason_present"),
              [{"archive": a.archive, "line": a.line, "rater": a.rater, "round": a.round_id,
                "position": a.position, "frame_key": a.frame_key, "label": a.label,
                "label_status": a.label_status, "box_status": a.box_status,
                "in_native_frame": int(a.in_frame),
                "box_x": None if a.box is None else a.box[0], "box_y": None if a.box is None else a.box[1],
                "box_w": None if a.box is None else a.box[2], "box_h": None if a.box is None else a.box[3],
                "cx": a.cx, "cy": a.cy, "diameter": a.diameter, "width": a.width, "height": a.height,
                "duplicate_id": int(a.frame_key in duplicates), "reason_present": int(bool(a.reason.strip()))}
               for a in answers])

    redactions = replay.read_rows(source / "q6_redaction_manifest.csv")
    delivered = {who: {row["frame_key"]: row for row in replay.read_rows(source / ("ratings_%s.csv" % who))}
                 for who in ("terra", "sol")}
    parity = []
    for record in redactions:
        target = source / record["file"]
        semantic = "NOT_APPLICABLE"
        if record["file"].startswith("rater_raw/"):
            who = "terra" if "terra" in record["file"] else "sol"
            mine = [a for a in answers if a.archive == Path(record["file"]).name]
            match = all(delivered[who][a.frame_key]["label"] == a.label for a in mine)
            semantic = "MATCH" if match else "MISMATCH"
        parity.append({"file": record["file"], "sha256_after_manifest": record["sha256_after"],
                       "sha256_on_disk": digest(target) if target.exists() else "MISSING",
                       "digest_match": int(target.exists() and digest(target) == record["sha256_after"]),
                       "replacement": record["replacement"], "semantic_fields": semantic,
                       "parsed_rows": len([a for a in answers if a.archive == Path(record["file"]).name])})
    write_csv(EVIDENCE / "semantic_parity.csv",
              ("file", "sha256_after_manifest", "sha256_on_disk", "digest_match", "replacement",
               "semantic_fields", "parsed_rows"), parity)

    rounds = []
    for round_id in list(range(1, 11)) + [None]:
        pairs, terra_missing, sol_missing = replay.round_pairs(index, order, round_id)
        row = {"round": "POOLED" if round_id is None else round_id}
        row.update(replay.confusion(pairs))
        row.update({"terra_missing": terra_missing, "sol_missing": sol_missing,
                    "kappa_4dp": round(row["kappa"], 4), "bar": 0.6,
                    "verdict": "PASS" if round(row["kappa"], 4) >= 0.6 else "FAIL"})
        if row["paired_n"] < 30 or round_id is None and row["paired_n"] < 300:
            row["verdict"] = "INCOMPLETE"
        rounds.append(row)
    write_csv(EVIDENCE / "confusion_by_round.csv",
              ("round", "paired_n", "n_VIS_VIS", "n_VIS_ABS", "n_VIS_UNK", "n_ABS_VIS", "n_ABS_ABS",
               "n_ABS_UNK", "n_UNK_VIS", "n_UNK_ABS", "n_UNK_UNK", "terra_VIS", "terra_ABS", "terra_UNK",
               "sol_VIS", "sol_ABS", "sol_UNK", "observed_agreement", "expected_agreement", "kappa",
               "kappa_4dp", "bar", "verdict", "terra_missing", "sol_missing"), rounds)

    gaps = replay.centre_gaps(index, order)
    write_csv(EVIDENCE / "gaps.csv",
              ("frame_key", "round", "position", "width", "height", "terra_cx", "terra_cy", "terra_d",
               "sol_cx", "sol_cy", "sol_d", "gap_px"), gaps)
    gap_values = [math.hypot(index[row["frame_key"]]["terra"].cx - index[row["frame_key"]]["sol"].cx,
                             index[row["frame_key"]]["terra"].cy - index[row["frame_key"]]["sol"].cy)
                  for row in gaps]

    diameters = [{"archive": a.archive, "line": a.line, "rater": a.rater, "round": a.round_id,
                  "frame_key": a.frame_key, "width": a.width, "height": a.height, "box_w": a.box[2],
                  "box_h": a.box[3], "diameter": a.diameter, "cx": a.cx, "cy": a.cy,
                  "usable": int(a.usable_visible),
                  "exclusion": "" if a.usable_visible else "CENTRE_OUTSIDE_NATIVE_FRAME"}
                 for a in answers if a.label == "VISIBLE" and a.box is not None]
    write_csv(EVIDENCE / "diameter_population.csv",
              ("archive", "line", "rater", "round", "frame_key", "width", "height", "box_w", "box_h",
               "diameter", "cx", "cy", "usable", "exclusion"), diameters)
    usable_d = sorted(float(row["diameter"]) for row in diameters if row["usable"])

    invalid_keys = {a.frame_key for a in answers if a.label == "VISIBLE" and not a.usable_visible}
    summary = g403_package.build_package(source, EVIDENCE, SHEETS, {
        "write_csv": write_csv, "digest": digest, "answers": answers, "index": index, "order": order,
        "rounds": rounds, "gaps": gaps, "gap_values": gap_values, "usable_d": usable_d,
        "invalid_keys": invalid_keys, "duplicates": duplicates, "binding": binding,
        "redactions": redactions, "expected": EXPECTED})
    write_json(EVIDENCE / "summary.json", summary)
    print("G403_BUILD premise_all_match=%d answers=%d conflicts=%d controls=%d"
          % (summary["premise_all_match"], summary["premise_measured"]["raw_answers"],
             summary["premise_measured"]["conflicts"], summary["controls_total"]))
    return summary


def _artifact_digests() -> dict[str, str]:
    return {path.relative_to(EVIDENCE).as_posix(): digest(path)
            for path in sorted(EVIDENCE.rglob("*")) if path.is_file()
            and not any(part.startswith("pre_fix") for part in path.parts)
            and path.name not in {"repeats.json", "SHA256SUMS", "q6_scan.json"}}


def repeat() -> None:
    """Reproduce every table and render twice in fresh processes; parent receipt shape."""
    runs = []
    for attempt in (1, 2):
        completed = subprocess.run([sys.executable, "-m", "scripts.platformkit.tracking.g403_build", "build"],
                                   cwd=ROOT, capture_output=True, text=True)
        runs.append({"attempt": attempt, "module": "g403_build.build", "returncode": completed.returncode,
                     "stdout": completed.stdout.strip(), "digests": _artifact_digests()})
    identical = runs[0]["digests"] == runs[1]["digests"]
    write_json(EVIDENCE / "repeats.json",
               {"identical": identical, "runs": runs, "tables": sum(1 for name in runs[0]["digests"] if name.endswith(".csv")),
                "renders": sum(1 for name in runs[0]["digests"] if name.startswith("renders/"))})
    print("G403_REPEAT identical=%d returncodes=%s" % (int(identical), [run["returncode"] for run in runs]))


def seal() -> None:
    """Scan every landable text artifact, then write SHA256SUMS with its byte domain."""
    from scripts.platformkit.tracking.g403_q6_scan import scan
    texts = [path for path in sorted(EVIDENCE.rglob("*"))
             if path.is_file() and (path.suffix.lower() in {".csv", ".json", ".md", ".txt"}
                                  or path.name == "SHA256SUMS")
             and not any(part.startswith("pre_fix") for part in path.parts)]
    texts.append(ROOT / "docs/evidence/tracking/g403_ball_rater_failure_controls_2026-09-11.md")
    texts.extend(ROOT / value for value in (
        "scripts/platformkit/tracking/g403_build.py",
        "scripts/platformkit/tracking/g403_contract.py",
        "scripts/platformkit/tracking/g403_controls.py",
        "scripts/platformkit/tracking/g403_diagnose.py",
        "scripts/platformkit/tracking/g403_package.py",
        "scripts/platformkit/tracking/g403_prereg.py",
        "scripts/platformkit/tracking/g403_q6_scan.py",
        "scripts/platformkit/tracking/g403_render.py",
        "scripts/platformkit/tracking/g403_replay.py",
        "tests/platformkit/test_g403_ball_rater_controls.py",
        "docs/evidence/tracking/RESULTS_LEDGER.md"))
    write_json(EVIDENCE / "q6_scan.json", scan(texts, ROOT))
    lines = ["# byte domain: SHA-256 over LF-normalized bytes for .csv/.json/.md/.txt (this checkout "
             "has core.autocrlf true) and over exact on-disk bytes for .png/.jpg; paths are relative "
             "to the repository root"]
    targets = [path for path in sorted(EVIDENCE.rglob("*"))
               if path.is_file() and path != EVIDENCE / "SHA256SUMS"]
    targets.append(ROOT / "docs/evidence/tracking/g403_ball_rater_failure_controls_2026-09-11.md")
    for path in targets:
        lines.append("%s  %s" % (digest(path), path.relative_to(ROOT).as_posix()))
    (EVIDENCE / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")
    print("G403_SEAL files=%d" % len(targets))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "build"
    {"build": build, "repeat": repeat, "seal": seal}[mode]()
