"""G289: local arithmetic on committed detector-box coordinates; no route changes."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import statistics as st
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.verifier_footpoint_analyses import (
    FPS, G267, IMPLAUSIBLE_FT_PER_S, steps,
)

OUT = G267.parent.parent / "g289_implausible_step_decomposition_artifact"
BUCKETS = ("0", "(0,5]", "(5,20]", "(20,50]", "(50,150]", ">150")


class _ObservedX(float):
    # Observe the verifier's subtraction without duplicating its pairing logic.
    def __new__(cls, value: float, point: dict, pairs: list) -> _ObservedX:
        obj = super().__new__(cls, value)
        obj.point, obj.pairs = point, pairs
        return obj

    def __sub__(self, other: _ObservedX) -> float:
        self.pairs.append((other.point, self.point))
        return float(self) - float(other)


def baseline(records: list[dict]) -> list[tuple]:
    """Stop before decomposition unless the original imported verifier reproduces."""
    reference = steps(records)
    bad = sum(speed > IMPLAUSIBLE_FT_PER_S for _, speed in reference)
    rate = bad / len(reference) if reference else 0.0
    print(f"BASELINE FIRST: {bad} / {len(reference)} = {rate:.6f}")
    if (bad, len(reference), f"{rate:.6f}") != (4090, 29973, "0.136456"):
        raise ValueError("STOP: reference reproduction failed; no decomposition measured")
    return reference


def measure_steps(records: list[dict], reference: list[tuple]) -> list[dict]:
    """Capture endpoints chosen by steps(); assert every ID and speed is unchanged."""
    pairs, observed = [], []
    for rec in records:
        detections = []
        for det in rec.get("detections") or []:
            copy = dict(det)
            if det.get("finite"):
                point = dict(det, source_frame=rec["source_frame"])
                copy["court_x_ft"] = _ObservedX(det["court_x_ft"], point, pairs)
            detections.append(copy)
        observed.append(dict(rec, detections=detections))
    traced = steps(observed)
    assert traced == reference, "Endpoint observation changed verifier output"
    assert len(pairs) == len(reference), "Verifier subtraction contract changed"
    rows = []
    for index, ((tid, speed), (before, after)) in enumerate(zip(reference, pairs)):
        gap = after["source_frame"] - before["source_frame"]
        image_px = math.hypot(after["foot_x_px"] - before["foot_x_px"],
                              after["foot_y_px"] - before["foot_y_px"])
        court_ft = math.hypot(after["court_x_ft"] - before["court_x_ft"],
                              after["court_y_ft"] - before["court_y_ft"])
        assert tid == before["track_id"] == after["track_id"]
        assert speed == court_ft * FPS / gap
        assert math.isfinite(image_px) and math.isfinite(court_ft)
        row = dict(step_index=index, track_id=tid, frame_gap=gap,
                   image_displacement_px=image_px, court_displacement_ft=court_ft,
                   speed_ft_per_s=speed, implausible=speed > IMPLAUSIBLE_FT_PER_S,
                   secant_scale_ft_per_px=court_ft / image_px if image_px else None,
                   midpoint_foot_y_px=(before["foot_y_px"] + after["foot_y_px"]) / 2)
        for prefix, point in (("before", before), ("after", after)):
            for key in ("source_frame", "foot_x_px", "foot_y_px", "court_x_ft", "court_y_ft"):
                row[f"{prefix}_{key}"] = point[key]
        rows.append(row)
    return rows


def image_bucket(px: float) -> str:
    """Exhaustive disjoint descriptive bins, including exactly zero."""
    if px == 0:
        return BUCKETS[0]
    for upper, name in zip((5, 20, 50, 150), BUCKETS[1:]):
        if px <= upper:
            return name
    return BUCKETS[-1]


def _median(rows: list[dict], key: str) -> float | None:
    values = [r[key] for r in rows if r[key] is not None]
    return st.median(values) if values else None


def summarize(rows: list[dict]) -> dict[str, Any]:
    """Partition every implausible step; report eligible midpoint and gap denominators."""
    bad = [r for r in rows if r["implausible"]]
    partition = []
    for name in BUCKETS:
        cell = [r for r in bad if image_bucket(r["image_displacement_px"]) == name]
        partition.append(dict(image_px_bucket=name, count=len(cell), share=len(cell) / len(bad),
                              median_secant_scale_ft_per_px=_median(cell, "secant_scale_ft_per_px"),
                              median_court_ft=_median(cell, "court_displacement_ft")))
    # Linear empirical quantiles; equal midpoint values never split across cells.
    cuts = st.quantiles([r["midpoint_foot_y_px"] for r in rows], n=10, method="inclusive")
    deciles = []
    for i in range(10):
        cell = [r for r in rows if sum(r["midpoint_foot_y_px"] > c for c in cuts) == i]
        count = sum(r["implausible"] for r in cell)
        deciles.append(dict(decile=i + 1, lower_exclusive_px=cuts[i - 1] if i else None,
                            upper_inclusive_px=cuts[i] if i < 9 else None,
                            eligible_steps_with_midpoint_in_decile=len(cell), implausible=count,
                            implausible_rate=count / len(cell) if cell else None,
                            median_secant_scale_ft_per_px=_median(cell, "secant_scale_ft_per_px")))
    gaps = {}
    for label, flag in (("implausible", True), ("plausible", False)):
        values = [r["frame_gap"] for r in rows if r["implausible"] == flag]
        counts = Counter(values)
        gaps[label] = dict(eligible_steps=len(values), median=st.median(values),
                           p90=st.quantiles(values, n=10, method="inclusive")[8], max=max(values),
                           gap_gt_1_count=sum(v > 1 for v in values),
                           distribution=[dict(frame_gap=g, count=c, share=c / len(values))
                                         for g, c in sorted(counts.items())])
    zero = [r for r in rows if r["image_displacement_px"] == 0]
    return dict(eligible_steps=len(rows), implausible_steps=len(bad),
                implausible_rate=len(bad) / len(rows), partition=partition,
                partition_share_sum=sum(p["share"] for p in partition),
                image_le_20_count=sum(r["image_displacement_px"] <= 20 for r in bad),
                zero_pixel_steps=len(zero), zero_pixel_court_moved=sum(r["court_displacement_ft"] > 0 for r in zero),
                zero_pixel_implausible=sum(r["implausible"] for r in zero),
                y_deciles=deciles, gaps=gaps)


def main() -> None:
    """Write the complete per-step CSV and summary after successful baseline check."""
    source = json.loads(G267.read_text(encoding="utf-8"))
    records = source["frame_records"]
    reference = baseline(records)
    rows = measure_steps(records, reference)
    result = summarize(rows)
    result["input"] = dict(path=str(G267.resolve()), bytes=G267.stat().st_size,
                           sha256=hashlib.sha256(G267.read_bytes()).hexdigest(),
                           coordinate_resolution_px=source["input"]["resolution_px"],
                           inherited_video_metadata_not_opened=source["input"])
    result["machine"] = dict(host=platform.node(), system=platform.system(), python=platform.python_version(),
                             reason="Local CPU arithmetic on committed JSON; no video opened")
    result["secant_definition"] = (
        "Average ft-per-px along the step, NOT the local Jacobian. "
        "For a short step the two converge; for a long one they do not. "
        "That limit requires a single fixed differentiable mapping and a fixed direction. "
        "G267 composes a per-frame map, so the empirical ratio can include map changes "
        "and is not an isolated spatial amplification measurement. "
        "Zero pixels yields null, including 0/0; no steps excluded.")
    result["limits"] = (
        "Detector-box observations, not authenticated players; about 0.208 on feet and "
        "0.181 on overlay graphics (G286/G287), not shares of implausible steps. "
        "One clip, span 19599-23399, one non-deterministic draw; G241 808/1201 differed. "
        "G282 second-draw rate 0.136978 vs 0.136456, stable rate but not individual steps. "
        "G278 span friendlier than clip: 0.836 vs 0.656, p=0.0078; not clip-wide. "
        "No ground truth of any kind, no verified player positions, no eye check. "
        "Geometry of committed mapping only; cannot establish the homography is wrong.")
    result["code"] = {str(p): dict(bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                                  resolution="not applicable (Python source)") for p in
                      (Path(__file__).resolve(), Path(steps.__code__.co_filename).resolve())}
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "steps.csv").open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUT / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2, allow_nan=False))
    print(f"PARTITION SHARE SUM: {result['partition_share_sum']:.3f}")


if __name__ == "__main__":
    main()
