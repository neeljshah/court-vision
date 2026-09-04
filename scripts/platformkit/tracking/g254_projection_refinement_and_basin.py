"""Refine one published court matrix against Canny edges and measure its basin."""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

from scripts.platformkit.tracking import g252_projection_accuracy_in_pixels as g252


ROOT = Path(__file__).resolve().parents[3]
VIDEO = "/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4"
FRAME = 19599
WIDTH, HEIGHT = 1920, 1080
SEED = ROOT / "docs/evidence/tracking/g233d_seed_gate_validated_frame_artifact/g233d_measurement.json"
RADIUS = g252.SEARCH_RADIUS_PX
GRID_P95_PX = 2.0
INITIAL_STEPS = (8.0, 8.0, 0.75, 0.005)
MIN_STEPS = (0.0625, 0.0625, 0.005859375, 0.0000390625)


def perturbations() -> list[dict[str, object]]:
    """Return the fixed, pre-scoring translate/rotate/scale basin grid."""
    rows: list[dict[str, object]] = [{"name": "identity", "family": "identity", "tx": 0.0, "ty": 0.0, "degrees": 0.0, "scale": 1.0}]
    for axis in ("x", "y"):
        for sign in (-1.0, 1.0):
            for pixels in (8.0, 16.0, 32.0, 64.0):
                rows.append({"name": f"translate_{axis}_{sign:+.0f}_{pixels:.0f}", "family": "translation", "tx": sign * pixels if axis == "x" else 0.0, "ty": sign * pixels if axis == "y" else 0.0, "degrees": 0.0, "scale": 1.0})
    for degrees in (-8.0, -4.0, -2.0, -1.0, -0.5, 0.5, 1.0, 2.0, 4.0, 8.0):
        rows.append({"name": f"rotation_{degrees:+.1f}", "family": "rotation", "tx": 0.0, "ty": 0.0, "degrees": degrees, "scale": 1.0})
    for scale in (0.90, 0.95, 0.975, 1.025, 1.05, 1.10):
        rows.append({"name": f"scale_{scale:.3f}", "family": "scale", "tx": 0.0, "ty": 0.0, "degrees": 0.0, "scale": scale})
    for sign in (-1.0, 1.0):
        for pixels, degrees, scale_delta in ((8.0, 0.5, 0.01), (16.0, 1.0, 0.02), (32.0, 2.0, 0.04), (64.0, 4.0, 0.08), (96.0, 6.0, 0.12)):
            rows.append({"name": f"joint_{sign:+.0f}_{pixels:.0f}", "family": "joint", "tx": sign * pixels, "ty": sign * pixels, "degrees": sign * degrees, "scale": 1.0 + sign * scale_delta})
    return rows


