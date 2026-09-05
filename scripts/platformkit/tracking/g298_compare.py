"""Local paired arithmetic for G298; no labels are created or changed."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

ELIGIBLE_FEET = 143
TOLERANCES = (25, 50, 100)
FRAME_COUNT = 15


def sha256(path: Path) -> str:
    """Hash a file without loading a video into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict]:
    """Read an ASCII evidence CSV."""
    with path.open(encoding="ascii", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    """Write stable, ordered ASCII CSV bytes."""
    with path.open("w", encoding="ascii", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_locations(path: Path) -> list[dict]:
    """Require the complete committed 143-foot, 15-frame denominator."""
    rows = read_csv(path)
    assert len(rows) == ELIGIBLE_FEET, "eligible denominator must be 143"
    assert len({r["source_frame"] for r in rows}) == FRAME_COUNT
    assert len({(r["source_frame"], r["player_id"]) for r in rows}) == ELIGIBLE_FEET
    for row in rows:
        assert 0 <= float(row["foot_x_px"]) < 1920
        assert 0 <= float(row["foot_y_px"]) < 1080
    return rows


def bottom_centre(box: list[float], width: int = 1920, height: int = 1080) -> tuple[int, int]:
    """Use production's integer-truncated, image-clipped box bottom-centre."""
    x1, _, x2, y2 = map(int, box)
    return (max(0, x1) + min(width, x2)) // 2, min(height, y2)


def exact_mcnemar(left: list[bool], right: list[bool]) -> dict:
    """Two-sided exact conditional binomial test on discordant foot pairs."""
    assert len(left) == len(right)
    lost = sum(a and not b for a, b in zip(left, right))
    gained = sum(b and not a for a, b in zip(left, right))
    n = lost + gained
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(min(lost, gained) + 1)) / 2**n)
    return {"lost": lost, "gained": gained, "discordant": n, "nominal_p": p}


def compare(located: Path, output: Path) -> dict:
    """Score every located foot against all same-frame raw person detections."""
    locations = read_locations(located)
    frames = sorted({int(r["source_frame"]) for r in locations})
    deterministic = (output / "A.csv").read_bytes() == (output / "A_repeat.csv").read_bytes()
    summary = {"eligible_denominator": ELIGIBLE_FEET, "frames": frames,
               "tolerances_px": TOLERANCES, "A_byte_identical": deterministic,
               "located_feet_sha256": sha256(located), "arms": {}, "paired_tests": {}}
    paired = [{"source_frame": r["source_frame"], "player_id": r["player_id"],
               "located_x": r["foot_x_px"], "located_y": r["foot_y_px"]} for r in locations]
    indicators = {}
    for arm in ("A", "B", "C"):
        detections = read_csv(output / f"{arm}.csv")
        metadata = json.loads((output / f"{arm}_summary.json").read_text())
        assert metadata["frames"] == frames
        assert all(int(d["source_frame"]) in frames for d in detections)
        counts = {f: sum(int(d["source_frame"]) == f for d in detections) for f in frames}
        assert metadata["total_detections"] == len(detections)
        distances = []
        for index, location in enumerate(locations):
            candidates = [d for d in detections if d["source_frame"] == location["source_frame"]]
            distance = min((math.hypot(float(d["foot_x_px"]) - float(location["foot_x_px"]),
                                       float(d["foot_y_px"]) - float(location["foot_y_px"]))
                            for d in candidates), default=math.inf)
            distances.append(distance)
            paired[index][f"{arm}_nearest_px"] = distance
        indicators[arm] = {t: [d <= t for d in distances] for t in TOLERANCES}
        for t in TOLERANCES:
            for row, found in zip(paired, indicators[arm][t]):
                row[f"{arm}_within_{t}"] = int(found)
        summary["arms"][arm] = {
            "recall": {t: {"matched": sum(indicators[arm][t]), "eligible_denominator": ELIGIBLE_FEET,
                            "recall": sum(indicators[arm][t]) / ELIGIBLE_FEET} for t in TOLERANCES},
            "total_detections": len(detections), "counts_per_frame": counts,
            "mean_detections_per_frame": len(detections) / FRAME_COUNT,
            "median_nearest_px": statistics.median(distances)}
    for left, right in (("A", "B"), ("B", "C")):
        summary["paired_tests"][f"{left}_vs_{right}"] = {
            t: exact_mcnemar(indicators[left][t], indicators[right][t]) for t in TOLERANCES}
    write_csv(output / "paired_feet.csv", paired)
    (output / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="ascii")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--located-feet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.located_feet, args.output), indent=2))
