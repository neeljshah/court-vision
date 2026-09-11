"""G398 pod driver: premise receipts and the single paired DEV shadow launch.

Sealed by docs/evidence/tracking/g398_a8_high_resolution_dev_shadow_2026-09-11/
preregistration.md. Baseline and candidate share one archived A8 checkpoint and
one argument set; only imgsz differs. Held-out pixels are never opened.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, "/workspace/wt/a11")

from scripts.platformkit.tracking.g398_prepare import (  # noqa: E402
    assert_heldout_isolation, charge_paired_launch, validate_dev_inputs,
    verify_preregistration)

LANE = Path("/workspace/wt/a11")
SCRATCH = Path("/workspace/g398_scratch")
SHEETS = Path("/workspace/g373_scratch/sheets_v2")
TRACKING = LANE / "docs/evidence/tracking"
G389 = TRACKING / "g389_ball_reference_completion_2026-09-11"
OUT = TRACKING / "g398_a8_high_resolution_dev_shadow_2026-09-11"
MANIFEST = TRACKING / "g373_ball_detector_v2_2026-09-10/sheet_manifest_all.csv"
WEIGHTS = SCRATCH / "a8_final_epoch.pt"
G394_SCORES = ("85a91a9f3:docs/evidence/tracking/"
               "g394_ball_person_negatives_2026-09-11/paired_frame_scores.csv")

SEALED_HASHES = {
    "frames_v3.csv": "11797e162dd303441a7bde18e66fae4b404341fa2bd611678226182258d58945",
    "reference_v3.csv": "ad00670c3601706d5d817de734fc85d82e8fdc379ea03b21bbe1a46e272ad09e",
    "dev_boxes_v3.csv": "e151f932c3b4bffe84c89aa8fde18f08c346a1e3a6e65d27ed4b36f095b7b4fa",
}
A8_DIGEST = "0f05a61618687bda2005ce4ac8343c5987f60ba0076245597de59f7380398762"
G394_COUNTS = {"A0": [0, 8, 302], "A8": [90, 169, 212], "A10": [84, 156, 218]}
BASE_INFER = dict(conf=0.05, iou=0.70, max_det=300, agnostic_nms=False, half=True,
                  device=0, augment=False, visualize=False, verbose=False)
ARMS = {"A8_IMG960": 960, "A8_IMG1920": 1920}
BINS = 30
DEADLINE_SECONDS = 3600.0
PRED_FIELDS = ("arm", "inherits", "split", "frame_key", "rank", "x", "y", "w", "h",
               "score", "tick_history", "source", "imgsz", "conf")
TIMING_FIELDS = ("bin", "position", "arm", "imgsz", "keys", "elapsed_seconds",
                 "ms_per_key", "peak_reserved_bytes")
MANIFEST_FIELDS = ("frame_key", "game", "section", "frame_index", "width", "height",
                   "sheet_scale", "label", "cx", "cy", "diameter", "decided_by",
                   "in_dev_boxes", "sheet", "sheet_sha256")


def rows(path: Path) -> list[dict[str, str]]:
    """Read one bounded CSV input."""
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path) -> str:
    """Hash one bounded file without loading unrelated stores."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, fields: tuple[str, ...], records: list[dict]) -> None:
    """Write one ASCII CSV artifact with a fixed field order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def write_json(path: Path, payload: dict) -> None:
    """Persist one ASCII JSON artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                    encoding="ascii", newline="\n")


def sheet(frame_key: str) -> Path:
    """Native 1920x1080 sheet for one frame key."""
    return SHEETS / (frame_key[:12] + ".jpg")


def reproduce_g394() -> dict[str, list[int]]:
    """Recount the 549 held-out targets from the landed G394 per-frame table."""
    text = subprocess.run(["git", "show", G394_SCORES], cwd=str(LANE), check=True,
                          capture_output=True).stdout.decode("ascii")
    counts: dict[str, list[int]] = {}
    for row in csv.DictReader(text.splitlines()):
        entry = counts.setdefault(row["arm"], [0, 0, 0, 0])
        entry[0] += int(row["tp"])
        entry[1] += int(row["fp"])
        entry[3] += 1
        if row["label"] == "VISIBLE":
            entry[2] += 1
    result = {arm: [v[0], v[1], v[2] - v[0], v[3]] for arm, v in counts.items()}
    for arm, expected in G394_COUNTS.items():
        if result.get(arm, [0])[:3] != expected or result[arm][3] != 549:
            raise ValueError("g394-count-reproduction-failed-" + arm)
    return result


