"""G386 live runner: seal a census, draw evenly, capture one pass, check pixels.

Subcommands: census (seal CENSUS_UTC, write census.csv + draw.csv), capture
(run the sealed draw through pin_copy_one_pass), watch (rotation re-check).
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.platformkit.tracking.g386_pin_copy import (  # noqa: E402
    pin_copy_one_pass, release_staging)

LEDGER = Path("/workspace/data/tracking/track_daemon_ledger.jsonl")
POOLS = [("live_corpus", Path("/workspace/data/footage_corpus")),
         ("retained_g364_val", Path("/workspace/g364_scratch/val")),
         ("retained_g380_sources", Path("/workspace/g380_scratch/sources"))]
SCRATCH = Path("/workspace/g386_scratch")
EV = Path("docs/evidence/tracking/g386_pin_copy_one_pass_2026-09-10")
SECTION = re.compile(r"^(?:(?P<sport>[a-z0-9_]+?)__)?(?P<ytid>[A-Za-z0-9_-]+)_s(?P<off>\d+)$")
DRAW_N = 30


def _parse(stem: str):
    match = SECTION.match(stem)
    if not match:
        return None
    return match.group("ytid"), int(match.group("off"))


def _filesystem_index() -> dict:
    index = {}
    for pool, root in POOLS:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.mp4")):
            key = _parse(path.stem)
            if key is None or key in index:
                continue
            stat = path.stat()
            index[key] = dict(pool=pool, path=str(path), bytes=stat.st_size,
                              mtime=int(stat.st_mtime))
    return index


def even_draw(available: list, want: int) -> list:
    """Pick `want` items spread evenly over the whole ordered pool, never a head slice."""
    if len(available) < want or want < 2:
        return list(available)
    return [available[round(i * (len(available) - 1) / (want - 1))] for i in range(want)]


def census(out: Path) -> None:
    census_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    raw = LEDGER.read_bytes()
    ledger_digest = hashlib.sha256(raw).hexdigest()
    ledger_rows = [json.loads(line) for line in raw.decode("ascii", "replace").splitlines() if line.strip()]
    meta = {}
    for row in ledger_rows:
        key = _parse(str(row.get("game_id", "")))
        if key is None:
            continue
        meta.setdefault(key, dict(finished_at=row.get("finished_at") or 0,
                                  sport=row.get("sport", ""), status=row.get("status", "")))
    index = _filesystem_index()
    keys = sorted(set(meta) | set(index))
    out.mkdir(parents=True, exist_ok=True)
    with (out / "census.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ytid", "offset", "sport", "ledger_status", "finished_at",
                         "retained", "pool", "source_path", "source_bytes"])
        for ytid, off in keys:
            info = index.get((ytid, off))
            met = meta.get((ytid, off), {})
            writer.writerow([ytid, off, met.get("sport", ""), met.get("status", "ABSENT_FROM_LEDGER"),
                             met.get("finished_at", 0), int(info is not None),
                             info["pool"] if info else "", info["path"] if info else "",
                             info["bytes"] if info else 0])
    available = sorted(index)
    picks = even_draw(available, DRAW_N)
    with (out / "draw.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle)
        writer.writerow(["attempt_id", "ytid", "offset", "pool", "source_path",
                         "source_bytes_at_census", "reader_contract"])
        for i, key in enumerate(picks):
            info = index[key]
            writer.writerow(["a%02d" % (i + 1), key[0], key[1], info["pool"], info["path"],
                             info["bytes"], "full_replay_source"])
    stamp = dict(census_utc=census_utc, census_epoch=int(time.time()),
                 ledger_rows=len(ledger_rows), ledger_sha256=ledger_digest,
                 census_sections=len(keys),
                 census_videos=len({k[0] for k in keys}),
                 available_sections=len(available),
                 available_videos=len({k[0] for k in available}),
                 live_corpus_sections=sum(1 for v in index.values() if v["pool"] == "live_corpus"),
                 draw_sections=len(picks), draw_videos=len({k[0] for k in picks}))
    (out / "census_stamp.json").write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n",
                                           encoding="ascii")
    print(json.dumps(stamp, sort_keys=True))


def _interior_png_digest(video: Path, seconds: float, png_out: Path | None):
    command = ["ffmpeg", "-v", "error", "-ss", "%.3f" % seconds, "-i", str(video),
               "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"]
    done = subprocess.run(command, check=False, capture_output=True)
    if done.returncode or not done.stdout:
        return "", 0
    if png_out is not None:
        png_out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % seconds, "-i", str(video),
                        "-frames:v", "1", "-q:v", "3", str(png_out)], check=False)
    return hashlib.sha256(done.stdout).hexdigest(), len(done.stdout)


def _receiver_decodes_interior(video: Path) -> bool:
    """Decode the receiver copy's midpoint frame before its receipt is issued."""
    duration = _duration(video)
    if duration <= 0:
        return False
    return bool(_interior_png_digest(video, duration / 2.0, None)[0])


