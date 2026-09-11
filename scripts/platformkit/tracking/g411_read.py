"""Integer-PTS readers for G411: ffprobe decode path and a stdlib MP4 parser.

Both readers return native container integers plus an exact rational time
base.  No float seconds field is ever read or produced here.
"""
from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from fractions import Fraction
from pathlib import Path

CONTAINER_BOXES = {"moov", "trak", "mdia", "minf", "stbl", "edts"}


def sha256_file(path: Path) -> str:
    """Hash one file in binary mode."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_capture(argv: list[str]) -> dict[str, object]:
    """Run a tool and return an argv/stdout-digest/returncode receipt."""
    done = subprocess.run(argv, capture_output=True, text=True)
    return {"argv": argv, "returncode": done.returncode,
            "stdout_sha256": hashlib.sha256(done.stdout.encode()).hexdigest(),
            "stdout_bytes": len(done.stdout), "stdout": done.stdout,
            "stderr_head": done.stderr[:400]}


def ffprobe_stream(path: Path, ffprobe: str) -> tuple[dict[str, str], dict]:
    """Read the native stream time base and declared rates (no seconds)."""
    argv = [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
            "stream=time_base,avg_frame_rate,r_frame_rate,nb_frames,codec_name,"
            "width,height,start_pts", "-of", "json", str(path)]
    receipt = run_capture(argv)
    payload = json.loads(receipt["stdout"]) if receipt["returncode"] == 0 else {}
    streams = payload.get("streams") or [{}]
    return streams[0], receipt


def ffprobe_integer_pts(path: Path, ffprobe: str) -> tuple[list, list, dict]:
    """Return presented integer PTS and best-effort integers, in source order."""
    argv = [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
            "frame=pts,best_effort_timestamp", "-of", "csv=p=0", str(path)]
    receipt = run_capture(argv)
    pts: list[int | None] = []
    best: list[int | None] = []
    for line in receipt["stdout"].splitlines():
        if not line.strip():
            continue
        cells = line.split(",")
        pts.append(_int_or_none(cells[0]))
        best.append(_int_or_none(cells[1]) if len(cells) > 1 else None)
    receipt.pop("stdout")
    return pts, best, receipt


def _int_or_none(text: str) -> int | None:
    text = text.strip()
    if not text or text in {"N/A", "n/a"}:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _iter_boxes(blob: bytes, start: int, end: int):
    offset = start
    while offset + 8 <= end:
        size, kind = struct.unpack_from(">I4s", blob, offset)
        name = kind.decode("latin1")
        head = 8
        if size == 1:
            size = struct.unpack_from(">Q", blob, offset + 8)[0]
            head = 16
        elif size == 0:
            size = end - offset
        if size < head:
            return
        yield name, offset + head, offset + size
        offset += size


def _find(blob: bytes, span: tuple[int, int], trail: list[str]):
    start, end = span
    for name, body, stop in _iter_boxes(blob, start, end):
        if name == trail[0]:
            if len(trail) == 1:
                return body, stop
            if name in CONTAINER_BOXES:
                found = _find(blob, (body, stop), trail[1:])
                if found:
                    return found
    return None


def _video_trak(blob: bytes) -> tuple[int, int] | None:
    moov = _find(blob, (0, len(blob)), ["moov"])
    if not moov:
        return None
    for name, body, stop in _iter_boxes(blob, moov[0], moov[1]):
        if name != "trak":
            continue
        hdlr = _find(blob, (body, stop), ["mdia", "hdlr"])
        if hdlr and blob[hdlr[0] + 8:hdlr[0] + 12] == b"vide":
            return body, stop
    return None


def mp4_integer_pts(path: Path) -> dict[str, object]:
    """Parse timescale and integer composition times straight from the bytes.

    Composition times are sorted, trimmed by the edit list, then normalized to
    the first retained sample so both readers share the sealed PTS origin.
    """
    blob = path.read_bytes()
    trak = _video_trak(blob)
    if not trak:
        return {"status": "UNKNOWN", "reason": "no_video_trak"}
    mdhd = _find(blob, trak, ["mdia", "mdhd"])
    stts = _find(blob, trak, ["mdia", "minf", "stbl", "stts"])
    if not mdhd or not stts:
        return {"status": "UNKNOWN", "reason": "no_mdhd_or_stts"}
    version = blob[mdhd[0]]
    timescale = struct.unpack_from(">I", blob, mdhd[0] + (20 if version else 12))[0]
    if timescale <= 0:
        return {"status": "UNKNOWN", "reason": "nonpositive_timescale"}
    deltas = _decode_stts(blob, stts)
    offsets = _decode_ctts(blob, _find(blob, trak, ["mdia", "minf", "stbl", "ctts"]))
    shift = _edit_shift(blob, _find(blob, trak, ["edts", "elst"]))
    decode_time = 0
    composition: list[int] = []
    for index, delta in enumerate(deltas):
        offset = offsets[index] if index < len(offsets) else 0
        composition.append(decode_time + offset)
        decode_time += delta
    composition.sort()
    kept = [value for value in composition if value >= shift]
    origin = kept[0] if kept else 0
    return {"status": "OK", "timescale": timescale, "media_time_shift": shift,
            "sample_count": len(deltas), "trimmed_by_edit_list":
            len(composition) - len(kept), "raw_first_composition": origin,
            "pts": [value - origin for value in kept],
            "time_base": "1/%d" % timescale}


def _decode_stts(blob: bytes, span: tuple[int, int]) -> list[int]:
    count = struct.unpack_from(">I", blob, span[0] + 4)[0]
    deltas: list[int] = []
    for entry in range(count):
        n, delta = struct.unpack_from(">II", blob, span[0] + 8 + entry * 8)
        deltas.extend([delta] * n)
    return deltas


def _decode_ctts(blob: bytes, span: tuple[int, int] | None) -> list[int]:
    if not span:
        return []
    signed = blob[span[0]] == 1
    count = struct.unpack_from(">I", blob, span[0] + 4)[0]
    offsets: list[int] = []
    for entry in range(count):
        base = span[0] + 8 + entry * 8
        n = struct.unpack_from(">I", blob, base)[0]
        value = struct.unpack_from(">i" if signed else ">I", blob, base + 4)[0]
        offsets.extend([value] * n)
    return offsets


def _edit_shift(blob: bytes, span: tuple[int, int] | None) -> int:
    """Return the media_time an edit list removes from the presented stream."""
    if not span:
        return 0
    version = blob[span[0]]
    count = struct.unpack_from(">I", blob, span[0] + 4)[0]
    if count < 1:
        return 0
    if version == 1:
        media_time = struct.unpack_from(">q", blob, span[0] + 8 + 8)[0]
    else:
        media_time = struct.unpack_from(">i", blob, span[0] + 8 + 4)[0]
    return max(0, media_time)


def rational(text: str) -> Fraction:
    """Parse an `a/b` rational exactly."""
    numerator, denominator = text.split("/", 1)
    return Fraction(int(numerator), int(denominator))
