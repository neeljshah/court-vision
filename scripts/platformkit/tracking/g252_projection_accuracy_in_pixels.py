"""Measure full-resolution normal offsets from projected court markings to edges."""
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
LINE_TYPES = ("sideline", "baseline", "lane_boundary", "free_throw_line", "arc", "centre_circle")
SAMPLE_SPACING_PX = 4.0
SEARCH_RADIUS_PX = 24
CANNY_LOW = 50
CANNY_HIGH = 150


def court_line_geometry() -> list[tuple[str, list[list[float]]]]:
    """Return fixed WNBA marking curves grouped into the required line types."""
    def arc(cx: float, cy: float, radius: float, start: float, end: float) -> list[list[float]]:
        angles = np.linspace(start, end, 121)
        return [[float(cx + radius * np.cos(angle)), float(cy + radius * np.sin(angle))] for angle in angles]

    left, right, length, width, depth = 17.0, 33.0, 94.0, 50.0, 19.0
    lines: list[tuple[str, list[list[float]]]] = [
        ("baseline", [[0.0, 0.0], [width, 0.0]]),
        ("baseline", [[0.0, length], [width, length]]),
        ("sideline", [[0.0, 0.0], [0.0, length]]),
        ("sideline", [[width, 0.0], [width, length]]),
        ("lane_boundary", [[left, 0.0], [left, depth]]),
        ("lane_boundary", [[right, 0.0], [right, depth]]),
        ("lane_boundary", [[left, length], [left, length - depth]]),
        ("lane_boundary", [[right, length], [right, length - depth]]),
        ("free_throw_line", [[left, depth], [right, depth]]),
        ("free_throw_line", [[left, length - depth], [right, length - depth]]),
        ("free_throw_line", arc(width / 2.0, depth, 6.0, 0.0, np.pi)),
        ("free_throw_line", arc(width / 2.0, length - depth, 6.0, np.pi, 2.0 * np.pi)),
        ("centre_circle", arc(width / 2.0, length / 2.0, 6.0, 0.0, 2.0 * np.pi)),
    ]
    radius = 22.0 + 1.75 / 12.0
    for baseline, direction in ((0.0, 1.0), (length, -1.0)):
        basket = baseline + direction * 4.0
        projected_arc = arc(width / 2.0, basket, radius, 0.0, np.pi)
        if direction < 0:
            projected_arc = [[x, 2.0 * basket - y] for x, y in projected_arc]
        lines.extend((("arc", projected_arc), ("arc", [[projected_arc[0][0], baseline], projected_arc[0]]),
                      ("arc", [[projected_arc[-1][0], baseline], projected_arc[-1]])))
    return lines


def read_labels(path: Path) -> dict[int, str]:
    """Load the fixed committed G244 label table without alteration."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    labels = {int(row["frame"]): row["validity"] for row in rows}
    if len(labels) != 89 or len(rows) != 89 or set(labels.values()) - set(CLASSES):
        raise ValueError("G244 labels must contain 89 unique fixed-class rows")
    return labels


def read_g247(path: Path, labels: dict[int, str]) -> dict[int, list[list[float]]]:
    """Read only G247's persisted image-to-court maps for the fixed denominator."""
    report = json.loads(path.read_text(encoding="ascii"))
    matrices = {int(row["source_frame"]): row["homography_image_to_court"] for row in report["records"]}
    if set(matrices) != set(labels) or len(matrices) != 89:
        raise ValueError("G247 maps must match the complete fixed label denominator")
    return matrices


