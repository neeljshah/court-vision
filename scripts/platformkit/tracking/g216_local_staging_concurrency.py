"""Measure G200's unchanged route after staging its clip on the pod overlay."""
from __future__ import annotations

import argparse
import base64
import io
import json
import subprocess
import tarfile
import time
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking import g200_pod_concurrency as g200

SOURCE_VIDEO = g200.VIDEO
STAGE_PREFIX = "/root/g216_stage_"
SAFETY_MARGIN_BYTES = 5 * 1024**3


def _context() -> str:
    return """date -u +%FT%TZ; echo "cores=$(nproc)"; findmnt -no SOURCE,FSTYPE -T /workspace; findmnt -no SOURCE,FSTYPE -T /; df -B1 /; free -b
nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits
echo TOP_CPU; ps -eo pid=,ppid=,pcpu=,pmem=,rss=,etime=,args= --sort=-pcpu | head -40
echo NAMED_PROCESSES; ps -eo pid=,ppid=,pcpu=,pmem=,rss=,etime=,args= --sort=-pcpu | grep -Ei 'g203|run_clip|track_daemon|supervisor|keep_track_daemon|keeper' | grep -v grep || true"""


def _archive_script(body: str, root: str) -> str:
    return f"""#!/usr/bin/env bash
set -u
ROOT={root!r}; mkdir -p "$ROOT"
finish() {{ tar -C "$ROOT" -czf - . | base64 -w0; rm -rf "$ROOT"; }}
trap finish EXIT
{body}
"""


def stage_script(stage_dir: str) -> str:
    """Create a verified single-file local stage while retaining evidence."""
    staged = f"{stage_dir}/wnba__wnba_01.mp4"
    body = f"""SOURCE={SOURCE_VIDEO!r}; STAGE_DIR={stage_dir!r}; STAGED={staged!r}
context() {{ {{ {_context()}; }} > "$ROOT/context_$1.txt"; }}
context before
python3 - "$SOURCE" "$STAGED" "$STAGE_DIR" "$ROOT/stage.json" <<'PY'
import hashlib, json, os, subprocess, sys, time
source, staged, stage_dir, output = sys.argv[1:]
source_size = os.stat(source).st_size
available = int(subprocess.check_output(["df", "-B1", "--output=avail", "/"], text=True).splitlines()[-1])
result = {{"source_path": source, "staged_path": staged, "source_size_bytes": source_size,
          "overlay_available_before_bytes": available, "safety_margin_bytes": {SAFETY_MARGIN_BYTES}}}
if os.path.exists(stage_dir):
    result["error"] = "stage directory already exists"
elif available < source_size + {SAFETY_MARGIN_BYTES}:
    result["error"] = "overlay free space below source plus safety margin"
else:
    os.mkdir(stage_dir, 0o700)
    result["stage_created"] = True
    started = time.time()
    copied = subprocess.run(["cp", "--reflink=never", "--preserve=mode,timestamps", source, staged], check=False)
    ended = time.time()
    result.update({{"copy_started_epoch": started, "copy_ended_epoch": ended,
                   "copy_wall_seconds": ended - started, "copy_exit_code": copied.returncode}})
    if copied.returncode == 0:
        result["staged_size_bytes"] = os.stat(staged).st_size
        def md5(path):
            digest = hashlib.md5()
            with open(path, "rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        result["source_md5"] = md5(source)
        result["staged_md5"] = md5(staged)
        result["overlay_available_after_copy_bytes"] = int(subprocess.check_output(
            ["df", "-B1", "--output=avail", "/"], text=True).splitlines()[-1])
json.dump(result, open(output, "w"), sort_keys=True)
PY
context after
"""
    return _archive_script(body, "/tmp/g216_stage")


def read_script(stage_dir: str) -> str:
    """Measure direct sequential reads with one and four independent readers."""
    staged = f"{stage_dir}/wnba__wnba_01.mp4"
    body = f"""SOURCE={SOURCE_VIDEO!r}; STAGED={staged!r}
context() {{ {{ {_context()}; }} > "$ROOT/context_$1.txt"; }}
measure() {{
  LABEL="$1"; INPUT="$2"; READERS="$3"; context "${{LABEL}}_before"
  TOTAL_START=$(date +%s.%N); PIDS=""
  for I in $(seq 1 "$READERS"); do
    (
      START=$(date +%s.%N); dd if="$INPUT" of=/dev/null bs=16M iflag=direct status=none; RC=$?; END=$(date +%s.%N)
      python3 - "$ROOT/${{LABEL}}_${{I}}.json" "$LABEL" "$INPUT" "$I" "$START" "$END" "$RC" <<'PY'
import json, sys
p, label, path, reader, start, end, rc = sys.argv[1:]
json.dump({{"label": label, "path": path, "reader": int(reader), "started_epoch": float(start),
           "ended_epoch": float(end), "wall_seconds": float(end) - float(start), "exit_code": int(rc)}}, open(p, "w"), sort_keys=True)
PY
    ) & PIDS="$PIDS $!"
  done
  for PID in $PIDS; do wait "$PID" || true; done
  TOTAL_END=$(date +%s.%N); context "${{LABEL}}_after"
  python3 - "$ROOT/${{LABEL}}.json" "$ROOT" "$LABEL" "$INPUT" "$READERS" "$TOTAL_START" "$TOTAL_END" <<'PY'
import glob, json, os, sys
p, root, label, path, readers, start, end = sys.argv[1:]
jobs = [json.load(open(f)) for f in sorted(glob.glob(f"{{root}}/{{label}}_*.json"))]
size = os.stat(path).st_size
wall = float(end) - float(start)
result = {{"label": label, "path": path, "readers": int(readers), "bytes_per_reader": size,
          "total_wall_seconds": wall, "aggregate_bytes_per_second": size * int(readers) / wall if wall else None,
          "aggregate_mib_per_second": size * int(readers) / wall / 1024**2 if wall else None, "jobs": jobs}}
json.dump(result, open(p, "w"), sort_keys=True)
PY
}}
measure network_single "$SOURCE" 1
measure local_single "$STAGED" 1
measure network_four "$SOURCE" 4
measure local_four "$STAGED" 4
python3 - "$ROOT/reads.json" "$ROOT" <<'PY'
import glob, json, sys
output, root = sys.argv[1:]
items = [json.load(open(p)) for p in sorted(glob.glob(root + "/*_single.json") + glob.glob(root + "/*_four.json"))]
json.dump({{"measurements": items, "method": "dd bs=16M iflag=direct of=/dev/null"}}, open(output, "w"), sort_keys=True)
PY
"""
    return _archive_script(body, "/tmp/g216_reads")


