"""Retain G242 direct-match homographies and audit preregistered quad checks."""
from __future__ import annotations

import base64
import csv
import hashlib
import json
import statistics
import subprocess
from pathlib import Path

import numpy as np

from scripts.platformkit.tracking import g242_seed_reacquisition_whole_game as g242


ROOT = Path(__file__).resolve().parents[3]
G242_SOURCE_ROOT = Path(r"C:\Users\neelj\nba-track-a3")
LABELS = ROOT / "docs/evidence/tracking/g244_blind_validity_labels_2026-09-04.csv"
G242_TABLE = ROOT / "docs/evidence/tracking/g242_seed_reacquisition_whole_game_artifact/per_sample_table.csv"
G242_MEASUREMENT = ROOT / "docs/evidence/tracking/g242_seed_reacquisition_whole_game_artifact/g242_measurement.json"
VALIDITY_CLASSES = ("VALID", "INVALID", "CANNOT_JUDGE")
QUAD_PERIMETER_ROLE_INDICES = (0, 1, 3, 2)
EXPECTED_SOURCE_SHA256 = {
    "scripts.platformkit.tracking.g196_homography_from_labelled_corners": "f9655c338c92be6bcf90be998eac8b2904aaee52346b2f1593a2814458c737a3",
    "scripts.platformkit.tracking.g215_temporal_homography_propagation": "b3eb085fa0b57af006af19ff29f1e5d2f2bf5b61addc649940b998cc52b6442a",
    "scripts.platformkit.tracking.g222_direct_to_seed_propagation": "2b99a30f3ff6dd1d633e0d088dee150c379f655e2fb78556589b5a948743d8c4",
}


