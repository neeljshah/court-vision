"""G386 amendment A1 off-pod receiver: read back, verify, decode and RETAIN.

The PC is the receiver of record for every full_replay_source row.  It reads
each pulled object back independently, verifies its SHA-256 against the pod
receipt, decodes the requested interior frame locally, and keeps the object
outside the repository so `required reader objects retained` is measurable.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

OBJECTS = Path("C:/Users/neelj/nba-ai-system/data/pod_backup_2026-09-10/g386_objects")
CHUNK_BYTES = 1024 * 1024


def digest_and_size(path: Path) -> tuple[str, int]:
    """Independently read the retained object back from disk."""
    digest, total = hashlib.sha256(), 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(block)
            total += len(block)
    return digest.hexdigest(), total


def raw_frame_digest(path: Path, seconds: float) -> str:
    """Digest one interior frame as native yuv420p, which is decoder-version independent."""
    done = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % seconds, "-i", str(path),
                           "-frames:v", "1", "-pix_fmt", "yuv420p", "-f", "rawvideo", "-"],
                          check=False, capture_output=True)
    return "" if done.returncode or not done.stdout else hashlib.sha256(done.stdout).hexdigest()


def originals(evidence: Path) -> None:
    """Pod side: digest the interior frame of each ORIGINAL that still exists."""
    rows = list(csv.DictReader((evidence / "pixel_checks.csv").open(encoding="ascii")))
    sources = {row["attempt_id"]: row["source_path"]
               for row in csv.DictReader((evidence / "draw.csv").open(encoding="ascii"))}
    for row in rows:
        source = Path(sources[row["attempt_id"]])
        row["original_raw_yuv_sha256"] = (raw_frame_digest(source, float(row["mid_seconds"] or 0.0))
                                          if source.is_file() else "")
        row["original_present_at_pixel_check"] = int(source.is_file())
    _write(evidence / "pixel_checks.csv", rows)
    print(json.dumps(dict(rows=len(rows),
                          originals_digested=sum(1 for r in rows if r["original_raw_yuv_sha256"]))))


def decode_interior(path: Path, seconds: float) -> tuple[str, str]:
    """Decode one interior frame on the PC; return (png sha256, WxH) or ("", "")."""
    frame = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % seconds, "-i", str(path),
                            "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
                           check=False, capture_output=True)
    if frame.returncode or not frame.stdout:
        return "", ""
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0:s=x", str(path)],
                           check=False, capture_output=True, text=True)
    return hashlib.sha256(frame.stdout).hexdigest(), probe.stdout.strip()


def retain_row(receipt: dict, mid_seconds: float, objects: Path) -> dict:
    """Measure one retained object against the pod receipt it should reproduce."""
    stem = Path(receipt["source_path"]).stem
    obj = objects / (stem + ".mp4")
    if not obj.is_file():
        return dict(retained_path="", retained_sha256="", retained_bytes=0,
                    retained=0, pc_readback_match=0, pc_decode_ok=0,
                    pc_frame_png_sha256="", pc_frame_dims="")
    sha, size = digest_and_size(obj)
    png, dims = decode_interior(obj, mid_seconds)
    return dict(retained_path=str(obj), retained_sha256=sha, retained_bytes=size,
                retained=1, pc_readback_match=int(sha == receipt["receiver_sha256"]),
                pc_decode_ok=int(bool(png)), pc_frame_png_sha256=png, pc_frame_dims=dims)


def main(evidence: Path, objects: Path = OBJECTS) -> None:
    receipts = list(csv.DictReader((evidence / "receiver_receipts.csv").open(encoding="ascii")))
    pixels = {row["attempt_id"]: row
              for row in csv.DictReader((evidence / "pixel_checks.csv").open(encoding="ascii"))}
    identity = {row["attempt_id"]: row["source_path"]
                for row in csv.DictReader((evidence / "source_identity.csv").open(encoding="ascii"))}
    draw = {row["attempt_id"]: row["source_path"]
            for row in csv.DictReader((evidence / "draw.csv").open(encoding="ascii"))}
    for receipt in receipts:
        receipt["source_path"] = identity.get(receipt["attempt_id"]) or draw[receipt["attempt_id"]]
        pixel = pixels[receipt["attempt_id"]]
        measured = retain_row(receipt, float(pixel["mid_seconds"] or 0.0), objects)
        receipt.update(measured)
        mid = float(pixel["mid_seconds"] or 0.0)
        raw = raw_frame_digest(Path(measured["retained_path"]), mid) if measured["retained"] else ""
        original_raw = pixel.get("original_raw_yuv_sha256", "")
        pixel.update(pc_frame_png_sha256=measured["pc_frame_png_sha256"],
                     pc_frame_dims=measured["pc_frame_dims"],
                     pc_decode_ok=measured["pc_decode_ok"],
                     retained_raw_yuv_sha256=raw,
                     raw_pixel_agreement=("NO_RETAINED_OBJECT" if not raw else
                                          "ORIGINAL_ABSENT" if not original_raw else
                                          "MATCH" if raw == original_raw else "MISMATCH"))
    _write(evidence / "receiver_receipts.csv", receipts)
    _write(evidence / "pixel_checks.csv", list(pixels.values()))
    print(json.dumps(dict(rows=len(receipts),
                          retained=sum(int(r["retained"]) for r in receipts),
                          readback_match=sum(int(r["pc_readback_match"]) for r in receipts),
                          decoded=sum(int(r["pc_decode_ok"]) for r in receipts))))


def _write(path: Path, rows: list) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    if sys.argv[1] == "originals":
        originals(Path(sys.argv[2]))
    else:
        main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else OBJECTS)
