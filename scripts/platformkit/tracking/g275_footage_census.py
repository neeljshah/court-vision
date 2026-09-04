"""Create G275's blind, uniformly spaced frame sample using ffmpeg seeks."""

from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2


FRAME_COUNT = 174_430
FPS = 30
SAMPLE_SIZE = 180
RANDOM_SEED = 2_750_904
VALID_CATEGORIES = ("a", "b", "c", "d")


@dataclass(frozen=True)
class BlindFrame:
    blind_id: int
    source_frame: int
    source_seconds: float


def uniform_indices(frame_count: int = FRAME_COUNT, n: int = SAMPLE_SIZE) -> list[int]:
    """Return centred, evenly spaced source-frame indices for a finite clip."""
    if frame_count <= 0 or n <= 0 or n > frame_count:
        raise ValueError("require 0 < n <= frame_count")
    return [((2 * item + 1) * frame_count) // (2 * n) for item in range(n)]


def blind_plan(indices: list[int], seed: int = RANDOM_SEED) -> list[BlindFrame]:
    """Assign a reproducible random blind sequence to fixed sample indices."""
    shuffled = list(indices)
    random.Random(seed).shuffle(shuffled)
    return [BlindFrame(item, frame, frame / FPS) for item, frame in enumerate(shuffled)]


def _run_ffmpeg(video: Path, frame: BlindFrame, output: Path) -> None:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-ss",
        f"{frame.source_seconds:.6f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-q:v",
        "5",
        "-an",
        "-y",
        str(output),
    ]
    subprocess.run(command, check=True)


def _write_board(images: list[Path], board_path: Path) -> None:
    tiles: list[object] = []
    for image_path in images:
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"cannot open extracted frame {image_path}")
        tile = cv2.resize(image, (480, 270), interpolation=cv2.INTER_AREA)
        blind_id = image_path.stem.split("_")[-1]
        cv2.rectangle(tile, (0, 0), (125, 30), (0, 0, 0), -1)
        cv2.putText(
            tile,
            f"blind {blind_id}",
            (8, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        tiles.append(tile)
    while len(tiles) < 12:
        tiles.append(cv2.cvtColor(cv2.UMat(270, 480, cv2.CV_8UC1).get(), cv2.COLOR_GRAY2BGR))
    rows = [cv2.hconcat(tiles[offset : offset + 4]) for offset in range(0, 12, 4)]
    if not cv2.imwrite(str(board_path), cv2.vconcat(rows), [cv2.IMWRITE_JPEG_QUALITY, 90]):
        raise RuntimeError(f"cannot write board {board_path}")


def make_sample(video: Path, output_dir: Path) -> None:
    """Seek-extract the full blind sample and write its sealed mapping/template."""
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty {output_dir}")
    frames_dir = output_dir / "blind_frames"
    boards_dir = output_dir / "blind_boards"
    frames_dir.mkdir(parents=True)
    boards_dir.mkdir()
    indices = uniform_indices()
    plan = blind_plan(indices)
    for frame in plan:
        _run_ffmpeg(video, frame, frames_dir / f"blind_{frame.blind_id:03d}.jpg")
    for board_number, offset in enumerate(range(0, len(plan), 12)):
        board_images = [frames_dir / f"blind_{item:03d}.jpg" for item in range(offset, offset + 12)]
        _write_board(board_images, boards_dir / f"board_{board_number:02d}.jpg")
    manifest = {
        "purpose": "G275 blind first pass; do not read source_frame mapping until labels commit",
        "source_frame_count": FRAME_COUNT,
        "fps": FPS,
        "sample_size": SAMPLE_SIZE,
        "spacing_frames": f"{FRAME_COUNT}/{SAMPLE_SIZE} = {FRAME_COUNT / SAMPLE_SIZE:.9f}",
        "index_rule": "floor((2*i+1)*174430/(2*180)) for i=0..179",
        "random_seed": RANDOM_SEED,
        "sampled_indices_chronological": indices,
        "blind_order": [asdict(frame) for frame in plan],
    }
    (output_dir / "blind_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with (output_dir / "first_pass_labels.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("blind_id", "category"))
        writer.writeheader()
        writer.writerows({"blind_id": item, "category": ""} for item in range(SAMPLE_SIZE))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    make_sample(arguments.video, arguments.output_dir)


if __name__ == "__main__":
    main()
