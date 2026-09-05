"""G294: local descriptive census of the committed G289 steps, without re-pairing."""

import csv
import hashlib
import io
import json
import math
import platform
from pathlib import Path
from statistics import mean, median


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "docs/evidence/tracking/g289_implausible_step_decomposition_artifact/steps.csv"
OUTPUT = ROOT / "docs/evidence/tracking/g294_gap_conditioned_implausibility_artifact"
BUCKETS = ("1", "2", "3", "4", "5", "6-10", "above 10")
FIELDS = ("court_displacement_ft", "image_displacement_px", "speed_ft_per_s")


def gap_bucket(gap: int) -> str:
    """Assign every positive integer gap to exactly one specified category."""
    if isinstance(gap, bool) or not isinstance(gap, int) or gap < 1:
        raise ValueError("frame_gap must be a positive integer")
    return str(gap) if gap <= 5 else "6-10" if gap <= 10 else "above 10"


def read_steps(path: Path = SOURCE) -> tuple[list[dict], dict]:
    """Read stored measurements, preserving every step and recording input identity."""
    raw = path.read_bytes()
    rows = []
    for item in csv.DictReader(io.StringIO(raw.decode("utf-8"))):
        gap = int(item["frame_gap"])
        gap_bucket(gap)
        if item["implausible"] not in ("True", "False"):
            raise ValueError("invalid implausible flag")
        row = {key: float(item[key]) for key in FIELDS}
        if any(not math.isfinite(v) or v < 0 for v in row.values()):
            raise ValueError("invalid stored displacement or speed; no row excluded")
        row.update(step_index=int(item["step_index"]), frame_gap=gap,
                   implausible=item["implausible"] == "True")
        rows.append(row)
    if len({r["step_index"] for r in rows}) != len(rows):
        raise ValueError("duplicate step_index")
    return rows, {"path": path.resolve().as_posix(), "bytes": len(raw),
                  "sha256": hashlib.sha256(raw).hexdigest(),
                  "resolution": "CSV: no raster; inherited coordinates 1920x1080 px"}


def reproduce(rows: list[dict]) -> dict:
    """Stop if any published baseline or gap count fails before further analysis."""
    total = len(rows)
    bad = sum(r["implausible"] for r in rows)
    one = [r for r in rows if r["frame_gap"] == 1]
    bad_one = sum(r["implausible"] for r in one)
    if (total, bad, len(one), bad_one) != (29973, 4090, 26523, 2961):
        raise ValueError(f"STOP: baseline/gap counts disagree: {total, bad, len(one), bad_one}")
    pairs = {
        "baseline": (bad, total), "gap1_share_implausible": (bad_one, bad),
        "gap1_share_plausible": (len(one) - bad_one, total - bad),
        "gap1_rate": (bad_one, len(one)),
        "gap_above1_rate": (bad - bad_one, total - len(one)),
        "gap_above1_share_all": (total - len(one), total),
        "gap_above1_share_implausible": (bad - bad_one, bad),
    }
    return {key: {"numerator": a, "denominator": b, "rate": a / b}
            for key, (a, b) in pairs.items()}


def loglog_fit(gaps: list[float], distances: list[float]) -> dict:
    """Return unweighted OLS slope and nominal residual-based SE, never a p-value."""
    if len(gaps) != len(distances) or len(gaps) < 3:
        raise ValueError("fit requires at least three paired medians")
    if any(v <= 0 or not math.isfinite(v) for v in gaps + distances):
        raise ValueError("log fit requires positive finite medians; no cell dropped")
    x, y = list(map(math.log, gaps)), list(map(math.log, distances))
    xm, ym = mean(x), mean(y)
    sxx = sum((v - xm) ** 2 for v in x)
    slope = sum((a - xm) * (b - ym) for a, b in zip(x, y)) / sxx
    intercept = ym - slope * xm
    sse = sum((b - intercept - slope * a) ** 2 for a, b in zip(x, y))
    return {"exponent": slope, "standard_error": math.sqrt(sse / (len(x) - 2) / sxx),
            "intercept_log": intercept, "median_cells": len(x),
            "residual_degrees_of_freedom": len(x) - 2,
            "interpretation": "DESCRIPTIVE on dependent data; not an inferential test"}


