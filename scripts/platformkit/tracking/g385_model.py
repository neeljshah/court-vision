"""G385 development-only non-play head: frozen ResNet-18 features, L2 logistic fit.

Sealed by `docs/evidence/tracking/g385_nonplay_shadow_mask_2026-09-10/
g385_prereg_2026-09-10.md` (SEAL sha256
1dd44f12075456bd18b5797815d23ba8b4bf3e13eb24417d08d813c0f085d589). Fits on G375
development sheets only, freezes before any validation inference, and produces a
SHADOW probability that is never written to a flag, table, ledger or `data/`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from scripts.platformkit.tracking.g375_census import read_csv, write_csv
from scripts.platformkit.tracking.g375_diag import backbone, embed, sha256_file

SEED = 385
PLAY_LABEL = "BASKETBALL_PLAY"
DEFINITE_NONPLAY = ("BASKETBALL_NONPLAY", "OTHER_SPORT", "NON_SPORT")
FIELDS = ("sheet_id", "tick_key", "p_nonplay", "evidence_status")


def fit(features: np.ndarray, targets: np.ndarray):
    """The sealed development fit: L2, C=1, balanced, liblinear, seed 385."""
    from sklearn.linear_model import LogisticRegression

    model = LogisticRegression(penalty="l2", C=1.0, class_weight="balanced",
                               solver="liblinear", random_state=SEED, max_iter=1000)
    model.fit(features, targets)
    return model


def development_split(labels: list[dict[str, str]]) -> tuple[list[str], list[int], list[str]]:
    """Split G375 finals into the two fitted classes; UNKNOWN is excluded and named."""
    sheets, targets, excluded = [], [], []
    for row in labels:
        final = row["final_label"]
        if final == PLAY_LABEL:
            sheets.append(row["sheet_id"])
            targets.append(0)
        elif final in DEFINITE_NONPLAY:
            sheets.append(row["sheet_id"])
            targets.append(1)
        else:
            excluded.append("%s:%s" % (row["sheet_id"], final))
    return sheets, targets, excluded


def identity(model, weights: Path, sheets: list[str], targets: list[int],
             excluded: list[str]) -> dict[str, object]:
    """Freeze the exact bytes of the head before any validation frame is scored."""
    payload = json.dumps({"coef": model.coef_.tolist(), "intercept": model.intercept_.tolist()},
                         sort_keys=True).encode("ascii")
    return {"extractor": "torchvision_resnet18_imagenet1k_v1", "embedding_dim": 512,
            "weights_path": str(weights), "weights_sha256": sha256_file(weights),
            "head": "logistic_l2_C1_balanced_liblinear", "random_state": SEED,
            "max_iter": 1000, "threshold": 0.95, "device": "cpu",
            "development_sheets": len(sheets), "development_play": targets.count(0),
            "development_definite_nonplay": targets.count(1),
            "training_excluded_unknown": excluded,
            "head_sha256": hashlib.sha256(payload).hexdigest(),
            "shadow_only": True, "writes_no_flag_table_ledger_or_data": True}


def probabilities(model, features: np.ndarray) -> np.ndarray:
    """Return p(definite non-play) for each frozen embedding."""
    return model.predict_proba(features)[:, 1]


def main() -> None:
    parser = argparse.ArgumentParser(description="G385 frozen shadow head fit and inference")
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--dev-sheets", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--frames", type=Path)
    parser.add_argument("--validation-sheets", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    labels = read_csv(args.labels)
    sheets, targets, excluded = development_split(labels)
    model = backbone(args.weights)
    features = embed(model, [args.dev_sheets / (name + ".jpg") for name in sheets])
    head = fit(features, np.asarray(targets))
    record = identity(head, args.weights, sheets, targets, excluded)
    args.identity.parent.mkdir(parents=True, exist_ok=True)
    args.identity.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="ascii")
    print("FROZEN head_sha256=%s play=%d nonplay=%d excluded_unknown=%d" % (
        record["head_sha256"], record["development_play"],
        record["development_definite_nonplay"], len(excluded)))
    if not (args.frames and args.validation_sheets and args.out):
        return
    rows = read_csv(args.frames)
    readable = [row for row in rows if row["evidence_status"] == "READABLE" and row["sheet_id"]]
    scores = probabilities(head, embed(model, [args.validation_sheets / (row["sheet_id"] + ".jpg")
                                               for row in readable])) if readable else []
    lookup = {row["tick_key"]: "%.6f" % value for row, value in zip(readable, scores)}
    write_csv(args.out, [{"sheet_id": row["sheet_id"], "tick_key": row["tick_key"],
                          "p_nonplay": lookup.get(row["tick_key"], ""),
                          "evidence_status": row["evidence_status"]} for row in rows], FIELDS)
    print("SCORED readable=%d of planned=%d" % (len(readable), len(rows)))


if __name__ == "__main__":
    main()
