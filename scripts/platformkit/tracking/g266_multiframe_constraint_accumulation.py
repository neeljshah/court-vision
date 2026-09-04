"""G266 measurement-only same-shot line-constraint transport harness."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.g215_temporal_homography_propagation import _features, estimate_motion


def sha256(path: Path) -> str:
    """Return SHA-256 for one evidence input."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_frame(frame: int, output: Path, ssh_config: Path) -> dict[str, object]:
    """Stream one exact no-input-seek WNBA frame to local evidence."""
    video = "/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4"
    command = "ffmpeg -hide_banner -loglevel error -i " + video + " -vf 'select=eq(n\\," + str(frame) + ")' -vsync 0 -frames:v 1 -f image2pipe -vcodec mjpeg pipe:1"
    done = subprocess.run(["ssh", "-F", str(ssh_config), "pod", command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if done.returncode or not done.stdout:
        raise RuntimeError(done.stderr.decode("ascii", "replace"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(done.stdout)
    image = cv2.imread(str(output), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("JPEG decode failed")
    return {"frame": frame, "path": str(output), "bytes": output.stat().st_size, "resolution_px": [int(image.shape[1]), int(image.shape[0])], "jpeg_sha256": sha256(output), "bgr_sha256": hashlib.sha256(image.tobytes()).hexdigest()}


def motion(seed: np.ndarray, current: np.ndarray) -> tuple[np.ndarray, dict[str, object]]:
    """Use G222's unmodified ORB/BF/ratio/RANSAC matcher for seed-to-current motion."""
    orb = cv2.ORB_create(nfeatures=2000, fastThreshold=12)
    matrix, diagnostic = estimate_motion(
        _features(cv2.cvtColor(seed, cv2.COLOR_BGR2GRAY), orb),
        _features(cv2.cvtColor(current, cv2.COLOR_BGR2GRAY), orb),
    )
    if matrix is None:
        raise RuntimeError("G222 matcher returned no motion map")
    return matrix, asdict(diagnostic)


def transform(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Project image points through one image-to-image homography."""
    return cv2.perspectiveTransform(points.reshape(1, -1, 2).astype(np.float32), matrix)[0]


def write_identity_crops(inputs: dict[str, object], frames: dict[str, object], output_dir: Path) -> list[dict[str, object]]:
    """Write one enlarged own-frame crop for each manually observed primitive."""
    results = []
    for item in inputs["constraints"]:
        if "image_endpoints_px" not in item:
            continue
        frame = int(item["frame"]); image = cv2.imread(frames[frame]["path"], cv2.IMREAD_COLOR)
        points = np.asarray(item["image_endpoints_px"], dtype=float); low = np.floor(points.min(axis=0) - 55).astype(int); high = np.ceil(points.max(axis=0) + 55).astype(int)
        low = np.maximum(low, 0); high = np.minimum(high, [image.shape[1], image.shape[0]])
        crop = image[low[1]:high[1], low[0]:high[0]]; path = output_dir / "identity_crops" / ("frame_%06d_%s.jpg" % (frame, item["primitive"]))
        path.parent.mkdir(exist_ok=True); enlarged = cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        if not cv2.imwrite(str(path), enlarged, [cv2.IMWRITE_JPEG_QUALITY, 95]):
            raise OSError(path)
        results.append({"frame": frame, "primitive": item["primitive"], "crop": str(path), "source_rect_px": [int(low[0]), int(low[1]), int(high[0]-low[0]), int(high[1]-low[1])]})
    return results


def dlt_condition(image: np.ndarray, court: np.ndarray) -> float:
    """Return normalized DLT condition number excluding the null singular value."""
    def norm(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        centre = points.mean(axis=0); scale = np.sqrt(2.0) / np.mean(np.linalg.norm(points - centre, axis=1))
        matrix = np.array(((scale, 0.0, -scale * centre[0]), (0.0, scale, -scale * centre[1]), (0.0, 0.0, 1.0)))
        return transform(points, matrix), matrix
    source, _ = norm(image); target, _ = norm(court); rows = []
    for (x, y), (u, v) in zip(source, target):
        rows.extend(([-x, -y, -1, 0, 0, 0, u * x, u * y, u], [0, 0, 0, -x, -y, -1, v * x, v * y, v]))
    singular = np.linalg.svd(np.asarray(rows), compute_uv=False)
    return float(singular[-2] / singular[-1]) if singular[-1] else float("inf")


def line_homography(image_lines: list[np.ndarray], court_lines: list[np.ndarray]) -> np.ndarray:
    """Fit H from line-to-line constraints via the dual homography (G253 form)."""
    rows = []
    for source, target in zip(image_lines, court_lines):
        x, y, z = source; a, b, c = target
        rows.extend(([0, 0, 0, -c*x, -c*y, -c*z, b*x, b*y, b*z], [c*x, c*y, c*z, 0, 0, 0, -a*x, -a*y, -a*z]))
    _, _, right = np.linalg.svd(np.asarray(rows, dtype=float)); dual = right[-1].reshape(3, 3)
    homography = np.linalg.inv(dual).T
    return homography / homography[2, 2]


def prepare(inputs: dict[str, object], output_dir: Path, ssh_config: Path) -> dict[str, object]:
    """Extract source frames and report every unchanged G222 direct transport."""
    frames = sorted({int(item["frame"]) for item in inputs["constraints"]})
    reference = int(inputs["reference_frame"])
    if reference not in frames:
        frames.append(reference)
    images = {}
    for frame in sorted(frames):
        path = output_dir / "frames" / ("frame_%06d.jpg" % frame)
        if path.exists():
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError("retained frame JPEG decode failed")
            images[frame] = {"frame": frame, "path": str(path), "bytes": path.stat().st_size, "resolution_px": [int(image.shape[1]), int(image.shape[0])], "jpeg_sha256": sha256(path), "bgr_sha256": hashlib.sha256(image.tobytes()).hexdigest()}
        else:
            images[frame] = extract_frame(frame, path, ssh_config)
    seed = cv2.imread(images[reference]["path"], cv2.IMREAD_COLOR)
    transports: dict[str, object] = {str(reference): {"matrix_seed_to_frame": np.eye(3).tolist(), "diagnostic": {"matches": None, "inliers": None, "inlier_ratio": None, "rms_reprojection_px": None}}}
    for frame in sorted(frames):
        if frame == reference:
            continue
        current = cv2.imread(images[frame]["path"], cv2.IMREAD_COLOR)
        matrix, diagnostic = motion(seed, current)
        transports[str(frame)] = {"matrix_seed_to_frame": matrix.tolist(), "diagnostic": diagnostic}
    report = {"reference_frame": reference, "frames": images, "transports": transports, "identity_crops": write_identity_crops(inputs, images, output_dir), "g222_matcher": "ORB nfeatures=2000 fastThreshold=12; BF/Hamming; 0.75 ratio test; cv2.findHomography RANSAC 3 px"}
    (output_dir / "prepare.json").write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    return report


def fit(inputs: dict[str, object], output_dir: Path) -> dict[str, object]:
    """Transport separately recorded lines into the reference image and fit once."""
    prepared = json.loads((output_dir / "prepare.json").read_text(encoding="ascii"))
    reference = int(inputs["reference_frame"]); image_points = []; court_points = []; records = []; image_lines = []; court_lines = []
    for item in inputs["constraints"]:
        frame = int(item["frame"]); observed = np.asarray(item["image_endpoints_px"], dtype=np.float32)
        matrix = np.asarray(prepared["transports"][str(frame)]["matrix_seed_to_frame"], dtype=float)
        transported = transform(observed, np.linalg.inv(matrix)); court = np.asarray(item["court_endpoints_ft"], dtype=np.float32)
        image_points.extend(transported.tolist()); court_points.extend(court.tolist())
        image_lines.append(np.cross(np.r_[transported[0], 1.0], np.r_[transported[1], 1.0]))
        court_lines.append(np.cross(np.r_[court[0], 1.0], np.r_[court[1], 1.0]))
        records.append({"frame": frame, "primitive": item["primitive"], "observed_image_endpoints_px": observed.tolist(), "transported_to_reference_px": transported.tolist(), "court_endpoints_ft": court.tolist(), "transport": prepared["transports"][str(frame)]})
    image = np.asarray(image_points, dtype=np.float32); court = np.asarray(court_points, dtype=np.float32)
    homography = line_homography(image_lines, court_lines)
    published = np.asarray(inputs["published_homography_image_to_court"], dtype=float)
    reference_image = cv2.imread(prepared["frames"][str(reference)]["path"], cv2.IMREAD_COLOR)
    corners = np.float32(((0, 0), (50, 0), (50, 94), (0, 94), (0, 47), (50, 47), (17, 0), (33, 0), (33, 19), (17, 19), (17, 19), (33, 19)))
    left = transform(corners, np.linalg.inv(homography)); right = transform(corners, np.linalg.inv(published))
    inside = lambda points: (points[:, 0] >= 0) & (points[:, 0] < reference_image.shape[1]) & (points[:, 1] >= 0) & (points[:, 1] < reference_image.shape[0])
    shared = inside(left) & inside(right); distances = np.linalg.norm(left - right, axis=1)
    result = {"reference_frame": reference, "accumulated_constraint_count": len(records), "constraints": records, "homography_image_to_court": homography.tolist(), "published_homography_image_to_court": published.tolist(), "shared_in_frame_sample_points": int(shared.sum()), "all_sample_points": int(len(corners)), "shared_discrepancy_px": {"median": float(np.median(distances[shared])), "p90": float(np.quantile(distances[shared], .9)), "max": float(np.max(distances[shared]))}, "dlt_condition_number": dlt_condition(image, court)}
    (output_dir / "control_measurement.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ssh-config", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.inputs.read_text(encoding="ascii"))
    report = prepare(payload, args.output_dir, args.ssh_config)
    if all("image_endpoints_px" in item for item in payload["constraints"]):
        result = fit(payload, args.output_dir)
        print("G266_CONTROL_SHARED=" + str(result["shared_in_frame_sample_points"]))
    else:
        print("G266_EXTRACTED_FRAMES=" + str(len(report["frames"])))


if __name__ == "__main__":
    main()
