"""Measure fixed projection signals against a sealed synthetic displacement ladder."""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

from scripts.platformkit.tracking import g247_projected_quad_validity as g247
from scripts.platformkit.tracking import g248_projected_line_image_agreement as g248
from scripts.platformkit.tracking import g252_projection_accuracy_in_pixels as g252

ROOT = Path(__file__).resolve().parents[3]
VIDEO = "/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4"
FRAME = 19599
RUNGS = (0, 2, 5, 10, 20, 40, 100)
REPEATS = 5
G247 = ROOT / "docs/evidence/tracking/g247_projected_quad_validity_artifact/g247_measurement.json"
PREREG = ROOT / "docs/evidence/tracking/g258_synthetic_truth_validity_artifact/g258_preregistration.json"
FLOORS = {"offset_p90_px": 1.0, "edge_response_contrast": 1.0, "marking_contrast": 1.0,
          "line_detector_agreement": 0.01, "coverage": 0.01, "quad_projected_area_ratio_to_seed": 0.01,
          "quad_bbox_aspect_ratio": 0.01, "quad_outside_corner_fraction": 0.01}


def sha256(path: Path) -> str:
    """Return a file SHA-256 hex digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_matrix(path: Path = G247) -> np.ndarray:
    """Load the sole persisted G247 image-to-court matrix for frame 19599."""
    report = json.loads(path.read_text(encoding="ascii"))
    rows = [row for row in report["records"] if int(row["source_frame"]) == FRAME]
    if len(rows) != 1:
        raise ValueError("G258 requires exactly one persisted G247 seed record")
    return np.asarray(rows[0]["homography_image_to_court"], dtype=np.float64)


def displaced_image_to_court(homography: np.ndarray, pixels: float) -> np.ndarray:
    """Apply G257's P_N=T(N,0)P definition and return its inverse map."""
    projection = np.linalg.inv(homography)
    translate = np.array([[1.0, 0.0, pixels], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    return np.linalg.inv(translate @ projection)


def _worker_source(matrix: np.ndarray) -> str:
    payload = base64.b64encode(json.dumps(matrix.tolist()).encode("ascii")).decode("ascii")
    lines = base64.b64encode(json.dumps(g248.court_line_geometry()).encode("ascii")).decode("ascii")
    typed = base64.b64encode(json.dumps(g252.court_line_geometry()).encode("ascii")).decode("ascii")
    return f'''import base64, hashlib, json, math, os, subprocess, tempfile
import cv2
import numpy as np
VIDEO={VIDEO!r}; FRAME={FRAME}; RUNGS={RUNGS!r}; REPEATS={REPEATS}; H=np.asarray(json.loads(base64.b64decode({payload!r})),dtype=np.float64)
LINES=json.loads(base64.b64decode({lines!r})); TYPED=json.loads(base64.b64decode({typed!r})); WORK=tempfile.mkdtemp(prefix="g258_ladder_")
def exact():
 c=["ffmpeg","-v","error","-i",VIDEO,"-vf","select=eq(n\\,"+str(FRAME)+")","-vsync","0","-frames:v","1","-f","rawvideo","-pix_fmt","bgr24","pipe:1"]
 raw=subprocess.run(c,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
 if len(raw)!=1920*1080*3: raise RuntimeError("unexpected exact frame bytes")
 return np.frombuffer(raw,dtype=np.uint8).reshape(1080,1920,3).copy()
def clip(a,b,w,h):
 d=b-a; lo,hi=0.,1.
 for p,q in ((-d[0],a[0]),(d[0],w-1-a[0]),(-d[1],a[1]),(d[1],h-1-a[1])):
  if abs(p)<1e-12:
   if q<0:return None
  elif p<0:lo=max(lo,q/p)
  else:hi=min(hi,q/p)
 return None if lo>hi else (a+lo*d,b+hi*d)
def bilinear(img,pts):
 return cv2.remap(img,pts[:,0].astype(np.float32),pts[:,1].astype(np.float32),cv2.INTER_LINEAR).reshape(-1)
def generic(h,w,ht):
 inv=np.linalg.inv(h); pts=[]; tan=[]; total=inside=0.
 for raw in LINES:
  curve=cv2.perspectiveTransform(np.asarray(raw,np.float32).reshape(1,-1,2),inv)[0]
  for a,b in zip(curve[:-1],curve[1:]):
   d=b-a; length=float(np.linalg.norm(d))
   if not np.isfinite(length) or length<=1e-6:continue
   total+=length; hit=clip(a,b,w,ht)
   if hit is None:continue
   first,last=hit; cl=float(np.linalg.norm(last-first))
   if cl<=1e-6:continue
   inside+=cl; n=max(1,int(math.ceil(cl/2.))); f=(np.arange(n)+.5)/n
   pts.append(first+f[:,None]*(last-first));tan.append(np.repeat((d/length)[None,:],n,axis=0))
 if not pts:raise RuntimeError("no projected geometry")
 return np.concatenate(pts),np.concatenate(tan),inside/total
def offset(img,h):
 gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY); ed=cv2.Canny(gray,50,150,apertureSize=3,L2gradient=True); ht,w=gray.shape; inv=np.linalg.inv(h); ds=[]; samples=missing=0; radii=np.arange(-24,25,dtype=float)
 for _,raw in TYPED:
  curve=cv2.perspectiveTransform(np.asarray(raw,np.float32).reshape(1,-1,2),inv)[0]
  for a,b in zip(curve[:-1],curve[1:]):
   d=b-a; length=float(np.linalg.norm(d)); hit=clip(a,b,w,ht)
   if not np.isfinite(length) or length<=1e-6 or hit is None:continue
   first,last=hit; cl=float(np.linalg.norm(last-first))
   if cl<=1e-6:continue
   n=max(1,int(math.ceil(cl/4.))); f=(np.arange(n)+.5)/n; p=first+f[:,None]*(last-first); normal=np.array([-d[1],d[0]])/length
   xy=p[:,None,:]+radii[None,:,None]*normal; x=np.rint(xy[:,:,0]).astype(int); y=np.rint(xy[:,:,1]).astype(int); keep=(x>=0)&(x<w)&(y>=0)&(y<ht); hitmask=np.zeros(keep.shape,bool);hitmask[keep]=ed[y[keep],x[keep]]>0
   found=hitmask.any(axis=1); samples+=n;missing+=int((~found).sum())
   if found.any():ds.extend(np.where(hitmask,np.abs(radii)[None,:],np.inf).min(axis=1)[found].tolist())
 order=np.sort(ds); return {{"sample_points":samples,"found":len(order),"no_candidate":missing,"median":float(np.median(order)) if len(order) else None,"p90":float(np.quantile(order,.9)) if len(order) else None,"max":float(order[-1]) if len(order) else None,"bound_count":int(np.sum(order>=24))}}
def image_signals(img,h):
 gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY); grad=cv2.magnitude(cv2.Sobel(gray,cv2.CV_32F,1,0,ksize=3),cv2.Sobel(gray,cv2.CV_32F,0,1,ksize=3)); ht,w=gray.shape; on,tangent,coverage=generic(h,w,ht); normal=np.column_stack((-tangent[:,1],tangent[:,0])); controls=[]
 for off in (3.,9.):
  for sign in (-1.,1.):
   p=on+sign*off*normal; controls.append(p[(p[:,0]>=0)&(p[:,0]<w)&(p[:,1]>=0)&(p[:,1]<ht)])
 control=np.concatenate(controls); det=cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(gray)[0]; mask=np.zeros(gray.shape,np.uint8);cs=np.zeros(gray.shape,np.float32);sn=np.zeros(gray.shape,np.float32);segments=0
 if det is not None:
  segments=len(det)
  for x1,y1,x2,y2 in det.reshape(-1,4):
   dx,dy=float(x2-x1),float(y2-y1); norm=math.hypot(dx,dy)
   if norm<=1e-6:continue
   co,si=dx/norm,dy/norm; a,b=(int(round(x1)),int(round(y1))),(int(round(x2)),int(round(y2)));cv2.line(mask,a,b,9,9,cv2.LINE_AA);cv2.line(cs,a,b,co,9,cv2.LINE_AA);cv2.line(sn,a,b,si,9,9,cv2.LINE_AA)
 agreed=0; cos=math.cos(math.radians(15))
 for p,v in zip(on,tangent):
  x,y=map(int,np.rint(p)); x0,x1=max(0,x-4),min(w,x+5);y0,y1=max(0,y-4),min(ht,y+5);near=mask[y0:y1,x0:x1]>0
  if near.any() and np.any(np.abs(v[0]*cs[y0:y1,x0:x1][near]+v[1]*sn[y0:y1,x0:x1][near])>=cos):agreed+=1
 return {{"edge_response_contrast":float(np.mean(bilinear(grad,on))-np.mean(bilinear(grad,control))),"line_detector_agreement":float(agreed/len(on)),"marking_contrast":float(np.mean(bilinear(gray,on))-np.mean(bilinear(gray,control))),"coverage":float(coverage),"on_curve_samples":int(len(on)),"control_samples":int(len(control)),"lsd_segments":segments}}
def quad(h):
 court=np.asarray([[17.,0.],[33.,0.],[17.,19.],[33.,19.]],np.float32).reshape(1,-1,2);corners=cv2.perspectiveTransform(court,np.linalg.inv(h))[0];p=corners[[0,1,3,2]];seed=cv2.perspectiveTransform(court,np.linalg.inv(H))[0][[0,1,3,2]];cross=np.cross(np.roll(p,-1,axis=0)-p,np.roll(np.roll(p,-1,axis=0)-p,-1,axis=0));area=float(.5*np.sum(p[:,0]*np.roll(p[:,1],-1)-p[:,1]*np.roll(p[:,0],-1)));seed_area=float(.5*np.sum(seed[:,0]*np.roll(seed[:,1],-1)-seed[:,1]*np.roll(seed[:,0],-1)));convex=bool(np.all(np.abs(cross)>1e-9) and (np.all(cross>0) or np.all(cross<0)));inv=bool(area*seed_area<0);return {{"is_convex":convex,"signed_area_px2":area,"winding_inverted_relative_seed":inv,"corner_order_consistent_with_seed":bool(convex and np.unique(np.round(p,9),axis=0).shape[0]==4 and not inv),"projected_area_ratio_to_seed":abs(area)/abs(seed_area),"bbox_aspect_ratio":float((p[:,0].max()-p[:,0].min())/(p[:,1].max()-p[:,1].min())),"outside_corner_fraction":float(np.mean((p[:,0]<0)|(p[:,0]>=1920)|(p[:,1]<0)|(p[:,1]>=1080))),"homography_condition_number":float(np.linalg.cond(h/h[2,2])),"corners_px_role_order":corners.tolist()}}
records=[]
for repeat in range(REPEATS):
 img=exact(); conditions=[]
 for n in RUNGS:
  t=np.array([[1.,0.,n],[0.,1.,0.],[0.,0.,1.]]);hn=np.linalg.inv(t@np.linalg.inv(H));conditions.append({{"rung_px":n,"offset":offset(img,hn),"image_signals":image_signals(img,hn),"quad":quad(hn)}})
 records.append({{"repeat":repeat,"image_sha256":hashlib.sha256(img.tobytes()).hexdigest(),"conditions":conditions}})
out=os.path.join(WORK,"g258_measurement.json");report={{"video":{{"path":VIDEO,"bytes":os.stat(VIDEO).st_size,"resolution":[1920,1080]}},"source_frame":FRAME,"repeats":REPEATS,"rungs_px":list(RUNGS),"records":records}};open(out,"w",encoding="ascii").write(json.dumps(report,indent=2,allow_nan=False)+"\\n");print(json.dumps({{"temp_dir":WORK,"artifact_bytes":os.path.getsize(out)}}))
'''


def disk_guard(ssh_config: Path, ssh_host: str) -> dict[str, int]:
    """Probe pod disk with fsync before the remote worker creates output."""
    command = "set -e; du -sm /workspace/nba-ai-system/data; dd if=/dev/zero of=/workspace/nba-ai-system/g258_worker_probe.bin bs=1M count=1 conv=fsync status=none; wc -c < /workspace/nba-ai-system/g258_worker_probe.bin; rm -f /workspace/nba-ai-system/g258_worker_probe.bin"
    done = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if done.returncode:
        raise RuntimeError(done.stderr.decode("ascii", "replace"))
    lines = done.stdout.decode("ascii", "replace").splitlines()
    return {"data_megabytes": int(lines[0].split()[0]), "probe_bytes_removed": int(lines[1])}


def _rank(values: list[float]) -> np.ndarray:
    order = np.argsort(values); ranks = np.empty(len(values), dtype=float); ranks[order] = np.arange(len(values), dtype=float)
    for value in set(values):
        indices = np.flatnonzero(np.asarray(values) == value); ranks[indices] = float(np.mean(ranks[indices]))
    return ranks


def _scalar(condition: dict[str, object], name: str) -> float:
    if name == "offset_p90_px":
        return float(condition["offset"]["p90"])
    if name.startswith("quad_"):
        return float(condition["quad"][name.removeprefix("quad_")])
    return float(condition["image_signals"][name])


def analyze(report: dict[str, object]) -> dict[str, object]:
    """Apply the sealed repeat-spread detection declaration without fitting a classifier."""
    grouped = {n: [] for n in RUNGS}
    for row in report["records"]:
        for condition in row["conditions"]:
            grouped[int(condition["rung_px"])].append(condition)
    result: dict[str, object] = {"detection_rule": "sealed g258_preregistration.json", "signals": {}}
    for name, floor in FLOORS.items():
        values = {n: [_scalar(row, name) for row in grouped[n]] for n in RUNGS}; control = values[0]
        baseline = float(np.median(control)); spread = max(control) - min(control); rows = []
        for n in RUNGS:
            median = float(np.median(values[n])); delta = median - baseline; outside = all(v > max(control) for v in values[n]) or all(v < min(control) for v in values[n])
            saturated = name == "offset_p90_px" and any(float(row["offset"]["p90"]) >= g252.SEARCH_RADIUS_PX for row in grouped[n])
            rows.append({"rung_px": n, "repeat_values": values[n], "median": median, "delta_from_control": delta, "saturated": saturated,
                         "detected": bool(n and not saturated and abs(delta) > max(3.0 * spread, floor) and outside)})
        medians = [row["median"] for row in rows]; rho = float(np.corrcoef(_rank(list(RUNGS)), _rank(medians))[0, 1])
        detected = next((row["rung_px"] for row in rows if row["detected"]), None)
        result["signals"][name] = {"control_median": baseline, "control_range": spread, "floor": floor, "spearman_rho": rho,
                                   "nondecreasing": all(a <= b for a, b in zip(medians, medians[1:])), "smallest_detected_px": detected, "rungs": rows}
    return result


def run(output_dir: Path, ssh_config: Path, ssh_host: str = "pod") -> dict[str, object]:
    """Run the sealed one-frame ladder and remove the pod temporary artifact."""
    guard = disk_guard(ssh_config, ssh_host)
    done = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, "python3 -"], input=_worker_source(seed_matrix()).encode("ascii"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if done.returncode:
        raise RuntimeError(done.stderr.decode("ascii", "replace"))
    lines = [line for line in done.stdout.decode("utf-8", "replace").splitlines() if line.startswith('{"temp_dir":')]
    if len(lines) != 1:
        raise RuntimeError("G258 worker did not return one result")
    remote = json.loads(lines[0]); temp = str(remote["temp_dir"])
    if not temp.startswith("/tmp/g258_ladder_"):
        raise RuntimeError("unexpected G258 temporary path")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["scp", "-F", str(ssh_config), f"{ssh_host}:{temp}/g258_measurement.json", str(output_dir)], check=True)
    finally:
        if subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, f"rm -rf -- {temp}"], check=False).returncode:
            raise RuntimeError("could not remove G258 pod temporary data")
    path = output_dir / "g258_measurement.json"; report = json.loads(path.read_text(encoding="ascii"))
    report.update({"disk_guard": guard, "remote_temp_bytes_removed": int(remote["artifact_bytes"]), "preregistration_sha256": sha256(PREREG),
                   "input_sha256": {"g247_measurement": sha256(G247), "g248_route": sha256(Path(g248.__file__)), "g252_route": sha256(Path(g252.__file__)), "g247_route": sha256(Path(g247.__file__)), "g258_route": sha256(Path(__file__))}})
    report["analysis"] = analyze(report); path.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    return report


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output-dir", type=Path, required=True); parser.add_argument("--ssh-config", type=Path, required=True); parser.add_argument("--ssh-host", default="pod")
    args = parser.parse_args(); report = run(args.output_dir, args.ssh_config, args.ssh_host)
    print("G258_REPEATS=" + str(len(report["records"])))


if __name__ == "__main__":
    main()
