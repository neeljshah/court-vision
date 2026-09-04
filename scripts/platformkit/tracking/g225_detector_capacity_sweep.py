"""Run G225's repeated adapter capacity measurements without pod deployment."""
from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import tarfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any


PROJECT = "/workspace/nba-ai-system"
VIDEO = PROJECT + "/data/footage_corpus/wnba__wnba_01.mp4"
MODELS = ("yolov8n", "yolov8s", "yolov8m")
ROUTE_FILES = (
    "scripts/platformkit/adapter_run.py",
    "domains/basketball/tracking/adapter.py",
    "scripts/platformkit/detection/shim.py",
    "scripts/platformkit/tracking_timebase.py",
    "scripts/platformkit/tracking_harness.py",
    "scripts/platformkit/tracking_schema.py",
    "scripts/platformkit/tracking/run_environment.py",
)


def sitecustomize_source() -> str:
    """Return an in-memory detector probe applied before adapter construction."""
    return r'''import atexit, hashlib, json, os
from pathlib import Path
import cv2
from scripts.platformkit.detection import shim

root = Path(os.environ["G225_OUTPUT_DIR"]); root.mkdir(parents=True, exist_ok=True)
frames = {0, 2999, 5999}; records = []; state = {"backend": None, "weight": {}}
original = shim.get_box_detector

def sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def instrumented(name=None, model_path=None, sport=None):
    backend = shim.get_detector(name, model_path, sport); state["backend"] = backend
    model = getattr(backend, "_model", None)
    candidate = getattr(model, "ckpt_path", None) or model_path
    path = Path(str(candidate)).resolve() if candidate else None
    state["weight"] = {"requested": str(model_path), "reported_path": str(candidate),
                       "resolved_path": str(path) if path else None,
                       "exists": bool(path and path.is_file()),
                       "sha256": sha(path) if path and path.is_file() else None}
    def detect(frame):
        detections = backend.detect(frame); index = len(records)
        records.append({"evaluated_index": index, "source_frame": index * 3,
                        "raw_boxes": len(detections)})
        if index in frames:
            canvas = frame.copy()
            for item in detections:
                cv2.rectangle(canvas, (round(item.x1), round(item.y1)),
                              (round(item.x2), round(item.y2)), (0, 255, 255), 2)
            scale = min(1.0, 960.0 / canvas.shape[1])
            if scale < 1.0:
                canvas = cv2.resize(canvas, (round(canvas.shape[1] * scale),
                                             round(canvas.shape[0] * scale)))
            cv2.imwrite(str(root / ("raw_boxes_e%04d.jpg" % index)), canvas,
                        [cv2.IMWRITE_JPEG_QUALITY, 88])
        return [[item.x1, item.y1, item.x2, item.y2, item.conf] for item in detections]
    return detect

shim.get_box_detector = instrumented
def finish():
    (root / "raw_boxes.json").write_text(json.dumps(records, indent=2) + "\n")
    (root / "loaded_weight.json").write_text(json.dumps(state["weight"], indent=2) + "\n")
atexit.register(finish)
'''


