"""Build opaque blind G382 sheets as byte-identical copies of full native frames."""
from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
from pathlib import Path

SHEET_FIELDS = ("opaque_id", "sheet", "sheet_sha256", "sheet_bytes", "width", "height", "status")
IDENTITY_FIELDS = ("opaque_id", "frame_key", "native_path", "sheet", "native_sha256", "width", "height", "status")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(rows: list[dict[str, str]], out_dir: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Copy full native bytes without overlays; identity mapping stays separate from rater sheet rows."""
    import cv2
    out_dir.mkdir(parents=True, exist_ok=True)
    sheets, identities = [], []
    for index, row in enumerate(rows, start=1):
        opaque_id = "G382_%03d" % index
        source = Path(row["native_path"])
        status, width, height, digest, target = "ABSENT", "", "", "", out_dir / (opaque_id + source.suffix)
        if source.is_file():
            image = cv2.imread(str(source), cv2.IMREAD_COLOR)
            if image is None:
                status = "DECODE_FAILED"
            else:
                height, width = str(image.shape[0]), str(image.shape[1])
                shutil.copyfile(source, target)
                digest, status = sha256(target), "READY"
                if digest != sha256(source):
                    raise RuntimeError("native sheet copy digest mismatch")
        sheets.append({"opaque_id": opaque_id, "sheet": target.name if status == "READY" else "",
                       "sheet_sha256": digest, "sheet_bytes": str(target.stat().st_size) if target.exists() else "0",
                       "width": width, "height": height, "status": status})
        identities.append({"opaque_id": opaque_id, "frame_key": row["frame_key"],
                           "native_path": row["native_path"], "sheet": target.name if status == "READY" else "",
                           "native_sha256": digest, "width": width, "height": height, "status": status})
    return sheets, identities


def write(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--sheet-manifest", type=Path, required=True)
    parser.add_argument("--identity-map", type=Path, required=True)
    args = parser.parse_args()
    with args.frames.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    sheets, identities = build(rows, args.out_dir)
    write(args.sheet_manifest, SHEET_FIELDS, sheets); write(args.identity_map, IDENTITY_FIELDS, identities)
    print("G382_SHEETS planned=%d ready=%d" % (len(rows), sum(row["status"] == "READY" for row in sheets)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
