"""Local CPU-only LIMIT measurement for a three-class soccer crop classifier."""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np
from sklearn.model_selection import StratifiedGroupKFold

from scripts.platformkit.detection.deterministic import build_soccer_packet_detector, read_packet_frame

CLASS_NAMES = ("player", "other", "referee")
SEED = 20260904


@dataclass(frozen=True)
class TrainingConfig:
    """Fixed random-weight ResNet18 configuration for this measurement."""

    image_height: int = 160
    image_width: int = 96
    batch_size: int = 32
    epochs: int = 60
    learning_rate: float = 5e-4
    weight_decay: float = 1e-4


def read_labels(labels_dir: Path) -> list[dict[str, str]]:
    """Read the fixed label set and enforce its required 300/300 file join."""
    with (labels_dir / "labels.csv").open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    names = [row["crop_filename"] for row in rows]
    if len(rows) != 300 or len(set(names)) != 300:
        raise ValueError("G17C requires 300 uniquely named labels")
    if Counter(row["class"] for row in rows) != Counter(player=268, other=25, referee=7):
        raise ValueError("G17C requires the fixed player/other/referee label counts")
    files = {path.name for path in (labels_dir / "crops").glob("*.jpg")}
    if files != set(names):
        raise ValueError("labels.csv and crops/ are not an exact 300/300 filename join")
    return rows


def grouped_folds(rows: Sequence[dict[str, str]]) -> list[int]:
    """Assign each crop once while holding its entire source frame out."""
    labels = np.array([CLASS_NAMES.index(row["class"]) for row in rows])
    groups = np.array([row["source_frame"] for row in rows])
    folds = [-1] * len(rows)
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    for fold, (_, test_indices) in enumerate(splitter.split(np.zeros(len(rows)), labels, groups)):
        for index in test_indices:
            folds[int(index)] = fold
    if -1 in folds or set(folds) != set(range(5)):
        raise RuntimeError("five-fold assignment is incomplete")
    for frame in set(groups):
        if len({folds[i] for i, value in enumerate(groups) if value == frame}) != 1:
            raise RuntimeError("source frame leaked across folds: %s" % frame)
    return folds


def summarize_predictions(rows: Sequence[dict[str, str]], predictions: Sequence[str]) -> dict[str, Any]:
    """Return all-crop OOF accuracy, majority baseline, and every class recall."""
    if not rows or len(predictions) != len(rows) or any(not item for item in predictions):
        raise ValueError("one prediction is required for every scored crop")
    truth = [row["class"] for row in rows]
    counts = Counter(truth)
    return {
        "n": len(rows),
        "accuracy": sum(actual == predicted for actual, predicted in zip(truth, predictions)) / len(rows),
        "majority_class_baseline": max(counts.values()) / len(rows),
        "per_class_recall": {
            name: (sum(actual == name and predicted == name for actual, predicted in zip(truth, predictions)) / counts[name]
                   if counts[name] else None)
            for name in CLASS_NAMES
        },
    }


def _torch() -> Any:
    import torch

    return torch


def _seed(seed: int) -> None:
    torch = _torch()
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(min(8, max(1, torch.get_num_threads())))
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True


def _tensor(image: np.ndarray, config: TrainingConfig) -> Any:
    torch = _torch()
    resized = cv2.resize(image, (config.image_width, config.image_height), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    return torch.from_numpy(np.ascontiguousarray(rgb.transpose(2, 0, 1))).float().div_(255.0)


def _model() -> Any:
    from torchvision.models import resnet18

    return resnet18(weights=None, num_classes=len(CLASS_NAMES))


def _fit(inputs: Sequence[Any], rows: Sequence[dict[str, str]], folds: Sequence[int], fold: int,
         config: TrainingConfig, device: Any) -> Any:
    torch = _torch()
    train = [index for index, assigned in enumerate(folds) if assigned != fold]
    counts = Counter(rows[index]["class"] for index in train)
    if set(counts) != set(CLASS_NAMES):
        raise RuntimeError("a training fold is missing a class")
    weights = np.array([np.sqrt(len(train) / counts[name]) for name in CLASS_NAMES], dtype=np.float32)
    weights /= weights.mean()
    model = _model().to(device)
    loss = torch.nn.CrossEntropyLoss(weight=torch.tensor(weights, device=device))
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    generator = torch.Generator().manual_seed(SEED + fold)
    for _ in range(config.epochs):
        order = torch.randperm(len(train), generator=generator).tolist()
        for start in range(0, len(train), config.batch_size):
            batch = [train[i] for i in order[start:start + config.batch_size]]
            features = torch.stack([inputs[i] for i in batch]).to(device)
            target = torch.tensor([CLASS_NAMES.index(rows[i]["class"]) for i in batch], device=device)
            optimizer.zero_grad(set_to_none=True)
            loss(model(features), target).backward()
            optimizer.step()
    return model.eval()


def cross_validate(labels_dir: Path, output_dir: Path, config: TrainingConfig = TrainingConfig()) -> dict[str, Any]:
    """Train five CPU-only random-weight models and write all 300 OOF predictions."""
    torch = _torch()
    _seed(SEED)
    rows, folds = read_labels(labels_dir), None
    folds = grouped_folds(rows)
    inputs = [_tensor(cv2.imread(str(labels_dir / "crops" / row["crop_filename"]), cv2.IMREAD_COLOR), config) for row in rows]
    device = torch.device("cpu")
    predictions, models, per_fold = [""] * len(rows), {}, []
    for fold in range(5):
        model = _fit(inputs, rows, folds, fold, config, device)
        models[fold] = model
        indices = [i for i, assigned in enumerate(folds) if assigned == fold]
        with torch.no_grad():
            for index in indices:
                predictions[index] = CLASS_NAMES[int(model(inputs[index].unsqueeze(0)).argmax(dim=1).item())]
        per_fold.append({"fold": fold, **summarize_predictions([rows[i] for i in indices], [predictions[i] for i in indices])})
    output_dir.mkdir(parents=True, exist_ok=True)
    fields = ("crop_filename", "source_frame", "clip", "class", "fold", "prediction")
    with (output_dir / "cv_predictions.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{key: row[key] for key in fields[:4]} | {"fold": folds[i], "prediction": predictions[i]}
                          for i, row in enumerate(rows)])
    return {"rows": rows, "folds": folds, "models": models, "config": asdict(config), "device": str(device),
            "summary": summarize_predictions(rows, predictions), "per_fold": per_fold}


