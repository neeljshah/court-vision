"""G380 fix 1b: receipt-versus-trace agreement on FURTHER preserved sections.

Attempt 1 traced a single section, so the sealed 100 pct receipt-trace bar rested
on n = 1.  This runs the PATCHED arm alone under the independent import-time hook
on more sections -- the unpatched arm contributes nothing to this comparison --
and reports containment and equality SEPARATELY per section.  The bar is not
moved: the measured value is reported as measured.

  cd /workspace/g380_scratch/armA
  python3 -m scripts.platformkit.tracking.g380_trace_sections --out <dir> --n 3

Sections already present in the fix-1a receipts.csv are skipped, so every row here
is a further section.  Each source is copied from the rotating corpus, traced and
deleted, exactly as amendment A1 describes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import time
from pathlib import Path

from scripts.platformkit.tracking import g380_replay as replay
from scripts.platformkit.tracking import g380_report

FIELDS = ("game_id", "source_name", "source_bytes", "seconds", "rc", "receipt_present",
          "receipt_ticks", "trace_ticks", "receipt_equals_trace",
          "trace_subset_of_receipt", "receipt_only_ticks", "trace_only_ticks",
          "attempted_frames_capped")
# Amendment A3: the trace set is every producer-EVALUATED ATTEMPT (hook record
# "A,<tick>", written before any row filter), not the frames that emitted a row.
A3_FIELDS = ("game_id", "source_name", "source_bytes", "video", "seconds", "rc", "status",
             "receipt_present", "receipt_ticks", "trace_attempt_ticks",
             "trace_emitted_frames", "receipt_equals_trace", "trace_subset_of_receipt",
             "receipt_only_ticks", "trace_only_ticks", "attempted_frames_capped",
             "trace_bytes", "trace_sha256")


def attempt_ticks(trace) -> list:
    """Ticks the independent hook saw the producer evaluate, before row filtering."""
    trace = Path(trace)
    if not trace.is_file():
        return []
    seen = set()
    for line in trace.read_text(encoding="ascii", errors="replace").splitlines():
        if line.startswith("A,"):
            try:
                seen.add(int(line.split(",")[1]))
            except (IndexError, ValueError):
                continue
    return sorted(seen)


def measure_attempts(out_dir, trace) -> dict:
    """Compare the receipt's tick set with the hook's ATTEMPT set (A3), as sets."""
    receipts = list(Path(out_dir).rglob("evaluated_tick_receipt.json"))
    ticks = attempt_ticks(trace)
    emitted = g380_report._trace_rows(Path(trace)) if Path(trace).is_file() else []
    row = {"receipt_present": bool(receipts), "trace_attempt_ticks": len(ticks),
           "trace_emitted_frames": len({item["frame"] for item in emitted})}
    if receipts:
        data = json.loads(receipts[0].read_text(encoding="utf-8"))
        ids = {int(value) for value in data.get("evaluated_tick_ids") or []}
        row.update(receipt_ticks=len(ids),
                   attempted_frames_capped=data.get("attempted_frames_capped"),
                   receipt_equals_trace=ids == set(ticks),
                   trace_subset_of_receipt=set(ticks) <= ids,
                   receipt_only_ticks=len(ids - set(ticks)),
                   trace_only_ticks=len(set(ticks) - ids))
    return row


def _already_traced(out: Path) -> set:
    done = set()
    for name in ("receipts.csv", "receipts_trace.csv"):
        path = out / name
        if not path.exists():
            continue
        with path.open(newline="", encoding="ascii") as handle:
            done |= {row["game_id"] for row in csv.DictReader(handle)}
    return done


def _pick(done: set, count: int) -> tuple:
    items = sorted(p.name for p in replay.CORPUS.glob("*.mp4"))
    listing = hashlib.sha256("|".join(items).encode("ascii")).hexdigest()
    free = [name for name in items if name[:-4].split("__", 1)[-1] not in done]
    step = len(free) / float(count) if count else 1.0
    picks, seen = [], set()
    for i in range(count):
        name = free[min(len(free) - 1, int(i * step))] if free else None
        if name and name not in seen:
            seen.add(name)
            picks.append(name)
    return picks, {"corpus_n": len(items), "corpus_listing_sha256": listing,
                   "eligible": len(free), "picked": len(picks)}


def _measure(game_id: str, out_dir: Path, trace: Path) -> dict:
    row = {"game_id": game_id}
    receipts = list(out_dir.rglob("evaluated_tick_receipt.json"))
    emitted = g380_report._trace_rows(trace) if trace.is_file() else []
    trace_ticks = sorted({item["frame"] for item in emitted})
    row["receipt_present"] = bool(receipts)
    row["trace_ticks"] = len(trace_ticks)
    if receipts:
        data = json.loads(receipts[0].read_text(encoding="utf-8"))
        ids = sorted(int(value) for value in data.get("evaluated_tick_ids") or [])
        row.update(receipt_ticks=len(ids),
                   attempted_frames_capped=data.get("attempted_frames_capped"),
                   receipt_equals_trace=ids == trace_ticks,
                   trace_subset_of_receipt=set(trace_ticks) <= set(ids),
                   receipt_only_ticks=len(set(ids) - set(trace_ticks)),
                   trace_only_ticks=len(set(trace_ticks) - set(ids)))
    return row


def run_one(args) -> int:
    """A3 mode: trace ONE already-present source; the caller owns copy and delete."""
    out, scratch, tree = Path(args.out), Path(args.scratch), Path(args.tree)
    out.mkdir(parents=True, exist_ok=True)
    source = Path(args.source)
    game_id = args.game_id or source.stem
    run_dir = scratch / "out_trace" / game_id
    run_dir.mkdir(parents=True, exist_ok=True)
    trace = scratch / "traces" / (game_id + ".trace")
    trace.parent.mkdir(parents=True, exist_ok=True)
    row = {"game_id": game_id, "source_name": source.name, "video": game_id.split("_s")[0],
           "source_bytes": source.stat().st_size if source.exists() else 0}
    try:
        if not source.exists():
            row["status"] = "SOURCE_GONE"
        else:
            while replay.free_vram_mib() < args.min_vram:
                time.sleep(30)
            seconds, rc = replay.run_arm(tree, source, game_id, run_dir, trace)
            row.update(seconds=seconds, rc=rc)
            row.update(measure_attempts(run_dir, trace))
            row["status"] = "OK" if rc == 0 and row.get("receipt_present") else "ARM_FAILED"
            # The raw trace is kept (about 1 MB) and its digest recorded, so the
            # measured sets can be rebuilt from it without re-running the GPU.
            if trace.is_file():
                row.update(trace_bytes=trace.stat().st_size,
                           trace_sha256=replay.sha256_file(trace))
        replay._append(out / args.csv_name, A3_FIELDS, row)
        print(json.dumps(row, sort_keys=True, default=str), flush=True)
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
    print("TRACE_ONE_DONE du=%d" % replay.du_mb(), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--tree", default="/workspace/g380_scratch/armA")
    parser.add_argument("--scratch", default="/workspace/g380_scratch")
    parser.add_argument("--n", type=int, default=3)
    parser.add_argument("--min-vram", type=int, default=3000)
    parser.add_argument("--source", default="")
    parser.add_argument("--game-id", default="")
    parser.add_argument("--csv-name", default="receipts_trace_a3.csv")
    args = parser.parse_args()
    if args.source:
        return run_one(args)
    out, scratch, tree = Path(args.out), Path(args.scratch), Path(args.tree)
    out.mkdir(parents=True, exist_ok=True)
    picks, frame = _pick(_already_traced(out), args.n)
    print(json.dumps(frame, sort_keys=True), flush=True)
    (scratch / "sources").mkdir(parents=True, exist_ok=True)
    for name in picks:
        game_id = name[:-4].split("__", 1)[-1]
        src, copy = replay.CORPUS / name, scratch / "sources" / name
        if not src.exists():
            continue
        if replay.du_mb() > replay.DU_STOP_MB:
            print("DU STOP", replay.du_mb(), flush=True)
            break
        shutil.copyfile(src, copy)
        run_dir = scratch / "out_trace" / game_id
        run_dir.mkdir(parents=True, exist_ok=True)
        trace = scratch / "traces" / (game_id + ".trace")
        trace.parent.mkdir(parents=True, exist_ok=True)
        try:
            while replay.free_vram_mib() < args.min_vram:
                time.sleep(30)
            seconds, rc = replay.run_arm(tree, copy, game_id, run_dir, trace)
            row = _measure(game_id, run_dir, trace)
            row.update(source_name=name, source_bytes=src.stat().st_size,
                       seconds=seconds, rc=rc)
            replay._append(out / "receipts_trace.csv", FIELDS, row)
            print(json.dumps(row, sort_keys=True, default=str), flush=True)
        finally:
            copy.unlink(missing_ok=True)
            shutil.rmtree(run_dir, ignore_errors=True)
    print("TRACE_SECTIONS_DONE du=%d" % replay.du_mb(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
