"""Measure direct G222 seed reacquisition at sparse whole-game sample frames."""
from __future__ import annotations

import base64
import csv
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

VIDEO = "/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4"
SEED_FRAME = 19599
FRAME_COUNT = 174430
SAMPLE_STRIDE = 2000
SAMPLE_FRAMES = tuple(sorted(set(range(0, 174001, SAMPLE_STRIDE)) | {SEED_FRAME}))
AUDIT_ID = "wnba__wnba_01_1080p__s01__f001600"
ROLE_ORDER = (
    "paint_near_baseline_left_corner", "paint_near_baseline_right_corner",
    "paint_near_free_throw_left_corner", "paint_near_free_throw_right_corner",
)
PUBLISHED_H = (
    (0.050071754999888064, 0.01225404716365722, 2.3351407383547964),
    (-0.0047586809476217904, 0.1153980129798286, -44.493666860263815),
    (3.054485397744623e-05, 0.0011147252900901028, 1.0),
)
SOURCE_MODULES = (
    "scripts.platformkit.tracking.g196_homography_from_labelled_corners",
    "scripts.platformkit.tracking.g215_temporal_homography_propagation",
    "scripts.platformkit.tracking.g222_direct_to_seed_propagation",
)


def read_seed_labels(csv_path: Path) -> tuple[tuple[float, float], ...]:
    """Read the exact G233d WNBA label record in G196 role order."""
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["audit_id"] == AUDIT_ID]
    by_role = {row["role"]: row for row in rows}
    if set(by_role) != set(ROLE_ORDER) or len(rows) != 4:
        raise ValueError("G242 requires exactly the four published WNBA seed labels")
    dimensions = {(row["image_width"], row["image_height"]) for row in rows}
    if dimensions != {("1920", "1080")}:
        raise ValueError("G242 seed labels are not native 1920x1080")
    return tuple((float(by_role[role]["x_px"]), float(by_role[role]["y_px"])) for role in ROLE_ORDER)


def _source_payload(root: Path) -> dict[str, str]:
    return {name: base64.b64encode(root.joinpath(*name.split(".")).with_suffix(".py").read_bytes()).decode("ascii")
            for name in SOURCE_MODULES}


