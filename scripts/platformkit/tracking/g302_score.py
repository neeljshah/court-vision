"""G302 attempt 2: unblind the sealed pool and decompose the prior PLAYER gap.

Split from the pool builder because the two halves run in different places and at
different times: `g302_amateur_resolution_attribution.py` runs on the pod with the
GPU and seals the pool, this module runs locally and only AFTER the completed
verdict sheet has been committed by itself. Nothing here touches a video.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g302_amateur_resolution_attribution import (
    ARMS, PRIOR_PLAYER_GAP, SAMPLE_SIZE, VERDICTS, canonical_hash)

EYE_BINS = (6, 18, 30, 42, 54, 66)  # evenly spaced over 72; never a head slice

def two_proportion(left: int, right: int) -> dict[str, float]:
    """Pooled two-sided test for two equal 72-crop samples; nominal, no correction."""
    pooled = (left + right) / (2 * SAMPLE_SIZE)
    se = math.sqrt(pooled * (1 - pooled) * 2 / SAMPLE_SIZE)
    z = ((left - right) / SAMPLE_SIZE) / se if se else 0.0
    return {"pooled_p": pooled, "se": se, "z": z, "nominal_two_sided_p": math.erfc(abs(z) / math.sqrt(2))}


def _write_eye_check(output: Path, mapping: list[dict[str, Any]], verdicts: dict[int, str]) -> None:
    """Six EVENLY SPACED bins per arm, 18 rows, with their post-unblind verdicts (A3/B7)."""
    rows = sorted((r for r in mapping if r["frame_bin"] in EYE_BINS),
                  key=lambda r: (ARMS.index(r["arm"]), r["frame_bin"]))
    with (output / "eye_check.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle)
        writer.writerow(("arm", "frame_bin", "blind_index", "render", "source_frame",
                         "foot_x_px", "foot_y_px", "verdict"))
        writer.writerows((r["arm"], r["frame_bin"], r["blind_index"], r["render"], r["source_frame"],
                          r["foot_x_px"], r["foot_y_px"], verdicts[r["blind_index"]]) for r in rows)


def summarize(output: Path) -> dict[str, Any]:
    """Unblind only after the completed verdict sheet has been committed."""
    packet = output / "blind_packet"
    mapping = json.loads((output / "private" / "unblind_map.json").read_text(encoding="ascii"))
    commitment = json.loads((packet / "blind_order_commitment.json").read_text(encoding="ascii"))
    if canonical_hash(mapping) != commitment["unblind_map_sha256"]:
        raise RuntimeError("unblind map does not match the sealed commitment")
    with (packet / "blind_verdicts.csv").open(newline="", encoding="ascii") as handle:
        verdicts = {int(row["blind_index"]): row["verdict"] for row in csv.DictReader(handle)}
    if set(verdicts) != {row["blind_index"] for row in mapping} or any(v not in VERDICTS for v in verdicts.values()):
        raise ValueError("every pooled crop needs one of the four fixed G273 categories")
    grouped: dict[str, Counter] = {arm: Counter() for arm in ARMS}
    for row in mapping:
        grouped[row["arm"]][verdicts[row["blind_index"]]] += 1
    counts = {arm: {v: grouped[arm][v] for v in VERDICTS} for arm in ARMS}
    result = {"sample_size_per_arm": SAMPLE_SIZE, "counts": counts,
              "fractions": {arm: {v: n / SAMPLE_SIZE for v, n in vals.items()} for arm, vals in counts.items()},
              "b_plus_c": {arm: counts[arm][VERDICTS[1]] + counts[arm][VERDICTS[2]] for arm in ARMS},
              "tests": {"resolution_arm1_vs_arm2": {k: two_proportion(counts[ARMS[0]][k], counts[ARMS[1]][k])
                                                    for k in ("PLAYER", "NOT A PERSON")},
                        "amateur_at_matched_resolution_arm2_vs_arm3":
                            {k: two_proportion(counts[ARMS[1]][k], counts[ARMS[2]][k])
                             for k in ("PLAYER", "NOT A PERSON")}},
              "player_drop_resolution": (counts[ARMS[0]]["PLAYER"] - counts[ARMS[1]]["PLAYER"]) / SAMPLE_SIZE,
              "player_drop_amateur_matched": (counts[ARMS[1]]["PLAYER"] - counts[ARMS[2]]["PLAYER"]) / SAMPLE_SIZE,
              "player_drop_total_arm1_vs_arm3": (counts[ARMS[0]]["PLAYER"] - counts[ARMS[2]]["PLAYER"]) / SAMPLE_SIZE,
              "nominal_note": "two-sided nominal p values; no multiplicity correction"}
    result["unresolved_remainder"] = PRIOR_PLAYER_GAP - result["player_drop_total_arm1_vs_arm3"]
    _write_eye_check(output, mapping, verdicts)
    (packet / "blind_measurement_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="G302 attempt 2: unblind and score")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(summarize(args.output), sort_keys=True))


if __name__ == "__main__":
    main()