def _duration(video: Path) -> float:
    done = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                           "-of", "csv=p=0", str(video)], check=False, capture_output=True, text=True)
    try:
        return float(done.stdout.strip())
    except ValueError:
        return 0.0


def capture(out: Path, lo: int = 0, hi: int = DRAW_N) -> None:
    """Capture draw rows [lo, hi) and HOLD each receipted object for the off-pod receiver.

    Amendment A1: the staged copy is released after the pod receipt, but the
    acknowledged receiver object is held under scratch/hold until the PC
    receiver has read it back, verified its digest and retained it off-pod.
    """
    draw = list(csv.DictReader((out / "draw.csv").open(encoding="ascii")))[lo:hi]
    ledger_line = "track_daemon_ledger.jsonl@%s" % json.loads(
        (out / "census_stamp.json").read_text(encoding="ascii"))["ledger_sha256"]
    stage, receiver = SCRATCH / "stage", SCRATCH / "receiver"
    attempts, identities, receipts, pixels = [], [], [], []
    for row in draw:
        source = Path(row["source_path"])
        started = time.time()
        record = pin_copy_one_pass(source, stage, receiver, ledger_line, row["attempt_id"],
                                   receiver_decode=_receiver_decodes_interior)
        attempts.append(dict(attempt_id=row["attempt_id"], ytid=row["ytid"], offset=row["offset"],
                             pool=row["pool"], source_path=row["source_path"],
                             status=record.status, seconds=round(time.time() - started, 2)))
        identities.append(dict(attempt_id=row["attempt_id"], source_path=record.source_path,
                               source_sha256=record.source_sha256, source_bytes=record.source_bytes,
                               source_device=record.source_device, source_inode=record.source_inode,
                               ffprobe_stream_sha256=hashlib.sha256(
                                   record.ffprobe_stream.encode("ascii", "replace")).hexdigest(),
                               ledger_snapshot_line=record.ledger_snapshot_line))
        receipt = record.receipt
        receipts.append(dict(attempt_id=row["attempt_id"],
                             version_id=receipt.version_id if receipt else "",
                             receiver_sha256=receipt.receiver_sha256 if receipt else "",
                             receiver_bytes=receipt.receiver_bytes if receipt else 0,
                             acknowledged=int(bool(receipt and receipt.acknowledged)),
                             pixel_opened=int(bool(receipt and receipt.pixel_opened)),
                             byte_agreement=int(bool(receipt and receipt.receiver_sha256 == record.source_sha256)),
                             hold_path=""))
        if record.status != "CAPTURED" or receipt is None:
            pixels.append(dict(attempt_id=row["attempt_id"], mid_seconds=0.0, copy_png_sha256="",
                               original_png_sha256="", original_present=0, pixel_agreement="NO_CAPTURE",
                               render=""))
            continue
        staged = Path(record.staged_path)
        received = receiver / (receipt.version_id + ".bin")
        mid = round(_duration(received) / 2.0, 3)
        render = out / "renders" / ("render_%s_%s_s%s.jpg" % (row["attempt_id"], row["ytid"], row["offset"]))
        copy_digest, _ = _interior_png_digest(received, mid, render)
        original_present = source.is_file()
        original_digest = _interior_png_digest(source, mid, None)[0] if original_present else ""
        if not copy_digest:
            agreement = "DECODE_FAIL"
        elif not original_present:
            agreement = "ORIGINAL_ABSENT"
        else:
            agreement = "MATCH" if original_digest == copy_digest else "MISMATCH"
        pixels.append(dict(attempt_id=row["attempt_id"], mid_seconds=mid, copy_png_sha256=copy_digest,
                           original_png_sha256=original_digest, original_present=int(original_present),
                           pixel_agreement=agreement, render=render.name))
        release_staging(record)
        staged.unlink(missing_ok=True)
        held = SCRATCH / "hold" / (row["attempt_id"] + ".mp4")
        held.parent.mkdir(parents=True, exist_ok=True)
        received.replace(held)
        receipts[-1]["hold_path"] = str(held)
    _write(out / "attempts.csv", attempts, append=True)
    _write(out / "source_identity.csv", identities, append=True)
    _write(out / "receiver_receipts.csv", receipts, append=True)
    _write(out / "pixel_checks.csv", pixels, append=True)
    print(json.dumps(dict(attempts=len(attempts),
                          captured=sum(1 for a in attempts if a["status"] == "CAPTURED"),
                          pixel_match=sum(1 for p in pixels if p["pixel_agreement"] == "MATCH"))))