def _worker_source(payload: dict[str, str], labels: tuple[tuple[float, float], ...], reference: bytes) -> str:
    """Build a stdin-only pod worker; it streams one VideoCapture pass and bounds output."""
    return f'''import base64, hashlib, json, os, subprocess, sys, tempfile, types
from dataclasses import asdict
from pathlib import Path
import cv2
import numpy as np
VIDEO={VIDEO!r}; SEED={SEED_FRAME}; FRAMES={FRAME_COUNT}; SAMPLES={SAMPLE_FRAMES!r}
LABELS=np.float32({labels!r}); EXPECTED=np.float64({PUBLISHED_H!r})
PAYLOAD={payload!r}; REFERENCE=base64.b64decode({base64.b64encode(reference).decode("ascii")!r})
for name in {SOURCE_MODULES!r}:
    module=types.ModuleType(name); module.__file__="<streamed-"+name.rsplit(".",1)[-1]+">"
    sys.modules[name]=module; exec(compile(base64.b64decode(PAYLOAD[name]),module.__file__,"exec"),module.__dict__)
g196=sys.modules[{SOURCE_MODULES[0]!r}]; g215=sys.modules[{SOURCE_MODULES[1]!r}]
work=Path(tempfile.mkdtemp(prefix="g242_seed_")); acquired_dir=work/"acquired_renders"; failed_dir=work/"failed_renders"
acquired_dir.mkdir(); failed_dir.mkdir()
def exact(index):
    command=["ffmpeg","-v","error","-i",VIDEO,"-vf",f"select=eq(n\\,{{index}})","-vsync","0","-frames:v","1","-f","rawvideo","-pix_fmt","bgr24","pipe:1"]
    raw=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
    if len(raw)!=1920*1080*3: raise RuntimeError("exact decode byte count differs")
    return np.frombuffer(raw,dtype=np.uint8).reshape(1080,1920,3).copy()
seed_exact=exact(SEED); reference=cv2.imdecode(np.frombuffer(REFERENCE,dtype=np.uint8),cv2.IMREAD_COLOR)
if reference is None or reference.shape != seed_exact.shape: raise RuntimeError("G236b reference image unavailable or wrong shape")
seed_reference_mad=float(np.mean(np.abs(seed_exact.astype(np.int16)-reference.astype(np.int16))))
court=g196.court_points_for_sport("wnba"); seed_h=g196.solve_homography(LABELS,court)
matrix_max_abs=float(np.max(np.abs(seed_h-EXPECTED)))
if matrix_max_abs > 1e-12: raise RuntimeError("published G233d seed matrix mismatch")
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
    acquired=motion is not None
    record={{"source_frame":index,"signed_distance_frames":index-SEED,"acquired_g222_unchanged":acquired,"direct_seed":asdict(diagnostic)}}
    if acquired:
        image_to_court=g215.compose_image_to_court(seed_h,motion)
        corners=g215.project_court_points(image_to_court,court)
        rendered=g196.render_overlay(image,image_to_court,"wnba",corners)
        small=cv2.resize(rendered,(960,540),interpolation=cv2.INTER_AREA)
        cv2.putText(small,f"frame {{index}} acquired",(16,32),cv2.FONT_HERSHEY_SIMPLEX,0.8,(0,255,0),2,cv2.LINE_AA)
        path=acquired_dir/f"frame_{{index:06d}}.jpg"; cv2.imwrite(str(path),small,[cv2.IMWRITE_JPEG_QUALITY,82]); record["render_path"]=str(path.relative_to(work))
    else:
        small=cv2.resize(image,(640,360),interpolation=cv2.INTER_AREA)
        cv2.putText(small,f"frame {{index}} failed: no G222 direct map",(10,25),cv2.FONT_HERSHEY_SIMPLEX,0.52,(0,0,255),2,cv2.LINE_AA)
        path=failed_dir/f"frame_{{index:06d}}.jpg"; cv2.imwrite(str(path),small,[cv2.IMWRITE_JPEG_QUALITY,82]); record["render_path"]=str(path.relative_to(work))
    records.append(record)
capture.release()
if len(records)!=len(SAMPLES): raise RuntimeError("sample denominator not fully decoded")
check_index=100000; check_exact=exact(check_index); check_mad=float(np.mean(np.abs(check_exact.astype(np.int16)-sequential[check_index].astype(np.int16))))
seed_sequential_mad=float(np.mean(np.abs(seed_exact.astype(np.int16)-sequential[SEED].astype(np.int16))))
def contact(paths, name):
    tiles=[]
    for path in paths:
        image=cv2.imread(str(path)); tiles.append(image)
    if not tiles: return None
    rows=[]
    for start in range(0,len(tiles),4):
        row=tiles[start:start+4]; row += [np.zeros_like(tiles[0])]*(4-len(row)); rows.append(np.hstack(row))
    sheet=np.vstack(rows); out=work/name; cv2.imwrite(str(out),sheet,[cv2.IMWRITE_JPEG_QUALITY,80]); return str(out.relative_to(work))
failed_paths=sorted(failed_dir.glob("*.jpg")); acquired_paths=sorted(acquired_dir.glob("*.jpg"))
failed_sheets=[contact(failed_paths[i:i+20],f"failed_contact_sheet_{{i//20:02d}}.jpg") for i in range(0,len(failed_paths),20)]
report={{"video":{{"path":VIDEO,"declared_frames":FRAMES,"resolution":[1920,1080]}},"seed":{{"frame":SEED,"scale":1.0,"labels_px":LABELS.tolist(),"court_points_ft":court.tolist(),"homography_image_to_court":seed_h.tolist(),"published_matrix_max_abs_difference":matrix_max_abs,"exact_decode_reference_mad":seed_reference_mad,"sequential_seed_mad":seed_sequential_mad}},"sampling":{{"method":"one sequential cv2.VideoCapture decode pass from frame 0 through 174429; sample set is stride-2000 frames 0..174000 plus explicit seed","sample_frames":list(SAMPLES),"denominator":len(SAMPLES),"index_mapping_check":{{"sampled_frame":check_index,"method":"independent ffmpeg select=eq(n,N) decode with no input-side seek","mad_bgr":check_mad}}}},"g222_acceptance":"unchanged estimate_motion: ORB nfeatures=2000 fastThreshold=12; BF Hamming ratio < 0.75; at least 4 matches; cv2.findHomography RANSAC 3.0; finite matrix","records":records,"source_sha256":{{name:hashlib.sha256(base64.b64decode(value)).hexdigest() for name,value in PAYLOAD.items()}},"failed_contact_sheets":[x for x in failed_sheets if x],"artifact_bytes_before_cleanup":sum(p.stat().st_size for p in work.rglob("*") if p.is_file())}}
(work/"g242_measurement.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\\n",encoding="ascii")
print(json.dumps({{"temp_dir":str(work),"measurement_sha256":hashlib.sha256((work/"g242_measurement.json").read_bytes()).hexdigest(),"artifact_bytes":sum(p.stat().st_size for p in work.rglob("*") if p.is_file())}}))
'''