def _worker_source(matrices: dict[int, list[list[float]]]) -> str:
    packed_maps = base64.b64encode(json.dumps(matrices, separators=(",", ":")).encode("ascii")).decode("ascii")
    packed_geometry = base64.b64encode(json.dumps(court_line_geometry(), separators=(",", ":")).encode("ascii")).decode("ascii")
    return f'''import base64, json, math, os, tempfile, traceback
import cv2
import numpy as np
VIDEO={VIDEO!r}; FRAME_COUNT={FRAME_COUNT}; MATRICES=json.loads(base64.b64decode({packed_maps!r})); GEOMETRY=json.loads(base64.b64decode({packed_geometry!r}))
RADIUS={SEARCH_RADIUS_PX}; SPACING={SAMPLE_SPACING_PX}; LOW={CANNY_LOW}; HIGH={CANNY_HIGH}; SAMPLES=set(map(int,MATRICES)); work=tempfile.mkdtemp(prefix="g252_offsets_")
def clip(a,b,width,height):
    delta=b-a; low,high=0.0,1.0
    for p,q in ((-delta[0],a[0]),(delta[0],width-1-a[0]),(-delta[1],a[1]),(delta[1],height-1-a[1])):
        if abs(p)<1e-12:
            if q<0: return None
        elif p<0: low=max(low,q/p)
        else: high=min(high,q/p)
    return None if low>high else (a+low*delta,b+high*delta)
def edge_distances(edges,points,normals):
    radii=np.arange(-RADIUS,RADIUS+1,dtype=np.float64); count=len(points); found=np.full(count,np.nan,dtype=np.float64)
    for start in range(0,count,12000):
        end=min(count,start+12000); coords=points[start:end,None,:]+radii[None,:,None]*normals[start:end,None,:]
        xs=np.rint(coords[:,:,0]).astype(np.int32); ys=np.rint(coords[:,:,1]).astype(np.int32); keep=(xs>=0)&(xs<edges.shape[1])&(ys>=0)&(ys<edges.shape[0])
        hit=np.zeros(keep.shape,dtype=bool); hit[keep]=edges[ys[keep],xs[keep]] > 0
        any_hit=hit.any(axis=1)
        if any_hit.any():
            distances=np.abs(radii)[None,:]; nearest=np.where(hit,distances,np.inf).min(axis=1); found[start:end][any_hit]=nearest[any_hit]
    return found
def measure(image,h):
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY); edges=cv2.Canny(gray,LOW,HIGH,apertureSize=3,L2gradient=True); height,width=gray.shape; inverse=np.linalg.inv(np.asarray(h,dtype=np.float64)); out={{kind:{{"sample_points":0,"no_candidate":0,"distances_px":[]}} for kind in {LINE_TYPES!r}}}
    for kind,raw in GEOMETRY:
        curve=np.asarray(raw,dtype=np.float32); projected=cv2.perspectiveTransform(curve.reshape(1,-1,2),inverse)[0]; point_parts=[]; normal_parts=[]
        for a,b in zip(projected[:-1],projected[1:]):
            delta=b-a; length=float(np.linalg.norm(delta))
            if not np.isfinite(length) or length<=1e-6: continue
            clipped=clip(a,b,width,height)
            if clipped is None: continue
            first,last=clipped; clipped_delta=last-first; clipped_length=float(np.linalg.norm(clipped_delta))
            if clipped_length<=1e-6: continue
            count=max(1,int(math.ceil(clipped_length/SPACING))); fraction=(np.arange(count,dtype=np.float64)+0.5)/count; point_parts.append(first+fraction[:,None]*clipped_delta); tangent=delta/length; normal_parts.append(np.repeat(np.array([[-tangent[1],tangent[0]]]),count,axis=0))
        if not point_parts: continue
        points=np.concatenate(point_parts); normals=np.concatenate(normal_parts); distances=edge_distances(edges,points,normals); found=distances[np.isfinite(distances)]; out[kind]["sample_points"]+=int(len(distances)); out[kind]["no_candidate"]+=int(len(distances)-len(found)); out[kind]["distances_px"].extend(float(value) for value in found)
    return out
capture=cv2.VideoCapture(VIDEO)
if not capture.isOpened(): raise RuntimeError("could not open source video")
records=[]
try:
    for index in range(FRAME_COUNT):
        ok,image=capture.read()
        if not ok: raise RuntimeError("sequential decode ended before declared frame count")
        if index in SAMPLES: records.append({{"source_frame":index,"line_types":measure(image,MATRICES[str(index)])}})
    if len(records)!=len(SAMPLES): raise RuntimeError("not every named frame was measured")
    out=os.path.join(work,"g252_measurement.json"); report={{"video":{{"path":VIDEO,"bytes":os.stat(VIDEO).st_size,"resolution":[1920,1080],"declared_frames":FRAME_COUNT}},"decode":"one sequential cv2.VideoCapture pass over frames 0 through 174429; no seek, matcher rerun, or decoded image retention","method":{{"candidate":"Canny strong-edge pixel sampled along the projected-line normal","canny":{{"low":LOW,"high":HIGH,"aperture_size":3,"L2gradient":True}},"sample_spacing_px":SPACING,"search_radius_px":RADIUS,"distance":"minimum absolute integer-pixel normal displacement to an in-bounds candidate; no candidate is retained, not imputed","line_type_definition":"free_throw_line includes straight free-throw markings and circles; arc includes three-point curves and straight corner legs"}},"records":records}}; open(out,"w",encoding="ascii").write(json.dumps(report,indent=2,allow_nan=False)+"\\n"); print(json.dumps({{"temp_dir":work,"artifact_bytes":os.path.getsize(out)}}))
except Exception as exc:
    failure=os.path.join(work,"failure.txt"); open(failure,"w",encoding="ascii").write(traceback.format_exc()); print(json.dumps({{"temp_dir":work,"error":str(exc),"failure_bytes":os.path.getsize(failure)}}))
finally: capture.release()
'''


