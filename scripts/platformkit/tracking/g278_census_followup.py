"""Create and score G278's blinded sampling and re-judge artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import cv2


FPS = 30
SPAN_START = 19_599
SPAN_END = 23_399
SPAN_SIZE = SPAN_END - SPAN_START + 1
PART_A_SIZE = 61
PART_A_SEED = 2_780_904
PART_B_SEED = 2_780_905
G275_SPAN_INDICES = {19_865, 20_834, 21_803, 22_772}
G275_COUNTS = {"a": 118, "b": 11, "c": 50, "d": 1}
VALID_CATEGORIES = ("a", "b", "c", "d")
EXPECTED_VIDEO_SHA256 = "f361ad7a32ccc6d98ae8e98eee0b090f5e121f9425182e24a31c282ca226c678"


def span_indices(n: int = PART_A_SIZE) -> list[int]:
    """Return centred uniform indices in the inclusive G278 study span."""
    if n < 60 or n > SPAN_SIZE:
        raise ValueError("G278 requires 60 <= n <= span size")
    indices = [SPAN_START + ((2 * item + 1) * SPAN_SIZE) // (2 * n) for item in range(n)]
    if G275_SPAN_INDICES.intersection(indices):
        raise AssertionError("new Part A sample overlaps a G275 span frame")
    return indices


def shuffled_plan(indices: list[int], seed: int) -> list[dict[str, int | float]]:
    """Assign opaque blind identifiers in a reproducible random order."""
    shuffled = list(indices)
    random.Random(seed).shuffle(shuffled)
    return [
        {"blind_id": blind_id, "source_frame": frame, "source_seconds": frame / FPS}
        for blind_id, frame in enumerate(shuffled)
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(command: list[str]) -> str:
    return subprocess.run(command, check=True, text=True, capture_output=True).stdout


def verify_video(video: Path) -> dict[str, object]:
    """Verify the immutable full-resolution G278 input before extraction."""
    digest = _sha256(video)
    if digest != EXPECTED_VIDEO_SHA256:
        raise RuntimeError(f"unexpected video sha256: {digest}")
    probe = json.loads(
        _run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,nb_frames,r_frame_rate",
                "-of",
                "json",
                str(video),
            ]
        )
    )["streams"][0]
    if (probe["width"], probe["height"], probe["r_frame_rate"]) != (1920, 1080, "30/1"):
        raise RuntimeError(f"unexpected video metadata: {probe}")
    return {"path": str(video), "bytes": video.stat().st_size, "sha256": digest, "stream": probe}


def _extract_frame(video: Path, frame: dict[str, int | float], output: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-ss",
            f"{float(frame['source_seconds']):.6f}", "-i", str(video), "-frames:v", "1",
            "-q:v", "5", "-an", "-y", str(output),
        ],
        check=True,
    )


def _write_boards(frames_dir: Path, prefix: str, count: int, boards_dir: Path) -> None:
    boards_dir.mkdir()
    for board_number, offset in enumerate(range(0, count, 12)):
        tiles = []
        for blind_id in range(offset, min(offset + 12, count)):
            image = cv2.imread(str(frames_dir / f"{prefix}_{blind_id:03d}.jpg"), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError(f"cannot open {prefix}_{blind_id:03d}.jpg")
            tile = cv2.resize(image, (480, 270), interpolation=cv2.INTER_AREA)
            cv2.rectangle(tile, (0, 0), (150, 32), (0, 0, 0), -1)
            cv2.putText(tile, f"{prefix} {blind_id:03d}", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1)
            tiles.append(tile)
        while len(tiles) < 12:
            tiles.append(cv2.cvtColor(cv2.UMat(270, 480, cv2.CV_8UC1).get(), cv2.COLOR_GRAY2BGR))
        rows = [cv2.hconcat(tiles[index:index + 4]) for index in range(0, 12, 4)]
        if not cv2.imwrite(str(boards_dir / f"board_{board_number:02d}.jpg"), cv2.vconcat(rows), [cv2.IMWRITE_JPEG_QUALITY, 90]):
            raise RuntimeError("cannot write blind board")


def make_part_a(video: Path, output_dir: Path) -> None:
    """Verify and independently seek-extract G278's new blind Part A sample."""
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing nonempty output: {output_dir}")
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(parents=True)
    indices = span_indices()
    plan = shuffled_plan(indices, PART_A_SEED)
    source = verify_video(video)
    for frame in plan:
        _extract_frame(video, frame, frames_dir / f"part_a_{int(frame['blind_id']):03d}.jpg")
    _write_boards(frames_dir, "part_a", len(plan), output_dir / "boards")
    (output_dir / "blind_manifest.json").write_text(json.dumps({
        "purpose": "G278 Part A blinded new within-span sample; do not join labels until committed",
        "category_wording": {
            "a": "two or more distinct painted court lines visible AND at least one intersection of painted lines visible",
            "b": "painted court surface visible but not that",
            "c": "no painted court surface at all",
            "d": "cannot judge",
        },
        "span_inclusive": [SPAN_START, SPAN_END], "sample_size": len(plan),
        "spacing_frames": f"{SPAN_SIZE}/{len(plan)} = {SPAN_SIZE / len(plan):.6f}",
        "index_rule": "start + floor((2*i+1)*span_size/(2*n)) for i=0..n-1",
        "random_seed": PART_A_SEED, "sampled_indices_chronological": indices,
        "blind_order": plan, "source": source,
    }, indent=2) + "\n")


