"""G292 large-jump endpoint sampling, blinding, rendering, and summary."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np


SAMPLE_SIZE = 36
ENDPOINT_COUNT = 72
EXPECTED_ELIGIBLE = 1897
SAMPLE_SEED = 29220260904
BLIND_SEED = 29220904
CROP_WIDTH, CROP_HEIGHT = 512, 640
CATEGORIES = ("A", "B", "C", "D", "E", "F", "G")
PLAYER = frozenset(("A", "B"))
NON_PLAYER = frozenset(("C", "D", "E", "F"))


def sha256(path: Path) -> str:
    """Return a file digest without changing the input."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: Any) -> str:
    """Return a stable commitment hash for JSON-compatible content."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def read_steps(path: Path) -> list[dict[str, str]]:
    """Load the landed G289 rows and stop unless its required population reproduces."""
    with path.open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    required = {"step_index", "track_id", "implausible", "image_displacement_px", "before_source_frame", "after_source_frame"}
    if not rows or required.difference(rows[0]):
        raise ValueError("G289 steps.csv schema is incomplete")
    eligible = [row for row in rows if row["implausible"] == "True" and float(row["image_displacement_px"]) > 150.0]
    if len(eligible) != EXPECTED_ELIGIBLE:
        raise ValueError("STOP: G292 eligible jump population %d != %d" % (len(eligible), EXPECTED_ELIGIBLE))
    return eligible


def select_evenly(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Choose one unconditioned eligible G289 step per equal-width before-frame bin."""
    low = min(int(row["before_source_frame"]) for row in rows)
    high = max(int(row["before_source_frame"]) for row in rows)
    rng, selected = random.Random(SAMPLE_SEED), []
    for index in range(SAMPLE_SIZE):
        start = low + (high - low + 1) * index // SAMPLE_SIZE
        stop = low + (high - low + 1) * (index + 1) // SAMPLE_SIZE - 1
        members = [row for row in rows if start <= int(row["before_source_frame"]) <= stop]
        if not members:
            raise RuntimeError("empty G292 time bin %d" % (index + 1))
        selected.append({**rng.choice(members), "time_bin": index + 1, "time_bin_inclusive": [start, stop]})
    return selected


