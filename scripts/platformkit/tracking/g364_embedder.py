"""Extract one cached frozen ResNet-18 embedding per sealed G364 frame."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np


def sha256_file(path: Path) -> str:
    """Stream one input file to its full SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def frozen_backbone(weights: Path, device: str):
    """Load a local ResNet-18 state dictionary and expose its average-pool vector."""
    import torch
    from torchvision import models

    model = models.resnet18(weights=None)
    state = torch.load(weights, map_location="cpu", weights_only=True)
    model.load_state_dict(state.get("state_dict", state))
    model.fc = torch.nn.Identity()
    model.eval().to(device)
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    return model


def _frame(capture: cv2.VideoCapture, index: int) -> np.ndarray:
    capture.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, value = capture.read()
    if not ok:
        raise ValueError("unreadable sealed frame: %d" % index)
    return value


def embeddings(manifest: Path, weights: Path, output: Path, identity: Path, device: str) -> None:
    """Decode one source at a time, emit cache once, and record extractor identity."""
    with manifest.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["source_path"]].append(row)
    model = frozen_backbone(weights, device)
    import torch

    keys, vectors = [], []
    for source, selected in groups.items():
        capture = cv2.VideoCapture(source)
        if not capture.isOpened():
            raise ValueError("unreadable source: " + source)
        try:
            for row in selected:
                image = cv2.cvtColor(_frame(capture, int(row["frame_index"])), cv2.COLOR_BGR2RGB)
                image = cv2.resize(image, (224, 224), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
                tensor = torch.from_numpy(image.transpose(2, 0, 1)).to(device)
                tensor = ((tensor - torch.tensor((0.485, 0.456, 0.406), device=device)[:, None, None]) /
                          torch.tensor((0.229, 0.224, 0.225), device=device)[:, None, None])
                with torch.no_grad():
                    vectors.append(model(tensor.unsqueeze(0)).cpu().numpy()[0])
                keys.append(row["frame_key"])
        finally:
            capture.release()
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate stable frame keys in embedding manifest")
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, keys=np.asarray(keys), embeddings=np.asarray(vectors, dtype=np.float32))
    identity.parent.mkdir(parents=True, exist_ok=True)
    identity.write_text(json.dumps({"extractor": "torchvision_resnet18_imagenet1k_v1",
                                    "weights_path": str(weights), "weights_sha256": sha256_file(weights),
                                    "embedding_dim": 512, "device": device}, sort_keys=True, indent=1) + "\n",
                        encoding="ascii")
    print("embeddings=%d dim=512 weights_sha256=%s" % (len(keys), sha256_file(weights)))


def main() -> None:
    parser = argparse.ArgumentParser(description="G364 frozen embedding cache builder")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    embeddings(args.manifest, args.weights, args.out, args.identity, args.device)


if __name__ == "__main__":
    main()