def weight_receipt() -> dict[str, object]:
    """Hash the archived A8 bytes and read the checkpoint archive back."""
    digest = sha256_file(WEIGHTS)
    if digest != A8_DIGEST:
        raise ValueError("a8-weight-digest-mismatch")
    with zipfile.ZipFile(WEIGHTS) as archive:
        members = archive.namelist()
        readback = sum(len(archive.read(name)) for name in members)
    return {"path": WEIGHTS.as_posix(), "sha256": digest,
            "bytes": WEIGHTS.stat().st_size, "zip_members": len(members),
            "zip_readback_bytes": readback,
            "source": "/workspace/wt/a7/.g394_scratch/a8_final_epoch.pt"}


def premise() -> tuple[list[dict[str, str]], dict[str, object]]:
    """Step 0: identities, split isolation, saved-count reproduction, receipts."""
    seal = verify_preregistration(OUT / "preregistration.md")
    hashes = {name: sha256_file(G389 / name) for name in SEALED_HASHES}
    if hashes != SEALED_HASHES:
        raise ValueError("sealed-input-hash-mismatch")
    frames = rows(G389 / "frames_v3.csv")
    reference = {row["frame_key"]: row for row in rows(G389 / "reference_v3.csv")}
    boxes = rows(G389 / "dev_boxes_v3.csv")
    coverage = validate_dev_inputs(frames, list(reference.values()), boxes)
    dev = [row for row in frames if row["split"] == "development"]
    held = [row for row in frames if row["split"] == "heldout"]
    assert_heldout_isolation(dev, held)
    box_keys = {row["frame_key"] for row in boxes}
    held_keys = {row["frame_key"] for row in held}
    sheets = {row["frame_key"]: row for row in rows(MANIFEST)}
    order = sorted(dev, key=lambda row: (row["game"], row["section"],
                                         int(row["frame_index"]), row["frame_key"]))
    manifest = []
    for row in order:
        key = row["frame_key"]
        path = sheet(key)
        digest = sha256_file(path)
        if digest != sheets[key]["sheet_sha256"]:
            raise ValueError("sheet-digest-mismatch " + key)
        ref = reference[key]
        manifest.append({"frame_key": key, "game": row["game"], "section": row["section"],
                         "frame_index": row["frame_index"], "width": row["width"],
                         "height": row["height"], "sheet_scale": row["sheet_scale"],
                         "label": ref["label"], "cx": ref["cx"], "cy": ref["cy"],
                         "diameter": ref["diameter"], "decided_by": ref["decided_by"],
                         "in_dev_boxes": int(key in box_keys), "sheet": path.name,
                         "sheet_sha256": digest})
    write_csv(OUT / "dev_manifest.csv", MANIFEST_FIELDS, manifest)
    labels = {name: sum(r["label"] == name for r in manifest)
              for name in ("VISIBLE", "ABSENT", "UNKNOWN")}
    assertions = {
        "preregistration_seal": seal, "sealed_input_hashes": hashes,
        "dev_keys": len(dev), "dev_games": len({r["game"] for r in dev}),
        "dev_sections": len({r["section"] for r in dev}), "dev_labels": labels,
        "dev_boxes": len(boxes), "dev_box_games": coverage["box_games"],
        "dev_visible_without_training_box": labels["VISIBLE"] - len(boxes),
        "heldout_keys": len(held_keys), "heldout_games": coverage["heldout_games"],
        "heldout_sections": len({r["section"] for r in held}),
        "heldout_keys_absent_from_dev_tensors": len(held_keys),
        "key_overlap": 0, "game_overlap": 0, "section_overlap": 0,
        "sheets_verified": len(manifest), "sheet_manifest_rows": len(sheets),
        "g394_reproduced_counts": reproduce_g394(),
        "g394_source": G394_SCORES}
    write_json(OUT / "split_assertions.json", assertions)
    write_json(OUT / "weight_receipts.json", weight_receipt())
    return order, assertions


def environment() -> dict[str, object]:
    """Record the shared environment, library and GPU identities for both arms."""
    import torch
    import ultralytics

    return {"python": sys.version.split()[0], "torch": torch.__version__,
            "ultralytics": ultralytics.__version__, "cuda": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0),
            "gpu_shared_with_tracking_daemon": True,
            "code": {rel: sha256_file(LANE / rel) for rel in (
                "scripts/platformkit/tracking/g398_run.py",
                "scripts/platformkit/tracking/g398_score.py",
                "scripts/platformkit/tracking/g398_prepare.py",
                "scripts/platformkit/tracking/g363_score.py",
                "scripts/platformkit/tracking/g390_sealed_input.py")}}


