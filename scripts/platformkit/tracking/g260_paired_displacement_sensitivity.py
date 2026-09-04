"""Measure G260's sealed paired within-frame displacement experiment."""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np

from scripts.platformkit.tracking import g247_projected_quad_validity as g247
from scripts.platformkit.tracking import g248_projected_line_image_agreement as g248
from scripts.platformkit.tracking import g252_projection_accuracy_in_pixels as g252

ROOT = Path(__file__).resolve().parents[3]
VIDEO = "/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4"
FRAME_COUNT = 174430
RUNGS = (0, 2, 5, 10, 20, 40, 100)
SIGNALS = ("offset_p90_px", "edge_response_contrast", "line_detector_agreement",
           "marking_contrast", "coverage", "quad_projected_area_ratio_to_seed",
           "quad_bbox_aspect_ratio", "quad_outside_corner_fraction")
G247 = ROOT / "docs/evidence/tracking/g247_projected_quad_validity_artifact/g247_measurement.json"
PREREG = ROOT / "docs/evidence/tracking/g260_paired_displacement_sensitivity_artifact/g260_preregistration.json"


def sha256(path: Path) -> str:
    """Return the SHA-256 digest for a named route or evidence input."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preregistration() -> dict[str, object]:
    """Load the sealed G260 frame enumeration without changing it."""
    return json.loads(PREREG.read_text(encoding="ascii"))


def matrices_for_sample() -> tuple[list[int], dict[int, list[list[float]]]]:
    """Return only the preregistered G247 maps, rejecting a missing identity."""
    prereg = preregistration()
    frames = [int(value) for value in prereg["sampling"]["source_frames"]]
    rows = {int(row["source_frame"]): row["homography_image_to_court"]
            for row in json.loads(G247.read_text(encoding="ascii"))["records"]}
    if len(frames) != 35 or len(set(frames)) != len(frames) or any(frame not in rows for frame in frames):
        raise ValueError("sealed G260 sample does not match persisted G247 maps")
    return frames, {frame: rows[frame] for frame in frames}


def _worker_source(frames: list[int], matrices: dict[int, list[list[float]]]) -> str:
    encoded_maps = base64.b64encode(json.dumps(matrices).encode("ascii")).decode("ascii")
    encoded_lines = base64.b64encode(json.dumps(g248.court_line_geometry()).encode("ascii")).decode("ascii")
    encoded_typed = base64.b64encode(json.dumps(g252.court_line_geometry()).encode("ascii")).decode("ascii")
    return f'''import base64,hashlib,json,math,os,tempfile
import cv2
import numpy as np
VIDEO={VIDEO!r}; COUNT={FRAME_COUNT}; FRAMES={frames!r}; RUNGS={RUNGS!r}
MAPS={{int(k):np.asarray(v,dtype=np.float64) for k,v in json.loads(base64.b64decode({encoded_maps!r})).items()}}
LINES=json.loads(base64.b64decode({encoded_lines!r})); TYPED=json.loads(base64.b64decode({encoded_typed!r})); WORK=tempfile.mkdtemp(prefix="g260_pairs_")
def clip(a,b,w,h):
 d=b-a;lo,hi=0.,1.
 for p,q in ((-d[0],a[0]),(d[0],w-1-a[0]),(-d[1],a[1]),(d[1],h-1-a[1])):
  if abs(p)<1e-12:
   if q<0:return None
  elif p<0:lo=max(lo,q/p)
  else:hi=min(hi,q/p)
 return None if lo>hi else (a+lo*d,b+hi*d)
def samples(h,w,ht):
 inv=np.linalg.inv(h);pts=[];tan=[];total=inside=0.
 for raw in LINES:
  curve=cv2.perspectiveTransform(np.asarray(raw,np.float32).reshape(1,-1,2),inv)[0]
  for a,b in zip(curve[:-1],curve[1:]):
   d=b-a;z=float(np.linalg.norm(d));total+=z;hit=clip(a,b,w,ht)
   if not np.isfinite(z) or z<=1e-6 or hit is None:continue
   first,last=hit;cl=float(np.linalg.norm(last-first))
   if cl<=1e-6:continue
   inside+=cl;n=max(1,int(math.ceil(cl/2.)));f=(np.arange(n)+.5)/n;pts.append(first+f[:,None]*(last-first));tan.append(np.repeat((d/z)[None,:],n,axis=0))
 if not pts:raise RuntimeError("no projected geometry")
 return np.concatenate(pts),np.concatenate(tan),inside/total
def bilinear(image,points):
 chunks=[]
 for first in range(0,len(points),30000):
  part=points[first:first+30000];chunks.append(cv2.remap(image,part[:,0].astype(np.float32),part[:,1].astype(np.float32),cv2.INTER_LINEAR).reshape(-1))
 return np.concatenate(chunks)
def offset(edges,h):
 ht,w=edges.shape;inv=np.linalg.inv(h);found=[];count=missing=0;radii=np.arange(-24,25,dtype=float)
 for _,raw in TYPED:
  curve=cv2.perspectiveTransform(np.asarray(raw,np.float32).reshape(1,-1,2),inv)[0]
  for a,b in zip(curve[:-1],curve[1:]):
   d=b-a;z=float(np.linalg.norm(d));hit=clip(a,b,w,ht)
   if not np.isfinite(z) or z<=1e-6 or hit is None:continue
   first,last=hit;cl=float(np.linalg.norm(last-first))
   if cl<=1e-6:continue
   n=max(1,int(math.ceil(cl/4.)));f=(np.arange(n)+.5)/n;p=first+f[:,None]*(last-first);normal=np.array([-d[1],d[0]])/z;xy=p[:,None,:]+radii[None,:,None]*normal;x=np.rint(xy[:,:,0]).astype(int);y=np.rint(xy[:,:,1]).astype(int);keep=(x>=0)&(x<w)&(y>=0)&(y<ht);hits=np.zeros(keep.shape,bool);hits[keep]=edges[y[keep],x[keep]]>0;has=hits.any(axis=1);count+=n;missing+=int((~has).sum())
   if has.any():found.extend(np.where(hits,np.abs(radii)[None,:],np.inf).min(axis=1)[has].tolist())
 order=np.sort(found);return {{"sample_points":count,"found":len(order),"no_candidate":missing,"median":float(np.median(order)) if len(order) else None,"p90":float(np.quantile(order,.9)) if len(order) else None,"max":float(order[-1]) if len(order) else None,"bound_count":int(np.sum(order>=24))}}
def image_signals(gray,grad,det,h):
 ht,w=gray.shape;on,tan,coverage=samples(h,w,ht);normal=np.column_stack((-tan[:,1],tan[:,0]));controls=[]
 for distance in (3.,9.):
  for sign in (-1.,1.):
   points=on+sign*distance*normal;controls.append(points[(points[:,0]>=0)&(points[:,0]<w)&(points[:,1]>=0)&(points[:,1]<ht)])
 control=np.concatenate(controls);mask=np.zeros(gray.shape,np.uint8);cs=np.zeros(gray.shape,np.float32);sn=np.zeros(gray.shape,np.float32);segments=0
 if det is not None:
  segments=len(det)
  for x1,y1,x2,y2 in det.reshape(-1,4):
   dx,dy=float(x2-x1),float(y2-y1);z=math.hypot(dx,dy)
   if z<=1e-6:continue
   co,si=dx/z,dy/z;a,b=(int(round(x1)),int(round(y1))),(int(round(x2)),int(round(y2)));cv2.line(mask,a,b,9,9,cv2.LINE_AA);cv2.line(cs,a,b,co,9,cv2.LINE_AA);cv2.line(sn,a,b,si,9,9,cv2.LINE_AA)
 agreed=0;cos=math.cos(math.radians(15))
 for point,vector in zip(on,tan):
  x,y=map(int,np.rint(point));x0,x1=max(0,x-4),min(w,x+5);y0,y1=max(0,y-4),min(ht,y+5);near=mask[y0:y1,x0:x1]>0
  if near.any() and np.any(np.abs(vector[0]*cs[y0:y1,x0:x1][near]+vector[1]*sn[y0:y1,x0:x1][near])>=cos):agreed+=1
 return {{"edge_response_contrast":float(np.mean(bilinear(grad,on))-np.mean(bilinear(grad,control))),"line_detector_agreement":float(agreed/len(on)),"marking_contrast":float(np.mean(bilinear(gray,on))-np.mean(bilinear(gray,control))),"coverage":float(coverage),"on_curve_samples":int(len(on)),"control_samples":int(len(control)),"lsd_segments":segments}}
def quad(h,seed):
 court=np.asarray([[17.,0.],[33.,0.],[17.,19.],[33.,19.]],np.float32).reshape(1,-1,2);p=cv2.perspectiveTransform(court,np.linalg.inv(h))[0][[0,1,3,2]];q=cv2.perspectiveTransform(court,np.linalg.inv(seed))[0][[0,1,3,2]];area=lambda x:float(.5*np.sum(x[:,0]*np.roll(x[:,1],-1)-x[:,1]*np.roll(x[:,0],-1)))
 return {{"projected_area_ratio_to_seed":abs(area(p))/abs(area(q)),"bbox_aspect_ratio":float((p[:,0].max()-p[:,0].min())/(p[:,1].max()-p[:,1].min())),"outside_corner_fraction":float(np.mean((p[:,0]<0)|(p[:,0]>=1920)|(p[:,1]<0)|(p[:,1]>=1080)))}}
capture=cv2.VideoCapture(VIDEO)
if not capture.isOpened():raise RuntimeError("could not open source video")
records=[];wanted=set(FRAMES)
try:
 for index in range(COUNT):
  ok,image=capture.read()
  if not ok:raise RuntimeError("sequential decode ended before declared frame count")
  if index not in wanted:continue
  try:
   gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY);grad=cv2.magnitude(cv2.Sobel(gray,cv2.CV_32F,1,0,ksize=3),cv2.Sobel(gray,cv2.CV_32F,0,1,ksize=3));edges=cv2.Canny(gray,50,150,apertureSize=3,L2gradient=True);det=cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(gray)[0];seed=MAPS[index];conditions=[]
   for rung in RUNGS:
    t=np.array([[1.,0.,rung],[0.,1.,0.],[0.,0.,1.]]);h=np.linalg.inv(t@np.linalg.inv(seed));conditions.append({{"rung_px":rung,"offset":offset(edges,h),"image_signals":image_signals(gray,grad,det,h),"quad":quad(h,seed)}})
   records.append({{"source_frame":index,"image_sha256":hashlib.sha256(image.tobytes()).hexdigest(),"conditions":conditions}})
  except Exception as exc:records.append({{"source_frame":index,"error":str(exc)}})
finally:capture.release()
if {{row["source_frame"] for row in records}}!=wanted:raise RuntimeError("not every sealed frame was decoded")
out=os.path.join(WORK,"g260_measurement.json");report={{"video":{{"path":VIDEO,"bytes":os.stat(VIDEO).st_size,"resolution":[1920,1080],"declared_frames":COUNT}},"decode":"one sequential cv2.VideoCapture pass; each sealed source frame decoded once and reused in memory for all rungs","source_frames":FRAMES,"rungs_px":list(RUNGS),"records":records}};open(out,"w",encoding="ascii").write(json.dumps(report,indent=2,allow_nan=False)+"\\n");print(json.dumps({{"temp_dir":WORK,"artifact_bytes":os.path.getsize(out)}}))
'''


def disk_guard(ssh_config: Path, ssh_host: str) -> dict[str, int]:
    """Run G260's required authoritative write probe before the worker starts."""
    command = "set -e; du -sm /workspace/nba-ai-system/data; dd if=/dev/zero of=/workspace/nba-ai-system/g260_disk_probe.bin bs=1M count=1 conv=fsync status=none; wc -c < /workspace/nba-ai-system/g260_disk_probe.bin; rm -f /workspace/nba-ai-system/g260_disk_probe.bin"
    done = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if done.returncode:
        raise RuntimeError(done.stderr.decode("ascii", "replace"))
    rows = done.stdout.decode("ascii", "replace").splitlines()
    return {"data_megabytes": int(rows[0].split()[0]), "probe_bytes_removed": int(rows[1])}


