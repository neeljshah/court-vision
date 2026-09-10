"""Binding precondition for the frozen G374 G364 validation inputs (amendment 1)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from scripts.platformkit.tracking.g364_sampler import PREDICTIONS, assert_game_disjoint


EXPECTED_COUNTS = {"COURT": 224, "NON_COURT": 122, "ABSTAIN": 14}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _bound_head_sha256(prediction_rows: list[dict[str, str]]) -> str:
    """Return the one head digest every frozen prediction row binds (amendment A1)."""
    bound = {row.get("model_sha256", "") for row in prediction_rows}
    if len(bound) != 1 or len(next(iter(bound))) != 64:
        raise ValueError("validation_predictions.csv binds no single head SHA-256")
    return next(iter(bound))


def _assert_extractor_pinned(model: dict[str, object], identity: dict[str, object]) -> None:
    """Check model_identity.json pins the frozen model.json feature extractor (A1)."""
    pinned, declared = identity.get("weights_sha256"), model.get("feature_extractor_sha256")
    if not isinstance(pinned, str) or len(pinned) != 64 or pinned != declared:
        raise ValueError("model_identity.json does not pin the frozen feature extractor")


def verify(model: Path, identity: Path, pool: Path, predictions: Path,
           development: Path) -> dict[str, object]:
    """Verify the exact whole-pool G374 premise before any draw or rating."""
    payload = json.loads(model.read_text(encoding="utf-8"))
    identity_payload = json.loads(identity.read_text(encoding="utf-8"))
    model_sha256 = _sha256(model)
    threshold = float(payload.get("threshold", float("nan")))
    pool_rows, prediction_rows, development_rows = _read_csv(pool), _read_csv(predictions), _read_csv(development)
    _assert_extractor_pinned(payload, identity_payload)
    identity_sha256 = _bound_head_sha256(prediction_rows)
    if len(pool_rows) != 360 or len(prediction_rows) != 360:
        raise ValueError("pool and prediction manifests must each contain 360 rows")
    pool_keys = {row.get("frame_key", "") for row in pool_rows}
    prediction_keys = {row.get("frame_key", "") for row in prediction_rows}
    if not pool_keys or pool_keys != prediction_keys or len(pool_keys) != 360:
        raise ValueError("pool and prediction frame keys must be the same 360 unique values")
    census = Counter(row.get("prediction", "") for row in prediction_rows)
    if set(census) - set(PREDICTIONS):
        raise ValueError("prediction manifest contains an unknown frozen stratum")
    assert_game_disjoint(development_rows, pool_rows)
    if model_sha256 != identity_sha256 or threshold != 0.30 or dict(census) != EXPECTED_COUNTS:
        raise ValueError("frozen G364 binding differs from the sealed identity, threshold, or whole-pool census")
    return {"model_sha256": model_sha256, "threshold": threshold, "pool_total": len(pool_rows),
            "court": census["COURT"], "non_court": census["NON_COURT"], "abstain": census["ABSTAIN"],
            "game_overlap": []}


def main() -> None:
    parser = argparse.ArgumentParser(description="G374 frozen-head premise binding")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--development", type=Path, required=True)
    args = parser.parse_args()
    bound = verify(args.model, args.identity, args.pool, args.predictions, args.development)
    print("head_sha256=%s threshold=%.2f pool=%d court=%d non_court=%d abstain=%d game_overlap=%s" %
          (bound["model_sha256"], bound["threshold"], bound["pool_total"], bound["court"],
           bound["non_court"], bound["abstain"], bound["game_overlap"]))


if __name__ == "__main__":
    main()