def _worker_source(seed_h: list[list[float]]) -> str:
    geometry = base64.b64encode(json.dumps(g252.court_line_geometry(), separators=(",", ":")).encode("ascii")).decode("ascii")
    grid = base64.b64encode(json.dumps(perturbations(), separators=(",", ":")).encode("ascii")).decode("ascii")
    return f'''import base64, hashlib, json, math, os, subprocess, tempfile
import cv2
import numpy as np
VIDEO={VIDEO!r}; FRAME={FRAME}; WIDTH={WIDTH}; HEIGHT={HEIGHT}; RADIUS={RADIUS}; SPACING={g252.SAMPLE_SPACING_PX}; LOW={g252.CANNY_LOW}; HIGH={g252.CANNY_HIGH}
SEED=np.asarray({seed_h!r},dtype=np.float64); GEOMETRY=json.loads(base64.b64decode({geometry!r})); PERTURBATIONS=json.loads(base64.b64decode({grid!r})); LINE_TYPES={g252.LINE_TYPES!r}
INITIAL=np.array({INITIAL_STEPS!r},dtype=np.float64); MINIMUM=np.array({MIN_STEPS!r},dtype=np.float64); LIMIT=np.array([192.0,192.0,12.0,0.20],dtype=np.float64)
def clip(a,b):
    delta=b-a; low,high=0.0,1.0
    for p,q in ((-delta[0],a[0]),(delta[0],WIDTH-1-a[0]),(-delta[1],a[1]),(delta[1],HEIGHT-1-a[1])):
        if abs(p)<1e-12:
            if q<0: return None
        elif p<0: low=max(low,q/p)
        else: high=min(high,q/p)
    return None if low>high else (a+low*delta,b+high*delta)
def similarity(params):
    tx,ty,degrees,log_scale=params; scale=math.exp(float(log_scale)); angle=math.radians(float(degrees)); c,s=math.cos(angle),math.sin(angle); cx,cy=WIDTH/2.0,HEIGHT/2.0
    return np.array([[scale*c,-scale*s,cx+tx-scale*c*cx+scale*s*cy],[scale*s,scale*c,cy+ty-scale*s*cx-scale*c*cy],[0.0,0.0,1.0]],dtype=np.float64)
def matrix(params): return np.linalg.inv(similarity(params)@np.linalg.inv(SEED))
def samples(h, normals=False):
    forward=np.linalg.inv(h); out={{kind:[] for kind in LINE_TYPES}}; normal_out={{kind:[] for kind in LINE_TYPES}}
    for kind,raw in GEOMETRY:
        curve=np.asarray(raw,dtype=np.float32); projected=cv2.perspectiveTransform(curve.reshape(1,-1,2),forward)[0]
        for a,b in zip(projected[:-1],projected[1:]):
            delta=b-a; length=float(np.linalg.norm(delta))
            if not np.isfinite(length) or length<=1e-6: continue
            segment=clip(a,b)
            if segment is None: continue
            first,last=segment; clipped=last-first; clipped_length=float(np.linalg.norm(clipped))
            if clipped_length<=1e-6: continue
            count=max(1,int(math.ceil(clipped_length/SPACING))); fraction=(np.arange(count,dtype=np.float64)+0.5)/count; out[kind].append(first+fraction[:,None]*clipped)
            if normals: normal_out[kind].append(np.repeat(np.array([[-delta[1]/length,delta[0]/length]]),count,axis=0))
    packed={{kind:(np.concatenate(parts) if parts else np.empty((0,2),dtype=np.float64)) for kind,parts in out.items()}}
    return (packed,{{kind:(np.concatenate(parts) if parts else np.empty((0,2),dtype=np.float64)) for kind,parts in normal_out.items()}}) if normals else packed
def normal_offsets(edges,points,normals):
    radii=np.arange(-RADIUS,RADIUS+1,dtype=np.float64); found=np.full(len(points),np.nan,dtype=np.float64)
    for start in range(0,len(points),12000):
        end=min(start+12000,len(points)); coords=points[start:end,None,:]+radii[None,:,None]*normals[start:end,None,:]; xs=np.rint(coords[:,:,0]).astype(np.int32); ys=np.rint(coords[:,:,1]).astype(np.int32); keep=(xs>=0)&(xs<WIDTH)&(ys>=0)&(ys<HEIGHT); hit=np.zeros(keep.shape,dtype=bool); hit[keep]=edges[ys[keep],xs[keep]]>0; any_hit=hit.any(axis=1)
        if any_hit.any(): found[start:end][any_hit]=np.where(hit,np.abs(radii)[None,:],np.inf).min(axis=1)[any_hit]
    return found
def measure(h,edges):
    point_map,normal_map=samples(h,True); out={{}}
    for kind in LINE_TYPES:
        distances=normal_offsets(edges,point_map[kind],normal_map[kind]); values=distances[np.isfinite(distances)]; out[kind]={{"sample_points":int(len(distances)),"no_candidate":int(len(distances)-len(values)),"distances_px":[float(x) for x in values]}}
    return out
def summary(rows):
    values=[]; total=missing=0
    for item in rows.values(): values.extend(item["distances_px"]); total+=item["sample_points"]; missing+=item["no_candidate"]
    def one(xs):
        return {{"sample_points":total if xs is values else 0,"found":len(xs),"no_candidate":missing if xs is values else 0,"median":None if not xs else float(np.median(xs)),"p90":None if not xs else float(np.quantile(xs,.9)),"max":None if not xs else float(max(xs))}}
    out={{kind:{{"sample_points":item["sample_points"],"found":len(item["distances_px"]),"no_candidate":item["no_candidate"],"median":None if not item["distances_px"] else float(np.median(item["distances_px"])),"p90":None if not item["distances_px"] else float(np.quantile(item["distances_px"],.9)),"max":None if not item["distances_px"] else float(max(item["distances_px"]))}} for kind,item in rows.items()}}; out["pooled"]=one(values); return out
def optimise(start,distances):
    cache={{}}; evaluations=0
    def objective(params):
        nonlocal evaluations; key=tuple(np.round(params,12))
        if key in cache: return cache[key]
        try: point_map=samples(matrix(params)); means=[]
        except (np.linalg.LinAlgError,cv2.error): return float("inf")
        for kind,points in point_map.items():
            if len(points):
                xs=np.rint(points[:,0]).astype(np.int32); ys=np.rint(points[:,1]).astype(np.int32); keep=(xs>=0)&(xs<WIDTH)&(ys>=0)&(ys<HEIGHT); means.append(float(np.mean(np.minimum(distances[ys[keep],xs[keep]],RADIUS)**2)) if keep.any() else float(RADIUS**2))
        value=float(np.mean(means)) if means else float("inf"); cache[key]=value; evaluations+=1; return value
    current=np.asarray(start,dtype=np.float64); value=objective(current); steps=INITIAL.copy(); iterations=0
    while np.any(steps>MINIMUM) and iterations<240:
        choices=[]
        for index in range(4):
            for sign in (-1.0,1.0):
                candidate=current.copy(); candidate[index]+=sign*steps[index]
                if abs(candidate[index])<=LIMIT[index]: choices.append((objective(candidate),index,sign,candidate))
        best=min(choices,key=lambda row: (row[0],row[1],row[2]))
        if best[0] < value-1e-9: value,current=best[0],best[3]
        else: steps=steps/2.0
        iterations+=1
    return current,value,evaluations,iterations,steps
def discrepancy(reference,candidate):
    xs=np.arange(0.0,50.0001,5.0); ys=np.arange(0.0,94.0001,5.0); court=np.array([[x,y] for x in xs for y in ys],dtype=np.float32).reshape(1,-1,2); ref=cv2.perspectiveTransform(court,np.linalg.inv(reference))[0]; trial=cv2.perspectiveTransform(court,np.linalg.inv(candidate))[0]; keep=np.isfinite(ref).all(axis=1)&np.isfinite(trial).all(axis=1)&(ref[:,0]>=0)&(ref[:,0]<WIDTH)&(ref[:,1]>=0)&(ref[:,1]<HEIGHT); values=np.linalg.norm(ref[keep]-trial[keep],axis=1); return {{"points":int(keep.sum()),"p95_px":None if not len(values) else float(np.quantile(values,.95)),"max_px":None if not len(values) else float(values.max())}}
def overlay(image,h):
    canvas=image.copy(); forward=np.linalg.inv(h)
    for _,raw in GEOMETRY:
        curve=np.asarray(raw,dtype=np.float32); pts=cv2.perspectiveTransform(curve.reshape(1,-1,2),forward)[0]; finite=pts[np.isfinite(pts).all(axis=1)]
        if len(finite)>1: cv2.polylines(canvas,[np.rint(finite).astype(np.int32)],False,(0,255,0),2,cv2.LINE_AA)
    cv2.putText(canvas,"G254 refined matrix; independent geometry gate",(30,50),cv2.FONT_HERSHEY_SIMPLEX,0.9,(0,255,0),2,cv2.LINE_AA); return canvas
work=tempfile.mkdtemp(prefix="g254_refine_")
try:
    command=["ffmpeg","-v","error","-i",VIDEO,"-vf",f"select=eq(n\\,{{FRAME}})","-vsync","0","-frames:v","1","-f","rawvideo","-pix_fmt","bgr24","pipe:1"]
    raw=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
    if len(raw)!=WIDTH*HEIGHT*3: raise RuntimeError("frame-exact decode did not produce one native BGR frame")
    image=np.frombuffer(raw,dtype=np.uint8).reshape(HEIGHT,WIDTH,3); edges=cv2.Canny(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY),LOW,HIGH,apertureSize=3,L2gradient=True); distance=cv2.distanceTransform((edges==0).astype(np.uint8),cv2.DIST_L2,3)
    base,base_objective,base_evals,base_iters,base_steps=optimise([0.0,0.0,0.0,0.0],distance); refined=matrix(base); before=measure(SEED,edges); after=measure(refined,edges)
    basin=[]
    for row in PERTURBATIONS:
        start=np.array([row["tx"],row["ty"],row["degrees"],math.log(row["scale"])],dtype=np.float64); params,value,evaluations,iterations,steps=optimise(start,distance); candidate=matrix(params); delta=discrepancy(refined,candidate); basin.append(dict(row,final_params=[float(x) for x in params],objective=value,evaluations=evaluations,iterations=iterations,final_steps=[float(x) for x in steps],discrepancy=delta,same_answer=bool(delta["p95_px"] is not None and delta["p95_px"]<=2.0)))
    report={{"source":{{"path":VIDEO,"bytes":os.stat(VIDEO).st_size,"resolution":[WIDTH,HEIGHT],"frame":FRAME,"frame_bgr_sha256":hashlib.sha256(raw).hexdigest(),"decode":"ffmpeg select=eq(n,19599), -vsync 0, native bgr24 pipe; no input-side seek or retained decode"}},"seed_image_to_court":SEED.tolist(),"method":{{"reporting":"G252 exact 4-px curve samples; Canny 50/150, 3x3, L2; integer normal search [-24,+24]","objective":"mean across visible line types of squared min(Canny distance-transform distance, 24 px); no labels enter","optimiser":"deterministic four-coordinate pattern search over image-space tx, ty, degrees, log-scale; fixed initial/minimum steps and bounds","same_answer":"5-ft court grid, reference-refined in-image points, p95 projected discrepancy <= 2 px"}},"refinement":{{"params":[float(x) for x in base],"objective":base_objective,"evaluations":base_evals,"iterations":base_iters,"final_steps":[float(x) for x in base_steps],"matrix_image_to_court":refined.tolist()}},"offsets":{{"before":{{"raw":before,"summary":summary(before)}},"after":{{"raw":after,"summary":summary(after)}}}},"perturbations":basin,"environment":{{"python":os.sys.version,"opencv":cv2.__version__}}}}
    artifact=os.path.join(work,"g254_measurement.json"); render=os.path.join(work,"refined_overlay.jpg"); open(artifact,"w",encoding="ascii").write(json.dumps(report,indent=2,allow_nan=False)+"\\n"); cv2.imwrite(render,overlay(image,refined),[cv2.IMWRITE_JPEG_QUALITY,95]); print(json.dumps({{"temp_dir":work,"artifact_bytes":os.path.getsize(artifact),"render_bytes":os.path.getsize(render)}}))
except Exception as exc:
    failure=os.path.join(work,"failure.txt"); open(failure,"w",encoding="ascii").write(repr(exc)); print(json.dumps({{"temp_dir":work,"error":repr(exc),"failure_bytes":os.path.getsize(failure)}}))
'''


