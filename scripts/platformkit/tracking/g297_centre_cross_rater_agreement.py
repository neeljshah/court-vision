"""Recompute G297's sealed seven-category centre-cross agreement."""

import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Sequence

CATEGORIES = ("A", "B", "C", "D", "E", "F", "G")
CATEGORY_LABELS = {
    "A": "PLAYER'S FEET",
    "B": "PLAYER'S BODY not feet",
    "C": "BARE COURT OR FLOOR",
    "D": "BROADCAST GRAPHIC OR SCORE TICKER",
    "E": "PERSON not a player in play",
    "F": "SOMETHING ELSE",
    "G": "CANNOT JUDGE",
}
LABEL_TO_CATEGORY = {label: code for code, label in CATEGORY_LABELS.items()}
SEALING_SHA = "2607641d6d6f5308e23baca18acb3a32bb25a402"
BASE = Path("docs/evidence/tracking")
OWN = BASE / "g297_centre_cross_rater_agreement_clean_artifact"
REFERENCE = BASE / "g287_unconditioned_footpoint_content_artifact/blind_verdicts.csv"


def agreement(reference: Sequence[str], fresh: Sequence[str]) -> dict:
    """Return a fixed 7x7 matrix, kappa, delta-method SE, and category agreement."""
    if not reference or len(reference) != len(fresh):
        raise ValueError("Nonempty paired vectors of equal length required")
    if any(value not in CATEGORIES for value in (*reference, *fresh)):
        raise ValueError("Every verdict must use one of categories A-G")
    matrix = [[0] * len(CATEGORIES) for _ in CATEGORIES]
    for left, right in zip(reference, fresh):
        matrix[CATEGORIES.index(left)][CATEGORIES.index(right)] += 1
    n = len(reference)
    rows = [sum(row) for row in matrix]
    cols = [sum(matrix[i][j] for i in range(7)) for j in range(7)]
    row_rates = [count / n for count in rows]
    col_rates = [count / n for count in cols]
    observed = sum(matrix[i][i] for i in range(7)) / n
    chance = sum(left * right for left, right in zip(row_rates, col_rates))
    if chance == 1:
        raise ValueError("Kappa undefined for a single constant shared category")
    kappa = (observed - chance) / (1 - chance)
    gradients = []
    for i in range(7):
        for j in range(7):
            gradient = (
                (i == j) * (1 - chance)
                - (1 - observed) * (col_rates[i] + row_rates[j])
            ) / (1 - chance) ** 2
            gradients.append((matrix[i][j] / n, gradient))
    mean_gradient = sum(weight * gradient for weight, gradient in gradients)
    variance = sum(
        weight * (gradient - mean_gradient) ** 2
        for weight, gradient in gradients
    ) / n
    per_category = []
    for i, code in enumerate(CATEGORIES):
        both = matrix[i][i]
        positive_total = rows[i] + cols[i]
        per_category.append({
            "category": code,
            "label": CATEGORY_LABELS[code],
            "reference_n": rows[i],
            "fresh_n": cols[i],
            "both_n": both,
            "positive_agreement": 2 * both / positive_total if positive_total else None,
            "reference_retention": both / rows[i] if rows[i] else None,
            "fresh_overlap": both / cols[i] if cols[i] else None,
            "binary_agreement": (n - rows[i] - cols[i] + 2 * both) / n,
        })
    standard_error = math.sqrt(max(0.0, variance))
    return {
        "n": n,
        "categories": list(CATEGORIES),
        "matrix": matrix,
        "reference_marginal": rows,
        "fresh_marginal": cols,
        "raw_agreement": observed,
        "chance_agreement": chance,
        "kappa": kappa,
        "kappa_se": standard_error,
        "kappa_nominal_wald_95": [
            kappa - 1.96 * standard_error,
            kappa + 1.96 * standard_error,
        ],
        "per_category": per_category,
    }