def _write(path: Path, rows: list, append: bool = False) -> None:
    """Write rows; with append=True keep rows an earlier batch already wrote."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if append and path.is_file():
        rows = list(csv.DictReader(path.open(encoding="ascii"))) + rows
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def watch(out: Path, minutes: int, every: int) -> None:
    """Re-check every drawn source and the whole live corpus on a fixed cadence."""
    draw = list(csv.DictReader((out / "draw.csv").open(encoding="ascii")))
    rows, deadline = [], time.time() + minutes * 60
    live = POOLS[0][1]
    while True:
        elapsed = int(round((time.time() - _t0(out)) / 60.0))
        for row in draw:
            path = Path(row["source_path"])
            rows.append(dict(elapsed_min=elapsed, attempt_id=row["attempt_id"], pool=row["pool"],
                             source_path=row["source_path"], original_present=int(path.is_file()),
                             source_bytes=path.stat().st_size if path.is_file() else 0))
        for path in sorted(live.glob("*.mp4")) if live.is_dir() else []:
            rows.append(dict(elapsed_min=elapsed, attempt_id="live_observed", pool="live_corpus",
                             source_path=str(path), original_present=1,
                             source_bytes=path.stat().st_size if path.is_file() else 0))
        _write(out / "rotation_recheck.csv", rows)
        if time.time() >= deadline:
            break
        time.sleep(every * 60)
    print("watch done rows=%d" % len(rows))


def _t0(out: Path) -> float:
    return float(json.loads((out / "census_stamp.json").read_text(encoding="ascii"))["census_epoch"])


if __name__ == "__main__":
    command = sys.argv[1]
    target = EV if len(sys.argv) < 3 else Path(sys.argv[2])
    if command == "census":
        census(target)
    elif command == "capture":
        capture(target, int(sys.argv[3]) if len(sys.argv) > 4 else 0,
                int(sys.argv[4]) if len(sys.argv) > 4 else DRAW_N)
    elif command == "watch":
        watch(target, int(sys.argv[3]), int(sys.argv[4]))
    else:
        raise SystemExit("unknown command %s" % command)
