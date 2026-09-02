"""Offline clip-held-out G70 measurement for tennis player candidates."""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

LABELS = ("player", "non_player_person")
SPECIFICATION_MAJORITY_BASELINE = 155 / 210
FEATURE_NAMES = (
    "foot_x",
    "foot_y",
    "log_box_area",
    "box_aspect",
    "confidence",
)
SEED = 20260902


def wilson(successes: int, total: int, z: float = 1.96) -> list[float]:
    """Return the two-sided Wilson confidence interval for a binomial rate."""
    if total <= 0:
        raise ValueError("Wilson interval needs a positive denominator")
    rate = successes / total
    denominator = 1 + z * z / total
    centre = (rate + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
    return [centre - radius, centre + radius]


def load_rows(labels_path: Path) -> tuple[list[dict[str, str]], int]:
    """Load the G66 labels, removing only explicitly uncertain rows."""
    with labels_path.open(newline="", encoding="ascii") as handle:
        all_rows = list(csv.DictReader(handle))
    counts = Counter(row["label"] for row in all_rows)
    expected = Counter(player=51, non_player_person=155, uncertain=4)
    if counts != expected or len(all_rows) != 210:
        raise ValueError("G70 requires the fixed G66 51/155/4 label corpus")
    rows = [row for row in all_rows if row["label"] in LABELS]
    if len(rows) != 206 or len({row["candidate_csv_row_number"] for row in rows}) != 206:
        raise ValueError("G70 scored corpus must be 206 unique non-uncertain rows")
    return rows, counts["uncertain"]


def features(rows: Iterable[dict[str, str]]) -> np.ndarray:
    """Create fixed candidate-local geometric and confidence features."""
    matrix = []
    for row in rows:
        width = float(row["x2"]) - float(row["x1"])
        height = float(row["y2"]) - float(row["y1"])
        if width <= 0 or height <= 0:
            raise ValueError("candidate box must have positive area")
        matrix.append((
            float(row["foot_x"]),
            float(row["foot_y"]),
            math.log(width * height),
            width / height,
            float(row["confidence"]),
        ))
    return np.asarray(matrix, dtype=float)


def clip_folds(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Return leave-one-clip-out folds, with no clip shared by train and test."""
    clips = sorted({row["match"] for row in rows})
    if len(clips) != 3:
        raise ValueError("G70 requires exactly three labelled clips")
    folds = []
    for fold, held_out_clip in enumerate(clips):
        test_indices = [index for index, row in enumerate(rows) if row["match"] == held_out_clip]
        train_indices = [index for index, row in enumerate(rows) if row["match"] != held_out_clip]
        train_clips = sorted({rows[index]["match"] for index in train_indices})
        if held_out_clip in train_clips or len(test_indices) == 0:
            raise RuntimeError("clip leakage or empty held-out clip")
        folds.append({"fold": fold, "held_out_clip": held_out_clip, "train_clips": train_clips,
                      "train_indices": train_indices, "test_indices": test_indices})
    return folds


def _model() -> Pipeline:
    return Pipeline((
        ("scale", StandardScaler()),
        ("classifier", LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000,
                                            random_state=SEED, solver="liblinear")),
    ))


def metric(rows: list[dict[str, str]], predictions: list[str]) -> dict[str, Any]:
    """Summarize accuracy and per-class recall with Wilson 95 percent intervals."""
    if len(rows) != len(predictions) or not rows:
        raise ValueError("exactly one prediction is required for every scored row")
    truth = [row["label"] for row in rows]
    counts = Counter(truth)
    correct = sum(actual == predicted for actual, predicted in zip(truth, predictions))
    recalls = {}
    for label in LABELS:
        successes = sum(actual == label and predicted == label for actual, predicted in zip(truth, predictions))
        recalls[label] = {"correct": successes, "n": counts[label], "recall": successes / counts[label],
                          "wilson_95": wilson(successes, counts[label])}
    return {
        "n": len(rows), "correct": correct, "accuracy": correct / len(rows), "accuracy_wilson_95": wilson(correct, len(rows)),
        "specification_majority_baseline": SPECIFICATION_MAJORITY_BASELINE,
        "scored_majority_baseline": counts["non_player_person"] / len(rows),
        "per_class_recall": recalls,
    }


def evaluate(rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Fit one fixed classifier per held-out clip and return pooled OOF outputs."""
    matrix = features(rows)
    predictions = [""] * len(rows)
    probabilities = [0.0] * len(rows)
    fold_summaries = []
    for fold in clip_folds(rows):
        train, test = fold["train_indices"], fold["test_indices"]
        model = _model().fit(matrix[train], [rows[index]["label"] for index in train])
        class_index = list(model.classes_).index("player")
        predicted = model.predict(matrix[test]).tolist()
        probability = model.predict_proba(matrix[test])[:, class_index].tolist()
        for index, label, score in zip(test, predicted, probability):
            predictions[index], probabilities[index] = label, float(score)
        fold_summaries.append({
            "fold": fold["fold"], "held_out_clip": fold["held_out_clip"], "train_clips": fold["train_clips"],
            "train_label_counts": dict(Counter(rows[index]["label"] for index in train)),
            "held_out_label_counts": dict(Counter(rows[index]["label"] for index in test)),
            "metrics": metric([rows[index] for index in test], predicted),
        })
    if any(not prediction for prediction in predictions):
        raise RuntimeError("every row must receive a held-out prediction")
    outputs = []
    fold_by_clip = {fold["held_out_clip"]: fold["fold"] for fold in clip_folds(rows)}
    for row, prediction, probability in zip(rows, predictions, probabilities):
        outputs.append({**row, "fold": fold_by_clip[row["match"]], "prediction": prediction,
                        "player_probability": probability, "mistake_type": _mistake_type(row["label"], prediction)})
    return outputs, metric(rows, predictions), fold_summaries


def _mistake_type(actual: str, prediction: str) -> str:
    if actual == prediction:
        return ""
    return "false_positive" if prediction == "player" else "false_negative"


def _render_mistakes(outputs: list[dict[str, Any]], labels_dir: Path, output_dir: Path) -> list[dict[str, Any]]:
    render_dir = output_dir / "mistake_renders"
    render_dir.mkdir(parents=True, exist_ok=True)
    mistakes = [row for row in outputs if row["mistake_type"]]
    for row in mistakes:
        image = cv2.imread(str(labels_dir / row["render_path"]), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(row["render_path"])
        label = "%s: truth=%s prediction=%s p_player=%.3f" % (
            row["sample_id"], row["label"], row["prediction"], row["player_probability"])
        cv2.rectangle(image, (0, 0), (image.shape[1], 34), (0, 0, 0), -1)
        cv2.putText(image, label, (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.imwrite(str(render_dir / (row["sample_id"] + ".jpg")), image)
    return mistakes


def eye_check_sample(mistakes: list[dict[str, Any]], count_per_direction: int = 10) -> list[dict[str, Any]]:
    """Select error renders evenly over each error direction, never as a head slice."""
    selected = []
    for direction in ("false_positive", "false_negative"):
        group = sorted((row for row in mistakes if row["mistake_type"] == direction),
                       key=lambda row: (row["match"], int(row["source_frame"]), int(row["candidate_index"])))
        count = min(count_per_direction, len(group))
        indices = [round(index * (len(group) - 1) / (count - 1)) for index in range(count)] if count > 1 else list(range(count))
        selected.extend(group[index] for index in indices)
    return selected


def write_artifacts(labels_path: Path, output_dir: Path) -> dict[str, Any]:
    """Run the fixed LOCO measurement and write every audit artifact."""
    rows, uncertain_excluded = load_rows(labels_path)
    outputs, pooled, folds = evaluate(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    fields = list(outputs[0])
    with (output_dir / "clip_oof_predictions.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(outputs)
    mistakes = _render_mistakes(outputs, labels_path.parent, output_dir)
    with (output_dir / "mistake_manifest.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(mistakes)
    eye_check = eye_check_sample(mistakes)
    with (output_dir / "eye_check_selection.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(eye_check)
    split = {"method": "leave_one_clip_out", "unit": "match", "clips": [fold["held_out_clip"] for fold in clip_folds(rows)],
             "rule": "Each held-out clip is absent from its training set; no row-wise split is used."}
    (output_dir / "split_definition.json").write_text(json.dumps(split, indent=2), encoding="ascii")
    result = {"scored_n": len(rows), "uncertain_excluded": uncertain_excluded, "feature_names": FEATURE_NAMES,
              "pooled_held_out_metrics": pooled, "per_fold": folds, "mistake_count": len(mistakes),
              "mistake_counts": dict(Counter(row["mistake_type"] for row in mistakes)),
              "eye_check_selection_count": len(eye_check),
              "eye_check_selection_rule": "10 evenly spaced held-out errors per direction, ordered by clip, source frame, and candidate index"}
    (output_dir / "summary.json").write_text(json.dumps(result, indent=2), encoding="ascii")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(write_artifacts(args.labels, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
