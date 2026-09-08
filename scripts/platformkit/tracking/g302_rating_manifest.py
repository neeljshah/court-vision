"""Write the blind rater's input list: blind_index -> absolute crop path.

The rater opens image files directly, so the whole convenience it needs is the
committed presentation order re-expressed with resolvable paths. Nothing here
reveals an arm: the order, the names and the crop sizes are the sealed ones.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def build(packet: Path) -> int:
    """Re-express blind_presentation_order.csv with absolute crop paths."""
    with (packet / "blind_presentation_order.csv").open(newline="", encoding="ascii") as handle:
        rows = [(int(r["blind_index"]), r["render"]) for r in csv.DictReader(handle)]
    with (packet / "blind_rating_manifest.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle)
        writer.writerow(("blind_index", "crop_path"))
        writer.writerows((index, (packet / "blind_renders" / name).resolve().as_posix())
                         for index, name in rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    args = parser.parse_args()
    print("rows=%d" % build(args.packet))


if __name__ == "__main__":
    main()