def traverse(order: list[dict[str, str]]) -> dict[str, object]:
    """One paired launch: 30 interleaved bins, alternating arm order per bin."""
    import torch
    from ultralytics import YOLO

    total = len(order)
    bins = [order[index * total // BINS:(index + 1) * total // BINS] for index in range(BINS)]
    model = YOLO(str(WEIGHTS))
    predictions: dict[str, list[dict]] = {arm: [] for arm in ARMS}
    timing: list[dict] = []
    peak = {arm: 0 for arm in ARMS}
    started = time.time()
    for index, chunk in enumerate(bins):
        names = sorted(ARMS) if index % 2 == 0 else sorted(ARMS, reverse=True)
        for position, arm in enumerate(names):
            if time.time() - started > DEADLINE_SECONDS:
                raise TimeoutError("gpu-stage-deadline-spent")
            torch.cuda.reset_peak_memory_stats()
            mark = time.time()
            for row in chunk:
                key = row["frame_key"]
                result = model.predict(source=str(sheet(key)), imgsz=ARMS[arm],
                                       **BASE_INFER)[0]
                best, score = None, -1.0
                for box in result.boxes:
                    confidence = float(box.conf[0])
                    if confidence > score:
                        best, score = [float(v) for v in box.xywh[0]], confidence
                predictions[arm].append({
                    "arm": arm, "inherits": "A8", "split": "development",
                    "frame_key": key, "rank": "0" if best else "",
                    "x": round(best[0], 3) if best else "",
                    "y": round(best[1], 3) if best else "",
                    "w": round(best[2], 3) if best else "",
                    "h": round(best[3], 3) if best else "",
                    "score": round(score, 6) if best else "",
                    "tick_history": "OBSERVED" if best else "NO_DETECTION",
                    "source": "full", "imgsz": ARMS[arm], "conf": BASE_INFER["conf"]})
            elapsed = time.time() - mark
            reserved = int(torch.cuda.max_memory_reserved())
            peak[arm] = max(peak[arm], reserved)
            timing.append({"bin": index, "position": position, "arm": arm,
                           "imgsz": ARMS[arm], "keys": len(chunk),
                           "elapsed_seconds": round(elapsed, 4),
                           "ms_per_key": round(1000.0 * elapsed / max(len(chunk), 1), 4),
                           "peak_reserved_bytes": reserved})
    write_csv(OUT / "timing.csv", TIMING_FIELDS, timing)
    report: dict[str, object] = {"bins": BINS, "keys_per_arm": {}, "detections": {},
                                 "peak_reserved_bytes": peak,
                                 "gpu_stage_seconds": round(time.time() - started, 3)}
    for arm, records in predictions.items():
        if len({row["frame_key"] for row in records}) != total:
            raise ValueError("incomplete-dev-traversal-" + arm)
        name = "predictions_960.csv" if ARMS[arm] == 960 else "predictions_1920.csv"
        write_csv(OUT / name, PRED_FIELDS,
                  sorted(records, key=lambda row: row["frame_key"]))
        report["keys_per_arm"][arm] = len(records)
        report["detections"][arm] = sum(1 for row in records if row["rank"] == "0")
    return report


def main() -> int:
    """Run step 0, charge the sole launch prospectively, then traverse once."""
    order, assertions = premise()
    token = OUT / "launch_accounting.json"
    hashes = dict(SEALED_HASHES)
    hashes["a8_weights"] = A8_DIGEST
    charge_paired_launch(token, hashes)
    charged = json.loads(token.read_text(encoding="ascii"))
    charged.update({"arms": {arm: dict(BASE_INFER, imgsz=size) for arm, size in ARMS.items()},
                    "bins": BINS, "dev_keys": assertions["dev_keys"],
                    "gpu_stage_deadline_seconds": DEADLINE_SECONDS,
                    "charged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "environment": environment(),
                    "policy": "one paired launch; failure or partial execution spends it"})
    write_json(token, charged)
    write_json(OUT / "frozen_args.json", {"arms": charged["arms"], "bins": BINS,
                                          "order": "game,section,frame_index,frame_key",
                                          "rank_rule": "rank-0 OBSERVED",
                                          "centre_rule": "max(3 px, diameter_720p/2)",
                                          "transform": "native height to 720p",
                                          "environment": charged["environment"],
                                          "weights_sha256": A8_DIGEST})
    try:
        report = traverse(order)
    except BaseException as failure:  # noqa: BLE001 - the allowance is spent either way
        charged["state"] = "SPENT_FAILED"
        charged["result"] = {"error": type(failure).__name__, "detail": str(failure)[:200]}
        write_json(token, charged)
        raise
    charged["state"], charged["result"] = "SPENT_COMPLETE", report
    write_json(token, charged)
    print("G398 LAUNCH COMPLETE " + json.dumps(report["detections"], sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
