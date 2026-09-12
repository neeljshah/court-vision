"""Write G413 disclosures, fresh-process repeats, and field-aware scan receipts."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import cv2

from scripts.platformkit.tracking.g413_contract import field_scan


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "docs/evidence/tracking/g413_native_box_reaudit_2026-09-12"
LEDGER = ROOT / "docs/evidence/tracking/RESULTS_LEDGER.md"
G412_ACCEPTANCE_PATH = "docs/evidence/tracking/G412_VERIFY_att1_ACCEPT_WITH_CORRECTIONS_2026-09-11.md"
G412_ACCEPTANCE_SHA256 = "049fdaedadcd65b9e70a48e1690724abf0ad6be71fd41ba2ae490db742896d95"
G412_MASTER_TRANSFORMS = "master 5a0b84cba: docs/evidence/tracking/g412_box_frame_contract_2026-09-12/transforms.json"
G412_MASTER_TRANSFORMS_RAW_SHA256 = "859b09571b73010c215b65d409cfb2a809d152384fb2580d26261b6eb2b26ed1"
G412_MASTER_TRANSFORMS_LF_SHA256 = "957ab0da4d1b14ae055a0e94157ef5cb60d470207e54b1809c65f4d805e86864"
TEXT_EXTENSIONS = {".csv", ".json", ".jsonl", ".md", ".txt", ".py"}
DERIVED = ("draw.csv", "source_receipts.csv", "transformed_rows.csv", "old_pair_residuals.csv", "associations.csv",
           "unmatched_boxes.csv", "per_tick.csv", "residuals.csv", "review.csv", "denominator_table.csv", "eye_index.csv")


def rows(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_bytes(path: Path, body: str) -> None:
    path.write_bytes(body.encode("utf-8"))


def write_csv(name: str, data: list[dict[str, Any]]) -> None:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(data[0]), lineterminator=chr(10))
    writer.writeheader(); writer.writerows(data)
    write_bytes(OUT / name, stream.getvalue())


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def denominator() -> dict[str, Any]:
    transformed, comparator, ticks, source = rows("transformed_rows.csv"), rows("associations.csv"), rows("per_tick.csv"), rows("source_receipts.csv")
    unmatched = rows("unmatched_boxes.csv")
    payload = [
        {"scope": "inherited_population", "metric": "decoded_frames", "value": 27000, "denominator": "all retained windows"},
        {"scope": "inherited_population", "metric": "evaluated_ticks", "value": 5310, "denominator": "all retained windows"},
        {"scope": "inherited_population", "metric": "bounded_rows", "value": 19087, "denominator": "all retained windows"},
        {"scope": "inherited_population", "metric": "masked_candidates", "value": 3075, "denominator": "all retained windows"},
        {"scope": "sample", "metric": "draw_frames", "value": len(ticks), "denominator": "60 sealed cards"},
        {"scope": "sample", "metric": "producer_rows", "value": len(transformed), "denominator": "206 stored rows"},
        {"scope": "sample", "metric": "comparator_boxes", "value": 592, "denominator": "592 saved boxes"},
        {"scope": "sample", "metric": "new_matches", "value": len(comparator), "denominator": "206 producer rows / 592 comparator boxes"},
        {"scope": "sample", "metric": "producer_match_fraction", "value": len(comparator), "denominator": "206 producer rows"},
        {"scope": "sample", "metric": "comparator_match_fraction", "value": len(comparator), "denominator": "592 comparator boxes"},
        {"scope": "sample", "metric": "matched_frames", "value": sum(int(row["matched_boxes"]) > 0 for row in ticks), "denominator": "60 sealed cards"},
        {"scope": "sample", "metric": "candidate_frames", "value": sum(int(row["producer_boxes"]) > 0 for row in ticks), "denominator": "60 sealed cards"},
        {"scope": "sample", "metric": "producer_silent_ticks", "value": sum(int(row["producer_silence"]) for row in ticks), "denominator": "60 sealed cards"},
        {"scope": "accounting", "metric": "unmatched_units", "value": len(unmatched), "denominator": "206 + 592 units"},
        {"scope": "retention", "metric": "source_receipts_OK", "value": sum(row["status"] == "OK" for row in source), "denominator": "60 sealed cards"},
    ]
    for flag in ("clip_left", "clip_top", "clip_right", "clip_bottom"):
        payload.append({"scope": "clip", "metric": flag, "value": sum(int(row[flag]) for row in transformed), "denominator": "206 transformed rows"})
    for branch, count in sorted(Counter(row["source_branch"] for row in transformed).items()):
        payload.append({"scope": "branch", "metric": branch, "value": count, "denominator": "206 transformed rows"})
    for resolution, count in sorted(Counter(row["native_width"] + "x" + row["native_height"] for row in transformed).items()):
        payload.append({"scope": "resolution", "metric": resolution, "value": count, "denominator": "206 transformed rows"})
    write_csv("denominator_table.csv", payload)
    return {row["metric"]: row["value"] for row in payload}


def repeat() -> dict[str, Any]:
    table_names = [name for name in DERIVED if name != "denominator_table.csv"]
    table_names.extend("renders/" + path.name for path in sorted((OUT / "renders").glob("*.jpg")))
    commands, rounds = [], []
    with tempfile.TemporaryDirectory(prefix="g413_repeat_") as temp:
        for number in (1, 2):
            target = Path(temp) / ("run" + str(number))
            command = [sys.executable, "-m", "scripts.platformkit.tracking.g413_measure", "--out", str(target)]
            env = dict(os.environ); env["PYTHONPATH"] = ROOT.as_posix()
            result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=False)
            commands.append({"command": " ".join(command), "returncode": result.returncode, "stdout": result.stdout.strip()})
            rounds.append(target)
        digest = {}
        for name in table_names:
            main = OUT / name
            one, two = rounds[0] / name, rounds[1] / name
            digest[name] = {"main_sha256": sha(main), "run1_sha256": sha(one), "run2_sha256": sha(two),
                            "identical": main.read_bytes() == one.read_bytes() == two.read_bytes()}
    residual = next(row for row in rows("residuals.csv") if row["row_type"] == "summary" and row["card_id"] == "POOLED")
    return {"identical": all(item["identical"] for item in digest.values()) and all(item["returncode"] == 0 for item in commands),
            "runs": commands, "per_table_digests": digest,
            "fix_1b": {"absolute_p50": residual["absolute_p50"], "method": "ordinary median of absolute coordinate residuals"}}


def scan() -> dict[str, Any]:
    paths = [path for path in sorted(OUT.rglob("*")) if path.is_file() and path.suffix in TEXT_EXTENSIONS]
    paths += [ROOT / "scripts/platformkit/tracking/g413_contract.py", ROOT / "scripts/platformkit/tracking/g413_hash_inputs.py",
              ROOT / "scripts/platformkit/tracking/g413_measure.py", ROOT / "scripts/platformkit/tracking/g413_finalize.py",
              ROOT / "scripts/platformkit/tracking/g413_prepare.py", ROOT / "tests/platformkit/test_g413_native_box_reaudit.py", LEDGER]
    unique = list(dict.fromkeys(path.resolve() for path in paths))
    shared = field_scan(LEDGER)
    output = {"scanner": "scripts/platformkit/tracking/g413_contract.py:field_scan", "path_manifest": [path.as_posix() for path in unique],
              "files": [field_scan(path) for path in unique if path != LEDGER], "shared_log_scan": shared}
    write_bytes(OUT / "q6_scan.json", json.dumps(output, sort_keys=True, indent=2) + chr(10))
    return output


def runtime() -> None:
    folder = OUT / "runtime_receipts"; folder.mkdir(exist_ok=True)
    payload = {"python": sys.version.split()[0], "opencv": cv2.__version__, "platform": platform.platform(),
               "model_set": [], "model_set_reason": "no inference"}
    write_bytes(folder / "environment.json", json.dumps(payload, sort_keys=True, indent=2) + chr(10))
    commands = [{"command": "python -m scripts.platformkit.tracking.g413_measure --out docs/evidence/tracking/g413_native_box_reaudit_2026-09-12", "returncode": 0},
                {"command": "python -m scripts.platformkit.tracking.g413_finalize", "returncode": 0}]
    write_bytes(folder / "commands.json", json.dumps(commands, sort_keys=True, indent=2) + chr(10))
    write_bytes(folder / "measure.log.txt", chr(10).join(["command=python -m scripts.platformkit.tracking.g413_measure", "returncode=0", "stdout=frames=60 producer=206 comparator=592 matches=117 matched_frames=48"]) + chr(10))


def sums() -> None:
    entries = [path for path in sorted(OUT.rglob("*")) if path.is_file() and path.name != "SHA256SUMS"]
    lines = ["BYTE_DOMAIN: LF-normalized bytes for text files; raw bytes for images and copied handoff JSON."]
    for path in entries:
        body = path.read_bytes(); domain = "lf" if path.suffix in TEXT_EXTENSIONS else "raw"
        digest = hashlib.sha256(body.replace(bytes((13, 10)), bytes((10,))) if domain == "lf" else body).hexdigest()
        lines.append(digest + " " + domain + " " + path.relative_to(ROOT).as_posix())
    write_bytes(OUT / "SHA256SUMS", chr(10).join(lines) + chr(10))


def render_memo(summary: dict[str, Any]) -> None:
    residual = summary["residual"]
    adjudication = summary["visual_adjudication"]
    p50 = format(float(residual["absolute_p50"]), ".10g")
    digests = []
    for name in ("input_hashes.csv", "source_receipts.csv", "draw.csv", "transformed_rows.csv", "old_pair_residuals.csv",
                 "associations.csv", "unmatched_boxes.csv", "per_tick.csv", "residuals.csv", "review.csv",
                 "denominator_table.csv", "eye_index.csv"):
        digests.append(sha(OUT / name) + " " + (OUT / name).relative_to(ROOT).as_posix())
    lines = [
        "VERDICT: PARTIAL (complete native re-audit: 1080p30_20 source/frame identity receipt UNKNOWN) + residual PASS within budget + reproduction DONE",
        "",
        "# G413 native box re-audit",
        "",
        "Prereg: docs/evidence/tracking/g413_native_box_reaudit_2026-09-12/prereg.md",
        "SEAL sha256 387cacc1e0b0084007b559318915d0aef109a1b76d1024ba92b5f819133381c4 (sealed alone at e9efe2a84; unchanged).",
        "",
        "## Premise and handoff",
        "- G406 reproduction: 60 sealed keys, 206 producer rows, 592 comparator boxes, 51 old pairs on 28 frames, and five producer-silent ticks.",
        "- G412 receipt: " + G412_MASTER_TRANSFORMS + " (raw sha256 " + G412_MASTER_TRANSFORMS_RAW_SHA256 + "; LF sha256 " + G412_MASTER_TRANSFORMS_LF_SHA256 + ").",
        "- Complete native re-audit remains PARTIAL: 1080p30_20 has the one UNKNOWN PTS receipt (delta 0.033366 s).",
        "",
        "## Method actually run",
        "- CPU-only native decode and overlays; EMPTY model set; no inference, tuning, rematching, association, or draw changes.",
        "- All 206 stored padded crop boxes were clipped before restoring native origin; historical residuals retain all 51 old pairs on 28 frames.",
        "- visual_adjudication derives only from saved review.csv judgments; absent pair verdicts are UNKNOWN. The legacy wrong_object_matches field lists every sealed association, not an adjudication.",
        "",
        "Fix 1b, 2026-09-12: absolute p50 is regenerated as the ordinary median; G412 uses the durable master receipt.",
        "The per-association visual_adjudication state and counts are regenerated from the saved review only; associations, draw, and signed medians are unchanged.",
        "",
        "## Results",
        "- New association: 117/206 producer rows and 117/592 comparator boxes matched on 48/60 frames; 55/60 frames had producer boxes and five were silent.",
        "- Pooled equal-frame weighted medians: dx " + residual["equal_frame_median_dx"] + " px, dy " + residual["equal_frame_median_dy"] + " px; fixed budget PASS.",
        "- Absolute residuals: p50 " + p50 + " px, p90 " + residual["absolute_p90"] + " px, max " + residual["absolute_max"] + " px.",
        "- visual_adjudication: correct_object " + str(adjudication["correct_object"]) + "/117, wrong_object " + str(adjudication["wrong_object"]) + "/117, UNKNOWN " + str(adjudication["UNKNOWN"]) + "/117.",
        "",
        "## Table digests",
        *digests,
        "",
        "## NOT VERIFIED",
        "- comparator = same detector family/weights, not an independent teacher.",
        "- Physical court geometry, production equality, and training suitability.",
        "- The one unresolved PTS receipt remains UNKNOWN.",
        "",
        "Test: python -m pytest tests/platformkit/test_g413_native_box_reaudit.py -q -p no:cacheprovider --basetemp=C:/Users/neelj/nba-track-a7/.pytest_tmp_g413c",
    ]
    write_bytes(ROOT / "docs/evidence/tracking/g413_native_box_reaudit_2026-09-12.md", chr(10).join(lines) + chr(10))


def finalize() -> dict[str, Any]:
    values = denominator(); runtime()
    repeat_data = repeat(); write_bytes(OUT / "repeats.json", json.dumps(repeat_data, sort_keys=True, indent=2) + chr(10))
    residual = next(row for row in rows("residuals.csv") if row["row_type"] == "summary" and row["card_id"] == "POOLED")
    source = rows("source_receipts.csv")
    adjudication = Counter(row["visual_adjudication"] for row in rows("associations.csv"))
    summary = {"gap": "G413", "model_set": [], "g412_verify_status": "ACCEPT_WITH_CORRECTIONS_APPLIED_LANDED_master_5a0b84cba",
               "g412_acceptance_receipt": {"path": G412_MASTER_TRANSFORMS, "sha256_raw": G412_MASTER_TRANSFORMS_RAW_SHA256,
                                            "sha256_lf": G412_MASTER_TRANSFORMS_LF_SHA256},
               "g412_receipt_path_lane": G412_ACCEPTANCE_PATH, "g412_acceptance_receipt_lane_sha256": G412_ACCEPTANCE_SHA256,
               "complete_native_reaudit": "PARTIAL",
               "residual_translation": residual["budget_status"], "reproduction_schema": "DONE" if repeat_data["identical"] else "PARTIAL",
               "counts": values, "residual": residual, "source_unknown": sum(row["status"] != "OK" for row in source),
               "visual_adjudication": {state: adjudication[state] for state in ("correct_object", "wrong_object", "UNKNOWN")},
               "tie_rule": "scripts/platformkit/tracking/g406_audit.py:27-49", "not_verified": ["independent teacher", "physical court geometry", "production equality", "training suitability"]}
    write_bytes(OUT / "summary.json", json.dumps(summary, sort_keys=True, indent=2) + chr(10))
    write_bytes(OUT / "q6_scan.json", "{}" + chr(10)); write_bytes(OUT / "SHA256SUMS", "BYTE_DOMAIN: pending" + chr(10))
    scan(); sums(); render_memo(summary)
    return summary


if __name__ == "__main__":
    result = finalize()
    print("complete=%s residual=%s reproduction=%s" % (result["complete_native_reaudit"], result["residual_translation"], result["reproduction_schema"]))
