"""G373 phase 1: blind NATIVE reference-v2 rating sheets.

One sheet per frame key, at the frame's own 1920x1080 pixel dimensions.  The
pixel dimensions are never reduced; only JPEG quality is stepped down to meet the
sealed byte cap, and the quality each sheet actually landed on is recorded so the
cost of the cap is a measured number rather than an assumption.

A sheet carries no candidate box, no detector score, no arm name, no previous
centre, no v1 rating, no burned-in text and no causal strip -- the v1 builder's
960-pixel panel plus 320-pixel strip is deliberately NOT reused, because a strip
of neighbours and a downscaled panel are exactly what the v2 procedure replaces.
"""
from __future__ import annotations

import os

for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
             "NUMEXPR_NUM_THREADS", "OPENCV_NUM_THREADS"):
    os.environ[_var] = "1"

import argparse
from pathlib import Path

from scripts.platformkit.tracking.g363_ball_coverage import file_sha256, read_csv, write_csv

SHEET_MAX_BYTES = 200_000
QUALITY_LADDER = (92, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30)
SHEET_FIELDS = ("frame_key", "split", "source", "sheet", "sheet_sha256", "sheet_bytes",
                "quality", "width", "height", "over_cap")


def encode(cv2, image) -> tuple[bytes, int, bool]:
    """Native-size JPEG at the highest quality that fits the sealed byte cap."""
    buffer = None
    for quality in QUALITY_LADDER:
        ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        if ok and buffer.nbytes <= SHEET_MAX_BYTES:
            return buffer.tobytes(), quality, False
    return buffer.tobytes(), QUALITY_LADDER[-1], True


def build(rows: list[dict], caches: list[Path], out_dir: Path) -> list[dict]:
    """Write one native blind sheet per frame key and return the sheet manifest."""
    import cv2

    cv2.setNumThreads(1)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    for index, row in enumerate(rows):
        key = row["frame_key"]
        image = None
        for cache in caches:
            candidate = Path(cache) / (key + ".png")
            if candidate.exists():
                image = cv2.imread(str(candidate))
                break
        if image is None:
            print("ABSENT-CACHE " + key, flush=True)
            continue
        payload, quality, over = encode(cv2, image)
        target = out_dir / (key[:12] + ".jpg")
        target.write_bytes(payload)
        manifest.append({"frame_key": key, "split": row["split"], "source": row.get("source", ""),
                         "sheet": target.name, "sheet_sha256": file_sha256(target),
                         "sheet_bytes": target.stat().st_size, "quality": quality,
                         "width": image.shape[1], "height": image.shape[0],
                         "over_cap": int(over)})
        if (index + 1) % 200 == 0:
            print(f"SHEETS {index + 1}/{len(rows)}", flush=True)
    return manifest


def run(args) -> int:
    rows: list[dict] = []
    seen: set[str] = set()
    for label, path in (("sealed", args.frames), ("extra", args.extra)):
        if not path:
            continue
        for row in read_csv(Path(path)):
            if row["frame_key"] in seen:
                continue
            seen.add(row["frame_key"])
            rows.append({"frame_key": row["frame_key"], "split": row["split"], "source": label})
    rows.sort(key=lambda row: (row["source"], row["split"], row["frame_key"]))
    manifest = build(rows, [Path(item) for item in args.cache], Path(args.out_dir))
    write_csv(Path(args.manifest), SHEET_FIELDS, manifest)
    qualities = sorted(row["quality"] for row in manifest)
    print(f"SHEETS-V2 scheduled={len(rows)} written={len(manifest)} "
          f"absent={len(rows) - len(manifest)} over_cap={sum(row['over_cap'] for row in manifest)} "
          f"quality_min={qualities[0] if qualities else 0} "
          f"quality_p50={qualities[len(qualities) // 2] if qualities else 0} "
          f"max_bytes={max((row['sheet_bytes'] for row in manifest), default=0)}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g373_sheets_v2")
    parser.add_argument("--frames", required=True)
    parser.add_argument("--extra", default="")
    parser.add_argument("--cache", required=True, action="append")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--manifest", required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