def disk_guard(ssh_config: Path, ssh_host: str) -> dict[str, int]:
    """Run the required authoritative pod fsync probe immediately before output."""
    command = "set -e; du -sm /workspace/nba-ai-system/data; dd if=/dev/zero of=/workspace/nba-ai-system/g254_disk_probe.bin bs=1M count=1 conv=fsync status=none; wc -c < /workspace/nba-ai-system/g254_disk_probe.bin; rm -f /workspace/nba-ai-system/g254_disk_probe.bin"
    done = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if done.returncode:
        raise RuntimeError(done.stderr.decode("ascii", "replace"))
    rows = done.stdout.decode("ascii", "replace").splitlines()
    return {"data_megabytes": int(rows[0].split()[0]), "probe_bytes_removed": int(rows[1])}


def run(output_dir: Path, ssh_config: Path, ssh_host: str = "pod") -> dict[str, object]:
    """Run the one-frame worker, collect final evidence, and clean its pod directory."""
    seed = json.loads(SEED.read_text(encoding="ascii"))["seed_homography_image_to_court"]
    guard = disk_guard(ssh_config, ssh_host)
    done = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, "python3 -"], input=_worker_source(seed).encode("ascii"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if done.returncode:
        raise RuntimeError(done.stderr.decode("ascii", "replace"))
    replies = [json.loads(line) for line in done.stdout.decode("utf-8", "replace").splitlines() if line.startswith('{"temp_dir":')]
    if len(replies) != 1 or not str(replies[0]["temp_dir"]).startswith("/tmp/g254_refine_"):
        raise RuntimeError("remote worker did not return one expected temporary directory")
    remote = replies[0]; temp_dir = str(remote["temp_dir"]); output_dir.mkdir(parents=True, exist_ok=True)
    try:
        if "error" in remote:
            raise RuntimeError("G254 remote worker: " + str(remote["error"]))
        for name in ("g254_measurement.json", "refined_overlay.jpg"):
            subprocess.run(["scp", "-F", str(ssh_config), f"{ssh_host}:{temp_dir}/{name}", str(output_dir)], check=True)
    finally:
        cleanup = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, f"rm -rf -- {temp_dir}"], check=False)
        if cleanup.returncode:
            raise RuntimeError("pod temporary cleanup failed")
    path = output_dir / "g254_measurement.json"; report = json.loads(path.read_text(encoding="ascii"))
    report["disk_guard"] = guard
    report["remote_temp_bytes_removed"] = int(remote["artifact_bytes"]) + int(remote["render_bytes"])
    report["input_sha256"] = {"g233d_measurement": hashlib.sha256(SEED.read_bytes()).hexdigest(), "g252_route": hashlib.sha256(Path(g252.__file__).read_bytes()).hexdigest()}
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    return report


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ssh-config", type=Path, required=True)
    parser.add_argument("--ssh-host", default="pod")
    args = parser.parse_args()
    report = run(args.output_dir, args.ssh_config, args.ssh_host)
    print("G254_PERTURBATIONS=" + str(len(report["perturbations"])))


if __name__ == "__main__":
    main()
