"""G411 extraction stage: retained bytes -> native integer PTS, two readers.

Writes `integer_pts/`, `source_receipts.csv`, `time_bases.csv`,
`extraction_receipts.json` and `common_receipts/tool_receipt.json`.  No float
seconds field is read from any container.
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.platformkit.tracking import g411_read as READ  # noqa: E402

G401_DIR = ROOT / "docs/evidence/tracking/g401_fps_cap_duration_shadow_2026-09-11"
OUT = ROOT / "docs/evidence/tracking/g411_integer_pts_extent_audit_2026-09-12"
SOURCE_FIELDS = ("draw_j", "source_name", "retained_path", "bytes", "sha256",
                  "draw_digest", "digest_matches_draw", "width", "height",
                 "time_base_reader_ffprobe", "time_base_reader_mp4",
                 "time_base_agree", "reader_ffprobe_frames",
                 "reader_mp4_samples_presented", "reader_mp4_samples_total",
                 "reader_multiset_agree", "reader_order_diff_count",
                 "first_pts_ffprobe", "last_pts_ffprobe", "missing_pts_count",
                 "status")


def tool_receipt(ffprobe: str, ffmpeg: str) -> dict:
    """Hash the actual tool binaries and record their versions."""
    rows = {}
    for label, exe in (("ffprobe", ffprobe), ("ffmpeg", ffmpeg)):
        found = _which(exe)
        version = subprocess.run([exe, "-version"], capture_output=True, text=True)
        rows[label] = {
            "invoked_as": exe, "resolved_path": found,
            "binary_sha256": READ.sha256_file(Path(found)) if found else None,
            "version_line": version.stdout.splitlines()[0] if version.stdout else "",
            "returncode": version.returncode}
    rows["python"] = {"version": platform.python_version(),
                      "implementation": platform.python_implementation()}
    rows["models_exercised"] = []
    return rows


def _which(exe: str) -> str | None:
    import shutil
    return shutil.which(exe)


def extract(sources: Path, ffprobe: str) -> tuple[list, list, list]:
    """Read every drawn source with both readers; retain every failure."""
    draw = list(csv.DictReader((G401_DIR / "draw.csv").open(newline="")))
    receipts: list = []
    bases: list = []
    commands: list = []
    (OUT / "integer_pts").mkdir(parents=True, exist_ok=True)
    for row in draw:
        name = row["source_name"]
        path = sources / name
        if not path.exists():
            receipts.append({"draw_j": row["draw_j"], "source_name": name,
                             "retained_path": str(path), "status": "MISSING"})
            continue
        meta, meta_receipt = READ.ffprobe_stream(path, ffprobe)
        pts, best, pts_receipt = READ.ffprobe_integer_pts(path, ffprobe)
        parsed = READ.mp4_integer_pts(path)
        digest = READ.sha256_file(path)
        order_diff = sum(1 for left, right in zip(pts, parsed.get("pts", []))
                         if left != right)
        multiset = sorted(v for v in pts if v is not None) == sorted(
            parsed.get("pts", []))
        tb_ff = meta.get("time_base") or ""
        tb_mp4 = parsed.get("time_base") or ""
        (OUT / "integer_pts" / (name + ".json")).write_bytes((json.dumps(
            {"source_name": name, "sha256": digest, "time_base": tb_ff,
              "time_base_reader_mp4": tb_mp4, "avg_frame_rate":
              meta.get("avg_frame_rate"), "r_frame_rate": meta.get("r_frame_rate"),
              "ffprobe_integer_pts": pts, "mp4_integer_pts": parsed.get("pts", []),
              "best_effort_timestamp": best}, indent=1) + chr(10)).encode("ascii"))
        receipts.append({
            "draw_j": row["draw_j"], "source_name": name,
            "retained_path": str(path), "bytes": path.stat().st_size,
            "sha256": digest, "draw_digest": row["digest"],
            "digest_matches_draw": digest == row["digest"],
            "width": meta.get("width") or "UNKNOWN: stream_width_absent",
            "height": meta.get("height"),
            "time_base_reader_ffprobe": tb_ff,
            "time_base_reader_mp4": tb_mp4,
            "time_base_agree": bool(tb_ff and tb_ff == tb_mp4),
            "reader_ffprobe_frames": len(pts),
            "reader_mp4_samples_presented": len(parsed.get("pts", [])),
            "reader_mp4_samples_total": parsed.get("sample_count"),
            "reader_multiset_agree": multiset,
            "reader_order_diff_count": order_diff,
            "first_pts_ffprobe": pts[0] if pts else None,
            "last_pts_ffprobe": pts[-1] if pts else None,
            "missing_pts_count": sum(1 for value in pts if value is None),
            "status": "OK" if (tb_ff and multiset) else "UNKNOWN"})
        bases.append({"source_name": name, "time_base": tb_ff,
                      "time_base_reader_mp4": tb_mp4,
                      "avg_frame_rate": meta.get("avg_frame_rate"),
                      "r_frame_rate": meta.get("r_frame_rate"),
                      "media_time_shift": parsed.get("media_time_shift"),
                      "trimmed_by_edit_list": parsed.get("trimmed_by_edit_list"),
                      "agree": bool(tb_ff and tb_ff == tb_mp4)})
        commands.append({"source_name": name, "stream_probe": meta_receipt,
                         "frame_probe": pts_receipt,
                         "mp4_parser": {"reader": "stdlib_mp4_stbl",
                                        "status": parsed.get("status")}})
    return receipts, bases, commands


def write_csv(path: Path, fields: tuple, rows: list) -> None:
    """Write one LF/ASCII table with a fixed field order."""
    with path.open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields),
                                lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: ("" if row.get(key) is None else row.get(key))
                             for key in fields})


def refresh_widths(sources: Path, ffprobe: str) -> list:
    """Add the retained stream width without re-reading frame schedules."""
    receipts = list(csv.DictReader((OUT / "source_receipts.csv").open(newline="")))
    for row in receipts:
        path = sources / row["source_name"]
        if path.exists():
            meta, _ = READ.ffprobe_stream(path, ffprobe)
            row["width"] = meta.get("width") or "UNKNOWN: stream_width_absent"
        else:
            row["width"] = "UNKNOWN: retained_source_missing"
    return receipts


def main() -> int:
    """Run the extraction stage over the retained off-pod sources."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", default="C:/Users/neelj/g401_receiver/sources")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--width-only", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.width_only:
        receipts = refresh_widths(Path(args.sources), args.ffprobe)
        write_csv(OUT / "source_receipts.csv", SOURCE_FIELDS, receipts)
        print("refreshed_widths=%d" % len(receipts))
        return 0
    (OUT / "common_receipts").mkdir(exist_ok=True)
    tools = tool_receipt(args.ffprobe, args.ffmpeg)
    receipts, bases, commands = extract(Path(args.sources), args.ffprobe)
    write_csv(OUT / "source_receipts.csv", SOURCE_FIELDS, receipts)
    write_csv(OUT / "time_bases.csv", ("source_name", "time_base",
                                       "time_base_reader_mp4", "avg_frame_rate",
                                       "r_frame_rate", "media_time_shift",
                                       "trimmed_by_edit_list", "agree"), bases)
    (OUT / "common_receipts" / "tool_receipt.json").write_bytes(
        (json.dumps(tools, indent=1, sort_keys=True) + chr(10)).encode("ascii"))
    (OUT / "extraction_receipts.json").write_bytes((
        json.dumps({"readers": ["ffprobe_show_frames_integer_pts",
                                 "stdlib_mp4_stbl_composition_times"],
                    "commands": commands}, indent=1) + chr(10)).encode("ascii"))
    ok = sum(1 for row in receipts if row.get("status") == "OK")
    print("extracted_sources=%d ok=%d" % (len(receipts), ok))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