class ControlMismatchError(RuntimeError):
    """Raised after retaining a control artifact when G242 counts differ."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expected_counts(path: Path) -> dict[int, tuple[int, int]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    expected = {int(row["source_frame"]): (int(row["matches"]), int(row["inliers"])) for row in rows}
    if len(rows) != 89 or len(expected) != 89:
        raise ValueError("G242 expected control is not 89 unique frames")
    return expected


def _signed_area(points: np.ndarray) -> float:
    return float(0.5 * np.sum(points[:, 0] * np.roll(points[:, 1], -1) - points[:, 1] * np.roll(points[:, 0], -1)))


def _is_convex(points: np.ndarray) -> bool:
    edges = np.roll(points, -1, axis=0) - points
    following = np.roll(edges, -1, axis=0)
    crosses = edges[:, 0] * following[:, 1] - edges[:, 1] * following[:, 0]
    return bool(np.all(np.isfinite(crosses)) and np.all(np.abs(crosses) > 1e-9) and (np.all(crosses > 0) or np.all(crosses < 0)))


def quad_checks(homography: np.ndarray, role_ordered_corners: np.ndarray, width: int, height: int,
                seed_signed_area: float) -> dict[str, float | bool]:
    """Compute all seven preregistered checks with a fixed perimeter convention."""
    if homography.shape != (3, 3) or role_ordered_corners.shape != (4, 2):
        raise ValueError("G247 requires a 3x3 map and four role-ordered corners")
    perimeter = role_ordered_corners[list(QUAD_PERIMETER_ROLE_INDICES)].astype(np.float64)
    signed_area = _signed_area(perimeter)
    convex = _is_convex(perimeter)
    unique = np.unique(np.round(perimeter, 9), axis=0).shape[0] == 4
    winding_inverted = bool(signed_area * seed_signed_area < 0.0)
    x_span = float(np.max(perimeter[:, 0]) - np.min(perimeter[:, 0]))
    y_span = float(np.max(perimeter[:, 1]) - np.min(perimeter[:, 1]))
    normalized = homography.astype(np.float64) / float(homography[2, 2])
    outside = ((perimeter[:, 0] < 0) | (perimeter[:, 0] >= width) |
               (perimeter[:, 1] < 0) | (perimeter[:, 1] >= height))
    return {
        "is_convex": convex,
        "signed_area_px2": signed_area,
        "winding_inverted_relative_seed": winding_inverted,
        "corner_order_consistent_with_seed": bool(convex and unique and not winding_inverted),
        "projected_area_ratio_to_seed": abs(signed_area) / abs(seed_signed_area),
        "bbox_aspect_ratio": x_span / y_span if y_span else float("inf"),
        "outside_corner_fraction": float(np.mean(outside)),
        "homography_condition_number": float(np.linalg.cond(normalized)),
    }


def _worker_source(payload: dict[str, str], labels: tuple[tuple[float, float], ...], reference: bytes,
                   expected: dict[int, tuple[int, int]]) -> str:
    """Build the G242-equivalent one-pass worker, retaining geometry but no renders."""
    return f'''import base64, hashlib, json, os, subprocess, sys, tempfile, types
import cv2
import numpy as np
VIDEO={g242.VIDEO!r}; SEED={g242.SEED_FRAME}; FRAMES={g242.FRAME_COUNT}; SAMPLES={g242.SAMPLE_FRAMES!r}
LABELS=np.float32({labels!r}); EXPECTED=np.float64({g242.PUBLISHED_H!r}); COUNTS={expected!r}
PAYLOAD={payload!r}; REFERENCE=base64.b64decode({base64.b64encode(reference).decode("ascii")!r})
for name in {g242.SOURCE_MODULES!r}:
    module=types.ModuleType(name); module.__file__="<streamed-"+name.rsplit(".",1)[-1]+">"
    sys.modules[name]=module; exec(compile(base64.b64decode(PAYLOAD[name]),module.__file__,"exec"),module.__dict__)
g196=sys.modules[{g242.SOURCE_MODULES[0]!r}]; g215=sys.modules[{g242.SOURCE_MODULES[1]!r}]
work=tempfile.mkdtemp(prefix="g247_quad_")
def exact(index):
    filter_spec="select=eq(n"+chr(92)+","+str(index)+")"
    command=["ffmpeg","-v","error","-i",VIDEO,"-vf",filter_spec,"-vsync","0","-frames:v","1","-f","rawvideo","-pix_fmt","bgr24","pipe:1"]
    raw=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
    if len(raw)!=1920*1080*3: raise RuntimeError("exact decode byte count differs")
    return np.frombuffer(raw,dtype=np.uint8).reshape(1080,1920,3).copy()
seed_exact=exact(SEED); reference=cv2.imdecode(np.frombuffer(REFERENCE,dtype=np.uint8),cv2.IMREAD_COLOR)
if reference is None or reference.shape != seed_exact.shape: raise RuntimeError("G236b reference image unavailable or wrong shape")
reference_mad=float(np.mean(np.abs(seed_exact.astype(np.int16)-reference.astype(np.int16))))
court=g196.court_points_for_sport("wnba"); seed_h=g196.solve_homography(LABELS,court)
matrix_max_abs=float(np.max(np.abs(seed_h-EXPECTED)))
if matrix_max_abs > 1e-12: raise RuntimeError("published G233d seed matrix mismatch")
seed_corners=g215.project_court_points(seed_h,court)
orb=cv2.ORB_create(nfeatures=2000,fastThreshold=12); seed_features=g215._features(cv2.cvtColor(seed_exact,cv2.COLOR_BGR2GRAY),orb)
capture=cv2.VideoCapture(VIDEO)
if not capture.isOpened(): raise RuntimeError("could not open video for sequential pass")
records=[]; sequential={{}}; sample_set=set(SAMPLES)
for index in range(FRAMES):
    ok,image=capture.read()
    if not ok: raise RuntimeError("sequential decode ended before declared frame count")
    if index not in sample_set: continue
    sequential[index]=image
    motion,diagnostic=g215.estimate_motion(seed_features,g215._features(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY),orb))
    if motion is None: raise RuntimeError("G247 literal G222 acquisition unexpectedly failed")
    image_to_court=g215.compose_image_to_court(seed_h,motion); corners=g215.project_court_points(image_to_court,court)
    records.append({{"source_frame":index,"signed_distance_frames":index-SEED,"direct_seed":{{"matches":diagnostic.matches,"inliers":diagnostic.inliers,"inlier_ratio":diagnostic.inlier_ratio,"rms_reprojection_px":diagnostic.rms_reprojection_px}},"homography_image_to_court":image_to_court.tolist(),"projected_court_corners_px_role_order":corners.tolist()}})
capture.release()
if len(records)!=len(SAMPLES): raise RuntimeError("sample denominator not fully decoded")
check_exact=exact(100000); check_mad=float(np.mean(np.abs(check_exact.astype(np.int16)-sequential[100000].astype(np.int16))))
seed_sequential_mad=float(np.mean(np.abs(seed_exact.astype(np.int16)-sequential[SEED].astype(np.int16))))
mismatches=[{{"source_frame":row["source_frame"],"expected_matches":COUNTS[row["source_frame"]][0],"observed_matches":row["direct_seed"]["matches"],"expected_inliers":COUNTS[row["source_frame"]][1],"observed_inliers":row["direct_seed"]["inliers"]}} for row in records if COUNTS.get(row["source_frame"]) != (row["direct_seed"]["matches"],row["direct_seed"]["inliers"])]
report={{"video":{{"path":VIDEO,"bytes":os.stat(VIDEO).st_size,"declared_frames":FRAMES,"resolution":[1920,1080]}},"seed":{{"frame":SEED,"scale":1.0,"labels_px":LABELS.tolist(),"court_points_ft":court.tolist(),"homography_image_to_court":seed_h.tolist(),"projected_court_corners_px_role_order":seed_corners.tolist(),"published_matrix_max_abs_difference":matrix_max_abs,"exact_decode_reference_mad":reference_mad,"sequential_seed_mad":seed_sequential_mad}},"sampling":{{"method":"one sequential cv2.VideoCapture decode pass from frame 0 through 174429; sample set is stride-2000 frames 0..174000 plus explicit seed","sample_frames":list(SAMPLES),"denominator":len(SAMPLES),"index_mapping_check":{{"sampled_frame":100000,"method":"independent ffmpeg select=eq(n,N) decode with no input-side seek","mad_bgr":check_mad}}}},"g222_acceptance":"unchanged estimate_motion: ORB nfeatures=2000 fastThreshold=12; BF Hamming ratio < 0.75; at least 4 matches; cv2.findHomography RANSAC 3.0; finite matrix","control":{{"expected_source":"committed G242 per_sample_table.csv","exact_match_and_inlier_counts":not mismatches,"mismatch_count":len(mismatches),"mismatches":mismatches}},"records":records,"source_sha256":{{name:hashlib.sha256(base64.b64decode(value)).hexdigest() for name,value in PAYLOAD.items()}}}}
out=os.path.join(work,"g247_measurement.json"); open(out,"w",encoding="ascii").write(json.dumps(report,indent=2,allow_nan=False)+"\\n")
print(json.dumps({{"temp_dir":work,"artifact_bytes":os.path.getsize(out)}}))
'''


def disk_guard(ssh_config: Path, ssh_host: str) -> dict[str, int]:
    """Run the required authoritative dd probe before pod artifact creation."""
    command = "set -e; du -sm /workspace/nba-ai-system/data; dd if=/dev/zero of=/workspace/nba-ai-system/g247_disk_probe.bin bs=1M count=1 conv=fsync status=none; wc -c < /workspace/nba-ai-system/g247_disk_probe.bin; rm -f /workspace/nba-ai-system/g247_disk_probe.bin"
    result = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("ascii", "replace"))
    lines = result.stdout.decode("ascii", "replace").splitlines()
    return {"data_megabytes": int(lines[0].split()[0]), "probe_bytes_removed": int(lines[1])}


def _source_payload(source_root: Path) -> dict[str, str]:
    payload = g242._source_payload(source_root)
    observed = {name: hashlib.sha256(base64.b64decode(value)).hexdigest() for name, value in payload.items()}
    if observed != EXPECTED_SOURCE_SHA256:
        raise RuntimeError("G247 route source hash differs from G242's committed route")
    return payload


def _read_labels(path: Path) -> dict[int, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    labels = {int(row["frame"]): row["validity"] for row in rows}
    if len(rows) != 89 or len(labels) != 89 or set(labels.values()) - set(VALIDITY_CLASSES):
        raise ValueError("G244 labels are not the committed 89-row validity denominator")
    return labels


def _summary(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    return {"n": len(ordered), "min": ordered[0], "median": statistics.median(ordered),
            "p90": float(np.quantile(ordered, 0.9)), "max": ordered[-1]}


def _overlap(valid: list[float], invalid: list[float]) -> dict[str, float | int]:
    return {"invalid_range_min": min(invalid), "invalid_range_max": max(invalid),
            "valid_in_invalid_range": sum(min(invalid) <= value <= max(invalid) for value in valid),
            "valid_range_min": min(valid), "valid_range_max": max(valid),
            "invalid_in_valid_range": sum(min(valid) <= value <= max(valid) for value in invalid)}


def analyze(measurement: dict[str, object], labels: dict[int, str]) -> dict[str, object]:
    """Join fixed labels and recompute all pre-registered geometry summaries."""
    records = list(measurement["records"])
    if {int(row["source_frame"]) for row in records} != set(labels):
        raise ValueError("measurement and blind-label frame sets differ")
    seed = np.asarray(measurement["seed"]["projected_court_corners_px_role_order"], dtype=np.float64)
    seed_area = _signed_area(seed[list(QUAD_PERIMETER_ROLE_INDICES)])
    values = {kind: {} for kind in VALIDITY_CLASSES}
    for row in records:
        checks = quad_checks(np.asarray(row["homography_image_to_court"]),
                             np.asarray(row["projected_court_corners_px_role_order"]), 1920, 1080, seed_area)
        row["quad_checks"] = checks
        values[labels[int(row["source_frame"])]][int(row["source_frame"])] = checks
    fields = ("is_convex", "signed_area_px2", "winding_inverted_relative_seed", "corner_order_consistent_with_seed",
              "projected_area_ratio_to_seed", "bbox_aspect_ratio", "outside_corner_fraction", "homography_condition_number")
    distributions = {field: {kind: _summary([float(item[field]) for item in values[kind].values()]) for kind in VALIDITY_CLASSES}
                     for field in fields}
    overlaps = {field: _overlap([float(item[field]) for item in values["VALID"].values()],
                                 [float(item[field]) for item in values["INVALID"].values()]) for field in fields}
    return {"validity_counts": {kind: len(values[kind]) for kind in VALIDITY_CLASSES},
            "quad_perimeter_role_indices": list(QUAD_PERIMETER_ROLE_INDICES), "distributions": distributions,
            "valid_invalid_range_overlap": overlaps}


def run(output_dir: Path, ssh_config: Path, ssh_host: str, labels_csv: Path, reference_image: Path,
        source_root: Path, expected_table: Path) -> dict[str, object]:
    """Run a guarded G242-equivalent measurement and stop before analysis on mismatch."""
    labels = g242.read_seed_labels(labels_csv)
    expected = _expected_counts(expected_table)
    guard = disk_guard(ssh_config, ssh_host)
    result = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, "python3 -"],
                            input=_worker_source(_source_payload(source_root), labels, reference_image.read_bytes(), expected).encode("ascii"),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("ascii", "replace"))
    rows = [line for line in result.stdout.decode("utf-8", "replace").splitlines() if line.startswith('{"temp_dir":')]
    if len(rows) != 1:
        raise RuntimeError("remote worker did not return exactly one result")
    remote = json.loads(rows[0]); temp_dir = str(remote["temp_dir"])
    if not temp_dir.startswith("/tmp/g247_quad_"):
        raise RuntimeError("unexpected remote temporary directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["scp", "-F", str(ssh_config), "-r", f"{ssh_host}:{temp_dir}/.", str(output_dir)], check=True)
    finally:
        cleanup = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, f"rm -rf -- {temp_dir}"], check=False)
        if cleanup.returncode:
            raise RuntimeError("pod temporary cleanup failed")
    path = output_dir / "g247_measurement.json"
    measurement = json.loads(path.read_text(encoding="ascii"))
    measurement["disk_guard"] = guard
    measurement["remote_temp_bytes_removed"] = int(remote["artifact_bytes"])
    measurement["local_input_sha256"] = {"g242_per_sample_table": _sha256(expected_table), "g244_blind_labels": _sha256(LABELS)}
    if not measurement["control"]["exact_match_and_inlier_counts"]:
        path.write_text(json.dumps(measurement, indent=2) + "\n", encoding="ascii")
        raise ControlMismatchError("G247 stopped: G242 match/inlier control differs")
    measurement["analysis"] = analyze(measurement, _read_labels(LABELS))
    path.write_text(json.dumps(measurement, indent=2) + "\n", encoding="ascii")
    return measurement


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True); parser.add_argument("--ssh-config", type=Path, required=True)
    parser.add_argument("--labels-csv", type=Path, default=ROOT / "docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv")
    parser.add_argument("--reference-image", type=Path, required=True); parser.add_argument("--source-root", type=Path, default=G242_SOURCE_ROOT)
    parser.add_argument("--expected-table", type=Path, default=G242_TABLE); parser.add_argument("--ssh-host", default="pod")
    args = parser.parse_args()
    report = run(args.output_dir, args.ssh_config, args.ssh_host, args.labels_csv, args.reference_image, args.source_root, args.expected_table)
    print("G247_CONTROL_EXACT=" + str(report["control"]["exact_match_and_inlier_counts"]))


if __name__ == "__main__":
    main()
