"""Measure projected WNBA court-line agreement with source-image structure."""
from __future__ import annotations

import base64
import csv
import hashlib
import json
import statistics
import subprocess
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
VIDEO = "/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4"
FRAME_COUNT = 174430
LABELS = ROOT / "docs/evidence/tracking/g244_blind_validity_labels_2026-09-04.csv"
G247 = ROOT / "docs/evidence/tracking/g247_projected_quad_validity_artifact/g247_measurement.json"
CLASSES = ("VALID", "INVALID", "CANNOT_JUDGE")
NEAR_OFFSET_PX = 3.0
FAR_OFFSET_PX = 9.0
LINE_DISTANCE_PX = 4
ORIENTATION_DEGREES = 15.0


def court_line_geometry() -> list[list[list[float]]]:
    """Return fixed WNBA court-marking polylines in the G196 feet contract."""
    def arc(cx: float, cy: float, radius: float, start: float, end: float) -> list[list[float]]:
        angles = np.linspace(start, end, 121)
        return [[float(cx + radius * np.cos(angle)), float(cy + radius * np.sin(angle))] for angle in angles]

    left, right, length, width, depth = 17.0, 33.0, 94.0, 50.0, 19.0
    lines: list[list[list[float]]] = [
        [[0.0, 0.0], [width, 0.0]], [[0.0, length], [width, length]],
        [[0.0, 0.0], [0.0, length]], [[width, 0.0], [width, length]],
        [[left, 0.0], [left, depth]], [[right, 0.0], [right, depth]],
        [[left, length], [left, length - depth]], [[right, length], [right, length - depth]],
        [[left, depth], [right, depth]], [[left, length - depth], [right, length - depth]],
        arc(width / 2.0, length / 2.0, 6.0, 0.0, 2.0 * np.pi),
    ]
    radius = 22.0 + 1.75 / 12.0
    for baseline, direction in ((0.0, 1.0), (length, -1.0)):
        basket, free_throw = baseline + direction * 4.0, baseline + direction * depth
        lines.extend((arc(width / 2.0, free_throw, 8.0, 0.0, np.pi),))
        arc_points = arc(width / 2.0, basket, radius, 0.0, np.pi)
        if direction < 0:
            arc_points = [[x, 2.0 * basket - y] for x, y in arc_points]
        lines.extend((arc_points, [[arc_points[0][0], baseline], arc_points[0]],
                      [[arc_points[-1][0], baseline], arc_points[-1]]))
    return lines


def read_labels(path: Path) -> dict[int, str]:
    """Load the fixed, committed 89-row G244 labels without alteration."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    result = {int(row["frame"]): row["validity"] for row in rows}
    if len(rows) != 89 or len(result) != 89 or set(result.values()) - set(CLASSES):
        raise ValueError("G244 labels must be 89 unique rows in the fixed three classes")
    return result


def read_g247(path: Path, labels: dict[int, str]) -> dict[int, list[list[float]]]:
    """Load only G247's already-persisted per-frame image-to-court matrices."""
    report = json.loads(path.read_text(encoding="ascii"))
    records = {int(row["source_frame"]): row["homography_image_to_court"] for row in report["records"]}
    if set(records) != set(labels) or len(records) != 89:
        raise ValueError("G247 matrices and G244 labels must have the same 89 frames")
    return records


