"""G375 DIAGNOSTIC ONLY: frozen G364 nearest-class score over the census sheets.

Sealed by `docs/evidence/tracking/g375_corpus_sport_purity_2026-09-10/
g375_prereg_2026-09-10.md` (SEAL sha256
2f178a9d533cd9a36f90477ef5b81d499fbe282708433fa29a55344a830242b2). This fits
nothing, moves no threshold and is never a gate result. The G364 reference classes
are court-presence classes, not sport classes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.g375_census import read_csv, write_csv

FIELDS = ("sheet_id", "final_label", "prefix", "nearest_class", "cosine_distance")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def backbone(weights: Path):
    """Load the same frozen torchvision ResNet-18 the G364 reference was built with."""
    import torch
    from torchvision import models

    model = models.resnet18(weights=None)
    state = torch.load(weights, map_location="cpu", weights_only=True)
    model.load_state_dict(state.get("state_dict", state))
    model.fc = torch.nn.Identity()
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    return model


def embed(model, paths: list[Path]) -> np.ndarray:
    """Embed each sheet exactly as g364_embedder does: RGB, 224x224, ImageNet norm."""
    import torch

    mean = torch.tensor((0.485, 0.456, 0.406))[:, None, None]
    scale = torch.tensor((0.229, 0.224, 0.225))[:, None, None]
    vectors = []
    for path in paths:
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError("unreadable sheet: " + str(path))
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image = cv2.resize(image, (224, 224), interpolation=cv2.INTER_AREA)
        tensor = torch.from_numpy((image.astype(np.float32) / 255.0).transpose(2, 0, 1))
        with torch.no_grad():
            vectors.append(model(((tensor - mean) / scale).unsqueeze(0)).numpy()[0])
    return np.asarray(vectors, dtype=np.float32)


def nearest(query: np.ndarray, reference: np.ndarray,
            labels: list[str]) -> list[tuple[str, float]]:
    """Cosine nearest neighbour in the frozen feature space; no fitting occurs."""
    left = query / np.maximum(np.linalg.norm(query, axis=1, keepdims=True), 1e-12)
    right = reference / np.maximum(np.linalg.norm(reference, axis=1, keepdims=True), 1e-12)
    similarity = left @ right.T
    picks = similarity.argmax(axis=1)
    return [(labels[index], float(1.0 - similarity[row, index]))
            for row, index in enumerate(picks)]


def main() -> None:
    parser = argparse.ArgumentParser(description="G375 frozen nearest-class diagnostic")
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--sheets", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--reference-npz", type=Path, required=True)
    parser.add_argument("--reference-labels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    rows = read_csv(args.labels)
    prefixes = {row["sheet_id"]: row["prefix"] for row in read_csv(args.sample)}
    archive = np.load(args.reference_npz)
    reference_labels = {row["frame_key"]: row["label"]
                        for row in read_csv(args.reference_labels)}
    keys = [str(key) for key in archive["keys"]]
    missing = [key for key in keys if key not in reference_labels]
    if missing:
        raise ValueError("frozen reference is missing %d labels" % len(missing))
    model = backbone(args.weights)
    paths = [args.sheets / (row["sheet_id"] + ".jpg") for row in rows]
    picks = nearest(embed(model, paths), np.asarray(archive["embeddings"], dtype=np.float32),
                    [reference_labels[key] for key in keys])
    out = [{"sheet_id": row["sheet_id"], "final_label": row["final_label"],
            "prefix": prefixes.get(row["sheet_id"], ""), "nearest_class": pick[0],
            "cosine_distance": "%.6f" % pick[1]}
           for row, pick in zip(rows, picks)]
    write_csv(args.out, out, FIELDS)
    groups: dict[str, list[dict[str, str]]] = {}
    for row in out:
        groups.setdefault(row["final_label"], []).append(row)
    separation = {label: {
        "n": len(members),
        "nearest_usable_court_permille": int(round(
            1000.0 * sum(row["nearest_class"] == "USABLE_COURT" for row in members)
            / len(members)))} for label, members in sorted(groups.items())}
    summary = {"diagnostic_only": True, "fits_nothing": True,
               "reference_frames": len(keys),
               "reference_classes_are_court_presence_not_sport": True,
               "weights_sha256": sha256_file(args.weights),
               "reference_npz_sha256": sha256_file(args.reference_npz),
               "separation_by_final_label": separation}
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n",
                            encoding="ascii")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
