"""G281 two-pass, one-second identity measurement from frozen G267 records."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any

import cv2
import numpy as np


GAP, SAMPLE_SIZE, PER_ID_CAP = 30, 80, 4
CROP_WIDTH, CROP_HEIGHT = 512, 640
SAMPLE_SEED, PASS1_SEED, PASS2_SEED = 28120260904, 28120904, 28121904
PERSON_VERDICTS = ("PLAYER", "PERSON NOT PLAYER IN PLAY", "NOT A PERSON", "CANNOT JUDGE")
IDENTITY_VERDICTS = ("SAME PERSON", "DIFFERENT PERSON", "CANNOT JUDGE")


def digest(value: Any) -> str:
    """Return the canonical SHA-256 commitment for JSON-compatible evidence."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def sha256(path: Path) -> str:
    """Return a source-file digest without modifying it."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def inside(row: dict[str, Any]) -> bool:
    """Apply G270's unchanged inclusive 50 by 94 foot court definition."""
    return 0.0 <= row["court_x_ft"] <= 50.0 and 0.0 <= row["court_y_ft"] <= 94.0


def load_population(input_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Construct every fixed-gap same-ID pair before finite/on-court eligibility."""
    source = json.loads(input_path.read_text(encoding="ascii"))
    by_id: dict[int, dict[int, dict[str, Any]]] = defaultdict(dict)
    for frame in source["frame_records"]:
        for row in frame["detections"]:
            by_id[int(row["track_id"])][int(row["source_frame"])] = row
    all_pairs, eligible = [], []
    for track_id, frames in by_id.items():
        for frame, first in frames.items():
            second = frames.get(frame + GAP)
            if second is None:
                continue
            pair = {"emitted_track_id": track_id, "first_source_frame": frame,
                    "second_source_frame": frame + GAP,
                    "first": first, "second": second}
            all_pairs.append(pair)
            if first["finite"] and second["finite"] and inside(first) and inside(second):
                eligible.append(pair)
    all_pairs.sort(key=lambda row: (row["first_source_frame"], row["emitted_track_id"]))
    eligible.sort(key=lambda row: (row["first_source_frame"], row["emitted_track_id"]))
    spans = [max(rows) - min(rows) for rows in by_id.values()]
    observations = [len(rows) for rows in by_id.values()]
    stats = {"distinct_emitted_track_ids": len(by_id), "track_source_span_frames": describe(spans),
             "track_observation_count": describe(observations),
             "ids_spanning_at_least_30_frames": sum(span >= 30 for span in spans),
             "ids_spanning_at_least_90_frames": sum(span >= 90 for span in spans),
             "fps": source["input"]["fps"],
             "track_source_span_seconds": describe([span / source["input"]["fps"] for span in spans])}
    return source, eligible, {"pre_on_court_same_id_pair_count": len(all_pairs), "track_statistics": stats,
                               "all_pairs": all_pairs}


def describe(values: list[float]) -> dict[str, float | int]:
    """Describe a finite discrete distribution with an explicit unit at its caller."""
    return {"n": len(values), "min": min(values), "median": median(values), "max": max(values)}


def select_evenly(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Choose a time-spread sample using no post-pairing quantity and cap each ID."""
    low, high = pairs[0]["first_source_frame"], pairs[-1]["first_source_frame"]
    rng, selected, counts = random.Random(SAMPLE_SEED), [], Counter()
    for index in range(SAMPLE_SIZE):
        start = low + (high - low + 1) * index // SAMPLE_SIZE
        stop = low + (high - low + 1) * (index + 1) // SAMPLE_SIZE - 1
        members = [row for row in pairs if start <= row["first_source_frame"] <= stop and counts[row["emitted_track_id"]] < PER_ID_CAP]
        if not members:
            raise RuntimeError("empty capped time bin %d" % (index + 1))
        minimum = min(counts[row["emitted_track_id"]] for row in members)
        chosen = rng.choice([row for row in members if counts[row["emitted_track_id"]] == minimum])
        counts[chosen["emitted_track_id"]] += 1
        selected.append({**chosen, "time_bin": index + 1, "time_bin_inclusive": [start, stop]})
    return selected


def pass1_map(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pool both endpoints before the pairing-hidden person-ness presentation."""
    rows = []
    for pair_index, pair in enumerate(selected, start=1):
        for endpoint in ("first", "second"):
            row = pair[endpoint]
            rows.append({"pair_index": pair_index, "endpoint": endpoint, "emitted_track_id": pair["emitted_track_id"],
                         "source_frame": pair[endpoint + "_source_frame"], "foot_x_px": row["foot_x_px"],
                         "foot_y_px": row["foot_y_px"], "time_bin": pair["time_bin"],
                         "time_bin_inclusive": pair["time_bin_inclusive"]})
    random.Random(PASS1_SEED).shuffle(rows)
    return [{**row, "blind_index": index} for index, row in enumerate(rows, start=1)]


def write_csv(path: Path, header: tuple[str, ...], rows: list[tuple[Any, ...]]) -> None:
    """Write an ASCII CSV evidence table."""
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle); writer.writerow(header); writer.writerows(rows)


def prepare(input_path: Path, output: Path) -> dict[str, Any]:
    """Construct local G281 population and sealed Pass 1 order without opening video."""
    source, eligible, population = load_population(input_path)
    selected = select_evenly(eligible)
    mapping = pass1_map(selected)
    if len(selected) != SAMPLE_SIZE or max(Counter(row["emitted_track_id"] for row in selected).values()) > PER_ID_CAP:
        raise RuntimeError("sample size or per-ID cap failure")
    output.mkdir(parents=True, exist_ok=True)
    (output / "pass1_order_commitment.json").write_text(json.dumps({
        "sample_size_pairs": SAMPLE_SIZE, "sample_size_endpoint_crops": len(mapping), "gap_frames": GAP,
        "gap_seconds": GAP / source["input"]["fps"], "sample_seed": SAMPLE_SEED, "pass1_blind_seed": PASS1_SEED,
        "unblind_map_sha256": digest(mapping), "per_id_cap": PER_ID_CAP,
        "sampling": "one seeded draw per equal-width first-frame bin from every finite, same-ID, both-endpoints-on-court 30-frame pair; no speed, displacement, jump, or outcome condition",
        "presentation": "all endpoints pooled and randomized; order has no pair, endpoint, track ID, or source-frame field",
        "crop_policy": "512x640 native-pixel footpoint-centred crops, no detector box drawn, reconstructed, or inferred"}, indent=2) + "\n", encoding="ascii")
    write_csv(output / "pass1_presentation_order.csv", ("blind_index", "render"), [(row["blind_index"], "blind_renders/blind_%03d.jpg" % row["blind_index"]) for row in mapping])
    write_csv(output / "pass1_verdicts.csv", ("blind_index", "verdict"), [(row["blind_index"], "") for row in mapping])
    (output / "pass1_unblind_map.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="ascii")
    (output / "local_population.json").write_text(json.dumps({"input_artifact": str(input_path), "input_sha256": sha256(input_path),
        "inherited_source": source["input"], "gap_frames": GAP, "eligible_pair_count": len(eligible),
        **population, "eligible_pairs": eligible, "selected_pairs": selected}, indent=2, allow_nan=False) + "\n", encoding="ascii")
    return {"pre_on_court": population["pre_on_court_same_id_pair_count"], "eligible": len(eligible), "sample": len(selected), "crops": len(mapping)}


def crop(image: np.ndarray, x: float, y: float) -> np.ndarray:
    """Return a padded full-resolution crop centred at a retained footpoint."""
    left, top = round(x) - CROP_WIDTH // 2, round(y) - CROP_HEIGHT // 2
    padded = cv2.copyMakeBorder(image, CROP_HEIGHT, CROP_HEIGHT, CROP_WIDTH, CROP_WIDTH, cv2.BORDER_CONSTANT)
    return padded[top + CROP_HEIGHT:top + 2 * CROP_HEIGHT, left + CROP_WIDTH:left + 2 * CROP_WIDTH].copy()


def render(video: Path, output: Path) -> None:
    """Render only sealed endpoint crops; this is the pod-only source-video step."""
    mapping = json.loads((output / "pass1_unblind_map.json").read_text(encoding="ascii"))
    target = output / "blind_renders"; target.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened(): raise RuntimeError("could not open source video")
    for row in mapping:
        capture.set(cv2.CAP_PROP_POS_FRAMES, row["source_frame"]); ok, image = capture.read()
        if not ok: raise RuntimeError("could not decode source frame %s" % row["source_frame"])
        image = crop(image, row["foot_x_px"], row["foot_y_px"])
        cv2.drawMarker(image, (CROP_WIDTH // 2, CROP_HEIGHT // 2), (0, 0, 255), cv2.MARKER_CROSS, 19, 2, cv2.LINE_AA)
        if not cv2.imwrite(str(target / ("blind_%03d.jpg" % row["blind_index"])), image, [cv2.IMWRITE_JPEG_QUALITY, 86]): raise RuntimeError("crop write failed")
    capture.release()


def make_pass1_boards(output: Path) -> dict[str, int]:
    """Create eight-crop review sheets which retain the pairing-hidden blind order."""
    paths = sorted((output / "blind_renders").glob("blind_*.jpg"))
    target = output / "pass1_review_boards"; target.mkdir(exist_ok=True)
    for start in range(0, len(paths), 8):
        images = [cv2.imread(str(path)) for path in paths[start:start + 8]]
        if any(image is None for image in images): raise RuntimeError("unreadable Pass 1 crop")
        rows = [np.hstack(images[index:index + 4]) for index in range(0, len(images), 4)]
        if len(rows) == 1: rows.append(np.zeros_like(rows[0]))
        board = np.vstack(rows)
        if not cv2.imwrite(str(target / ("board_%03d.jpg" % (start // 8 + 1))), board, [cv2.IMWRITE_JPEG_QUALITY, 86]): raise RuntimeError("board write failed")
    return {"pass1_review_boards": math.ceil(len(paths) / 8)}


def verdict_map(path: Path, allowed: tuple[str, ...]) -> dict[int, str]:
    """Load a complete categorical verdict table without coercing unknown labels."""
    with path.open(newline="", encoding="ascii") as handle:
        rows = {int(row["blind_index"]): row["verdict"] for row in csv.DictReader(handle)}
    if not rows or any(value not in allowed for value in rows.values()): raise RuntimeError("incomplete or invalid verdict table")
    return rows


def prepare_pass2(output: Path) -> dict[str, int]:
    """Make pairing-visible identity boards only for Pass-1 person-person pairs."""
    mapping = json.loads((output / "pass1_unblind_map.json").read_text(encoding="ascii")); verdicts = verdict_map(output / "pass1_verdicts.csv", PERSON_VERDICTS)
    by_pair: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in mapping: by_pair[row["pair_index"]].append({**row, "person_verdict": verdicts[row["blind_index"]]})
    pairs = [rows for _, rows in sorted(by_pair.items()) if len(rows) == 2 and all(row["person_verdict"] in PERSON_VERDICTS[:2] for row in rows)]
    random.Random(PASS2_SEED).shuffle(pairs)
    pair_map = [{"blind_index": index, "pair": sorted(rows, key=lambda row: row["endpoint"])} for index, rows in enumerate(pairs, start=1)]
    (output / "pass2_order_commitment.json").write_text(json.dumps({"pass2_blind_seed": PASS2_SEED, "eligible_person_person_pairs": len(pair_map), "unblind_map_sha256": digest(pair_map), "presentation": "two endpoint crops together; pairing is visible by necessity for identity judgement"}, indent=2) + "\n", encoding="ascii")
    write_csv(output / "pass2_presentation_order.csv", ("blind_index", "render"), [(row["blind_index"], "identity_renders/identity_%03d.jpg" % row["blind_index"]) for row in pair_map])
    write_csv(output / "pass2_verdicts.csv", ("blind_index", "verdict"), [(row["blind_index"], "") for row in pair_map])
    (output / "pass2_unblind_map.json").write_text(json.dumps(pair_map, indent=2) + "\n", encoding="ascii")
    target = output / "identity_renders"; target.mkdir(exist_ok=True)
    for entry in pair_map:
        images = [cv2.imread(str(output / "blind_renders" / ("blind_%03d.jpg" % row["blind_index"]))) for row in entry["pair"]]
        if any(image is None for image in images): raise RuntimeError("missing endpoint crop for identity board")
        if not cv2.imwrite(str(target / ("identity_%03d.jpg" % entry["blind_index"])), np.hstack(images), [cv2.IMWRITE_JPEG_QUALITY, 86]): raise RuntimeError("identity board write failed")
    return {"person_person_pairs": len(pair_map), "identity_boards": len(pair_map)}


def wilson(successes: int, total: int) -> list[float] | None:
    """Return a two-sided 95 percent Wilson interval, or None for no denominator."""
    if not total: return None
    z, p, d = 1.959963984540054, successes / total, 1 + 1.959963984540054 ** 2 / total
    centre = (p + z ** 2 / (2 * total)) / d
    half = z * math.sqrt(p * (1 - p) / total + z ** 2 / (4 * total ** 2)) / d
    return [centre - half, centre + half]


def summarize(output: Path) -> dict[str, Any]:
    """Unblind two sealed verdict sets and calculate the named identity funnel."""
    pass1 = json.loads((output / "pass1_unblind_map.json").read_text(encoding="ascii")); pass1_v = verdict_map(output / "pass1_verdicts.csv", PERSON_VERDICTS)
    if digest(pass1) != json.loads((output / "pass1_order_commitment.json").read_text(encoding="ascii"))["unblind_map_sha256"]: raise RuntimeError("Pass 1 commitment mismatch")
    pass2 = json.loads((output / "pass2_unblind_map.json").read_text(encoding="ascii")); pass2_v = verdict_map(output / "pass2_verdicts.csv", IDENTITY_VERDICTS)
    if digest(pass2) != json.loads((output / "pass2_order_commitment.json").read_text(encoding="ascii"))["unblind_map_sha256"]: raise RuntimeError("Pass 2 commitment mismatch")
    p1_counts, p2_counts = Counter(pass1_v.values()), Counter(pass2_v.values())
    judgeable = p2_counts["SAME PERSON"] + p2_counts["DIFFERENT PERSON"]
    summary = {"pass1_counts": dict(p1_counts), "sampled_pairs": len(pass1) // 2, "both_endpoints_person_pairs": len(pass2),
               "identity_counts": dict(p2_counts), "judgeable_person_person_pairs": judgeable,
               "purity_same_over_same_plus_different": None if not judgeable else p2_counts["SAME PERSON"] / judgeable,
               "purity_wilson_95": wilson(p2_counts["SAME PERSON"], judgeable),
               "pass1_unblinded_rows": [{**row, "verdict": pass1_v[row["blind_index"]]} for row in pass1],
               "pass2_unblinded_rows": [{**row, "verdict": pass2_v[row["blind_index"]]} for row in pass2]}
    (output / "measurement_summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="ascii")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("action", choices=("prepare", "render", "make-pass1-boards", "prepare-pass2", "summarize")); parser.add_argument("--output", required=True, type=Path); parser.add_argument("--input", type=Path); parser.add_argument("--video", type=Path); args = parser.parse_args()
    if args.action == "prepare": report = prepare(args.input, args.output) if args.input else parser.error("prepare requires --input")
    elif args.action == "render": report = render(args.video, args.output) if args.video else parser.error("render requires --video")
    elif args.action == "make-pass1-boards": report = make_pass1_boards(args.output)
    elif args.action == "prepare-pass2": report = prepare_pass2(args.output)
    else: report = summarize(args.output)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__": main()