def _worker_source(matrices: dict[int, list[list[float]]]) -> str:
    payload = base64.b64encode(json.dumps(matrices, separators=(",", ":")).encode("ascii")).decode("ascii")
    geometry = base64.b64encode(json.dumps(court_line_geometry(), separators=(",", ":")).encode("ascii")).decode("ascii")
    return f'''import base64, json, math, os, tempfile, traceback
import cv2
import numpy as np
VIDEO={VIDEO!r}; FRAME_COUNT={FRAME_COUNT}; MATRICES=json.loads(base64.b64decode({payload!r})); GEOMETRY=json.loads(base64.b64decode({geometry!r}))
NEAR={NEAR_OFFSET_PX}; FAR={FAR_OFFSET_PX}; DIST={LINE_DISTANCE_PX}; COS=math.cos(math.radians({ORIENTATION_DEGREES}))
SAMPLES=set(map(int, MATRICES)); work=tempfile.mkdtemp(prefix="g248_lines_")
def bilinear(image, points):
    values=[]
    for start in range(0,len(points),16000):
        batch=points[start:start+16000]
        values.append(cv2.remap(image,batch[:,0].astype(np.float32),batch[:,1].astype(np.float32),cv2.INTER_LINEAR).reshape(-1))
    return np.concatenate(values)
def clip(a,b,width,height):
    delta=b-a; low,high=0.0,1.0
    for p,q in ((-delta[0],a[0]),(delta[0],width-1-a[0]),(-delta[1],a[1]),(delta[1],height-1-a[1])):
        if abs(p)<1e-12:
            if q<0: return None
        elif p<0: low=max(low,q/p)
        else: high=min(high,q/p)
    return None if low>high else (a+low*delta,b+high*delta)
def geometry_samples(h,width,height):
    inverse=np.linalg.inv(np.asarray(h,dtype=np.float64)); points=[]; tangents=[]; total=0.0; inside=0.0
    for raw_curve in GEOMETRY:
        curve=np.asarray(raw_curve,dtype=np.float32)
        projected=cv2.perspectiveTransform(curve.reshape(1,-1,2), inverse)[0]
        for a,b in zip(projected[:-1],projected[1:]):
            delta=b-a; length=float(np.linalg.norm(delta))
            if not np.isfinite(length) or length <= 1e-6: continue
            total+=length; clipped=clip(a,b,width,height)
            if clipped is None: continue
            start,end=clipped; clipped_delta=end-start; clipped_length=float(np.linalg.norm(clipped_delta))
            if clipped_length <= 1e-6: continue
            inside+=clipped_length; count=max(1,int(math.ceil(clipped_length/2.0))); fraction=(np.arange(count,dtype=np.float64)+0.5)/count
            points.append(start+fraction[:,None]*clipped_delta); tangents.append(np.repeat((delta/length)[None,:],count,axis=0))
    if not points: raise RuntimeError("no projected curve segment intersects the image")
    return np.concatenate(points),np.concatenate(tangents),inside/total
def lsd_maps(gray):
    mask=np.zeros(gray.shape,np.uint8); cs=np.zeros(gray.shape,np.float32); sn=np.zeros(gray.shape,np.float32)
    result=cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(gray)[0]
    if result is None: return mask,cs,sn,0
    for item in result.reshape(-1,4):
        x1,y1,x2,y2=map(float,item); dx=x2-x1; dy=y2-y1; norm=math.hypot(dx,dy)
        if norm <= 1e-6: continue
        angle_cos,angle_sin=dx/norm,dy/norm
        start,end=(int(round(x1)),int(round(y1))),(int(round(x2)),int(round(y2)))
        cv2.line(mask,start,end,255,2*DIST+1,cv2.LINE_AA); cv2.line(cs,start,end,float(angle_cos),2*DIST+1,cv2.LINE_AA); cv2.line(sn,start,end,float(angle_sin),2*DIST+1,cv2.LINE_AA)
    return mask,cs,sn,len(result)
def measure(image,h):
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY); grad=cv2.magnitude(cv2.Sobel(gray,cv2.CV_32F,1,0,ksize=3),cv2.Sobel(gray,cv2.CV_32F,0,1,ksize=3))
    height,width=gray.shape; points,tangent,coverage=geometry_samples(h,width,height); on=points; direction=tangent; normal=np.column_stack((-direction[:,1],direction[:,0])); controls=[]
    for offset in (NEAR,FAR):
        for sign in (-1.0,1.0):
            candidate=on+sign*offset*normal; keep=(candidate[:,0]>=0)&(candidate[:,0]<width)&(candidate[:,1]>=0)&(candidate[:,1]<height)
            controls.append(candidate[keep])
    control=np.concatenate(controls) if controls else np.empty((0,2))
    if not len(on) or not len(control): raise RuntimeError("no in-bounds curve/control samples")
    mask,cs,sn,segments=lsd_maps(gray); agreed=0
    for point,vector in zip(on,direction):
        x,y=int(round(point[0])),int(round(point[1])); x0,x1=max(0,x-DIST),min(width,x+DIST+1); y0,y1=max(0,y-DIST),min(height,y+DIST+1)
        nearby=mask[y0:y1,x0:x1]>0
        if nearby.any() and np.any(np.abs(vector[0]*cs[y0:y1,x0:x1][nearby]+vector[1]*sn[y0:y1,x0:x1][nearby])>=COS): agreed+=1
    return {{"edge_response_contrast":float(np.mean(bilinear(grad,on))-np.mean(bilinear(grad,control))),"line_detector_agreement":float(agreed/len(on)),"marking_contrast":float(np.mean(bilinear(gray,on))-np.mean(bilinear(gray,control))),"coverage":float(coverage),"on_curve_samples":int(len(on)),"control_samples":int(len(control)),"lsd_segments":int(segments)}}
capture=cv2.VideoCapture(VIDEO)
if not capture.isOpened(): raise RuntimeError("could not open source video")
records=[]
try:
    for index in range(FRAME_COUNT):
        ok,image=capture.read()
        if not ok: raise RuntimeError("sequential decode ended before declared frame count")
        if index in SAMPLES: records.append({{"source_frame":index,"signals":measure(image,MATRICES[str(index)])}})
except Exception as exc:
    capture.release(); failure=os.path.join(work,"failure.txt"); open(failure,"w",encoding="ascii").write(traceback.format_exc())
    print(json.dumps({{"temp_dir":work,"error":str(exc),"failure_bytes":os.path.getsize(failure)}})); raise SystemExit(0)
capture.release()
try:
    if len(records)!=len(SAMPLES): raise RuntimeError("not every named G247 frame was decoded")
    out=os.path.join(work,"g248_measurement.json"); report={{"video":{{"path":VIDEO,"bytes":os.stat(VIDEO).st_size,"resolution":[1920,1080],"declared_frames":FRAME_COUNT}},"decode":"one sequential cv2.VideoCapture pass, frames 0 through 174429; no frame seek and no images retained","geometry":"baselines, sidelines, lane boundaries, both free-throw lines/circles, both three-point arcs/corner lines, and centre circle; curves sampled at projected 2 px arclength","parameters":{{"edge_and_marking_offsets_px":{{"near":NEAR,"far":FAR,"sides":"both perpendicular sides; aggregate control mean"}},"line_detector":"OpenCV LSD_REFINE_STD","line_distance_px":DIST,"orientation_degrees":{ORIENTATION_DEGREES}}},"records":records}}; open(out,"w",encoding="ascii").write(json.dumps(report,indent=2,allow_nan=False)+"\\n"); print(json.dumps({{"temp_dir":work,"artifact_bytes":os.path.getsize(out)}}))
except Exception as exc:
    failure=os.path.join(work,"failure.txt"); open(failure,"w",encoding="ascii").write(traceback.format_exc())
    print(json.dumps({{"temp_dir":work,"error":str(exc),"failure_bytes":os.path.getsize(failure)}}))
'''