def paired_on_player(reference: Sequence[str], fresh: Sequence[str]) -> dict:
    """Run exact two-sided McNemar on A+B versus all other categories."""
    if not reference or len(reference) != len(fresh):
        raise ValueError("Nonempty paired vectors of equal length required")
    on_player = {"A", "B"}
    lost = sum(a in on_player and b not in on_player for a, b in zip(reference, fresh))
    gained = sum(a not in on_player and b in on_player for a, b in zip(reference, fresh))
    discordant = lost + gained
    if discordant:
        tail = sum(math.comb(discordant, k) for k in range(min(lost, gained) + 1))
        nominal_p = min(1.0, 2 * tail / (2 ** discordant))
    else:
        nominal_p = 1.0
    return {
        "reference_on_player_fresh_not": lost,
        "reference_not_fresh_on_player": gained,
        "discordant_n": discordant,
        "nominal_exact_two_sided_p": nominal_p,
    }


def file_identity(path: Path, resolution: list[int] | None = None) -> dict:
    """Describe one exact local input."""
    return {
        "path": path.resolve().as_posix(),
        "bytes": path.stat().st_size,
        "resolution": resolution,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def load_pairs() -> tuple[list[dict], list[dict]]:
    """Validate the seal and load all 72 paired judgments without exclusions."""
    for filename in ("blind_order.csv", "blind_ratings.csv"):
        path = OWN / filename
        committed = subprocess.check_output(
            ["git", "show", f"{SEALING_SHA}:{path.as_posix()}"]
        )
        if committed != path.read_bytes().replace(b"\r\n", b"\n"):
            raise ValueError(f"Sealed input changed: {path}")
    with (OWN / "blind_order.csv").open(newline="", encoding="utf-8") as handle:
        order = list(csv.DictReader(handle))
    with (OWN / "blind_ratings.csv").open(newline="", encoding="utf-8") as handle:
        ratings = list(csv.DictReader(handle))
    with REFERENCE.open(newline="", encoding="utf-8") as handle:
        reference = list(csv.DictReader(handle))
    ordered_ids = [row["crop_id"] for row in order]
    if len(ordered_ids) != 72 or len(set(ordered_ids)) != 72:
        raise ValueError("The seal must contain all 72 unique crops")
    if ordered_ids != [row["crop_id"] for row in ratings]:
        raise ValueError("Ratings must remain in sealed presentation order")
    references = {row["blind_filename"]: row["category"] for row in reference}
    if len(references) != 72 or set(references) != set(ordered_ids):
        raise ValueError("G287 and G297 crop sets must match exactly")
    pairs = []
    for order_row, rating in zip(order, ratings):
        if not rating["free_text"].strip():
            raise ValueError("Every G297 verdict requires free text")
        crop_id = rating["crop_id"]
        pairs.append({
            "presentation_index": int(order_row["presentation_index"]),
            "crop_id": crop_id,
            "reference": references[crop_id],
            "fresh": LABEL_TO_CATEGORY[rating["category"]],
            "fresh_free_text": rating["free_text"],
        })
    render_dir = BASE / "g273_detector_precision_blind_sample_artifact/blind_renders"
    inputs = [file_identity(render_dir / crop_id, [512, 640]) for crop_id in ordered_ids]
    inputs.extend(file_identity(path) for path in (
        OWN / "blind_order.csv", OWN / "blind_ratings.csv", REFERENCE
    ))
    return pairs, inputs


def run() -> dict:
    """Recompute the complete comparison from committed inputs."""
    pairs, inputs = load_pairs()
    reference = [row["reference"] for row in pairs]
    fresh = [row["fresh"] for row in pairs]
    result = agreement(reference, fresh)
    result.update({
        "sealing_sha": SEALING_SHA,
        "reference_rater": "G287 gpt-5.6-terra",
        "fresh_rater": "G297 gpt-5.6-sol",
        "mcnemar_on_player": paired_on_player(reference, fresh),
        "disagreements": [row for row in pairs if row["reference"] != row["fresh"]],
        "input_manifest": inputs,
    })
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
