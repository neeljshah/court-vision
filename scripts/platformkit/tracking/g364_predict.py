"""Apply a frozen G364 linear head to cached embeddings without fitting."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from scripts.platformkit.tracking.g364_train import decisions, probabilities


def predict(model_path: Path, embeddings_path: Path, manifest_path: Path,
            output_path: Path) -> None:
    """Write frozen probabilities, margins, and categorical predictions by frame key."""
    model = json.loads(model_path.read_text(encoding="ascii"))
    threshold = float(model["threshold"])
    archive = np.load(embeddings_path)
    keys = [str(key) for key in archive["keys"]]
    values = np.asarray(archive["embeddings"], dtype=float)
    if len(keys) != len(set(keys)):
        raise ValueError("cached embedding keys are not unique")
    probs = probabilities(model, values)
    ordered = np.sort(probs, axis=1)
    derived = {key: {"court_probability": "%.9f" % value[0],
                     "margin": "%.9f" % (value[-1] - value[-2]), "prediction": prediction}
               for key, value, prediction in zip(keys, probs, decisions(model, values, threshold))}
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if {row["frame_key"] for row in rows} != set(derived):
        raise ValueError("frozen prediction manifest and embedding keys differ")
    model_sha256 = hashlib.sha256(model_path.read_bytes()).hexdigest()
    fields = list(rows[0]) + ["court_probability", "margin", "prediction", "model_sha256"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, **derived[row["frame_key"]], "model_sha256": model_sha256})
    non_court = sum(value["prediction"] == "NON_COURT" for value in derived.values())
    print("frozen_predictions=%d threshold=%.2f non_court_reach_per_mille=%.6f" %
          (len(rows), threshold, 1000.0 * non_court / len(rows)))


def main() -> None:
    parser = argparse.ArgumentParser(description="G364 frozen-head predictor")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    predict(args.model, args.embeddings, args.manifest, args.out)


if __name__ == "__main__":
    main()
