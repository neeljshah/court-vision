"""G394 pod driver: the one A10 training launch and the one charged held-out pass.

Sealed by docs/evidence/tracking/g394_ball_person_negatives_2026-09-11/preregistration.md.
A10 changes training DATA only: the 530 original positives, the 425 original ABSENT
negatives, and each audited person-contained crop appended once with an empty label.
Every other setting reproduces G390's args.yaml.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, "/workspace/wt/a7")

from scripts.platformkit.tracking.g394_prepare import assert_launch_not_spent  # noqa: E402
from scripts.platformkit.tracking.g394_run import (  # noqa: E402
    A8_INFER, G389, INIT_WEIGHTS, SCRATCH, rows, save, sha256_file, sheet, write_csv)

DATASET = SCRATCH / "ds"
RUNS = SCRATCH / "runs"
FINAL = RUNS / "a10/weights/last.pt"
ACCOUNTING = SCRATCH / "launch_accounting.json"
ACCEPTED = SCRATCH / "accepted_negatives.csv"
PRED_FIELDS = ("arm", "inherits", "split", "frame_key", "rank", "x", "y", "w", "h",
               "score", "tick_history", "source", "imgsz", "conf")
TRAIN = dict(imgsz=960, batch=2, epochs=10, optimizer="SGD", lr0=0.001, lrf=0.01,
             momentum=0.937, weight_decay=0.0005, warmup_epochs=3.0,
             warmup_momentum=0.8, warmup_bias_lr=0.1, seed=373, workers=0, device=0,
             deterministic=True, amp=False, pretrained=True, resume=False,
             cos_lr=False, patience=0, save=True, save_period=-1, exist_ok=False,
             cache=False, rect=False, multi_scale=False, single_cls=True,
             fraction=1.0, val=False, plots=False, verbose=False, profile=False,
             freeze=0, close_mosaic=0,
             hsv_h=0.0, hsv_s=0.0, hsv_v=0.0, degrees=0.0, translate=0.0, scale=0.0,
             shear=0.0, perspective=0.0, flipud=0.0, fliplr=0.0, bgr=0.0, mosaic=0.0,
             mixup=0.0, copy_paste=0.0, erasing=0.0, crop_fraction=1.0)


def charge(phase: str, extra: dict | None = None) -> dict:
    """Charge one fixed allowance before the work it pays for begins."""
    ledger = json.loads(ACCOUNTING.read_text(encoding="ascii")) if ACCOUNTING.exists() else {}
    assert_launch_not_spent(ledger, phase)
    ledger[phase + "_charged"] = True
    ledger[phase + "_charged_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ledger.update(extra or {})
    ACCOUNTING.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n",
                          encoding="ascii", newline="\n")
    return ledger


def build_dataset() -> dict[str, object]:
    """Link development pixels, write YOLO labels and append the audited negatives."""
    frames = {row["frame_key"]: row for row in rows(G389 / "frames_v3.csv")}
    reference = {row["frame_key"]: row for row in rows(G389 / "reference_v3.csv")}
    boxes = {row["frame_key"]: row for row in rows(G389 / "dev_boxes_v3.csv")}
    heldout = {key for key, row in frames.items() if row["split"] == "heldout"}
    if heldout & set(boxes):
        raise ValueError("heldout-key-in-training-boxes")
    images, labels = DATASET / "images/train", DATASET / "labels/train"
    for target in (images, labels):
        target.mkdir(parents=True, exist_ok=True)
    positives = negatives = 0
    for key, frame in sorted(frames.items()):
        if frame["split"] != "development":
            continue
        label = reference[key]["label"]
        if label == "UNKNOWN" or (label == "VISIBLE" and key not in boxes):
            continue
        source = sheet(key)
        if not source.is_file():
            raise FileNotFoundError("ABSENT-IN-CACHE " + source.as_posix())
        link = images / (key + ".jpg")
        if not link.exists():
            link.symlink_to(source)
        width, height = float(frame["width"]), float(frame["height"])
        if label == "VISIBLE":
            box = boxes[key]
            diameter = float(box["diameter"])
            text = "0 %.6f %.6f %.6f %.6f\n" % (
                float(box["cx"]) / width, float(box["cy"]) / height,
                diameter / width, diameter / height)
            positives += 1
        else:
            text, negatives = "", negatives + 1
        (labels / (key + ".txt")).write_text(text, encoding="ascii", newline="\n")
    accepted = rows(ACCEPTED)
    if len(accepted) < 30:
        raise ValueError("audited-negative-supply-below-30")
    for row in accepted:
        crop = SCRATCH / "crops" / (row["packet_id"] + ".jpg")
        if sha256_file(crop) != row["crop_sha256"]:
            raise ValueError("accepted-crop-digest-mismatch " + row["packet_id"])
        link = images / (row["packet_id"] + ".jpg")
        if not link.exists():
            link.symlink_to(crop)
        (labels / (row["packet_id"] + ".txt")).write_text("", encoding="ascii", newline="\n")
    yaml = DATASET / "g394.yaml"
    yaml.write_text("path: " + DATASET.as_posix() +
                    "\ntrain: images/train\nval: images/train\nnames:\n  0: ball\n",
                    encoding="ascii", newline="\n")
    return {"positives": positives, "negatives": negatives,
            "audited_negatives": len(accepted), "heldout_linked": 0,
            "images": positives + negatives + len(accepted), "yaml": yaml.as_posix()}


def train() -> dict[str, object]:
    """One training launch from A8's own initialization checkpoint, ten epochs."""
    from ultralytics import YOLO

    started = time.time()
    model = YOLO(str(INIT_WEIGHTS))
    model.train(data=str(DATASET / "g394.yaml"), project=str(RUNS), name="a10", **TRAIN)
    if not FINAL.is_file():
        raise FileNotFoundError("ABSENT-FINAL-EPOCH " + FINAL.as_posix())
    return {"elapsed_seconds": time.time() - started, "epochs": TRAIN["epochs"],
            "weights": FINAL.as_posix(), "final_weights_sha256": sha256_file(FINAL)}