def _value(condition: dict[str, object], signal: str) -> float | None:
    if signal == "offset_p90_px":
        return condition["offset"]["p90"]
    if signal.startswith("quad_"):
        return float(condition["quad"][signal.removeprefix("quad_")])
    return float(condition["image_signals"][signal])


def _pair_summary(pairs: list[dict[str, float | int]], exclusions: list[dict[str, object]]) -> dict[str, object]:
    values = np.asarray([float(pair["paired_difference"]) for pair in pairs], dtype=float)
    if not len(values):
        return {"n": 0, "median": None, "scaled_mad": None, "direction": "none", "strict_sign_count": 0,
                "pair_effect_pass": False, "exclusion_reasons": dict(Counter(row["reason"] for row in exclusions))}
    median = float(np.median(values)); mad = float(1.4826 * np.median(np.abs(values - median)))
    direction = "positive" if median > 0 else "negative" if median < 0 else "zero"
    signed = int(np.sum(values > 0)) if direction == "positive" else int(np.sum(values < 0)) if direction == "negative" else 0
    passed = bool(len(values) >= 30 and np.isfinite(mad) and mad > 0 and abs(median) >= 3 * mad and signed / len(values) >= 0.8)
    return {"n": int(len(values)), "median": median, "scaled_mad": mad, "direction": direction,
            "strict_sign_count": signed, "pair_effect_pass": passed,
            "exclusion_reasons": dict(Counter(row["reason"] for row in exclusions))}


