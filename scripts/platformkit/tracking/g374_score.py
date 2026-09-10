"""One-shot G374 scorer binding around the frozen G364 reference scorer."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from scripts.platformkit.tracking.g364_sampler import assert_game_disjoint
from scripts.platformkit.tracking.g364_score import references, score


PREDICTION_FIELDS = ("frame_key", "prediction", "court_probability", "model_sha256")
CONFUSION_FIELDS = ("scope", "prediction", "reference_label", "count")


def _read(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _write(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def score_once(development: Path, validation: Path, ratings: Path, adjudication: Path,
               model: Path, output: Path) -> dict[str, object]:
    """Write the additive G374 artifacts after the sealed draw and blind ratings."""
    development_rows, validation_rows = _read(development), _read(validation)
    assert_game_disjoint(development_rows, validation_rows)
    keys = [row.get("frame_key", "") for row in validation_rows]
    if len(validation_rows) != 300 or len(keys) != len(set(keys)):
        raise ValueError("scoring requires exactly 300 unique sealed frame keys")
    model_sha256 = _sha256(model)
    if {row.get("model_sha256", "") for row in validation_rows} != {model_sha256}:
        raise ValueError("sealed validation manifest does not bind this frozen model")
    if any(any(field not in row for field in PREDICTION_FIELDS) for row in validation_rows):
        raise ValueError("validation manifest lacks required prediction fields")
    ratings_rows, adjudication_rows = _read(ratings), _read(adjudication)
    resolved, agreement = references(validation_rows, ratings_rows, adjudication_rows)
    confusion, summary = score(validation_rows, ratings_rows, adjudication_rows)
    prediction_rows = [{field: row[field] for field in PREDICTION_FIELDS}
                       for row in sorted(validation_rows, key=lambda row: row["frame_key"])]
    reference_rows = [{"frame_key": key, "reference_label": resolved[key]} for key in sorted(resolved)]
    _write(output / "predictions.csv", PREDICTION_FIELDS, prediction_rows)
    _write(output / "reference.csv", ("frame_key", "reference_label"), reference_rows)
    _write(output / "confusion.csv", CONFUSION_FIELDS, confusion)
    _write(output / "ratings.csv", tuple(ratings_rows[0]), ratings_rows)
    summary["kappa"] = agreement
    summary["bar_predicted_strata"] = min(summary["predicted_counts"].values()) >= 60
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                                           encoding="ascii")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="G374 frozen validation scorer binding")
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--ratings", type=Path, required=True)
    parser.add_argument("--adjudication", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(score_once(args.development, args.validation, args.ratings,
                                args.adjudication, args.model, args.out), sort_keys=True))


if __name__ == "__main__":
    main()
