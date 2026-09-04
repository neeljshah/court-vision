"""Run the G233d validated WNBA seed measurement without pod deployment."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


VIDEO = "/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4"
SEED_FRAME = 19599
IMAGE_POINTS = ((350.0, 400.0), (835.0, 420.0), (390.0, 696.0), (990.0, 730.0))
SPORT = "wnba"
FRAME_COUNT = 1200
SOURCE_MODULES = (
    "scripts.platformkit.tracking.g196_homography_from_labelled_corners",
    "scripts.platformkit.tracking.g215_temporal_homography_propagation",
    "scripts.platformkit.tracking.g222_direct_to_seed_propagation",
)


def _source_payload() -> dict[str, str]:
    """Return base64 source bytes for the unmodified propagation modules."""
    root = Path(__file__).resolve().parents[3]
    payload: dict[str, str] = {}
    for module in SOURCE_MODULES:
        source = root.joinpath(*module.split(".")).with_suffix(".py").read_bytes()
        payload[module] = base64.b64encode(source).decode("ascii")
    return payload


def _worker_source(payload: dict[str, str]) -> str:
    """Build the stdin-only pod worker; its output directory is removed by launcher."""
    return f'''import base64, csv, hashlib, json, math, os, sys, tempfile, types
from pathlib import Path
import cv2
import numpy as np

VIDEO = {VIDEO!r}
SEED_FRAME = {SEED_FRAME}
IMAGE_POINTS = np.float32({IMAGE_POINTS!r})
FRAME_COUNT = {FRAME_COUNT}
PAYLOAD = {payload!r}

for name in {SOURCE_MODULES!r}:
    module = types.ModuleType(name)
    module.__file__ = "<streamed-" + name.rsplit(".", 1)[-1] + ">"
    sys.modules[name] = module
    exec(compile(base64.b64decode(PAYLOAD[name]), module.__file__, "exec"), module.__dict__)

g196 = sys.modules[{SOURCE_MODULES[0]!r}]
g215 = sys.modules[{SOURCE_MODULES[1]!r}]
g222 = sys.modules[{SOURCE_MODULES[2]!r}]
sys.path.insert(0, "/workspace/nba-ai-system")
work = Path(tempfile.mkdtemp(prefix="g233d_seed_"))
paired = work / "paired"
records = g222.measure_paired(Path(VIDEO), paired, seed_frame=SEED_FRAME,
                              frame_count=FRAME_COUNT, stride=1)

def outside(x, y):
    return math.hypot(max(0.0, -x, x - 50.0), max(0.0, -y, y - 94.0))

def quantiles(values):
    if not values:
        return {{"n": 0, "median_ft": None, "p90_ft": None, "p99_ft": None, "max_ft": None}}
    ordered = sorted(values)
    def q(p):
        pos = (len(ordered) - 1) * p; lo, hi = math.floor(pos), math.ceil(pos)
        return ordered[lo] if lo == hi else ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)
    return {{"n": len(values), "median_ft": q(.5), "p90_ft": q(.9), "p99_ft": q(.99), "max_ft": max(values)}}

from src.tracking.player_detection import FeetDetector
detector = FeetDetector([])
capture = cv2.VideoCapture(VIDEO)
capture.set(cv2.CAP_PROP_POS_FRAMES, SEED_FRAME)
ok, seed = capture.read()
if not ok:
    raise RuntimeError("could not decode seed")
court = g196.court_points_for_sport("wnba")
seed_h = g196.solve_homography(IMAGE_POINTS, court)
orb = cv2.ORB_create(nfeatures=2000, fastThreshold=12)
seed_features = g215._features(cv2.cvtColor(seed, cv2.COLOR_BGR2GRAY), orb)
projection_records = []
for distance in range(FRAME_COUNT + 1):
    image = seed if distance == 0 else g215._read_stride(capture, 1)
    if image is None:
        break
    image_to_court, diag = seed_h, None
    if distance:
        motion, diag = g215.estimate_motion(seed_features, g215._features(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), orb))
        if motion is None:
            projection_records.append({{"distance_frames": distance, "source_frame": SEED_FRAME + distance, "direct_seed_eligible": False, "direct_seed": diag.__dict__, "player_rows": []}})
            continue
        image_to_court = g215.compose_image_to_court(seed_h, motion)
    result = detector.model(image, classes=[0], conf=.3, verbose=False, imgsz=detector._infer_imgsz, half=detector._use_half, device=detector._device)
    boxes = result[0].boxes.xyxy.cpu().numpy() if result[0].boxes is not None else []
    feet = [(float((x1 + x2) / 2), float(y2)) for x1, _y1, x2, y2 in boxes]
    projected = cv2.perspectiveTransform(np.float32(feet).reshape(1, -1, 2), image_to_court)[0] if feet else []
    rows = []
    for (foot_x, foot_y), (court_x, court_y) in zip(feet, projected):
        finite = bool(np.isfinite(court_x) and np.isfinite(court_y))
        distance_ft = outside(float(court_x), float(court_y)) if finite else float("inf")
        rows.append({{"foot_x_px": foot_x, "foot_y_px": foot_y, "court_x_ft": float(court_x), "court_y_ft": float(court_y), "finite": finite, "inside_94x50ft_court": bool(finite and distance_ft == 0.0), "outside_distance_ft": distance_ft}})
    projection_records.append({{"distance_frames": distance, "source_frame": SEED_FRAME + distance, "direct_seed_eligible": True, "direct_seed": None if diag is None else diag.__dict__, "player_rows": rows}})
capture.release()
bins = []
for start in range(0, FRAME_COUNT + 1, 200):
    selected = [row for record in projection_records if start <= record["distance_frames"] <= min(FRAME_COUNT, start + 199) for row in record["player_rows"]]
    finite = [row for row in selected if row["finite"]]
    inside = sum(row["inside_94x50ft_court"] for row in finite)
    bins.append({{"distance_bin_frames": [start, min(FRAME_COUNT, start + 199)], "detected_player_boxes": len(selected), "finite_projected_player_feet": len(finite), "inside_94x50ft_court_rows": inside, "in_court_fraction_of_finite_projected_rows": inside / len(finite) if finite else None, "outside_distance_ft_positive_rows_only": quantiles([row["outside_distance_ft"] for row in finite if row["outside_distance_ft"] > 0])}})
report = {{"seed_frame": SEED_FRAME, "seed_image_points_px": IMAGE_POINTS.tolist(), "seed_court_points_ft": court.tolist(), "seed_homography_image_to_court": seed_h.tolist(), "paired_records": records, "projection_records": projection_records, "physical_plausibility": {{"denominator": "all direct-detector player boxes with finite projections; positive outside distances are retained", "distance_bins": bins}}, "source_sha256": {{name: hashlib.sha256(base64.b64decode(value)).hexdigest() for name, value in PAYLOAD.items()}}, "temp_dir": str(work)}}
(work / "g233d_measurement.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="ascii")
print(json.dumps({{"temp_dir": str(work), "measurement_sha256": hashlib.sha256((work / "g233d_measurement.json").read_bytes()).hexdigest(), "files": sorted(str(path.relative_to(work)) for path in work.rglob("*"))}}))
'''


def _remote_run(worker: str, ssh_config: Path, ssh_host: str) -> dict[str, object]:
    completed = subprocess.run(
        ["ssh", "-F", str(ssh_config), ssh_host, "python3 -"], input=worker.encode("ascii"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.decode("ascii", "replace"))
    lines = completed.stdout.decode("utf-8", "replace").splitlines()
    result_lines = [line for line in lines if line.startswith('{"temp_dir":')]
    if len(result_lines) != 1:
        raise RuntimeError(f"expected one worker result JSON line, got {len(result_lines)}")
    return json.loads(result_lines[0])


def run(output_dir: Path, ssh_config: Path, ssh_host: str) -> dict[str, object]:
    """Measure remotely, copy its temporary artifacts locally, then remove them."""
    payload = _source_payload()
    remote = _remote_run(_worker_source(payload), ssh_config, ssh_host)
    temp_dir = str(remote["temp_dir"])
    if not temp_dir.startswith("/tmp/g233d_seed_"):
        raise RuntimeError(f"unexpected pod temporary directory: {temp_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    copied = subprocess.run(["scp", "-F", str(ssh_config), "-r", f"{ssh_host}:{temp_dir}/.", str(output_dir)], check=False)
    if copied.returncode:
        raise RuntimeError("could not copy pod artifacts")
    cleanup = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, f"rm -rf {temp_dir}"], check=False)
    if cleanup.returncode:
        raise RuntimeError(f"could not remove pod temporary directory: {temp_dir}")
    (output_dir / "launcher_metadata.json").write_text(json.dumps(remote, indent=2) + "\n", encoding="ascii")
    return json.loads((output_dir / "g233d_measurement.json").read_text(encoding="ascii"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ssh-config", type=Path, required=True)
    parser.add_argument("--ssh-host", default="pod")
    args = parser.parse_args()
    result = run(args.output_dir, args.ssh_config, args.ssh_host)
    print("G233D_SEED_FRAME=" + str(result["seed_frame"]))
    print("G233D_PROJECTION_FRAMES=" + str(len(result["projection_records"])))


if __name__ == "__main__":
    main()