def analyze(report: dict[str, object]) -> dict[str, object]:
    """Apply G260's sealed paired-spread declaration without fitting a gate."""
    output: dict[str, object] = {"detection_rule": preregistration()["detection_criterion_before_measurement"], "signals": {}}
    for signal in SIGNALS:
        rungs: dict[int, dict[str, object]] = {}
        for rung in RUNGS[1:]:
            pairs: list[dict[str, float | int]] = []; excluded: list[dict[str, object]] = []
            for row in report["records"]:
                frame = int(row["source_frame"])
                if "error" in row:
                    excluded.append({"source_frame": frame, "reason": "frame_measurement_error"}); continue
                conditions = {int(item["rung_px"]): item for item in row["conditions"]}
                base, moved = conditions[0], conditions[rung]
                if signal == "offset_p90_px" and (base["offset"]["p90"] is None or moved["offset"]["p90"] is None):
                    excluded.append({"source_frame": frame, "reason": "offset_no_found_candidate"}); continue
                if signal == "offset_p90_px" and (float(base["offset"]["p90"]) >= 24 or float(moved["offset"]["p90"]) >= 24):
                    excluded.append({"source_frame": frame, "reason": "offset_p90_censored_at_24px"}); continue
                left, right = _value(base, signal), _value(moved, signal)
                if left is None or right is None or not np.isfinite(left) or not np.isfinite(right):
                    excluded.append({"source_frame": frame, "reason": "nonfinite_or_undefined_scalar"}); continue
                pairs.append({"source_frame": frame, "unperturbed": float(left), "displaced": float(right), "paired_difference": float(right-left)})
            summary = _pair_summary(pairs, excluded); summary["pairs"] = pairs; summary["excluded"] = excluded; rungs[rung] = summary
        medians = [rungs[rung]["median"] for rung in RUNGS[1:]]
        numeric = all(value is not None for value in medians)
        increasing = numeric and all(float(a) >= 0 and float(b) >= float(a) for a, b in zip(medians, medians[1:]))
        decreasing = numeric and all(float(a) <= 0 and float(b) <= float(a) for a, b in zip(medians, medians[1:]))
        monotone = bool(increasing or decreasing)
        smallest = next((rung for rung in RUNGS[1:] if monotone and rungs[rung]["pair_effect_pass"]), None)
        output["signals"][signal] = {"rungs": rungs, "full_ladder_monotone": monotone,
                                      "monotone_direction": "positive" if increasing else "negative" if decreasing else "none",
                                      "one_sided_gate_eligible": monotone, "smallest_reliably_detected_px": smallest}
    return output