def _read_labels(path: Path, id_field: str) -> dict[int, str]:
    with path.open(newline="") as handle:
        rows = {int(row[id_field]): row["category"] for row in csv.DictReader(handle)}
    if not rows or set(rows.values()).difference(VALID_CATEGORIES):
        raise ValueError(f"labels missing or outside categories: {path}")
    return rows


def make_part_b(g275_dir: Path, output_dir: Path) -> None:
    """Copy an exact stratified random G275 re-judge set without decoding frames."""
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing nonempty output: {output_dir}")
    labels = _read_labels(g275_dir / "first_pass_labels.csv", "blind_id")
    strata = {category: sorted(key for key, value in labels.items() if value == category) for category in VALID_CATEGORIES}
    chooser = random.Random(PART_B_SEED)
    selected = sorted(chooser.sample(strata["a"], 20) + strata["b"] + chooser.sample(strata["c"], 9))
    plan_ids = list(selected)
    chooser.shuffle(plan_ids)
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(parents=True)
    copied = []
    for rejudge_id, g275_id in enumerate(plan_ids):
        source = g275_dir / "blind_frames" / f"blind_{g275_id:03d}.jpg"
        target = frames_dir / f"part_b_{rejudge_id:03d}.jpg"
        shutil.copyfile(source, target)
        copied.append({"rejudge_id": rejudge_id, "g275_blind_id": g275_id, "sha256": _sha256(target)})
    _write_boards(frames_dir, "part_b", len(plan_ids), output_dir / "boards")
    (output_dir / "blind_manifest.json").write_text(json.dumps({
        "purpose": "G278 Part B blind stratified re-judge; do not join first-pass labels until committed",
        "random_seed": PART_B_SEED, "composition": {"a": 20, "b": 11, "c": 9, "d": 0},
        "blind_order": copied,
        "source_frames": str(g275_dir / "blind_frames"),
        "source_frame_resolution": "1920x1080",
        "copy_method": "shutil.copyfile; no decode, crop, or pixel alteration",
    }, indent=2) + "\n")


def two_proportion(count_a: int, n_a: int, count_b: int, n_b: int) -> dict[str, float]:
    """Return pooled two-sided normal two-proportion test statistics."""
    pooled = (count_a + count_b) / (n_a + n_b)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
    z = ((count_a / n_a) - (count_b / n_b)) / se
    return {"pooled_p": pooled, "se": se, "z": z, "p_two_sided_nominal": math.erfc(abs(z) / math.sqrt(2))}


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    """Return a two-sided 95 percent Wilson interval."""
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return centre - radius, centre + radius


def write_summary(part_a_dir: Path, part_b_dir: Path, g275_dir: Path, output: Path) -> None:
    """Unblind committed verdicts and write reproducible Part A/B statistics."""
    part_a = _read_labels(part_a_dir / "blind_labels.csv", "blind_id")
    part_b = _read_labels(part_b_dir / "blind_labels.csv", "rejudge_id")
    original = _read_labels(g275_dir / "first_pass_labels.csv", "blind_id")
    part_a_counts = Counter(part_a.values())
    manifest_b = json.loads((part_b_dir / "blind_manifest.json").read_text())
    confusion = {row: {column: 0 for column in VALID_CATEGORIES} for row in VALID_CATEGORIES}
    for item in manifest_b["blind_order"]:
        confusion[original[int(item["g275_blind_id"])]] [part_b[int(item["rejudge_id"])]] += 1
    a_count = part_a_counts["a"]
    interval = wilson_interval(a_count, len(part_a))
    a_to_b = confusion["a"]["b"]
    b_to_a = confusion["b"]["a"]
    output.write_text(json.dumps({
        "part_a": {
            "counts": {category: part_a_counts[category] for category in VALID_CATEGORIES},
            "n": len(part_a), "a_fraction": a_count / len(part_a), "a_wilson_95": interval,
            "two_proportion_vs_g275_118_of_180": two_proportion(a_count, len(part_a), 118, 180),
        },
        "part_b": {
            "n": len(part_b), "confusion_rows_first_pass_columns_rejudge": confusion,
            "a_to_b": a_to_b, "b_to_a": b_to_a,
            "a_b_boundary_observed_transition_rates": {"a_to_b": a_to_b / 20, "b_to_a": b_to_a / 11},
            "repeatability_adjusted_a_fraction": (118 * (1 - a_to_b / 20) + 11 * (b_to_a / 11)) / 180,
        },
    }, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    part_a = commands.add_parser("part-a")
    part_a.add_argument("--video", type=Path, required=True)
    part_a.add_argument("--output-dir", type=Path, required=True)
    part_b = commands.add_parser("part-b")
    part_b.add_argument("--g275-dir", type=Path, required=True)
    part_b.add_argument("--output-dir", type=Path, required=True)
    summary = commands.add_parser("summary")
    summary.add_argument("--part-a-dir", type=Path, required=True)
    summary.add_argument("--part-b-dir", type=Path, required=True)
    summary.add_argument("--g275-dir", type=Path, required=True)
    summary.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.command == "part-a":
        make_part_a(arguments.video, arguments.output_dir)
    elif arguments.command == "part-b":
        make_part_b(arguments.g275_dir, arguments.output_dir)
    else:
        write_summary(arguments.part_a_dir, arguments.part_b_dir, arguments.g275_dir, arguments.output)


if __name__ == "__main__":
    main()