def disk_guard(ssh_config: Path, ssh_host: str) -> dict[str, int]:
    command = "set -e; du -sm /workspace/nba-ai-system/data; dd if=/dev/zero of=/workspace/nba-ai-system/g242_disk_probe.bin bs=1M count=1 conv=fsync status=none; wc -c < /workspace/nba-ai-system/g242_disk_probe.bin; rm -f /workspace/nba-ai-system/g242_disk_probe.bin"
    result = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("ascii", "replace"))
    lines = result.stdout.decode("ascii", "replace").splitlines()
    return {"data_megabytes": int(lines[0].split()[0]), "probe_bytes_removed": int(lines[1])}


def write_per_sample_table(measurement: dict[str, object], path: Path) -> None:
    """Write the complete named acquisition denominator as a flat reader table."""
    fields = ("source_frame", "signed_distance_frames", "acquired_g222_unchanged", "matches", "inliers",
              "inlier_ratio", "rms_reprojection_px", "render_path")
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in measurement["records"]:  # type: ignore[index]
            diagnostic = record["direct_seed"]
            writer.writerow({**{field: record[field] for field in fields[:3]}, **diagnostic,
                             "render_path": record["render_path"]})


def run(output_dir: Path, ssh_config: Path, ssh_host: str, labels_csv: Path, reference_image: Path,
        source_root: Path) -> dict[str, object]:
    """Run the guarded remote measurement and retain only bounded evidence locally."""
    labels = read_seed_labels(labels_csv)
    guard = disk_guard(ssh_config, ssh_host)
    worker = _worker_source(_source_payload(source_root), labels, reference_image.read_bytes())
    result = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, "python3 -"], input=worker.encode("ascii"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("ascii", "replace"))
    lines = [line for line in result.stdout.decode("utf-8", "replace").splitlines() if line.startswith('{"temp_dir":')]
    if len(lines) != 1:
        raise RuntimeError("remote worker did not return exactly one result")
    remote = json.loads(lines[0]); temp_dir = str(remote["temp_dir"])
    if not temp_dir.startswith("/tmp/g242_seed_"):
        raise RuntimeError("unexpected remote temporary directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["scp", "-F", str(ssh_config), "-r", f"{ssh_host}:{temp_dir}/.", str(output_dir)], check=True)
    finally:
        cleanup = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, f"rm -rf {temp_dir}"], check=False)
        if cleanup.returncode:
            raise RuntimeError("pod temporary cleanup failed")
    measurement = json.loads((output_dir / "g242_measurement.json").read_text(encoding="ascii"))
    measurement["disk_guard"] = guard
    (output_dir / "g242_measurement.json").write_text(json.dumps(measurement, indent=2) + "\n", encoding="ascii")
    write_per_sample_table(measurement, output_dir / "per_sample_table.csv")
    return measurement


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True); parser.add_argument("--ssh-config", type=Path, required=True)
    parser.add_argument("--labels-csv", type=Path, required=True); parser.add_argument("--reference-image", type=Path, required=True); parser.add_argument("--source-root", type=Path, required=True); parser.add_argument("--ssh-host", default="pod")
    args = parser.parse_args(); report = run(args.output_dir, args.ssh_config, args.ssh_host, args.labels_csv, args.reference_image, args.source_root)
    print("G242_DENOMINATOR=" + str(report["sampling"]["denominator"]))


if __name__ == "__main__":
    main()