def cleanup_script(stage_dir: str) -> str:
    """Remove only the known staged file and report whether its bytes were freed."""
    staged = f"{stage_dir}/wnba__wnba_01.mp4"
    body = f"""STAGE_DIR={stage_dir!r}; STAGED={staged!r}
context() {{ {{ {_context()}; }} > "$ROOT/context_$1.txt"; }}
context before
python3 - "$STAGE_DIR" "$STAGED" "$ROOT/cleanup.json" <<'PY'
import json, os, subprocess, sys
stage_dir, staged, output = sys.argv[1:]
result = {{"stage_dir": stage_dir, "staged_path": staged, "exists_before": os.path.isfile(staged)}}
if not stage_dir.startswith("{STAGE_PREFIX}"):
    result["error"] = "refused non-G216 stage path"
elif not result["exists_before"]:
    result["error"] = "staged file missing before cleanup"
    result["rmdir_exit_code"] = subprocess.run(["rmdir", "--", stage_dir], check=False).returncode
else:
    size = os.stat(staged).st_size
    removed = subprocess.run(["rm", "-f", "--", staged], check=False)
    directory = subprocess.run(["rmdir", "--", stage_dir], check=False)
    result.update({{"size_before_bytes": size, "remove_exit_code": removed.returncode,
                   "rmdir_exit_code": directory.returncode, "exists_after": os.path.exists(staged),
                   "bytes_freed": size if removed.returncode == 0 and not os.path.exists(staged) else 0}})
json.dump(result, open(output, "w"), sort_keys=True)
PY
context after
"""
    return _archive_script(body, "/tmp/g216_cleanup")


def _run_remote(script: str, ssh_config: Path) -> dict[str, Any]:
    completed = subprocess.run(
        ["ssh", "-F", str(ssh_config), "pod", r"tr -d '\r' | bash -s"], input=script.encode(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    result = g200.bundle(completed.stdout)
    result["ssh_exit_code"] = completed.returncode
    result["ssh_stderr"] = completed.stderr.decode("utf-8", errors="replace")
    return result


def _result(raw: dict[str, Any], name: str) -> dict[str, Any]:
    return {"record": raw["json"].get(name, {}), "context": raw["text"],
            "ssh_exit_code": raw["ssh_exit_code"], "ssh_stderr": raw["ssh_stderr"]}


def _stage_is_valid(stage: dict[str, Any], ssh_exit_code: int) -> bool:
    return (ssh_exit_code == 0 and stage.get("copy_exit_code") == 0
            and stage.get("source_size_bytes") == stage.get("staged_size_bytes")
            and stage.get("source_md5") == stage.get("staged_md5"))


def _reads_are_valid(reads: dict[str, Any]) -> bool:
    measurements = reads.get("measurements", [])
    return bool(measurements) and all(
        job["exit_code"] == 0 for item in measurements for job in item["jobs"]
    )


def run(output: Path, ssh_config: Path) -> int:
    """Stage, read-benchmark, run G200's four arms, and clean the single copy."""
    token = str(int(time.time()))
    stage_dir = f"{STAGE_PREFIX}{token}"
    records: dict[str, Any] = {"source_video": SOURCE_VIDEO, "stage_dir": stage_dir}
    stage = _run_remote(stage_script(stage_dir), ssh_config)
    records["staging"] = _result(stage, "stage.json")
    output.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    stage_record = records["staging"]["record"]
    run_status = 1
    cleanup_status = 1
    try:
        if not _stage_is_valid(stage_record, stage["ssh_exit_code"]):
            return run_status
        reads = _run_remote(read_script(stage_dir), ssh_config)
        records["reads"] = _result(reads, "reads.json")
        output.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if reads["ssh_exit_code"] != 0 or not _reads_are_valid(records["reads"]["record"]):
            return run_status
        g200.VIDEO = f"{stage_dir}/wnba__wnba_01.mp4"
        g200_output = output.with_name(output.stem + "_g200_arms.json")
        arm_exit = g200.run(g200_output, ssh_config)
        records["local_arms"] = json.loads(g200_output.read_text(encoding="utf-8"))
        records["local_arms_exit_code"] = arm_exit
        output.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        run_status = arm_exit
    finally:
        if stage_record.get("stage_created"):
            cleanup = _run_remote(cleanup_script(stage_dir), ssh_config)
            records["cleanup"] = _result(cleanup, "cleanup.json")
            output.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            cleanup_status = cleanup["ssh_exit_code"]
    return 0 if run_status == 0 and cleanup_status == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ssh-config", type=Path, required=True)
    args = parser.parse_args()
    return run(args.output, args.ssh_config)


if __name__ == "__main__":
    raise SystemExit(main())
