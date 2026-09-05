"""G290: local signed image-pixel arithmetic on the frozen in-box population."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics as st
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.verifier_footpoint_analyses import (
    CROP_HALF_H, CROP_HALF_W, G267, LOCATED, footpoint_player_split,
    load_detections, load_located,
)

OUT = Path("docs/evidence/tracking/g290_footpoint_offset_axis_decomposition_artifact")


def reproduce(records: list[dict], located: dict) -> dict:
    """Stop before axis analysis unless the frozen verifier pairing reproduces."""
    check = footpoint_player_split(records, located)
    expected = {
        "n": 112, "in_box": 79, "in_box_fraction": 79 / 112,
        "no_player_fraction": 33 / 112,
        "median_px_when_player_present": 172.35954426720906,
    }
    if any(not math.isclose(check[k], v, rel_tol=0, abs_tol=1e-10)
           for k, v in expected.items()):
        raise ValueError(f"STOP: pairing does not reproduce: {check}")
    return check


def pair_offsets(records: list[dict], located: dict) -> tuple[list[dict], list[dict]]:
    """Pair nearest in-box feet; positive dx is right and positive dy is below."""
    pairs, excluded = [], []
    for record_index, rec in enumerate(records):
        pts = located.get(rec["source_frame"])
        if not pts:
            continue
        for detection_index, det in enumerate(rec.get("detections") or []):
            if not det.get("finite"):
                continue
            fx, fy = det["foot_x_px"], det["foot_y_px"]
            near = [(i, px, py) for i, (px, py) in enumerate(pts)
                    if abs(px - fx) <= CROP_HALF_W and abs(py - fy) <= CROP_HALF_H]
            row = {
                "record_index": record_index, "source_frame": rec["source_frame"],
                "detection_index": detection_index, "track_id": det["track_id"],
                "detection_x_px": fx, "foot_y_px": fy,
                "located_feet_in_box": len(near),
            }
            if not near:
                excluded.append(row)
                continue
            i, px, py = min(near, key=lambda p: math.hypot(p[1] - fx, p[2] - fy))
            dx, dy = fx - px, fy - py
            row.update(located_index=i, located_x_px=px, located_y_px=py,
                       dx_px=dx, dy_px=dy, distance_px=math.hypot(dx, dy))
            pairs.append(row)
    return pairs, excluded


def quantile(values: list[float], probability: float) -> float:
    """Linear interpolation at (n-1)*p (inclusive/type-7 quantile)."""
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lo, hi = math.floor(index), math.ceil(index)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (index - lo)


def sign_test(values: list[float]) -> dict:
    """Exact two-sided binomial p against 0.5; zeros are named and excluded."""
    pos, neg = sum(v > 0 for v in values), sum(v < 0 for v in values)
    eligible = pos + neg
    p = min(1.0, 2 * sum(math.comb(eligible, k)
                       for k in range(min(pos, neg) + 1)) / 2**eligible)
    return {"positive": pos, "negative": neg, "zero": len(values) - eligible,
            "eligible_nonzero_pairs": eligible,
            "positive_fraction_of_all_pairs": pos / len(values),
            "negative_fraction_of_all_pairs": neg / len(values),
            "nominal_two_sided_p": p if eligible else None,
            "multiplicity_correction": "none"}


def summarize(pairs: list[dict]) -> dict:
    """Describe both axes and detector-foot-y terciles without changing any bar."""
    axes = {axis: [r[f"d{axis}_px"] for r in pairs] for axis in ("x", "y")}
    total_squared = sum(v * v for values in axes.values() for v in values)
    result: dict[str, Any] = {"eligible_in_box_pairs": len(pairs), "axes": {}}
    for axis, values in axes.items():
        absolute = [abs(v) for v in values]
        q1, q3 = quantile(absolute, 0.25), quantile(absolute, 0.75)
        result["axes"][axis] = {
            "median_absolute_px": st.median(absolute), "q1_absolute_px": q1,
            "q3_absolute_px": q3, "iqr_px": q3 - q1,
            "sum_squared_px2": sum(v * v for v in values),
            "squared_offset_share": sum(v * v for v in values) / total_squared,
            "sign_test": sign_test(values),
        }
    result["squared_offset_share_sum"] = sum(
        a["squared_offset_share"] for a in result["axes"].values())
    ratios = [abs(r["dy_px"]) / abs(r["dx_px"]) if r["dx_px"] else math.inf
              for r in pairs if r["dx_px"] or r["dy_px"]]
    ratio = st.median(ratios)
    result["median_pair_absolute_dy_over_dx"] = ratio if math.isfinite(ratio) else "infinity"
    result["ratio_eligible_pairs"] = len(ratios)
    result["ratio_zero_dx_pairs"] = sum(r["dx_px"] == 0 for r in pairs)
    result["ratio_undefined_zero_zero_pairs"] = len(pairs) - len(ratios)
    result["pairs_with_second_located_foot_in_box"] = sum(
        r["located_feet_in_box"] >= 2 for r in pairs)
    result["unique_observation_keys"] = len({
        (r["source_frame"], r["detection_index"]) for r in pairs})
    ys = [r["foot_y_px"] for r in pairs]
    c1, c2 = quantile(ys, 1 / 3), quantile(ys, 2 / 3)
    result["foot_y_tercile_cutpoints_px"] = [c1, c2]
    result["tercile_definition"] = "detector foot_y_px: low <= c1; c1 < middle <= c2; high > c2"
    result["terciles"] = []
    for label, rows in (
        ("low", [r for r in pairs if r["foot_y_px"] <= c1]),
        ("middle", [r for r in pairs if c1 < r["foot_y_px"] <= c2]),
        ("high", [r for r in pairs if r["foot_y_px"] > c2]),
    ):
        result["terciles"].append({
            "tercile": label, "eligible_in_box_pairs": len(rows),
            "foot_y_min_px": min(r["foot_y_px"] for r in rows),
            "foot_y_max_px": max(r["foot_y_px"] for r in rows),
            "median_absolute_dy_px": st.median(abs(r["dy_px"]) for r in rows),
        })
    return result


def _manifest(path: Path, resolution: list[int] | None) -> dict:
    return {"absolute_path": path.resolve().as_posix(), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "coordinate_resolution_px": resolution}


def main() -> None:
    """Reproduce first, then persist all pairs, exclusions, metadata and arithmetic."""
    records, located = load_detections(), load_located()
    check = reproduce(records, located)
    line = (f"REPRODUCED n={check['n']}, in_box={check['in_box']} "
            f"({check['in_box_fraction']:.3f}), no_player={check['no_player_fraction']:.3f}, "
            f"median={check['median_px_when_player_present']:.2f} px")
    print(line)
    pairs, excluded = pair_offsets(records, located)
    if (len(pairs), len(excluded)) != (check["in_box"], check["n"] - check["in_box"]):
        raise ValueError("STOP: component pairing disagrees with verifier")
    if not math.isclose(st.median(r["distance_px"] for r in pairs),
                        check["median_px_when_player_present"], abs_tol=1e-10):
        raise ValueError("STOP: component distances disagree with verifier")
    result = summarize(pairs)
    source = json.loads(G267.read_text(encoding="utf-8"))["input"]
    result.update(
        reproduction=check, excluded_no_located_foot_in_box=len(excluded),
        convention="dx=detection_x-located_x; dy=detection_y-located_y; image y increases DOWNWARD",
        units="image pixels; no ground-plane conversion",
        machine="local CPU arithmetic in C:/Users/neelj/nba-track-a3; committed coordinates only",
        population="detector-box observations CONDITIONED on a located player in the box",
        located_frames=len(located), located_foot_observations=sum(map(len, located.values())),
        source_frame_selection=sorted(located),
        source_video_metadata_only_not_opened=source,
        inputs=[_manifest(p, source["resolution_px"]) for p in (LOCATED, G267)],
        route=[_manifest(p, None) for p in (Path(__file__), Path(
            "scripts/platformkit/tracking/verifier_footpoint_analyses.py"))],
        limits=["33/112 excluded; no transfer to the unconditioned population",
                "one clip, one span, one labeller (also prior verdicts), one non-deterministic draw",
                "hand locations are not ground truth; nearest-foot pairing is an assumption",
                "no eye check; no independent validation; observations are not authenticated players",
                "G241: 808/1201 records differed; G278: span 0.836 vs clip 0.656, p=0.0078",
                "nominal sign p-values: no multiplicity correction or dependence adjustment"],
    )
    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in (("paired_offsets.csv", pairs), ("excluded_footpoints.csv", excluded)):
        with (OUT / name).open("w", newline="", encoding="ascii") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    (OUT / "measurement_summary.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="ascii")
    lines = [line, result["convention"]]
    for axis, values in result["axes"].items():
        lines.append(f"|d{axis}| median={values['median_absolute_px']:.3f} px; "
                     f"Q1={values['q1_absolute_px']:.3f}; Q3={values['q3_absolute_px']:.3f}; "
                     f"IQR={values['iqr_px']:.3f}; squared share={values['squared_offset_share']:.6f}")
        lines.append(f"d{axis} signs: {values['sign_test']}")
    lines.append(f"Squared-offset share SUM={result['squared_offset_share_sum']:.3f}")
    lines.append(f"Median pair |dy|/|dx|={result['median_pair_absolute_dy_over_dx']:.6f}")
    lines.append(f"Second located foot in box: {result['pairs_with_second_located_foot_in_box']}/{len(pairs)}")
    for cell in result["terciles"]:
        lines.append(f"foot_y {cell['tercile']}: {cell['foot_y_min_px']}..{cell['foot_y_max_px']} px; "
                     f"median |dy|={cell['median_absolute_dy_px']:.3f} px; "
                     f"eligible in-box pairs={cell['eligible_in_box_pairs']}")
    lines.append(f"EXCLUDED no located foot in box: {len(excluded)}/{check['n']} = {len(excluded)/check['n']:.3f}")
    print("\n".join(lines[1:]))
    (OUT / "measurement_stdout.txt").write_text("\n".join(lines) + "\n", encoding="ascii")


if __name__ == "__main__":
    main()
