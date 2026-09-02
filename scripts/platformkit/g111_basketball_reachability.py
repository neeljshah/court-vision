"""Build the reproducible, all-clip frame sample for the G111 census."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import random

import cv2


SEED = 1112026
STRATA = 20
EXPECTED_CLIPS = (
    "ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4",
    "ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p.mp4",
    "ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss.mp4",
    "ncaa_basketball__ncaa_basketball_sRtHQbywiTE.mp4",
    "ncaa_basketball__ncaa_basketball_tiUvyvWOCxo.mp4",
    "ncaa_basketball__ncaa_basketball_zqBCKovJCQU.mp4",
    "wnba__wnba_01.mp4",
    "wnba__wnba_01_1080p.mp4",
    "wnba__wnba_02.mp4",
    "wnba__wnba_04.mp4",
    "wnba__wnba_05.mp4",
)


def seeded_stratified_indices(
    frame_count: int, rng: random.Random, strata: int = STRATA
) -> list[int]:
    """Return one random index from every non-overlapping temporal stratum."""
    if frame_count < strata:
        raise ValueError(f"frame_count={frame_count} is smaller than strata={strata}")
    result: list[int] = []
    for slot in range(strata):
        start = frame_count * slot // strata
        stop = frame_count * (slot + 1) // strata
        result.append(rng.randrange(start, stop))
    return result


def _source_files(source_dir: Path) -> list[Path]:
    files = sorted(source_dir / name for name in EXPECTED_CLIPS)
    missing = [path.name for path in files if not path.is_file()]
    observed = sorted(path.name for path in source_dir.glob("ncaa_basketball__*.mp4"))
    observed += sorted(path.name for path in source_dir.glob("wnba__*.mp4"))
    unexpected = sorted(set(observed).difference(EXPECTED_CLIPS))
    if missing or unexpected:
        raise ValueError(f"basketball inventory mismatch: missing={missing}, unexpected={unexpected}")
    return files


def _video_metadata(path: Path) -> tuple[int, int, int]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"cannot open {path}")
    try:
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        capture.release()
    if count <= 0 or width <= 0 or height <= 0:
        raise ValueError(f"invalid metadata for {path}: {count}x{width}x{height}")
    return count, width, height


def _read_frame(path: Path, frame_index: int) -> object:
    capture = cv2.VideoCapture(str(path))
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok:
        raise ValueError(f"cannot read {path} frame {frame_index}")
    return frame


def _annotate(frame: object, clip: str, slot: int, frame_index: int) -> object:
    annotated = frame.copy()
    label = f"{clip} slot={slot:02d} frame={frame_index}"
    cv2.rectangle(annotated, (0, 0), (min(annotated.shape[1], 760), 34), (0, 0, 0), -1)
    cv2.putText(annotated, label, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 1)
    return annotated


def _contact_sheet(rows: list[dict[str, object]], output: Path) -> None:
    tiles: list[object] = []
    for row in rows:
        image = cv2.imread(str(output.parent.parent / str(row["render"])))
        if image is None:
            raise ValueError(f"missing render {row['render']}")
        height = 180
        width = round(image.shape[1] * height / image.shape[0])
        tiles.append(cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA))
    cell_width = max(tile.shape[1] for tile in tiles)
    padded: list[object] = []
    for tile in tiles:
        canvas = cv2.copyMakeBorder(tile, 0, 0, 0, cell_width - tile.shape[1], cv2.BORDER_CONSTANT)
        padded.append(canvas)
    grid = [cv2.hconcat(padded[index:index + 4]) for index in range(0, len(padded), 4)]
    cv2.imwrite(str(output), cv2.vconcat(grid))


def build_sample(source_dir: Path, output_dir: Path) -> list[dict[str, object]]:
    """Render every seeded sample frame and return the manifest records."""
    source_files = _source_files(source_dir)
    renders = output_dir / "final_renders"
    contact_sheets = output_dir / "contact_sheets"
    renders.mkdir(parents=True, exist_ok=True)
    contact_sheets.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    rows: list[dict[str, object]] = []
    for source in source_files:
        frame_count, width, height = _video_metadata(source)
        clip = source.stem
        for slot, frame_index in enumerate(seeded_stratified_indices(frame_count, rng)):
            render_name = f"{clip}__s{slot:02d}__f{frame_index:06d}.jpg"
            frame = _annotate(_read_frame(source, frame_index), clip, slot, frame_index)
            if not cv2.imwrite(str(renders / render_name), frame):
                raise ValueError(f"cannot write {render_name}")
            rows.append({
                "clip": clip,
                "source_file": source.name,
                "slot": slot,
                "source_frame": frame_index,
                "decoded_frames": frame_count,
                "width": width,
                "height": height,
                "render": f"final_renders/{render_name}",
            })
    for clip in sorted({str(row["clip"]) for row in rows}):
        _contact_sheet([row for row in rows if row["clip"] == clip], contact_sheets / f"{clip}_contact_sheet.jpg")
    return rows


def write_manifest(output_dir: Path, rows: list[dict[str, object]]) -> None:
    """Write the sample manifest with the seed and per-clip strata counts."""
    counts = {clip: sum(row["clip"] == clip for row in rows) for clip in sorted({str(row["clip"]) for row in rows})}
    manifest = {
        "seed": SEED,
        "method": "one random frame from each of 20 equal temporal strata per clip",
        "strata_per_clip": STRATA,
        "per_clip": counts,
        "frames": rows,
    }
    (output_dir / "sample_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")


def _feature_count(value: str) -> int:
    features = [item for item in value.split(";") if item]
    if len(features) != len(set(features)):
        raise ValueError(f"duplicate named point feature: {value}")
    return len(features)


def write_hand_labels(output_dir: Path, decisions_path: Path) -> None:
    """Expand reviewed slot decisions into one explicit, complete frame-label row."""
    manifest = json.loads((output_dir / "sample_manifest.json").read_text(encoding="ascii"))
    decisions = json.loads(decisions_path.read_text(encoding="ascii"))
    expected_clips = set(manifest["per_clip"])
    if set(decisions["clips"]) != expected_clips:
        raise ValueError("manual decision clips do not match the complete manifest")
    labels: list[dict[str, str]] = []
    for frame in manifest["frames"]:
        clip_decisions = decisions["clips"][frame["clip"]]
        four = set(clip_decisions["four_point_slots"])
        two = set(clip_decisions["two_point_slots"])
        if four.intersection(two) or not four.union(two).issubset(set(range(STRATA))):
            raise ValueError(f"invalid reviewed slots for {frame['clip']}")
        slot = frame["slot"]
        if slot in four:
            point_features = ";".join((
                "paint_near_baseline_left_corner",
                "paint_near_baseline_right_corner",
                "paint_near_free_throw_left_corner",
                "paint_near_free_throw_right_corner",
            ))
            visible_lines = ";".join((
                "paint_near_baseline",
                "paint_near_free_throw",
                "paint_near_left_side",
                "paint_near_right_side",
            ))
            directions, note = "2", "four paint corners visibly discernible"
        elif slot in two:
            point_features = ";".join((
                "paint_near_baseline_left_corner",
                "paint_near_baseline_right_corner",
            ))
            visible_lines = ";".join((
                "paint_near_baseline",
                "paint_near_left_side",
                "paint_near_right_side",
            ))
            directions, note = "2", "two paint baseline corners visibly discernible"
        else:
            point_features = visible_lines = ""
            directions, note = "0", "fewer than two named point landmarks discernible"
        labels.append({
            "clip": str(frame["clip"]),
            "source_frame": str(frame["source_frame"]),
            "slot": str(slot),
            "point_features": point_features,
            "visible_lines": visible_lines,
            "visible_curves": "",
            "independent_directions": directions,
            "judgment_note": note,
            "render": str(frame["render"]),
        })
    with (output_dir / "frame_labels.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(labels[0]))
        writer.writeheader()
        writer.writerows(labels)


def summarize_labels(output_dir: Path) -> dict[str, object]:
    """Validate the complete hand-label set and write its additive summary."""
    manifest = json.loads((output_dir / "sample_manifest.json").read_text(encoding="ascii"))
    with (output_dir / "frame_labels.csv").open(newline="", encoding="ascii") as handle:
        labels = list(csv.DictReader(handle))
    expected = {(row["clip"], str(row["source_frame"]), str(row["slot"])) for row in manifest["frames"]}
    observed = {(row["clip"], row["source_frame"], row["slot"]) for row in labels}
    if expected != observed or len(labels) != len(observed):
        raise ValueError("labels must contain exactly one row for every manifest frame")
    point_counts = [_feature_count(row["point_features"]) for row in labels]
    directions = [int(row["independent_directions"]) for row in labels]
    if any(value < 0 for value in directions):
        raise ValueError("independent_directions cannot be negative")
    g84_path = Path("docs/evidence/tracking/g84_candidate_quality/sample_manifest.csv")
    with g84_path.open(newline="", encoding="ascii") as handle:
        g84_pairs = {(row["clip"], row["frame_index"]) for row in csv.DictReader(handle)}
    point_distribution = {str(value): point_counts.count(value) for value in range(max(point_counts) + 1)}
    direction_distribution = {str(value): directions.count(value) for value in range(max(directions) + 1)}
    summary: dict[str, object] = {
        "n": len(labels),
        "unique_clip_source_slot_pairs": len(observed),
        "g84_overlap_count": sum((row["clip"], row["source_frame"]) in g84_pairs for row in labels),
        "points_ge_2": sum(value >= 2 for value in point_counts),
        "points_ge_3": sum(value >= 3 for value in point_counts),
        "points_ge_4": sum(value >= 4 for value in point_counts),
        "point_distribution": point_distribution,
        "independent_direction_distribution": direction_distribution,
        "per_clip": {clip: sum(row["clip"] == clip for row in labels) for clip in sorted(manifest["per_clip"])},
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="ascii")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--summarize", action="store_true")
    parser.add_argument("--labels-decisions", type=Path)
    args = parser.parse_args()
    if args.summarize:
        summary = summarize_labels(args.output_dir)
        print(f"g111 summarized {summary['n']} hand labels")
    elif args.labels_decisions:
        write_hand_labels(args.output_dir, args.labels_decisions)
        print("g111 wrote complete hand-label rows")
    else:
        rows = build_sample(args.source_dir, args.output_dir)
        write_manifest(args.output_dir, rows)
        print(f"g111 sampled {len(rows)} frames across {len(EXPECTED_CLIPS)} clips")


if __name__ == "__main__":
    main()
