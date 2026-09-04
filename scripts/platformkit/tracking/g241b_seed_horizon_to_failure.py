"""Run G241b's corrected geometry gate and extended direct-seed horizon."""

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
CONTROL_FRAME_COUNT = 1200
DEFAULT_TARGET_FRAME_COUNT = 10000
SOURCE_MODULES = (
    "scripts.platformkit.tracking.g196_homography_from_labelled_corners",
    "scripts.platformkit.tracking.g215_temporal_homography_propagation",
    "scripts.platformkit.tracking.g222_direct_to_seed_propagation",
)


def _source_payload() -> dict[str, str]:
    """Return base64 source bytes for the frozen G222 route modules."""
    root = Path(__file__).resolve().parents[3]
    return {
        name: base64.b64encode(root.joinpath(*name.split(".")).with_suffix(".py").read_bytes()).decode("ascii")
        for name in SOURCE_MODULES
    }


def _worker_source(payload: dict[str, str], frame_count: int, with_detector: bool) -> str:
    """Build an in-memory pod worker; only its named temporary directory is copied."""
    if frame_count < 1:
        raise ValueError("frame_count must be positive")
    return f'''import base64, hashlib, json, math, shutil, sys, tempfile, types
from pathlib import Path
import cv2
import numpy as np

VIDEO = {VIDEO!r}
SEED_FRAME = {SEED_FRAME}
IMAGE_POINTS = np.float32({IMAGE_POINTS!r})
FRAME_COUNT = {frame_count}
WITH_DETECTOR = {with_detector!r}
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
work = Path(tempfile.mkdtemp(prefix="g241b_seed_"))
paired = work / "paired"
intervals = frozenset(range(0, FRAME_COUNT + 1, 1000)) | frozenset((FRAME_COUNT,))
records = g222.measure_paired(Path(VIDEO), paired, seed_frame=SEED_FRAME,
                              frame_count=FRAME_COUNT, stride=1, render_distances=intervals)
direct_records = [{{"distance_frames": row["distance_frames"], "source_frame": row["source_frame"],
                   "direct_seed_eligible": row["direct_seed_eligible"], "direct_seed": row["direct_seed"]}}
                  for row in records]
failure_distance = next((row["distance_frames"] for row in direct_records
                         if not row["direct_seed_eligible"]), None)
horizon_frames = failure_distance if failure_distance is not None else direct_records[-1]["distance_frames"]
shutil.rmtree(paired / "chained_renders", ignore_errors=True)

def compact_renders():
    direct_dir = paired / "direct_seed_renders"
    for path in direct_dir.glob("*.jpg"):
        image = cv2.imread(str(path))
        if image is None:
            raise RuntimeError("could not reread render " + str(path))
        height, width = image.shape[:2]
        compact = cv2.resize(image, (960, round(height * 960 / width)), interpolation=cv2.INTER_AREA)
        if not cv2.imwrite(str(path), compact, [cv2.IMWRITE_JPEG_QUALITY, 85]):
            raise RuntimeError("could not compact render " + str(path))

def detector_records(limit):
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
    output = []
    for distance in range(limit + 1):
        image = seed if distance == 0 else g215._read_stride(capture, 1)
        if image is None:
            break
        motion = None
        if distance:
            motion, _ = g215.estimate_motion(seed_features, g215._features(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), orb))
        image_to_court = seed_h if distance == 0 else (g215.compose_image_to_court(seed_h, motion) if motion is not None else None)
        result = detector.model(image, classes=[0], conf=.3, verbose=False, imgsz=detector._infer_imgsz,
                                half=detector._use_half, device=detector._device)
        boxes = result[0].boxes.xyxy.cpu().numpy() if result[0].boxes is not None else []
        feet = [(float((x1 + x2) / 2), float(y2)) for x1, _y1, x2, y2 in boxes]
        projected = cv2.perspectiveTransform(np.float32(feet).reshape(1, -1, 2), image_to_court)[0] if feet and image_to_court is not None else []
        finite = [(float(x), float(y)) for x, y in projected if np.isfinite(x) and np.isfinite(y)]
        inside = sum(0 <= x <= 50 and 0 <= y <= 94 for x, y in finite)
        output.append({{"distance_frames": distance, "source_frame": SEED_FRAME + distance,
                       "detected_player_boxes": len(feet), "finite_projected_player_feet": len(finite),
                       "inside_94x50ft_court_rows": inside}})
    capture.release()
    return output

compact_renders()
detector = detector_records(horizon_frames) if WITH_DETECTOR else []
report = {{"seed_frame": SEED_FRAME, "seed_image_points_px": IMAGE_POINTS.tolist(),
          "seed_court_points_ft": g196.court_points_for_sport("wnba").tolist(),
          "frame_count_requested": FRAME_COUNT, "failure_distance_frames": failure_distance,
          "measured_horizon_frames": horizon_frames, "direct_geometry_records": direct_records,
          "advisory_detector_records": detector,
          "source_sha256": {{name: hashlib.sha256(base64.b64decode(value)).hexdigest()
                              for name, value in PAYLOAD.items()}}, "temp_dir": str(work)}}
(work / "g241b_measurement.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\\n", encoding="ascii")
for path in (paired / "drift_records.csv", paired / "run_summary.json"):
    path.unlink(missing_ok=True)
print(json.dumps({{"temp_dir": str(work), "files": sorted(str(path.relative_to(work)) for path in work.rglob("*") if path.is_file())}}))
'''


