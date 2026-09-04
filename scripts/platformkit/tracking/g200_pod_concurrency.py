"""Run G200's unchanged route arms through SSH and preserve resource records."""
from __future__ import annotations
import argparse, base64, io, json, subprocess, tarfile, time
from pathlib import Path
from statistics import mean
from typing import Any

PROJECT = "/workspace/nba-ai-system"
VIDEO = f"{PROJECT}/data/footage_corpus/wnba__wnba_01.mp4"

def remote_script(arm: int, token: str) -> str:
    """Return a pod-only wrapper which never changes the pod checkout."""
    return f"""#!/usr/bin/env bash
set -u
ARM={arm}; TOKEN={token}; ROOT=/tmp/g200_@{{TOKEN}}_n@{{ARM}}; mkdir -p "@ROOT"
context() {{
  {{ date -u +%FT%TZ; echo "cores=@(nproc)"; free -b; du -sm {PROJECT}/data
     nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits
     echo TOP_CPU; ps -eo pid=,ppid=,pcpu=,pmem=,rss=,etime=,args= --sort=-pcpu | head -40
     echo NAMED_PROCESSES; ps -eo pid=,ppid=,pcpu=,pmem=,rss=,etime=,args= --sort=-pcpu | grep -Ei 'g203|run_clip|track_daemon|supervisor|keep_track_daemon|keeper' | grep -v grep || true
     echo SOURCE_HASHES; sha256sum {PROJECT}/src/pipeline/unified_pipeline.py {PROJECT}/src/tracking/advanced_tracker.py
  }} > "@ROOT/context_@1.txt"
}}
context before; GUARD="@ROOT/disk_guard.bin"
if dd if=/dev/zero of="@GUARD" bs=1M count=4 conv=fsync status=none; then
  rm -f "@GUARD"; echo "pass: wrote and removed 4 MiB" > "@ROOT/disk_guard.txt"
else
  echo "fail: dd returned non-zero; guard retained and no job launched" > "@ROOT/disk_guard.txt"
  context after; tar -C "@ROOT" -czf - . | base64 -w0; exit 42
fi
declare -a PARENTS=()
for I in @(seq 1 "@ARM"); do
  DATA="/tmp/g200_@{{TOKEN}}_n@{{ARM}}_job@{{I}}_data"
  (
    START=@(date +%s.%N)
    /usr/local/bin/python {PROJECT}/scripts/run_clip.py --video {VIDEO} --frames 1200 --no-show --skip-features --data-dir "@DATA" >"@ROOT/job_@I.log" 2>&1
    RC=@?; END=@(date +%s.%N)
    python3 - "@ROOT/job_@I.json" "@I" "@DATA" "@START" "@END" "@RC" <<'PY'
import json, sys
p, n, d, s, e, rc = sys.argv[1:]
json.dump({{"job": int(n), "data_dir": d, "started_epoch": float(s), "ended_epoch": float(e), "wall_seconds": float(e)-float(s), "exit_code": int(rc)}}, open(p, "w"), sort_keys=True)
PY
    exit "@RC"
  ) &
  PARENTS+=("@!")
done
printf '%s\n' "@{{PARENTS[*]}}" > "@ROOT/parents.txt"
python3 - "@ROOT" @{{PARENTS[*]}} <<'PY' &
import json, subprocess, sys, time
root, parents = sys.argv[1], sys.argv[2:]
out = open(root + "/samples.jsonl", "w")
def run(*args): return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
def memory():
    v = {{}}
    for line in open("/proc/meminfo"):
        key, value = line.split(":", 1); v[key] = int(value.strip().split()[0]) * 1024
    return {{"total_bytes": v["MemTotal"], "used_bytes": v["MemTotal"]-v["MemAvailable"], "available_bytes": v["MemAvailable"]}}
def gpu():
    try:
        x = [float(v.strip()) for v in run("nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits").splitlines()[0].split(",")]
        return {{"utilization_pct": x[0], "memory_used_mib": x[1]}}
    except Exception: return {{"utilization_pct": None, "memory_used_mib": None}}
while True:
    jobs, live = {{}}, False
    for parent in parents:
        try: children = run("pgrep", "-P", parent).split()
        except Exception: children = []
        try: rows = run("ps", "-o", "pid=,ppid=,pcpu=,rss=", "-p", ",".join([parent, *children])).splitlines()
        except Exception: rows = []
        item = {{"cpu_pct": 0.0, "rss_kib": 0, "pids": []}}
        for row in rows:
            pid, ppid, cpu, rss = row.split()
            item["cpu_pct"] += float(cpu); item["rss_kib"] += int(rss); item["pids"].append(int(pid)); live = True
        jobs[parent] = item
    out.write(json.dumps({{"epoch": time.time(), "jobs": jobs, "memory": memory(), "gpu": gpu()}}, sort_keys=True) + "\\n"); out.flush()
    if not live: break
    time.sleep(5)
out.close()
PY
MONITOR=@!; TOTAL_START=@(date +%s.%N)
set +e; for PID in @{{PARENTS[*]}}; do wait "@PID"; done; set -e
wait "@MONITOR"; TOTAL_END=@(date +%s.%N)
python3 - "@ROOT/arm.json" "@ARM" "@TOTAL_START" "@TOTAL_END" <<'PY'
import json, sys
p, n, s, e = sys.argv[1:]; json.dump({{"concurrency": int(n), "total_wall_seconds": float(e)-float(s)}}, open(p, "w"), sort_keys=True)
PY
for I in @(seq 1 "@ARM"); do rm -rf "/tmp/g200_@{{TOKEN}}_n@{{ARM}}_job@{{I}}_data"; rm -f "@ROOT/job_@I.log"; done
context after; tar -C "@ROOT" -czf - . | base64 -w0; rm -rf "@ROOT"
""".replace("@", "$")

