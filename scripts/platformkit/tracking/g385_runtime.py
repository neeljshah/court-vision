"""G385 runtime receipt: milliseconds per section for the unused SHADOW route.

Sealed by `docs/evidence/tracking/g385_nonplay_shadow_mask_2026-09-10/
g385_prereg_2026-09-10.md` (SEAL sha256
1dd44f12075456bd18b5797815d23ba8b4bf3e13eb24417d08d813c0f085d589). Times the same
frozen embedding and head that produced `predictions.csv`; writes no operational field.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from scripts.platformkit.tracking.g375_census import read_csv, write_csv
from scripts.platformkit.tracking.g375_diag import backbone, embed
from scripts.platformkit.tracking.g385_mask import shadow_decisions
from scripts.platformkit.tracking.g385_model import development_split, fit, probabilities

FIELDS = ("section_id", "frames", "milliseconds", "milliseconds_per_frame")


def main() -> None:
    parser = argparse.ArgumentParser(description="G385 per-section shadow-route runtime")
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--dev-sheets", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--sheets", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sheets, targets, _ = development_split(read_csv(args.labels))
    model = backbone(args.weights)
    head = fit(embed(model, [args.dev_sheets / (name + ".jpg") for name in sheets]),
               np.asarray(targets))
    sections: dict[str, list[dict[str, str]]] = {}
    for row in read_csv(args.frames):
        sections.setdefault(row["section_id"], []).append(row)
    out = []
    for section_id in sorted(sections):
        members = [row for row in sections[section_id] if row["sheet_id"]]
        start = time.perf_counter()
        if members:
            scores = probabilities(head, embed(model, [args.sheets / (row["sheet_id"] + ".jpg")
                                                       for row in members]))
            shadow_decisions([{"p_nonplay": float(value), "evidence_status": "READABLE"}
                              for value in scores])
        elapsed = (time.perf_counter() - start) * 1000.0
        count = len(sections[section_id])
        out.append({"section_id": section_id, "frames": str(count),
                    "milliseconds": "%.1f" % elapsed,
                    "milliseconds_per_frame": "%.1f" % (elapsed / count if count else 0.0)})
    write_csv(args.out, out, FIELDS)
    total = sum(float(row["milliseconds"]) for row in out)
    print("SECTIONS %d TOTAL_MS %.1f MEDIAN_MS %.1f" % (
        len(out), total, sorted(float(row["milliseconds"]) for row in out)[len(out) // 2]))


if __name__ == "__main__":
    main()