def _ssh_options(ssh_key: Path, ssh_port: int) -> list[str]:
    """Return the explicit local transport options used for a non-deploying pod call."""
    if ssh_port < 1:
        raise ValueError("ssh_port must be positive")
    return ["-i", str(ssh_key), "-p", str(ssh_port), "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=accept-new"]


def _scp_options(ssh_key: Path, ssh_port: int) -> list[str]:
    """Return SCP's port spelling while preserving the same explicit transport identity."""
    if ssh_port < 1:
        raise ValueError("ssh_port must be positive")
    return ["-i", str(ssh_key), "-P", str(ssh_port), "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=accept-new"]


def _remote_run(worker: str, ssh_key: Path, ssh_port: int, ssh_host: str) -> dict[str, object]:
    completed = subprocess.run(
        ["ssh", *_ssh_options(ssh_key, ssh_port), ssh_host, "python3 -"], input=worker.encode("ascii"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.decode("ascii", "replace"))
    results = [line for line in completed.stdout.decode("utf-8", "replace").splitlines() if line.startswith('{"temp_dir":')]
    if len(results) != 1:
        raise RuntimeError(f"expected one worker result JSON line, got {len(results)}")
    return json.loads(results[0])


def _copy_and_cleanup(remote: dict[str, object], output_dir: Path, ssh_key: Path, ssh_port: int, ssh_host: str) -> dict[str, object]:
    temp_dir = str(remote["temp_dir"])
    if not temp_dir.startswith("/tmp/g241b_seed_"):
        raise RuntimeError(f"unexpected pod temporary directory: {temp_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    copied = subprocess.run(["scp", *_scp_options(ssh_key, ssh_port), "-r", f"{ssh_host}:{temp_dir}/.", str(output_dir)], check=False)
    if copied.returncode:
        raise RuntimeError("could not copy pod artifacts")
    cleanup = subprocess.run(["ssh", *_ssh_options(ssh_key, ssh_port), ssh_host, f"rm -rf -- {temp_dir}"], check=False)
    if cleanup.returncode:
        raise RuntimeError(f"could not remove pod temporary directory: {temp_dir}")
    (output_dir / "launcher_metadata.json").write_text(json.dumps(remote, indent=2) + "\n", encoding="ascii")
    return json.loads((output_dir / "g241b_measurement.json").read_text(encoding="ascii"))


def run(output_dir: Path, ssh_key: Path, ssh_port: int, ssh_host: str, frame_count: int, with_detector: bool) -> dict[str, object]:
    """Run one geometry-only or extended measurement, then remove its pod temporary directory."""
    remote = _remote_run(_worker_source(_source_payload(), frame_count, with_detector), ssh_key, ssh_port, ssh_host)
    return _copy_and_cleanup(remote, output_dir, ssh_key, ssh_port, ssh_host)


def direct_geometry_rows(report: dict[str, object]) -> list[dict[str, object]]:
    """Return exactly the control fields G241b permits to block extension."""
    return list(report["direct_geometry_records"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ssh-key", type=Path, required=True)
    parser.add_argument("--ssh-port", type=int, default=40034)
    parser.add_argument("--ssh-host", default="root@213.192.2.123")
    parser.add_argument("--frame-count", type=int, default=DEFAULT_TARGET_FRAME_COUNT)
    parser.add_argument("--with-detector", action="store_true")
    args = parser.parse_args()
    report = run(args.output_dir, args.ssh_key, args.ssh_port, args.ssh_host, args.frame_count, args.with_detector)
    print("G241B_MEASURED_HORIZON=" + str(report["measured_horizon_frames"]))
    print("G241B_FAILURE_DISTANCE=" + str(report["failure_distance_frames"]))


if __name__ == "__main__":
    main()
