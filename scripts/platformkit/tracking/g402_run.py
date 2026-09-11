"""G402 sequential instrumented producer traversals over the sealed windows.

One traversal per planned window on a patched SCRATCH copy of the deploy tree.
Nothing is retried and nothing is topped up: a failed launch stays in the
planned 60 with its recorded status.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

TREE = Path("/workspace/g402_scratch/tree")
HOOK = Path("/workspace/g402_scratch/hook")
DEPLOY = Path("/workspace/deploy/nba-ai-system")
ROUTE_FILES = ("src/tracking/advanced_tracker.py", "src/pipeline/unified_pipeline.py",
               "scripts/run_clip.py", "scripts/platformkit/track_daemon.py")
KEEP = ("tracking_data.csv", "ball_tracking.csv", "evaluated_tick_receipt.json",
        "evaluated_frame_count.json")
LAUNCH_FIELDS = ("draw_kind", "draw_order", "section_id", "source_path", "source_bytes",
                 "source_sha256", "start_frame", "frames", "window_start_s", "argv",
                 "returncode", "seconds", "vram_free_mib_before", "weight_digest",
                 "tree_sha256_digest", "log_sha256", "outputs_present", "status")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def free_vram_mib() -> int:
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free",
                          "--format=csv,noheader,nounits"], capture_output=True, text=True)
    try:
        return int(out.stdout.split()[0])
    except (IndexError, ValueError):
        return -1


def route_hashes(out: Path) -> dict:
    data = {"deploy_tree": str(DEPLOY), "scratch_tree": str(TREE),
            "original": {rel: sha256_file(DEPLOY / rel) for rel in ROUTE_FILES},
            "modified": {rel: sha256_file(TREE / rel) for rel in ROUTE_FILES},
            "provenance_module_sha256": sha256_file(
                TREE / "scripts/platformkit/tracking/g380_provenance.py"),
            "trace_hook_sha256": sha256_file(HOOK / "sitecustomize.py"),
            "python": sys.version.split()[0], "platform": sys.platform,
            "env": {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
                    "OPENBLAS_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1"}}
    data["tree_sha256_digest"] = hashlib.sha256(
        "|".join(data["modified"][rel] for rel in ROUTE_FILES).encode("ascii")).hexdigest()
    weights = sorted((TREE / "data" / "models").rglob("*.pt")) if (TREE / "data" / "models").is_dir() else []
    data["weights"] = {str(item.relative_to(TREE)): item.stat().st_size for item in weights}
    (out / "route_hashes.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                                           encoding="ascii")
    return data


def append(path: Path, fields: tuple, row: dict) -> None:
    fresh = not path.exists()
    with path.open("a", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        if fresh:
            writer.writeheader()
        writer.writerow(row)


def traverse(row: dict, out: Path, routes: dict, min_vram: int) -> dict:
    section = row["section_id"]
    raw = out / "raw_tables" / row["draw_kind"] / section
    trace = out / "trace" / (row["draw_kind"] + "__" + section + ".trace")
    work = Path("/workspace/g402_scratch/out") / section
    log = Path("/workspace/g402_scratch/out") / (section + ".log")
    raw.mkdir(parents=True, exist_ok=True)
    trace.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    receipt = {"draw_kind": row["draw_kind"], "draw_order": row["draw_order"],
               "section_id": section, "source_path": row["source_path"],
               "source_bytes": row["source_bytes"], "source_sha256": row["source_sha256"],
               "start_frame": row["start_frame"], "frames": row["frames"],
               "window_start_s": row["window_start_s"],
               "tree_sha256_digest": routes["tree_sha256_digest"]}
    if not Path(row["source_path"]).is_file():
        return {**receipt, "status": "SOURCE_GONE", "returncode": "", "seconds": ""}
    while True:
        free = free_vram_mib()
        if free < 0 or free >= min_vram:
            break
        time.sleep(20)
    cmd = [sys.executable, "scripts/run_clip.py", "--video=" + row["source_path"],
           "--game-id=" + section, "--no-show", "--frames", str(row["frames"]),
           "--start-frame", str(row["start_frame"]), "--data-dir=" + str(work)]
    env = dict(os.environ, OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
               PYTHONDONTWRITEBYTECODE="1", G380_TRACE=str(trace), PYTHONPATH=str(HOOK))
    start = time.time()
    with log.open("w", encoding="utf-8") as handle:
        proc = subprocess.run(cmd, cwd=str(TREE), env=env, stdout=handle,
                              stderr=subprocess.STDOUT)
    receipt.update(argv=" ".join(cmd), returncode=proc.returncode,
                   seconds=round(time.time() - start, 2), vram_free_mib_before=free,
                   weight_digest=routes.get("weight_digest", ""))
    present = []
    for name in KEEP:
        found = next(iter(sorted(work.rglob(name))), None)
        if found is not None and found.is_file():
            shutil.copyfile(found, raw / name)
            present.append(name)
    shutil.copyfile(log, raw / "run.log.txt")
    receipt["log_sha256"] = sha256_file(raw / "run.log.txt")
    receipt["outputs_present"] = ";".join(present)
    complete = proc.returncode == 0 and {"tracking_data.csv",
                                         "evaluated_tick_receipt.json"} <= set(present) \
        and trace.is_file()
    receipt["status"] = "COMPLETE" if complete else "INCOMPLETE"
    shutil.rmtree(work, ignore_errors=True)
    log.unlink(missing_ok=True)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draw", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--min-vram", type=int, default=3000)
    parser.add_argument("--deadline-min", type=int, default=85)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    routes = route_hashes(out)
    with Path(args.draw).open(newline="", encoding="ascii") as handle:
        plan = list(csv.DictReader(handle))
    # Interleave the two kinds by ordinal so a stage-deadline truncation cannot
    # fall entirely on one kind; the sealed draw order itself is unchanged.
    plan.sort(key=lambda item: (int(item["draw_order"]), item["draw_kind"]))
    launches = out / "launch_receipts.csv"
    done = set()
    if launches.exists():
        with launches.open(newline="", encoding="ascii") as handle:
            done = {item["section_id"] for item in csv.DictReader(handle)}
    began = time.time()
    for row in plan:
        if row["section_id"] in done:
            continue
        if (time.time() - began) / 60.0 >= args.deadline_min:
            append(launches, LAUNCH_FIELDS, {**row, "status": "STAGE_DEADLINE_NOT_LAUNCHED"})
            continue
        receipt = traverse(row, out, routes, args.min_vram)
        append(launches, LAUNCH_FIELDS, receipt)
        print("%s %s %s %ss" % (receipt["draw_kind"], receipt["section_id"],
                                receipt["status"], receipt.get("seconds", "")), flush=True)
    print("RUN_DONE elapsed_min=%.1f" % ((time.time() - began) / 60.0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