def disk_guard(ssh_config: Path, ssh_host: str) -> dict[str, int]:
    """Run G248's authoritative dd guard before remote measurement output exists."""
    command = "set -e; du -sm /workspace/nba-ai-system/data; dd if=/dev/zero of=/workspace/nba-ai-system/g248_disk_probe.bin bs=1M count=1 conv=fsync status=none; wc -c < /workspace/nba-ai-system/g248_disk_probe.bin; rm -f /workspace/nba-ai-system/g248_disk_probe.bin"
    done = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if done.returncode:
        raise RuntimeError(done.stderr.decode("ascii", "replace"))
    lines = done.stdout.decode("ascii", "replace").splitlines()
    return {"data_megabytes": int(lines[0].split()[0]), "probe_bytes_removed": int(lines[1])}


def _summary(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    return {"n": len(ordered), "min": ordered[0], "median": float(statistics.median(ordered)),
            "p90": float(np.quantile(ordered, 0.9)), "max": ordered[-1]}


def _overlap(valid: list[float], invalid: list[float]) -> dict[str, float | int]:
    return {"invalid_range_min": min(invalid), "invalid_range_max": max(invalid),
            "valid_in_invalid_range": sum(min(invalid) <= item <= max(invalid) for item in valid),
            "valid_range_min": min(valid), "valid_range_max": max(valid),
            "invalid_in_valid_range": sum(min(valid) <= item <= max(valid) for item in invalid)}


def analyze(measurement: dict[str, object], labels: dict[int, str]) -> dict[str, object]:
    """Join G244 classes and give complete per-class distributions and overlaps."""
    rows = list(measurement["records"])
    if {int(row["source_frame"]) for row in rows} != set(labels):
        raise ValueError("measurement rows differ from the fixed blind-label denominator")
    fields = ("edge_response_contrast", "line_detector_agreement", "marking_contrast", "coverage")
    values = {kind: {field: [] for field in fields} for kind in CLASSES}
    for row in rows:
        for field in fields:
            values[labels[int(row["source_frame"])]] [field].append(float(row["signals"][field]))
    return {"validity_counts": {kind: len(values[kind][fields[0]]) for kind in CLASSES},
            "distributions": {field: {kind: _summary(values[kind][field]) for kind in CLASSES} for field in fields},
            "valid_invalid_range_overlap": {field: _overlap(values["VALID"][field], values["INVALID"][field]) for field in fields}}


def run(output_dir: Path, ssh_config: Path, ssh_host: str = "pod") -> dict[str, object]:
    """Measure once on the pod, remove its temporary JSON, then add local summaries."""
    labels, matrices = read_labels(LABELS), read_g247(G247, read_labels(LABELS))
    guard = disk_guard(ssh_config, ssh_host)
    done = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, "python3 -"], input=_worker_source(matrices).encode("ascii"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if done.returncode:
        raise RuntimeError(done.stderr.decode("ascii", "replace"))
    rows = [line for line in done.stdout.decode("utf-8", "replace").splitlines() if line.startswith('{"temp_dir":')]
    if len(rows) != 1:
        raise RuntimeError("remote worker did not return exactly one result")
    remote = json.loads(rows[0]); temp_dir = str(remote["temp_dir"])
    if not temp_dir.startswith("/tmp/g248_lines_"):
        raise RuntimeError("unexpected remote temporary directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        if "error" in remote:
            subprocess.run(["scp", "-F", str(ssh_config), f"{ssh_host}:{temp_dir}/failure.txt", str(output_dir)], check=True)
            raise RuntimeError("G248 remote worker: " + str(remote["error"]))
        subprocess.run(["scp", "-F", str(ssh_config), f"{ssh_host}:{temp_dir}/g248_measurement.json", str(output_dir)], check=True)
    finally:
        cleanup = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, f"rm -rf -- {temp_dir}"], check=False)
        if cleanup.returncode:
            raise RuntimeError("pod temporary cleanup failed")
    path = output_dir / "g248_measurement.json"; report = json.loads(path.read_text(encoding="ascii"))
    report["disk_guard"] = guard; report["remote_temp_bytes_removed"] = int(remote["artifact_bytes"])
    report["input_sha256"] = {"g244_blind_labels": hashlib.sha256(LABELS.read_bytes()).hexdigest(), "g247_measurement": hashlib.sha256(G247.read_bytes()).hexdigest()}
    report["analysis"] = analyze(report, labels)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    return report


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True); parser.add_argument("--ssh-config", type=Path, required=True)
    parser.add_argument("--ssh-host", default="pod")
    args = parser.parse_args(); report = run(args.output_dir, args.ssh_config, args.ssh_host)
    print("G248_ROWS=" + str(len(report["records"])))


if __name__ == "__main__":
    main()
