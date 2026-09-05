"""Independently reproduce G298 distances/tests and inventory its receipts locally."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.spatial.distance import cdist
from scipy.stats import binomtest

from scripts.platformkit.tracking.g298_compare import read_csv, sha256

OUT = Path("docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact")
LOCATED = Path("docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv")


def audit() -> None:
    """Cross-check with SciPy, then write exact local byte/hash inventories."""
    result = json.loads((OUT / "comparison.json").read_text())
    feet = read_csv(LOCATED)
    metadata = {a: json.loads((OUT / f"{a}_summary.json").read_text()) for a in ("A", "A_repeat", "B", "C")}
    assert len(feet) == 143
    assert len({(f["source_frame"], f["player_id"]) for f in feet}) == 143
    for arm, meta in metadata.items():
        assert meta["decoded_frames"] == metadata["A"]["decoded_frames"]
        assert meta["frames"] == result["frames"]
        assert meta["environment"] == metadata["A"]["environment"]
        assert meta["located_feet"]["sha256"] == sha256(LOCATED)
        assert meta["detections_sha256"] == sha256(OUT / f"{arm}.csv")
        expected = dict(metadata["A"]["settings"], imgsz=640 if arm.startswith("A") else 1920)
        assert meta["settings"] == expected
    assert metadata["A"]["weight"] == metadata["B"]["weight"]
    masks = {}
    for arm in ("A", "B", "C"):
        boxes = read_csv(OUT / f"{arm}.csv")
        nearest = np.full(143, np.inf)
        for frame in result["frames"]:
            indices = [i for i, f in enumerate(feet) if int(f["source_frame"]) == frame]
            candidates = [b for b in boxes if int(b["source_frame"]) == frame]
            if candidates:
                truth = [[float(feet[i][k]) for k in ("foot_x_px", "foot_y_px")] for i in indices]
                points = [[float(b[k]) for k in ("foot_x_px", "foot_y_px")] for b in candidates]
                nearest[indices] = cdist(truth, points).min(axis=1)
        masks[arm] = {t: nearest <= t for t in (25, 50, 100)}
        assert np.isclose(np.median(nearest), result["arms"][arm]["median_nearest_px"])
        assert len(boxes) == result["arms"][arm]["total_detections"]
        for t in masks[arm]:
            assert masks[arm][t].sum() == result["arms"][arm]["recall"][str(t)]["matched"]
    for a, b in (("A", "B"), ("B", "C")):
        for t in (25, 50, 100):
            lost = int((masks[a][t] & ~masks[b][t]).sum())
            gained = int((~masks[a][t] & masks[b][t]).sum())
            expected = result["paired_tests"][f"{a}_vs_{b}"][str(t)]
            p = binomtest(lost, lost + gained).pvalue if lost + gained else 1.0
            assert (lost, gained) == (expected["lost"], expected["gained"])
            assert np.isclose(p, expected["nominal_p"], rtol=1e-12, atol=0)
    files = [p for p in OUT.iterdir() if p.is_file() and p.name != "artifact_inventory.json"]
    inputs = [LOCATED, Path("src/tracking/player_detection.py"), Path("src/tracking/utils/plot_tools.py")]
    inputs += sorted(Path("scripts/platformkit/tracking").glob("*g298*"))
    def entry(p: Path) -> dict:
        return {"path": str(p.resolve()), "bytes": p.stat().st_size, "sha256": sha256(p)}
    inventory = {"independent_scipy_reproduction": "PASS", "inputs_and_code": [entry(p) for p in inputs if p.is_file()],
                 "artifacts": [entry(p) for p in sorted(files)],
                 "artifact_bytes_excluding_inventory": sum(p.stat().st_size for p in files)}
    (OUT / "artifact_inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="ascii")
    print("Independent SciPy distance, count, median, settings, pixel identity and exact-binomial checks: PASS")


if __name__ == "__main__":
    audit()