def infer() -> dict[str, object]:
    """The one charged candidate pass over every planned held-out key."""
    from ultralytics import YOLO

    heldout = [row for row in rows(G389 / "frames_v3.csv") if row["split"] == "heldout"]
    started = time.time()
    model = YOLO(str(FINAL))
    out: list[dict[str, object]] = []
    for row in heldout:
        result = model.predict(source=str(sheet(row["frame_key"])), **A8_INFER)[0]
        best, score = None, -1.0
        for box in result.boxes:
            confidence = float(box.conf[0])
            if confidence > score:
                best, score = [float(v) for v in box.xywh[0]], confidence
        if best is None:
            continue
        out.append({"arm": "A10", "inherits": "A0", "split": "heldout",
                    "frame_key": row["frame_key"], "rank": "0",
                    "x": round(best[0], 3), "y": round(best[1], 3),
                    "w": round(best[2], 3), "h": round(best[3], 3),
                    "score": round(score, 6), "tick_history": "OBSERVED",
                    "source": "full", "imgsz": A8_INFER["imgsz"], "conf": A8_INFER["conf"]})
    write_csv(SCRATCH / "predictions_A10.csv", PRED_FIELDS, out)
    return {"elapsed_seconds": time.time() - started, "frames": len(heldout),
            "predictions": len(out)}


def main() -> None:
    """Run one phase: `train` charges and fine-tunes, `infer` spends the one token."""
    os.environ.setdefault("YOLO_CONFIG_DIR", str(SCRATCH / "ultralytics"))
    phase = sys.argv[1] if len(sys.argv) > 1 else "train"
    if phase == "train":
        dataset = build_dataset()
        charge("training", {"dataset": dataset,
                            "init_weights_sha256": sha256_file(INIT_WEIGHTS)})
        report = {"dataset": dataset, "train": train()}
        gpu = report["train"]["elapsed_seconds"] / 60.0
        charge_free = json.loads(ACCOUNTING.read_text(encoding="ascii"))
        charge_free["training_gpu_minutes"] = round(gpu, 4)
        charge_free["prior_training_gpu_minutes"] = 9.232826793193817
        charge_free["cumulative_training_gpu_minutes"] = round(gpu + 9.232826793193817, 4)
        ACCOUNTING.write_text(json.dumps(charge_free, indent=2, sort_keys=True) + "\n",
                              encoding="ascii", newline="\n")
        save("train", report)
        return
    if phase != "infer":
        raise SystemExit("unknown-phase " + phase)
    charge("candidate_inference", {"candidate_weights_sha256": sha256_file(FINAL)})
    report = {"infer": infer()}
    ledger = json.loads(ACCOUNTING.read_text(encoding="ascii"))
    ledger["inference_gpu_minutes"] = round(report["infer"]["elapsed_seconds"] / 60.0, 4)
    ledger["candidate_heldout_executions"] = 1
    ACCOUNTING.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n",
                          encoding="ascii", newline="\n")
    save("infer", report)


if __name__ == "__main__":
    sys.exit(main())