def remote_script(model: str, repetition: int, token: str) -> str:
    """Return one pod script whose only persistent outputs are adapter results."""
    root = "/tmp/g225_{}_{}_{}".format(model, repetition, token)
    source = base64.b64encode(sitecustomize_source().encode("utf-8")).decode("ascii")
    route_hashes = " ".join(PROJECT + "/" + path for path in ROUTE_FILES)
    game_id = "g225_{}_r{}_{}".format(model, repetition, token)
    return """#!/usr/bin/env bash
set -eu
ROOT={root}; SITE="$ROOT/site"; OUT="$ROOT/artifact"; PROBE={project}/data/.g225_dd_write_probe
mkdir -p "$SITE" "$OUT"
cd {project}
context() {{
  {{ date -u +%FT%TZ; du -sm {project}/data; nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits; free -b; sha256sum {route_hashes}; }} > "$OUT/context_$1.txt"
}}
context before
if ! dd if=/dev/zero of="$PROBE" bs=1M count=4 conv=fsync status=none; then
  printf 'FAIL\n' > "$OUT/disk_guard.txt"; context after; tar -C "$ROOT" -czf - artifact | base64 -w0; exit 42
fi
printf 'PASS bytes=' > "$OUT/disk_guard.txt"; stat -c %s "$PROBE" >> "$OUT/disk_guard.txt"; sha256sum "$PROBE" >> "$OUT/disk_guard.txt"; rm -f "$PROBE"
printf '%s' '{source}' | base64 -d > "$SITE/sitecustomize.py"
START=$(date +%s.%N)
PYTHONPATH="$SITE:{project}" G225_OUTPUT_DIR="$OUT" CV_DETECTOR_MODEL="{model}.pt" /usr/local/bin/python -m scripts.platformkit.adapter_run basketball {video} {game_id} --max-frames 6000 > "$OUT/adapter.log" 2>&1 &
PID=$!
/usr/local/bin/python - "$PID" "$OUT/resource_samples.jsonl" <<'PY' &
import json, subprocess, sys, time
pid, path = sys.argv[1:]
with open(path, "w") as handle:
    while True:
        alive = subprocess.run(["kill", "-0", pid]).returncode == 0
        text = subprocess.check_output(["ps", "-p", pid, "-o", "pcpu=,rss="], text=True).strip()
        gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"], text=True).strip().splitlines()[0]
        values = [value.strip() for value in gpu.split(",")]
        sample = {{"epoch": time.time(), "cpu_pct": None, "rss_kib": None,
                  "gpu_utilization_pct": float(values[0]), "gpu_memory_mib": float(values[1])}}
        if text:
            cpu, rss = text.split(); sample["cpu_pct"] = float(cpu); sample["rss_kib"] = int(rss)
        handle.write(json.dumps(sample, sort_keys=True) + "\\n"); handle.flush()
        if not alive: break
        time.sleep(1)
PY
MONITOR=$!
set +e; wait "$PID"; RC=$?; set -e; wait "$MONITOR" || true
END=$(date +%s.%N)
printf '%s\n' "$RC" > "$OUT/exit_code.txt"
/usr/local/bin/python - "$OUT/run.json" "$START" "$END" "{model}" "{repetition}" "{game_id}" <<'PY'
import json, sys
path, start, end, model, repetition, game_id = sys.argv[1:]
json.dump({{"model": model, "repetition": int(repetition), "game_id": game_id,
           "started_epoch": float(start), "ended_epoch": float(end),
           "wall_seconds": float(end) - float(start)}}, open(path, "w"), indent=2)
PY
context after
tar -C "$ROOT" -czf - artifact | base64 -w0
rm -rf "$ROOT"
exit "$RC"
""".format(root=root, project=PROJECT, route_hashes=route_hashes, source=source,
           model=model, video=VIDEO, game_id=game_id, repetition=repetition)


def extract(stdout: bytes, output: Path) -> None:
    """Extract the tar stream returned by one temporary pod measurement."""
    archive = tarfile.open(fileobj=BytesIO(base64.b64decode(stdout)), mode="r:gz")
    output.mkdir(parents=True, exist_ok=False)
    for member in archive.getmembers():
        if member.isfile():
            archive.extract(member, output)


def cleanup_downloaded_weights(output: Path, ssh_config: Path, ssh_host: str) -> None:
    """Remove only the two capacity weights absent at the recorded preflight."""
    script = """set -eu
cd /workspace/nba-ai-system
/usr/local/bin/python - <<'PY'
import json
from pathlib import Path
removed = []
for name in ('yolov8s.pt', 'yolov8m.pt'):
    path = Path(name)
    if path.is_file():
        size = path.stat().st_size
        path.unlink()
        removed.append({'path': str(path.resolve()), 'bytes_freed': size})
print(json.dumps({'removed': removed, 'total_bytes_freed': sum(x['bytes_freed'] for x in removed)}))
PY
"""
    result = subprocess.run(
        ["ssh", "-F", str(ssh_config), ssh_host, "bash -s"],
        input=script.encode("ascii"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    payload = {"returncode": result.returncode, "stderr": result.stderr.decode("ascii", "replace")}
    if result.returncode == 0:
        payload.update(json.loads(result.stdout.decode("ascii")))
    (output / "downloaded_weight_cleanup.json").write_text(json.dumps(payload, indent=2) + "\n")


def run(output: Path, ssh_config: Path, ssh_host: str = "pod") -> int:
    """Run all required three-by-three arms and retain their evidence locally."""
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    records: list[dict[str, Any]] = []
    try:
        for model in MODELS:
            for repetition in range(1, 4):
                token = str(int(time.time()))
                result = subprocess.run(
                    ["ssh", "-F", str(ssh_config), ssh_host, "bash -s"],
                    input=remote_script(model, repetition, token).encode("ascii"),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                )
                target = output / ("{}_r{}".format(model, repetition))
                extract(result.stdout, target)
                (target / "ssh_stderr.txt").write_bytes(result.stderr)
                records.append({"model": model, "repetition": repetition,
                                "returncode": result.returncode, "artifact": str(target)})
                (output / "manifest.json").write_text(json.dumps(records, indent=2) + "\n")
                if result.returncode:
                    return result.returncode
        return 0
    finally:
        cleanup_downloaded_weights(output, ssh_config, ssh_host)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ssh-config", type=Path, required=True)
    parser.add_argument("--ssh-host", default="pod")
    args = parser.parse_args()
    return run(args.output, args.ssh_config, args.ssh_host)


if __name__ == "__main__":
    raise SystemExit(main())