def analyze(rows: list[dict]) -> dict:
    """Measure all seven buckets and overlaps after mandatory count reproduction."""
    check = reproduce(rows)
    table = []
    for label in BUCKETS:
        eligible = [r for r in rows if gap_bucket(r["frame_gap"]) == label]
        count = len(eligible)
        if not count:
            raise ValueError(f"empty required median cell: {label}")
        bad = sum(r["implausible"] for r in eligible)
        cell = {"gap_bucket": label, "eligible_steps_at_gap": count,
                "implausible_steps": bad, "implausible_rate": bad / count,
                "median_gap_frames": median(r["frame_gap"] for r in eligible),
                "small_cell": "TOO SMALL TO READ" if count < 30 else "OK (>=30 steps)"}
        cell.update({"median_" + key: median(r[key] for r in eligible) for key in FIELDS})
        table.append(cell)
    assert sum(c["eligible_steps_at_gap"] for c in table) == len(rows)
    fits = {key: loglog_fit([c["median_gap_frames"] for c in table],
                           [c["median_" + key] for c in table]) for key in FIELDS[:2]}
    overlap = {"gap1_small_image": 0, "gap1_larger_image": 0,
               "gap_above1_small_image": 0, "gap_above1_larger_image": 0}
    for row in rows:
        if row["implausible"]:
            gap = "gap1" if row["frame_gap"] == 1 else "gap_above1"
            image = "small_image" if row["image_displacement_px"] <= 20 else "larger_image"
            overlap[f"{gap}_{image}"] += 1
    assert overlap["gap1_small_image"] + overlap["gap_above1_small_image"] == 630
    baseline, one = check["baseline"]["rate"], check["gap1_rate"]["rate"]
    return {"reproduction": check, "per_gap": table, "loglog_fits": fits,
            "fit_method": "Unweighted ln(median distance) ~ intercept + exponent * ln(median gap); seven buckets, all eligible steps",
            "standardized_rate": one, "gap_composition_share": (baseline - one) / baseline,
            "gap_above1_rate_ratio_to_gap1": check["gap_above1_rate"]["rate"] / one,
            "overlap_implausible_steps": overlap,
            "overlap_denominator": "4090 eligible implausible steps; cells partition this set",
            "historical_bimodal_overlap": None,
            "historical_bimodal_overlap_reason": "The sole input has no historical bimodal membership flag or sealed ID list; not assumed disjoint.",
            "limits": ["One clip, span 19599-23399, one non-deterministic draw",
                       "Detector-box observations, not authenticated players",
                       "No ground truth; eye check NONE; not clip-wide",
                       "Retained-record gaps cannot distinguish absent from dropped detections",
                       "Rate decomposition is not causal attribution"]}


def report(result: dict) -> str:
    """Render the exact reproduction and denominator-bearing tables in ASCII."""
    lines = ["REPRODUCTION FIRST (all required figures MATCH):"]
    for name, item in result["reproduction"].items():
        lines.append(f"{name}: {item['numerator']}/{item['denominator']} = {item['rate']:.9f}")
    lines.append(f"rate ratio gap>1/gap1: {result['gap_above1_rate_ratio_to_gap1']:.9f}")
    lines += ["", "Every metric cell names the eligible steps at that gap.",
              "| Gap | Median gap (frames) | Implausible rate | Median court ft | Median image px | Median speed ft/s | Cell mark |",
              "|---|---|---|---|---|---|---|"]
    for c in result["per_gap"]:
        count = c["eligible_steps_at_gap"]
        suffix = f"({count} eligible steps at this gap)"
        metrics = [f"{c['median_' + key]:.6f} {suffix}" for key in FIELDS]
        rate = f"{c['implausible_steps']}/{count} = {c['implausible_rate']:.6f} {suffix}"
        lines.append("| " + " | ".join([c["gap_bucket"], f"{c['median_gap_frames']:g} {suffix}",
                                        rate, *metrics, c["small_cell"]]) + " |")
    lines += ["", result["fit_method"]]
    for name, fit in result["loglog_fits"].items():
        lines.append(f"{name}: exponent={fit['exponent']:.6f}, SE={fit['standard_error']:.6f}; 7 medians, residual df=5")
    lines += ["DESCRIPTIVE on dependent data, not an inferential test; no p-value.",
              f"standardized rate (gap1): {result['standardized_rate']:.9f}",
              f"gap-composition share: {result['gap_composition_share']:.9f}",
              "Overlap counts, denominator 4090 eligible implausible steps:"]
    lines += [f"{key}: {value}/4090" for key, value in result["overlap_implausible_steps"].items()]
    return "\n".join(lines) + "\n"


def main() -> None:
    """Write G294-only evidence from the single committed CSV on the local CPU."""
    rows, source = read_steps()
    check = reproduce(rows)
    for name, item in check.items():
        print(f"CHECK {name}: {item['numerator']}/{item['denominator']} = {item['rate']:.9f}")
    result = analyze(rows)
    result.update(source=source, machine=platform.node(), python=platform.python_version(),
                  execution="Local CPU; no video, decode, GPU or pod")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="ascii")
    with (OUTPUT / "per_gap.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result["per_gap"][0]))
        writer.writeheader()
        writer.writerows(result["per_gap"])
    rendered = report(result)
    (OUTPUT / "run_stdout.txt").write_text(rendered, encoding="ascii")
    print(rendered, end="")


if __name__ == "__main__":
    main()
