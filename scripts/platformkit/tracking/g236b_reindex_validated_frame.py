"""Run G236's memory-only existence search for the G196-validated WNBA still."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np


VIDEO = "/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4"
LABELLED_INDEX = 1600
COARSE_SIZE = (64, 36)
COARSE_STRIDE = 5


def _worker_source(label_b64: str) -> str:
    """Return the stdin-only pod worker; only its guarded probe writes to disk."""
    return f'''import base64, hashlib, json, os, shutil, subprocess, time
import cv2
import numpy as np

VIDEO = {VIDEO!r}
LABEL_B64 = {label_b64!r}
LABELLED_INDEX = {LABELLED_INDEX}
COARSE_SIZE = {COARSE_SIZE!r}
COARSE_STRIDE = {COARSE_STRIDE}

def sha256_path(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def reduced_gray(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, COARSE_SIZE, interpolation=cv2.INTER_AREA)

def raw_exact_range(start, end, width, height):
    expression = "select=between(n\\," + str(start) + "\\," + str(end) + ")"
    command = ["ffmpeg", "-v", "error", "-i", VIDEO, "-vf", expression,
               "-vsync", "0", "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1"]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            check=False)
    expected = (end - start + 1) * width * height * 3
    if result.returncode or len(result.stdout) != expected:
        raise RuntimeError("frame extraction failed range=" + str(start) + "-" + str(end) +
                           " rc=" + str(result.returncode) + " bytes=" + str(len(result.stdout)) +
                           " expected=" + str(expected) +
                           " stderr=" + result.stderr.decode("ascii", "replace"))
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape(end - start + 1, height, width, 3)

started = time.perf_counter()
label_bytes = base64.b64decode(LABEL_B64)
label_array = np.frombuffer(label_bytes, dtype=np.uint8)
label = cv2.imdecode(label_array, cv2.IMREAD_COLOR)
if label is None or label.shape != (1080, 1920, 3):
    raise RuntimeError("expected 1920x1080 BGR label still")
target_small = reduced_gray(label)
capture = cv2.VideoCapture(VIDEO)
if not capture.isOpened():
    raise RuntimeError("could not open source video")
width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
declared_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
distances = []
decoded = 0
while True:
    ok, frame = capture.read()
    if not ok:
        break
    if decoded % COARSE_STRIDE == 0:
        small = reduced_gray(frame)
        distances.append([decoded, float(np.abs(small.astype(np.int16) - target_small.astype(np.int16)).mean())])
    decoded += 1
capture.release()
if not distances:
    raise RuntimeError("coarse scan decoded no frames")
ordered = sorted(distances, key=lambda pair: pair[1])
coarse_best_index, coarse_best_distance = ordered[0]
refine_start = max(0, coarse_best_index - COARSE_STRIDE)
refine_end = min(decoded - 1, coarse_best_index + COARSE_STRIDE)
candidate = None
refined = []
for offset, native in enumerate(raw_exact_range(refine_start, refine_end, width, height)):
    index = refine_start + offset
    distance = float(np.abs(reduced_gray(native).astype(np.int16) - target_small.astype(np.int16)).mean())
    refined.append([index, distance])
    if candidate is None or distance < candidate[0]:
        candidate = (distance, index, native)
candidate_distance, candidate_index, candidate_native = candidate
confirmation_mad = float(np.abs(candidate_native.astype(np.int16) - label.astype(np.int16)).mean())
baseline_native = raw_exact_range(LABELLED_INDEX, LABELLED_INDEX, width, height)[0]
baseline_mad = float(np.abs(baseline_native.astype(np.int16) - label.astype(np.int16)).mean())
encoded_ok, encoded_candidate = cv2.imencode(".jpg", candidate_native,
                                               [cv2.IMWRITE_JPEG_QUALITY, 95])
if not encoded_ok:
    raise RuntimeError("candidate JPEG encode failed")
report = {{
    "video": {{"path": VIDEO, "bytes": os.stat(VIDEO).st_size,
              "resolution": [width, height], "declared_frames": declared_frames}},
    "label_payload_sha256": hashlib.sha256(label_bytes).hexdigest(),
    "label_resolution": [1920, 1080],
    "decode_method": "sequential cv2.VideoCapture.read from frame 0 through EOF; refinement and MAD use ffmpeg select=between(n,index) at native 1920x1080",
    "metric": "mean absolute grayscale difference on 64x36 INTER_AREA reductions",
    "coarse_stride": COARSE_STRIDE, "coarse_size": list(COARSE_SIZE),
    "decoded_frames": decoded, "coarse_distances": distances,
    "coarse_best": {{"frame_index": coarse_best_index, "distance": coarse_best_distance}},
    "coarse_top_20": ordered[:20],
    "refinement": {{"start": refine_start, "end": refine_end, "distances": refined}},
    "best": {{"frame_index": candidate_index, "distance": candidate_distance}},
    "confirmation_mad_1920x1080": confirmation_mad,
    "labelled_index_baseline_mad_1920x1080": baseline_mad,
    "wall_seconds": time.perf_counter() - started,
    "disk_guard": {{"pre_du_mb": int(os.environ["G236B_PRE_DU"]),
                   "post_du_mb": int(os.environ["G236B_POST_DU"]),
                   "probe_bytes": int(os.environ["G236B_PROBE_BYTES"]),
                   "probe": "dd 4MiB conv=fsync passed then removed"}},
    "code_identity": {{"worker_sha256": os.environ["G236B_WORKER_SHA256"],
        "opencv": cv2.__version__, "ffmpeg_path": shutil.which("ffmpeg"),
        "ffmpeg_sha256": sha256_path(shutil.which("ffmpeg")) if shutil.which("ffmpeg") else None}},
    "candidate_1920_jpeg_b64": base64.b64encode(encoded_candidate.tobytes()).decode("ascii"),
}}
print(json.dumps(report, separators=(",", ":"), sort_keys=True))
'''


def remote_script(label_b64: str) -> str:
    """Build the guarded pod command and stream the worker without copying code."""
    worker_bytes = _worker_source(label_b64).encode("ascii")
    worker = base64.b64encode(worker_bytes).decode("ascii")
    worker_sha256 = hashlib.sha256(worker_bytes).hexdigest()
    return f'''#!/usr/bin/env bash
set -u
DATA_ROOT=/workspace/nba-ai-system/data
PROBE="$DATA_ROOT/.g236b_reindex_probe_$$"
PRE_DU=$(du -sm "$DATA_ROOT" | awk '{{print $1}}')
dd if=/dev/zero of="$PROBE" bs=1M count=4 conv=fsync status=none
PROBE_RC=$?
PROBE_BYTES=$(stat -c %s "$PROBE" 2>/dev/null || echo 0)
rm -f "$PROBE"
if [ "$PROBE_RC" -ne 0 ]; then
  printf '{{"disk_probe":"failed","pre_du_mb":%s,"probe_bytes":%s}}\\n' "$PRE_DU" "$PROBE_BYTES"
  exit "$PROBE_RC"
fi
POST_DU=$(du -sm "$DATA_ROOT" | awk '{{print $1}}')
printf '%s' '{worker}' | base64 -d | env G236B_WORKER_SHA256={worker_sha256} G236B_PRE_DU="$PRE_DU" G236B_POST_DU="$POST_DU" G236B_PROBE_BYTES="$PROBE_BYTES" python3 -
'''


def run(still: Path, output_json: Path, candidate_image: Path,
        comparison_image: Path, ssh_config: Path, ssh_host: str) -> dict:
    """Run the search and write only committed local evidence images and JSON."""
    label_bytes = still.read_bytes()
    completed = subprocess.run(
        ["ssh", "-F", str(ssh_config), ssh_host, "bash -s"],
        input=remote_script(base64.b64encode(label_bytes).decode("ascii")).encode("ascii"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.decode("ascii", errors="replace"))
    report = json.loads(completed.stdout.decode("ascii"))
    report["label_source"] = {"path": str(still.resolve()), "bytes": len(label_bytes),
                              "sha256": hashlib.sha256(label_bytes).hexdigest(),
                              "resolution": [1920, 1080]}
    report["launcher_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    candidate = cv2.imdecode(np.frombuffer(base64.b64decode(report.pop("candidate_1920_jpeg_b64")), dtype=np.uint8), cv2.IMREAD_COLOR)
    label = cv2.imread(str(still), cv2.IMREAD_COLOR)
    if candidate is None or label is None or candidate.shape != label.shape:
        raise RuntimeError("final comparison image inputs are invalid")
    for path in (output_json, candidate_image, comparison_image):
        path.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    if not cv2.imwrite(str(candidate_image), candidate):
        raise RuntimeError("candidate image write failed")
    if not cv2.imwrite(str(comparison_image), cv2.hconcat([label, candidate])):
        raise RuntimeError("comparison image write failed")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--still", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--candidate-image", type=Path, required=True)
    parser.add_argument("--comparison-image", type=Path, required=True)
    parser.add_argument("--ssh-config", type=Path, required=True)
    parser.add_argument("--ssh-host", default="pod")
    args = parser.parse_args()
    report = run(args.still, args.output_json, args.candidate_image, args.comparison_image,
                 args.ssh_config, args.ssh_host)
    print("G236B_BEST_FRAME=" + str(report["best"]["frame_index"]))
    print("G236B_BEST_DISTANCE=" + f'{report["best"]["distance"]:.6f}')


if __name__ == "__main__":
    main()
