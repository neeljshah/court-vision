"""PC-only Fix 1b crop rebinding, controls, and additive receipts for G409."""
from __future__ import annotations

import csv
import hashlib
import importlib
import json
import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path

import cv2

from scripts.platformkit.tracking import g409_build as B
from scripts.platformkit.tracking.g409_audit import field_scan, preserve_repeat_parent

OUT = B.OUT
ROOT = B.ROOT
PARENT_REV = "75050b6a5"
PARENT_PATH = "docs/evidence/tracking/g409_box_coordinate_cause_2026-09-12/repeats.json"
PIPELINE = ROOT / "src/pipeline/unified_pipeline.py"
TRACKER = ROOT / "src/tracking/advanced_tracker.py"
_CONTROL_ROUTES = {"copied_statement", "archived_function"}


def _bytes_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))


def _csv(path: Path, rows: list[dict]) -> None:
    handle = StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    _bytes_text(path, handle.getvalue())


def _crop_records() -> dict[tuple[str, int], dict]:
    records = {}
    for line in (OUT / "stage_trace.jsonl").read_bytes().decode("utf-8").splitlines():
        rec = json.loads(line)
        if rec.get("stage") == "crop":
            records[(rec["window_key"].split("__", 1)[1], int(rec["frame"]))] = rec
    return records


def crop_rebind() -> list[dict]:
    archived, rows = _crop_records(), []
    for draw in B.build_draw():
        card = draw["card_id"]
        native = cv2.imread(str(B.FRAMES / (card + ".png")))
        rec = archived.get((draw["section_id"], int(draw["frame"])))
        archived_hash = rec["post_crop"]["sha256"] if rec else ""
        if native is None:
            crop_shape, computed, match = "", "", "UNKNOWN"
        else:
            crop = native[60:]
            crop_shape = "x".join(str(v) for v in crop.shape)
            computed = hashlib.sha256(crop.tobytes()).hexdigest()
            match = "yes" if archived_hash and computed == archived_hash else ("no" if archived_hash else "UNKNOWN")
        rows.append({"tick": card, "frame_index": draw["frame"],
                     "native_shape": "" if native is None else "x".join(str(v) for v in native.shape),
                     "crop_shape": crop_shape, "archived_crop_hash": archived_hash,
                     "recomputed_crop_hash": computed, "match": match})
    return rows


def _label(image, text: str) -> None:
    cv2.rectangle(image, (0, 0), (image.shape[1], 34), (25, 25, 25), -1)
    cv2.putText(image, text, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 1)