def endpoint_map(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build the hidden source endpoint map before pooled blind presentation."""
    endpoints = []
    for pair_index, step in enumerate(selected, start=1):
        for endpoint, prefix in (("BEFORE", "before"), ("AFTER", "after")):
            endpoints.append({"pair_index": pair_index, "endpoint": endpoint,
                              "step_index": int(step["step_index"]), "emitted_track_id": int(step["track_id"]),
                              "time_bin": step["time_bin"], "time_bin_inclusive": step["time_bin_inclusive"],
                              "image_displacement_px": float(step["image_displacement_px"]),
                              "source_frame": int(step[prefix + "_source_frame"]),
                              "foot_x_px": float(step[prefix + "_foot_x_px"]),
                              "foot_y_px": float(step[prefix + "_foot_y_px"])})
    random.Random(BLIND_SEED).shuffle(endpoints)
    return [{**row, "blind_index": index} for index, row in enumerate(endpoints, start=1)]


def write_csv(path: Path, header: tuple[str, ...], rows: list[tuple[Any, ...]]) -> None:
    """Write compact ASCII CSV evidence."""
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def prepare(input_path: Path, output: Path) -> dict[str, Any]:
    """Create a sealed blind packet from the landed G289 step artifact only."""
    eligible = read_steps(input_path)
    selected = select_evenly(eligible)
    mapping = endpoint_map(selected)
    if len(selected) != SAMPLE_SIZE or len(mapping) != ENDPOINT_COUNT:
        raise RuntimeError("G292 sample cardinality failure")
    output.mkdir(parents=True, exist_ok=True)
    commitment = {"eligible_jump_steps": len(eligible), "sampled_steps": len(selected), "endpoint_crops": len(mapping),
                  "sample_seed": SAMPLE_SEED, "blind_seed": BLIND_SEED, "unblind_map_sha256": canonical_hash(mapping),
                  "selection": "one seeded uniform eligible G289 step per equal-width before-source-frame bin; no track ID, location, speed, or condition beyond implausible and image displacement above 150 px",
                  "presentation": "both endpoints pooled and randomized; no pair, endpoint, frame, ID, or coordinate is exposed",
                  "crop_policy": "512x640 native-pixel crop centred on the footpoint; padded at boundaries; red cross marker 19 px thickness 2 plus red circle radius 8 thickness 2; JPEG quality 88"}
    (output / "blind_order_commitment.json").write_text(json.dumps(commitment, indent=2) + "\n", encoding="ascii")
    write_csv(output / "blind_presentation_order.csv", ("blind_index", "blind_filename"), [(row["blind_index"], "blind_%03d.jpg" % row["blind_index"]) for row in mapping])
    write_csv(output / "blind_verdicts.csv", ("blind_index", "blind_filename", "category", "detail"), [(row["blind_index"], "blind_%03d.jpg" % row["blind_index"], "", "") for row in mapping])
    (output / "unblind_map.json").write_text(json.dumps(mapping, indent=2, allow_nan=False) + "\n", encoding="ascii")
    metadata = {"input_path": str(input_path), "input_bytes": input_path.stat().st_size, "input_sha256": sha256(input_path),
                "eligible_jump_steps": len(eligible), "eligible_before_frame_range": [min(int(r["before_source_frame"]) for r in eligible), max(int(r["before_source_frame"]) for r in eligible)],
                "eligible_distinct_track_ids": len({int(r["track_id"]) for r in eligible}), "selected_time_bins": len({r["time_bin"] for r in selected}),
                "selected_before_frame_range": [min(int(r["before_source_frame"]) for r in selected), max(int(r["before_source_frame"]) for r in selected)],
                "selected_after_frame_range": [min(int(r["after_source_frame"]) for r in selected), max(int(r["after_source_frame"]) for r in selected)],
                "selected_distinct_track_ids": len({int(r["track_id"]) for r in selected}), "selected_steps": selected}
    (output / "selection_metadata.json").write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n", encoding="ascii")
    return {"eligible_jump_steps": len(eligible), "sampled_steps": len(selected), "endpoint_crops": len(mapping)}


def crop(image: np.ndarray, foot_x: float, foot_y: float) -> np.ndarray:
    """Return the G273-matched padded native-pixel footpoint crop."""
    left, top = round(foot_x) - CROP_WIDTH // 2, round(foot_y) - CROP_HEIGHT // 2
    padded = cv2.copyMakeBorder(image, CROP_HEIGHT, CROP_HEIGHT, CROP_WIDTH, CROP_WIDTH, cv2.BORDER_CONSTANT)
    return padded[top + CROP_HEIGHT:top + 2 * CROP_HEIGHT, left + CROP_WIDTH:left + 2 * CROP_WIDTH].copy()


def render(video: Path, output: Path) -> dict[str, int]:
    """Decode and render the hidden endpoint map on the pod only."""
    mapping = json.loads((output / "unblind_map.json").read_text(encoding="ascii"))
    target = output / "blind_renders"
    target.mkdir(exist_ok=True)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("could not open source video")
    for row in mapping:
        capture.set(cv2.CAP_PROP_POS_FRAMES, row["source_frame"])
        ok, image = capture.read()
        if not ok:
            raise RuntimeError("could not decode source frame %s" % row["source_frame"])
        image = crop(image, row["foot_x_px"], row["foot_y_px"])
        centre = (CROP_WIDTH // 2, CROP_HEIGHT // 2)
        cv2.drawMarker(image, centre, (0, 0, 255), cv2.MARKER_CROSS, 19, 2, cv2.LINE_AA)
        cv2.circle(image, centre, 8, (0, 0, 255), 2, cv2.LINE_AA)
        if not cv2.imwrite(str(target / ("blind_%03d.jpg" % row["blind_index"])), image, [cv2.IMWRITE_JPEG_QUALITY, 88]):
            raise RuntimeError("could not write crop")
    capture.release()
    return {"rendered_endpoint_crops": len(mapping)}


def read_verdicts(path: Path, mandatory_detail: bool = True) -> dict[int, dict[str, str]]:
    """Load complete rows, applying G292's mandatory-detail rule when requested."""
    with path.open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    index_key = "blind_index" if rows and "blind_index" in rows[0] else "order"
    indexes = [int(row[index_key]) for row in rows]
    if indexes != list(range(1, ENDPOINT_COUNT + 1)):
        raise ValueError("blind indexes must be exactly 1..72")
    if len({row["blind_filename"] for row in rows}) != ENDPOINT_COUNT:
        raise ValueError("blind filenames must be unique")
    if any(row["category"] not in CATEGORIES for row in rows):
        raise ValueError("verdict category is outside G287's seven-category schema")
    if mandatory_detail and any(not row["detail"].strip() for row in rows):
        raise ValueError("each G292 verdict needs mandatory free text")
    return {int(row[index_key]): row for row in rows}


def two_proportion(sample_count: int, baseline_count: int) -> dict[str, float]:
    """Return the requested pooled unpaired two-proportion result for two n=72 samples."""
    pooled = (sample_count + baseline_count) / (2 * ENDPOINT_COUNT)
    se = math.sqrt(pooled * (1.0 - pooled) * (2.0 / ENDPOINT_COUNT))
    z = ((sample_count - baseline_count) / ENDPOINT_COUNT) / se if se else 0.0
    return {"pooled_p": pooled, "se": se, "z": z, "nominal_two_sided_p": math.erfc(abs(z) / math.sqrt(2.0))}


def binomial_two_sided(successes: int, total: int) -> float | None:
    """Return the exact nominal two-sided p value against p=0.5."""
    if not total:
        return None
    tail = sum(math.comb(total, index) for index in range(min(successes, total - successes) + 1)) / (2 ** total)
    return min(1.0, 2.0 * tail)


def write_input_manifest(output: Path) -> None:
    """Archive paths, dimensions, sizes, and digests for all locally judged crops."""
    paths = sorted((output / "blind_renders").glob("blind_*.jpg"))
    if len(paths) != ENDPOINT_COUNT:
        raise ValueError("G292 requires exactly 72 blind crop inputs")
    with (output / "input_manifest.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=("input_path", "bytes", "width_px", "height_px", "sha256"))
        writer.writeheader()
        for path in paths:
            image = cv2.imread(str(path))
            if image is None:
                raise ValueError("unreadable crop: " + str(path))
            height, width = image.shape[:2]
            writer.writerow({"input_path": str(path.resolve()), "bytes": path.stat().st_size,
                             "width_px": width, "height_px": height, "sha256": sha256(path)})


def same_draw_check(root: Path) -> dict[str, Any]:
    """Reproduce G273's committed draw from G289's current retained-record source."""
    from scripts.platformkit.tracking.g273_detector_precision_blind_sample import (
        blind_order as g273_blind_order, map_commitment, records, select_evenly as g273_select, unblind_map,
    )
    g267 = root / "g267_court_space_physical_plausibility_artifact/g267_measurement.json"
    stored_path = root / "g273_detector_precision_blind_sample_artifact/unblind_map.json"
    source, rows = records(g267)
    recreated, stored = unblind_map(g273_blind_order(g273_select(rows))), json.loads(stored_path.read_text(encoding="ascii"))
    return {"g267_path": str(g267), "g267_bytes": g267.stat().st_size, "g267_sha256": sha256(g267),
            "g273_stored_map_sha256": map_commitment(stored), "g273_recreated_map_sha256": map_commitment(recreated),
            "g273_selector_reproduces_stored_map": recreated == stored, "g273_stored_records": len(stored)}


def summarize(output: Path, baseline_path: Path) -> dict[str, Any]:
    """Unblind sealed endpoint verdicts and calculate all requested paired summaries."""
    mapping = json.loads((output / "unblind_map.json").read_text(encoding="ascii"))
    commitment = json.loads((output / "blind_order_commitment.json").read_text(encoding="ascii"))
    if canonical_hash(mapping) != commitment["unblind_map_sha256"]:
        raise ValueError("unblind map does not match blind commitment")
    verdicts = read_verdicts(output / "blind_verdicts.csv")
    baseline = read_verdicts(baseline_path, mandatory_detail=False)
    counts = Counter(verdicts[index]["category"] for index in verdicts)
    baseline_counts = Counter(baseline[index]["category"] for index in baseline)
    joined = [{**row, "category": verdicts[row["blind_index"]]["category"], "detail": verdicts[row["blind_index"]]["detail"]} for row in mapping]
    by_pair: dict[int, list[dict[str, Any]]] = {}
    for row in joined:
        by_pair.setdefault(row["pair_index"], []).append(row)
    pairs = []
    for pair_index in range(1, SAMPLE_SIZE + 1):
        rows = sorted(by_pair.get(pair_index, []), key=lambda row: row["endpoint"])
        if len(rows) != 2:
            raise ValueError("each G292 step must have exactly two endpoints")
        before, after = sorted(rows, key=lambda row: row["endpoint"] != "BEFORE")
        pairs.append({"pair_index": pair_index, "step_index": before["step_index"], "track_id": before["emitted_track_id"], "time_bin": before["time_bin"], "before_category": before["category"], "after_category": after["category"]})
    mixed = [pair for pair in pairs if {pair["before_category"], pair["after_category"]} & PLAYER and {pair["before_category"], pair["after_category"]} & NON_PLAYER]
    non_player_before = sum(pair["before_category"] in NON_PLAYER for pair in mixed)
    player_count, baseline_player_count = sum(counts[c] for c in PLAYER), sum(baseline_counts[c] for c in PLAYER)
    result = {"endpoint_crops": ENDPOINT_COUNT, "sampled_steps": SAMPLE_SIZE, "category_counts": {c: counts[c] for c in CATEGORIES}, "baseline_category_counts": {c: baseline_counts[c] for c in CATEGORIES},
              "on_player": {"large_jump_endpoints": player_count, "historical_g287": baseline_player_count, "unpaired_two_proportion": two_proportion(player_count, baseline_player_count), "nominal_note": "two-sided nominal p with no multiplicity correction; independent endpoint samples require an unpaired test, not McNemar"},
              "joint_pairs": pairs, "joint_distribution": {"at_least_one_non_player_c_to_f": sum(any(pair[key] in NON_PLAYER for key in ("before_category", "after_category")) for pair in pairs), "both_non_player_c_to_f": sum(all(pair[key] in NON_PLAYER for key in ("before_category", "after_category")) for pair in pairs), "both_on_player_a_or_b": sum(all(pair[key] in PLAYER for key in ("before_category", "after_category")) for pair in pairs), "pairs_with_cannot_judge": sum(any(pair[key] == "G" for key in ("before_category", "after_category")) for pair in pairs)},
              "direction_among_mixed_player_non_player_pairs": {"mixed_pairs": len(mixed), "non_player_before": non_player_before, "non_player_after": len(mixed) - non_player_before, "nominal_binomial_two_sided_p": binomial_two_sided(non_player_before, len(mixed))}}
    write_input_manifest(output)
    root = baseline_path.parents[1]
    (output / "same_draw_check.json").write_text(json.dumps(same_draw_check(root), indent=2) + "\n", encoding="ascii")
    (output / "measurement_summary.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="ascii")
    return result


def main() -> None:
    """Run one narrow G292 stage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "render", "summarize"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    if args.action == "prepare": report = prepare(args.input, args.output) if args.input else parser.error("prepare requires --input")
    elif args.action == "render": report = render(args.video, args.output) if args.video else parser.error("render requires --video")
    else: report = summarize(args.output, args.baseline) if args.baseline else parser.error("summarize requires --baseline")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