def disk_guard(ssh_config: Path, ssh_host: str) -> dict[str, int]:
    """Run the required authoritative pod write probe before remote output exists."""
    command = "set -e; du -sm /workspace/nba-ai-system/data; dd if=/dev/zero of=/workspace/nba-ai-system/g252_disk_probe.bin bs=1M count=1 conv=fsync status=none; wc -c < /workspace/nba-ai-system/g252_disk_probe.bin; rm -f /workspace/nba-ai-system/g252_disk_probe.bin"
    done = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if done.returncode:
        raise RuntimeError(done.stderr.decode("ascii", "replace"))
    lines = done.stdout.decode("ascii", "replace").splitlines()
    return {"data_megabytes": int(lines[0].split()[0]), "probe_bytes_removed": int(lines[1])}


def _summary(values: list[float], sample_points: int, no_candidate: int) -> dict[str, float | int | None]:
    ordered = sorted(values)
    result: dict[str, float | int | None] = {"sample_points": sample_points, "found": len(ordered), "no_candidate": no_candidate}
    result.update({"median": None, "p90": None, "max": None} if not ordered else {"median": float(statistics.median(ordered)), "p90": float(np.quantile(ordered, 0.9)), "max": ordered[-1]})
    return result


def analyze(measurement: dict[str, object], labels: dict[int, str]) -> dict[str, object]:
    """Aggregate complete retained samples by inherited class and line type."""
    records = list(measurement["records"])
    if {int(row["source_frame"]) for row in records} != set(labels):
        raise ValueError("measurement rows must be the complete fixed blind-label denominator")
    buckets = {kind: {line: {"distances": [], "sample_points": 0, "no_candidate": 0} for line in LINE_TYPES + ("pooled",)} for kind in CLASSES}
    for row in records:
        target = buckets[labels[int(row["source_frame"])]]
        for line in LINE_TYPES:
            item = row["line_types"][line]; values = [float(value) for value in item["distances_px"]]
            for bucket in (target[line], target["pooled"]):
                bucket["distances"].extend(values); bucket["sample_points"] += int(item["sample_points"]); bucket["no_candidate"] += int(item["no_candidate"])
    return {"validity_counts": {kind: sum(labels[frame] == kind for frame in labels) for kind in CLASSES}, "distributions": {kind: {line: _summary(bucket["distances"], bucket["sample_points"], bucket["no_candidate"]) for line, bucket in buckets[kind].items()} for kind in CLASSES}}


def run(output_dir: Path, ssh_config: Path, ssh_host: str = "pod") -> dict[str, object]:
    """Run one guarded pod decode, collect its JSON, and remove all pod temporary data."""
    labels = read_labels(LABELS); matrices = read_g247(G247, labels); guard = disk_guard(ssh_config, ssh_host)
    done = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, "python3 -"], input=_worker_source(matrices).encode("ascii"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if done.returncode:
        raise RuntimeError(done.stderr.decode("ascii", "replace"))
    rows = [line for line in done.stdout.decode("utf-8", "replace").splitlines() if line.startswith('{"temp_dir":')]
    if len(rows) != 1:
        raise RuntimeError("remote worker did not return exactly one result")
    remote = json.loads(rows[0]); temp_dir = str(remote["temp_dir"])
    if not temp_dir.startswith("/tmp/g252_offsets_"):
        raise RuntimeError("unexpected remote temporary directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        if "error" in remote:
            subprocess.run(["scp", "-F", str(ssh_config), f"{ssh_host}:{temp_dir}/failure.txt", str(output_dir)], check=True)
            raise RuntimeError("G252 remote worker: " + str(remote["error"]))
        subprocess.run(["scp", "-F", str(ssh_config), f"{ssh_host}:{temp_dir}/g252_measurement.json", str(output_dir)], check=True)
    finally:
        cleanup = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, f"rm -rf -- {temp_dir}"], check=False)
        if cleanup.returncode:
            raise RuntimeError("pod temporary cleanup failed")
    path = output_dir / "g252_measurement.json"; report = json.loads(path.read_text(encoding="ascii"))
    report["disk_guard"] = guard; report["remote_temp_bytes_removed"] = int(remote["artifact_bytes"])
    report["input_sha256"] = {"g244_blind_labels": hashlib.sha256(LABELS.read_bytes()).hexdigest(), "g247_measurement": hashlib.sha256(G247.read_bytes()).hexdigest()}
    report["analysis"] = analyze(report, labels); path.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    return report


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True); parser.add_argument("--ssh-config", type=Path, required=True); parser.add_argument("--ssh-host", default="pod")
    args = parser.parse_args(); report = run(args.output_dir, args.ssh_config, args.ssh_host)
    print("G252_ROWS=" + str(len(report["records"])))


if __name__ == "__main__":
    main()