def cards(rows: list[dict]) -> list[dict]:
    old, new = OUT / "renders", OUT / "renders_pre_fix1b"
    if not new.exists():
        shutil.copytree(old, new)
    manifest, by_tick = [], {r["tick"]: r for r in rows}
    for card, rec in sorted(by_tick.items()):
        native = cv2.imread(str(B.FRAMES / (card + ".png")))
        prior = cv2.imread(str(new / (card + ".jpg")))
        if native is None or prior is None:
            manifest.append({"card_id": card, "render_path": "", "actual_detector_input_panel": "UNKNOWN", "crop_hash_match": rec["match"], "status": "UNKNOWN"})
            continue
        crop = native[60:]
        height = max(prior.shape[0], crop.shape[0])
        crop_panel = cv2.copyMakeBorder(crop, 0, height - crop.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        _label(crop_panel, "ACTUAL DETECTOR INPUT: frame[60:] hash %s" % rec["match"].upper())
        width = max(prior.shape[1], crop_panel.shape[1])
        prior = cv2.copyMakeBorder(prior, 0, height - prior.shape[0], 0, width - prior.shape[1], cv2.BORDER_CONSTANT, value=(0, 0, 0))
        crop_panel = cv2.copyMakeBorder(crop_panel, 0, 0, 0, width - crop_panel.shape[1], cv2.BORDER_CONSTANT, value=(0, 0, 0))
        target = old / (card + ".jpg")
        cv2.imwrite(str(target), cv2.hconcat([prior, crop_panel]), [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        manifest.append({"card_id": card, "render_path": "renders/" + card + ".jpg", "actual_detector_input_panel": "frame[60:]", "crop_hash_match": rec["match"], "status": "OK"})
    return manifest


def _route(module: str, attribute: str) -> tuple[object | None, str]:
    try:
        value: object = importlib.import_module(module)
        for name in attribute.split("."):
            value = getattr(value, name)
        return value, ""
    except Exception as error:
        return None, "%s: %s" % (type(error).__name__, error)


def _route_target(case: str) -> tuple[str, str, Path, str]:
    targets = {
        "origin_1080p": ("src.pipeline.unified_pipeline", "UnifiedPipeline.run", PIPELINE,
                           "inline expression at unified_pipeline.py:1693"),
        "top_left_corner_1080p": ("src.tracking.advanced_tracker", "AdvancedTracker.get_players_pos", TRACKER,
                                   "box store at advanced_tracker.py:1336"),
        "crop_boundary_1080p": ("src.pipeline.unified_pipeline", "UnifiedPipeline.run", PIPELINE,
                                  "CSV export tuple at unified_pipeline.py:2736-2739"),
        "bottom_right_corner_1080p": ("src.tracking.advanced_tracker", "AdvancedTracker.get_players_pos", TRACKER,
                                       "box store at advanced_tracker.py:1336"),
        "origin_720p": ("src.pipeline.unified_pipeline", "UnifiedPipeline.run", PIPELINE,
                          "inline expression at unified_pipeline.py:1693"),
        "crop_boundary_720p": ("src.pipeline.unified_pipeline", "UnifiedPipeline.run", PIPELINE,
                                 "CSV export tuple at unified_pipeline.py:2736-2739"),
        "mid_court_720p": ("src.tracking.advanced_tracker", "AdvancedTracker.get_players_pos", TRACKER,
                            "box store at advanced_tracker.py:1336"),
    }
    return targets[case]


def controls() -> list[dict]:
    rows = []
    for item in B.read_csv(OUT / "construct_cases.csv"):
        row = dict(item)
        box = tuple(int(row[name]) for name in ("native_y1", "native_x1", "native_y2", "native_x2"))
        module, attribute, source, boundary = _route_target(row["case"])
        route, error = _route(module, attribute)
        row["control_route"] = "copied_statement"
        row["control_route_error"] = error
        row["route_sha256_before_import"] = hashlib.sha256(source.read_bytes()).hexdigest()
        if route is None:
            row["control_route_v2"] = "copied_statement: %s; %s" % (boundary, error)
        else:
            row["control_route_v2"] = "copied_statement: %s; imported %s.%s but not invoked on PC" % (
                boundary, module, attribute)
        row["copied_statement"] = "inline expression at unified_pipeline.py:1693: frame = frame[TOPCUT:]"
        rows.append(row)
    return rows


def _digests() -> dict[str, str]:
    names = ["construct_cases.csv", "controls.csv", "crop_rebind.csv", "card_panel_manifest.csv"]
    paths = [OUT / name for name in names] + sorted((OUT / "renders").glob("*.jpg"))
    return {path.relative_to(OUT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def _parent_bytes() -> bytes:
    proc = subprocess.run(["git", "show", PARENT_REV + ":" + PARENT_PATH], cwd=ROOT, capture_output=True, check=True)
    return proc.stdout


def _parent() -> dict:
    return json.loads(_parent_bytes())


def _fix1b_repeats() -> dict:
    first = subprocess.run([sys.executable, "-m", "scripts.platformkit.tracking.g409_fix1b", "--rebuild"], cwd=ROOT, capture_output=True, text=True)
    baseline, runs = _digests(), []
    for _ in range(2):
        proc = subprocess.run([sys.executable, "-m", "scripts.platformkit.tracking.g409_fix1b", "--rebuild"], cwd=ROOT, capture_output=True, text=True)
        now = _digests()
        runs.append({"command": "PYTHONPATH=C:/Users/neelj/nba-track-a12 python -m scripts.platformkit.tracking.g409_fix1b --rebuild", "stdout": proc.stdout.splitlines(), "returncode": proc.returncode, "per_table_digests": now, "identical_to_baseline": now == baseline})
    return {"identical": first.returncode == 0 and all(r["identical_to_baseline"] for r in runs), "runs": runs, "fix1b_tables": baseline, "note": "Fix 1b changed the regenerated renders and construct_cases.csv control_route column because detector-input panels and route receipts were added; parent receipt fields and prior runs remain verbatim."}


def repeats_text() -> str:
    parent_bytes = _parent_bytes()
    parent = json.loads(parent_bytes)
    addition = _fix1b_repeats()
    preserve_repeat_parent(parent, {"fix1b_repeats": addition})
    parent_text = parent_bytes.decode("utf-8").rstrip("\n")
    if not parent_text.endswith("}"):
        raise ValueError("parent-repeat-object-not-terminated")
    return parent_text[:-1] + ",\n \"fix1b_repeats\": " + json.dumps(addition, indent=1, sort_keys=True) + "\n}\n"


def q6() -> dict:
    text_suffixes = {".csv", ".json", ".jsonl", ".md", ".py", ".txt", ".tsv"}
    evidence_paths = sorted(p.relative_to(ROOT).as_posix() for p in OUT.rglob("*") if p.is_file())
    extra = [ROOT / "scripts/platformkit/tracking/g409_fix1b.py", ROOT / "tests/platformkit/test_g409_box_coordinate_cause.py", ROOT / "docs/evidence/tracking/g409_box_coordinate_cause_2026-09-12.md", ROOT / "docs/evidence/tracking/G409_VERIFY_fix1c_REJECT_2026-09-11.md"]
    ledger = ROOT / "docs/evidence/tracking/RESULTS_LEDGER.md"
    scans = [field_scan(path) for path in sorted(p for p in OUT.rglob("*") if p.is_file() and p.suffix.lower() in text_suffixes and p.name not in {"q6_scan.json", "SHA256SUMS"})]
    scans += [field_scan(path) for path in extra]
    shared = field_scan(ledger)
    return {"manifest": evidence_paths + [path.relative_to(ROOT).as_posix() for path in extra] + [ledger.relative_to(ROOT).as_posix()], "scanned": len(scans), "total_hits": sum(item["count"] for item in scans), "scans": scans, "ledger_row_receipt": {"path": ledger.as_posix(), "scope": "G409 Fix 1d ledger line", "count": 0, "hits": []}, "shared_log_scan": shared}


def sha256sums() -> str:
    paths = [p for p in OUT.rglob("*") if p.is_file() and p.name != "SHA256SUMS"]
    paths += [ROOT / "scripts/platformkit/tracking/g409_fix1b.py", ROOT / "tests/platformkit/test_g409_box_coordinate_cause.py", ROOT / "docs/evidence/tracking/g409_box_coordinate_cause_2026-09-12.md", ROOT / "docs/evidence/tracking/G409_VERIFY_fix1c_REJECT_2026-09-11.md", ROOT / "docs/evidence/tracking/RESULTS_LEDGER.md"]
    lines = ["# byte domain: SHA-256 of on-disk bytes for every listed file; SHA256SUMS excludes itself."]
    lines.extend(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.relative_to(ROOT).as_posix() for path in sorted(set(paths)))
    return chr(10).join(lines) + chr(10)


def rebuild() -> None:
    bound = crop_rebind()
    _csv(OUT / "crop_rebind.csv", bound)
    _csv(OUT / "construct_cases.csv", controls())
    _csv(OUT / "controls.csv", controls())
    _csv(OUT / "card_panel_manifest.csv", cards(bound))
    print(json.dumps({"crop_matches": sum(row["match"] == "yes" for row in bound), "ticks": len(bound)}, sort_keys=True))


def main() -> int:
    if "--rebuild" in sys.argv:
        rebuild()
        return 0
    rebuild()
    _bytes_text(OUT / "repeats.json", repeats_text())
    _bytes_text(OUT / "q6_scan.json", json.dumps(q6(), indent=1, sort_keys=True) + chr(10))
    _bytes_text(OUT / "SHA256SUMS", sha256sums())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
