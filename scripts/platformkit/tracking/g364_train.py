"""Train the preregistered linear G364 head on frozen embeddings only."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


LABELS = ("USABLE_COURT", "CLOSEUP", "CROWD_GRAPHICS", "UNKNOWN")
SEED, L2, STEPS, RATE = 364, 0.0001, 400, 0.05
THRESHOLDS = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30)


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - values.max(axis=1, keepdims=True)
    exponent = np.exp(shifted)
    return exponent / exponent.sum(axis=1, keepdims=True)


def fit_head(features: np.ndarray, labels: list[str]) -> dict[str, object]:
    """Fit the fixed seed/loss/step logistic head to development embeddings."""
    if features.ndim != 2 or len(features) != len(labels) or not len(features):
        raise ValueError("features and labels must be aligned nonempty two-dimensional data")
    targets = np.array([LABELS.index(label) for label in labels], dtype=np.int64)
    mean, scale = features.mean(axis=0), features.std(axis=0)
    normalized = (features - mean) / np.maximum(scale, 1e-6)
    rng = np.random.default_rng(SEED)
    weights = rng.normal(0.0, 0.01, (normalized.shape[1], len(LABELS)))
    bias = np.zeros(len(LABELS))
    one_hot = np.eye(len(LABELS))[targets]
    for _ in range(STEPS):
        probabilities = _softmax(normalized @ weights + bias)
        error = (probabilities - one_hot) / len(normalized)
        weights -= RATE * (normalized.T @ error + L2 * weights)
        bias -= RATE * error.sum(axis=0)
    return {"labels": list(LABELS), "mean": mean.tolist(), "scale": scale.tolist(),
            "head_weights": weights.tolist(), "bias": bias.tolist(), "seed": SEED, "l2": L2,
            "steps": STEPS, "learning_rate": RATE}


def probabilities(model: dict[str, object], features: np.ndarray) -> np.ndarray:
    """Apply the frozen linear head without refitting or threshold selection."""
    mean, scale = np.asarray(model["mean"]), np.asarray(model["scale"])
    weights, bias = np.asarray(model["head_weights"]), np.asarray(model["bias"])
    return _softmax(((features - mean) / np.maximum(scale, 1e-6)) @ weights + bias)


def decisions(model: dict[str, object], features: np.ndarray, threshold: float) -> list[str]:
    """Map frozen class probabilities to COURT, NON_COURT, or ABSTAIN."""
    values = probabilities(model, features)
    order = np.argsort(values, axis=1)
    margin = values[np.arange(len(values)), order[:, -1]] - values[np.arange(len(values)), order[:, -2]]
    return ["ABSTAIN" if gap < threshold else ("COURT" if cls == 0 else "NON_COURT")
            for cls, gap in zip(order[:, -1], margin)]


def choose_threshold(model: dict[str, object], features: np.ndarray, labels: list[str]) -> float:
    """Select the preregistered development-only abstention threshold."""
    for threshold in reversed(THRESHOLDS):
        predicted = decisions(model, features, threshold)
        court = sum(value == "COURT" for value in predicted)
        actual = sum(value == "USABLE_COURT" for value in labels)
        true_positive = sum(p == "COURT" and y == "USABLE_COURT" for p, y in zip(predicted, labels))
        if court and actual and true_positive / court >= 0.90 and true_positive / actual >= 0.80:
            return threshold
    raise ValueError("no preregistered development threshold meets the frozen bar")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _labels(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = {row["frame_key"]: row["label"] for row in rows}
    if len(result) != len(rows) or any(label not in LABELS for label in result.values()):
        raise ValueError("development labels need unique frame keys and the fixed vocabulary")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="G364 frozen linear-head trainer")
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--backbone-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if len(args.backbone_sha256) != 64 or any(c not in "0123456789abcdef" for c in args.backbone_sha256):
        raise ValueError("backbone SHA-256 must be lowercase hexadecimal")
    archive, labels = np.load(args.embeddings), _labels(args.labels)
    keys = [str(key) for key in archive["keys"]]
    if set(keys) != set(labels):
        raise ValueError("development labels and embeddings have different frame keys")
    model = fit_head(np.asarray(archive["embeddings"], dtype=float), [labels[key] for key in keys])
    model["threshold"] = choose_threshold(model, np.asarray(archive["embeddings"], dtype=float),
                                          [labels[key] for key in keys])
    model["feature_extractor"] = "torchvision_resnet18_imagenet1k_v1"
    model["feature_extractor_sha256"] = args.backbone_sha256
    model["development_embedding_sha256"] = _sha256(args.embeddings)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(model, sort_keys=True, indent=1) + "\n", encoding="ascii")
    print("head=linear classes=%d threshold=%.2f model=%s" % (len(LABELS), model["threshold"], args.out))


if __name__ == "__main__":
    main()