def bundle(stdout: bytes) -> dict[str, Any]:
    """Decode the remote tar stream into JSON, samples, and context text."""
    archive = tarfile.open(fileobj=io.BytesIO(base64.b64decode(stdout)), mode="r:gz")
    result: dict[str, Any] = {"json": {}, "text": {}, "samples": []}
    for member in archive.getmembers():
        if not member.isfile(): continue
        handle = archive.extractfile(member)
        assert handle is not None
        name, text = Path(member.name).name, handle.read().decode("utf-8", errors="replace")
        if name.endswith(".json"): result["json"][name] = json.loads(text)
        elif name == "samples.jsonl": result["samples"] = [json.loads(line) for line in text.splitlines()]
        else: result["text"][name] = text
    return result

def summarize_arm(raw: dict[str, Any], baseline_seconds: float | None) -> dict[str, Any]:
    """Compute scheduling metrics while retaining every job and every sample."""
    jobs = sorted((v for k, v in raw["json"].items() if k.startswith("job_")), key=lambda x: x["job"])
    parents, samples = raw["text"]["parents.txt"].split(), raw["samples"]
    for job, parent in zip(jobs, parents):
        values = [sample["jobs"][parent] for sample in samples]
        cpu, rss = [x["cpu_pct"] for x in values], [x["rss_kib"] for x in values]
        job["mean_cpu_pct"] = mean(cpu) if cpu else None
        job["peak_rss_kib"] = max(rss) if rss else None
        job["slowdown_factor_vs_n1"] = None if baseline_seconds is None else job["wall_seconds"] / baseline_seconds
    arm = raw["json"]["arm.json"]
    aggregate = [sum(v["cpu_pct"] for v in x["jobs"].values()) for x in samples]
    return {"concurrency": arm["concurrency"], "total_wall_seconds": arm["total_wall_seconds"], "jobs_per_minute": len(jobs) * 60 / arm["total_wall_seconds"], "jobs": jobs, "resource_series": samples, "mean_aggregate_cpu_pct": mean(aggregate) if aggregate else None, "peak_host_memory_used_bytes": max((x["memory"]["used_bytes"] for x in samples), default=None), "peak_gpu_memory_used_mib": max((x["gpu"]["memory_used_mib"] for x in samples if x["gpu"]["memory_used_mib"] is not None), default=None), "peak_gpu_utilization_pct": max((x["gpu"]["utilization_pct"] for x in samples if x["gpu"]["utilization_pct"] is not None), default=None), "load_context_before": raw["text"].get("context_before.txt", ""), "load_context_after": raw["text"].get("context_after.txt", ""), "disk_guard": raw["text"].get("disk_guard.txt", "")}

def run(output: Path, ssh_config: Path) -> int:
    """Run N=1,2,4,8 arms; stop immediately after a disk-guard failure."""
    records: list[dict[str, Any]] = []
    baseline: float | None = None
    for arm in (1, 2, 4, 8):
        done = subprocess.run(["ssh", "-F", str(ssh_config), "pod", r"tr -d '\r' | bash -s"], input=remote_script(arm, f"{int(time.time())}_{arm}").encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        record = summarize_arm(bundle(done.stdout), baseline)
        record["ssh_exit_code"], record["ssh_stderr"] = done.returncode, done.stderr.decode("utf-8", errors="replace")
        records.append(record)
        output.write_text(json.dumps({"arms": records}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if done.returncode or not record["disk_guard"].startswith("pass"): return done.returncode or 1
        if arm == 1: baseline = record["jobs"][0]["wall_seconds"]
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ssh-config", type=Path, required=True)
    args = parser.parse_args()
    return run(args.output, args.ssh_config)

if __name__ == "__main__":
    raise SystemExit(main())
