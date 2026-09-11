"""G390 pod driver: build the A8 dataset, fine-tune once, infer once on held-out.

Sealed by docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/preregistration.md.
Training touches development frames only; held-out pixels are opened once, at
inference, after the final-epoch checkpoint hash is frozen.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

SCRATCH = Path("/workspace/g390_scratch")
SHEETS = Path("/workspace/g373_scratch/sheets_v2")
INPUTS = SCRATCH / "inputs/docs/evidence/tracking"
G389 = INPUTS / "g389_ball_reference_completion_2026-09-11"
MANIFEST = Path("/workspace/wt/a11/docs/evidence/tracking/"
                "g373_ball_detector_v2_2026-09-10/sheet_manifest_all.csv")
WEIGHTS = Path("/workspace/deploy/nba-ai-system/models/weights/yolov8n_ball.pt")

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
INFER = dict(imgsz=960, conf=0.05, iou=0.70, max_det=300, agnostic_nms=False,
             half=True, device=0, augment=False, visualize=False, verbose=False)
PRED_FIELDS = ("arm", "inherits", "split", "frame_key", "rank", "x", "y", "w", "h",
               "score", "tick_history", "source", "imgsz", "conf")


def rows(path: Path) -> list[dict[str, str]]:
    """Read one bounded CSV input."""
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sheet(frame_key: str) -> Path:
    """Native 1920x1080 sheet for one frame key."""
    return SHEETS / (frame_key[:12] + ".jpg")


def build_dataset() -> dict[str, object]:
    """Symlink development pixels and write YOLO labels; held-out is never linked."""
    frames = {row["frame_key"]: row for row in rows(G389 / "frames_v3.csv")}
    reference = {row["frame_key"]: row for row in rows(G389 / "reference_v3.csv")}
    boxes = {row["frame_key"]: row for row in rows(G389 / "dev_boxes_v3.csv")}
    heldout = {key for key, row in frames.items() if row["split"] == "heldout"}
    if heldout & set(boxes):
        raise ValueError("heldout-key-in-training-boxes")
    images = SCRATCH / "ds/images/train"
    labels = SCRATCH / "ds/labels/train"
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
    yaml = SCRATCH / "ds/g390.yaml"
    yaml.write_text("path: " + (SCRATCH / "ds").as_posix() +
                    "\ntrain: images/train\nval: images/train\nnames:\n  0: ball\n",
                    encoding="ascii", newline="\n")
    return {"positives": positives, "negatives": negatives,
            "images": positives + negatives, "yaml": yaml.as_posix(),
            "heldout_linked": 0}


def verify_cache(keys: set[str]) -> dict[str, int]:
    """Confirm every needed sheet matches the G373 sealed manifest digest."""
    import hashlib

    manifest = {row["frame_key"]: row for row in rows(MANIFEST)}
    checked = 0
    for key in sorted(keys):
        path = sheet(key)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != manifest[key]["sheet_sha256"]:
            raise ValueError("cache-digest-mismatch " + key)
        checked += 1
    return {"sheets_verified": checked, "manifest_rows": len(manifest)}


def train() -> dict[str, object]:
    """Fine-tune once from the deployed checkpoint on development pixels only."""
    from ultralytics import YOLO

    started = time.time()
    model = YOLO(str(WEIGHTS))
    model.train(data=str(SCRATCH / "ds/g390.yaml"), project=str(SCRATCH / "runs"),
                name="a8", **TRAIN)
    final = SCRATCH / "runs/a8/weights/last.pt"
    if not final.is_file():
        raise FileNotFoundError("ABSENT-FINAL-EPOCH " + final.as_posix())
    return {"elapsed_seconds": time.time() - started, "weights": final.as_posix(),
            "epochs": TRAIN["epochs"]}


def infer(weights: Path, arm: str) -> dict[str, object]:
    """One held-out pass; keep the highest-confidence box and every empty frame."""
    from ultralytics import YOLO

    frames = rows(G389 / "frames_v3.csv")
    heldout = [row for row in frames if row["split"] == "heldout"]
    started = time.time()
    model = YOLO(str(weights))
    out: list[dict[str, object]] = []
    for row in heldout:
        result = model.predict(source=str(sheet(row["frame_key"])), **INFER)[0]
        best, score = None, -1.0
        for box in result.boxes:
            confidence = float(box.conf[0])
            if confidence > score:
                best, score = [float(v) for v in box.xywh[0]], confidence
        if best is None:
            continue
        out.append({"arm": arm, "inherits": "A0", "split": "heldout",
                    "frame_key": row["frame_key"], "rank": "0",
                    "x": round(best[0], 3), "y": round(best[1], 3),
                    "w": round(best[2], 3), "h": round(best[3], 3),
                    "score": round(score, 6), "tick_history": "OBSERVED",
                    "source": "full", "imgsz": INFER["imgsz"], "conf": INFER["conf"]})
    path = SCRATCH / ("predictions_" + arm + ".csv")
    with path.open("w", encoding="ascii", newline="\n") as handle:
        writer = csv.DictWriter(handle, PRED_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(out)
    return {"elapsed_seconds": time.time() - started, "frames": len(heldout),
            "predictions": len(out), "path": path.as_posix()}


def render(scores: Path, out: Path, count: int = 30) -> dict[str, object]:
    """Draw evenly spaced held-out cases; reference in green, A8 prediction in red."""
    from PIL import Image, ImageDraw

    preds = {row["frame_key"]: row for row in rows(SCRATCH / "predictions_A8.csv")}
    reference = {row["frame_key"]: row for row in rows(G389 / "reference_v3.csv")}
    candidate = sorted((row for row in rows(scores) if row["arm"] == "A8"),
                       key=lambda row: row["frame_key"])
    out.mkdir(parents=True, exist_ok=True)
    picked = [candidate[round(i * (len(candidate) - 1) / (count - 1))] for i in range(count)]
    index = []
    for position, row in enumerate(picked):
        key = row["frame_key"]
        image = Image.open(sheet(key)).convert("RGB")
        draw = ImageDraw.Draw(image)
        ref = reference[key]
        if ref["label"] == "VISIBLE" and ref["cx"]:
            cx, cy, d = float(ref["cx"]), float(ref["cy"]), max(float(ref["diameter"]), 24.0)
            draw.rectangle([cx - d, cy - d, cx + d, cy + d], outline=(0, 255, 0), width=4)
        pred = preds.get(key)
        if pred:
            x, y = float(pred["x"]), float(pred["y"])
            w, h = float(pred["w"]) / 2.0, float(pred["h"]) / 2.0
            draw.rectangle([x - w, y - h, x + w, y + h], outline=(255, 0, 0), width=4)
        case = ("TP" if int(row["tp"]) else
                "FP" if int(row["fp"]) else
                "NO_DETECTION" if not pred else "UNMATCHED")
        if not int(row["tp"]) and ref["label"] == "VISIBLE":
            case = case + "/FN"
        draw.text((20, 20), "%s %s %s" % (key[:12], ref["label"], case), fill=(255, 255, 0))
        name = "render_%02d_%s.jpg" % (position, key[:12])
        image.save(out / name, quality=70)
        index.append({"position": position, "frame_key": key, "label": ref["label"],
                      "case": case, "n_predictions": row["n_predictions"],
                      "distance_720p": row["distance_720p"], "render": name})
    with (out / "renders_index.csv").open("w", encoding="ascii", newline="\n") as handle:
        writer = csv.DictWriter(handle, list(index[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(index)
    counts: dict[str, int] = {}
    for row in index:
        counts[row["case"]] = counts.get(row["case"], 0) + 1
    return {"renders": len(index), "cases": counts}


def _save(name: str, payload: dict[str, object]) -> None:
    (SCRATCH / (name + "_report.json")).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="ascii", newline="\n")
    print("G390 " + name.upper() + " COMPLETE " + json.dumps(payload, sort_keys=True))


def main() -> None:
    """Run one phase: `train` builds and fine-tunes, `infer` spends the token once."""
    os.environ.setdefault("YOLO_CONFIG_DIR", str(SCRATCH / "ultralytics"))
    phase = sys.argv[1] if len(sys.argv) > 1 else "train"
    if phase == "train":
        report: dict[str, object] = {"dataset": build_dataset()}
        report["cache"] = verify_cache({row["frame_key"]
                                        for row in rows(G389 / "frames_v3.csv")})
        report["train"] = train()
        _save("train", report)
        return
    if phase == "render":
        _save("render", {"render": render(Path(sys.argv[2]), SCRATCH / "renders")})
        return
    if phase != "infer":
        raise SystemExit("unknown-phase " + phase)
    from scripts.platformkit.tracking.g390_arm_runner import sha256_file
    from scripts.platformkit.tracking.g390_receipt import advance_token, charge_candidate_token

    weights = SCRATCH / "runs/a8/weights/last.pt"
    token = SCRATCH / "candidate_token.json"
    charge_candidate_token(token, source_hashes={
        "candidate_weights": sha256_file(weights),
        "init_weights": sha256_file(WEIGHTS),
        "frames": sha256_file(G389 / "frames_v3.csv"),
        "reference": sha256_file(G389 / "reference_v3.csv")})
    report = {"infer": infer(weights, "A8")}
    advance_token(token, "CHARGED_BEFORE_INFERENCE", "INFERENCE_COMPLETE")
    _save("infer", report)


if __name__ == "__main__":
    sys.exit(main())