def run(output_dir: Path, ssh_config: Path, ssh_host: str = "pod") -> dict[str, object]:
    """Stream the sealed experiment on the pod and remove its sole temporary artifact."""
    frames, matrices = matrices_for_sample(); guard = disk_guard(ssh_config, ssh_host)
    done = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, "python3 -"], input=_worker_source(frames, matrices).encode("ascii"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if done.returncode:
        raise RuntimeError(done.stderr.decode("ascii", "replace"))
    replies = [line for line in done.stdout.decode("ascii", "replace").splitlines() if line.startswith('{"temp_dir":')]
    if len(replies) != 1:
        raise RuntimeError("G260 worker did not return one result")
    remote = json.loads(replies[0]); temp = str(remote["temp_dir"])
    if not temp.startswith("/tmp/g260_pairs_"):
        raise RuntimeError("unexpected G260 temporary path")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["scp", "-F", str(ssh_config), f"{ssh_host}:{temp}/g260_measurement.json", str(output_dir)], check=True)
    finally:
        if subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, f"rm -rf -- {temp}"], check=False).returncode:
            raise RuntimeError("could not remove G260 temporary data")
    path = output_dir / "g260_measurement.json"; report = json.loads(path.read_text(encoding="ascii"))
    report.update({"disk_guard": guard, "remote_temp_bytes_removed": int(remote["artifact_bytes"]), "preregistration_sha256": sha256(PREREG),
                   "input_sha256": {"g247_measurement": sha256(G247), "g247_route": sha256(Path(g247.__file__)),
                                    "g248_route": sha256(Path(g248.__file__)), "g252_route": sha256(Path(g252.__file__)), "g260_route": sha256(Path(__file__))}})
    report["analysis"] = analyze(report); path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="ascii")
    return report


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output-dir", type=Path, required=True); parser.add_argument("--ssh-config", type=Path, required=True); parser.add_argument("--ssh-host", default="pod")
    args = parser.parse_args(); report = run(args.output_dir, args.ssh_config, args.ssh_host)
    print("G260_FRAMES=" + str(len(report["records"])))


if __name__ == "__main__":
    main()