def _packet_rows(packet_root: Path) -> list[dict[str, str]]:
    paths = (packet_root / "blind_labels_2026-09-01.csv", packet_root / "ext_2026-09-01" / "blind_labels_ext_2026-09-01.csv")
    records: list[dict[str, str]] = []
    for path in paths:
        with path.open(newline="", encoding="ascii") as handle:
            records.extend(csv.DictReader(handle))
    if len(records) != 100 or len({row["frame_id"] for row in records}) != 100:
        raise ValueError("sealed packet is not 100 unique frames")
    return records


def _sealed_counts(packet_root: Path) -> dict[str, int]:
    paths = (packet_root / "detector_counts_separate.csv", packet_root / "ext_2026-09-01" / "detector_counts_separate_ext.csv")
    counts: dict[str, int] = {}
    for path in paths:
        with path.open(newline="", encoding="ascii") as handle:
            for row in csv.DictReader(handle):
                counts[row["frame_id"]] = int(row.get("raw_boxes") or row.get("detector_observed_distinct_player_count") or 0)
    return counts


def _predict(model: Any, crop: np.ndarray, config: TrainingConfig) -> str:
    torch = _torch()
    with torch.no_grad():
        return CLASS_NAMES[int(model(_tensor(crop, config).unsqueeze(0)).argmax(dim=1).item())]


def _render(frame: np.ndarray, boxes: Sequence[Sequence[float]], roles: Sequence[str], frame_id: str, output: Path) -> None:
    colors = {"player": (0, 220, 0), "other": (0, 165, 255), "referee": (0, 0, 255)}
    canvas = frame.copy()
    for box, role in zip(boxes, roles):
        x1, y1, x2, y2 = map(lambda value: int(round(value)), box[:4])
        cv2.rectangle(canvas, (x1, y1), (x2, y2), colors[role], 2)
        cv2.putText(canvas, role[0].upper(), (x1, max(14, y1 - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, colors[role], 1)
    cv2.putText(canvas, frame_id, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.imwrite(str(output), canvas)


def measure_packet(cv: dict[str, Any], packet_root: Path, output_dir: Path) -> dict[str, Any]:
    """Use the source-frame-held-out model on every fresh local detector box."""
    frame_fold = {row["source_frame"]: cv["folds"][i] for i, row in enumerate(cv["rows"])}
    packet, sealed, detector = _packet_rows(packet_root), _sealed_counts(packet_root), build_soccer_packet_detector()
    config, records = TrainingConfig(**cv["config"]), []
    renders = output_dir / "renders"
    renders.mkdir(exist_ok=True)
    for row in packet:
        frame_id = row["frame_id"]
        folder = packet_root / ("frames" if int(frame_id[-4:]) <= 36 else "ext_2026-09-01/frames")
        frame, boxes = read_packet_frame(folder / (frame_id + ".jpg")), []
        for box in detector(frame):
            if len(box) >= 4 and box[2] > box[0] and box[3] > box[1]:
                boxes.append(box)
        roles = [_predict(cv["models"][frame_fold[frame_id]], frame[int(box[1]):int(box[3]), int(box[0]):int(box[2])], config) for box in boxes]
        _render(frame, boxes, roles, frame_id, renders / (frame_id + ".jpg"))
        records.append({"frame_id": frame_id, "clip": row["clip"], "manual": int(row["manual_player_count"]),
                        "sealed_detector": sealed[frame_id], "fresh_detector": len(boxes), "oof_player_boxes": roles.count("player"),
                        "fold": frame_fold[frame_id]})
    with (output_dir / "packet_paired_delta.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    before = np.mean([row["manual"] - row["sealed_detector"] for row in records])
    after = np.mean([row["manual"] - row["oof_player_boxes"] for row in records])
    return {"n": len(records), "baseline_delta": float(before), "oof_delta": float(after), "fresh_vs_sealed_mismatches": sum(row["fresh_detector"] != row["sealed_detector"] for row in records)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels-dir", type=Path, required=True)
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = cross_validate(args.labels_dir, args.output_dir)
    result["packet"] = measure_packet(result, args.packet_root, args.output_dir)
    for key in ("rows", "folds", "models"):
        result.pop(key)
    (args.output_dir / "summary.json").write_text(json.dumps(result, indent=2), encoding="ascii")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
