"""G330 driver -- writes census.csv and proxies.csv from a read-only pod snapshot.

Usage:
    python -m scripts.platformkit.tracking.g330_run <workdir> <evidence_dir>

<workdir> holds, all copied DOWN from the read-only pod:
    pod_census.txt    lines 'sha256|bytes|mtime|path' for every pod panorama file
    ledger_stems.txt  one '<sport>__<game_id>' per ledgered pod tracking run
    <stem>.mp4        the sections named by the prereg selection rule
    armF_<stem>.png   the panorama the pod route actually used for that section
Nothing is written back to the pod and nothing under src/ is touched.
"""
from __future__ import annotations

import importlib.machinery
import os
import subprocess
import sys
import time
import types
from pathlib import Path

# The G330 row is CPU only by its spec. Hiding the device also keeps the route's
# `_warp_perspective` (src/tracking/rectify_court.py lines 16-31) on its cv2 branch, which is the
# branch whose output the pod's surviving per-clip panoramas match.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
os.environ.setdefault("COURTV_NO_LOFTR", "1")


def _shim_onnx():
    """Local-box workaround, not a G330 finding: this conda env pairs onnx with an ml_dtypes too
    old for it, so `import torchvision` (and therefore `from ultralytics import YOLO`) dies with
    AttributeError, which torch's guarded import does not catch. A stub module named onnx lets the
    guard fail as an ImportError instead. Nothing in this row uses onnx.
    ponytail: stub, not an env repair -- remove it once ml_dtypes is upgraded on this box.
    """
    if "onnx" in sys.modules:
        return
    stub = types.ModuleType("onnx")
    stub.__spec__ = importlib.machinery.ModuleSpec("onnx", None)
    stub.__getattr__ = lambda name: None
    sys.modules["onnx"] = stub


_shim_onnx()

from scripts.platformkit.tracking.g330_panorama_identity import (  # noqa: E402
    collisions, eval_frames, feet_from_boxes, frac, inside_court, local_census,
    match_frame, pad6, parse_census_line, build_arm_v, premise_holds, sha256_of,
    sift_reference,
)

STRIDE = 90
LIMIT = 40
CENSUS_COLS = "side,path,bytes,mtime,sha256,claimed_stem"
PROXY_COLS = ("section,arm,pano_source,pano_sha256,n_frames,feet_total,good_matches_total,"
              "inliers_total,inlier_ratio,valid_homography_frames,valid_homography_share,"
              "feet_evaluated,feet_inside,feet_inside_share,note")


def ffprobe_props(video: Path) -> str:
    """width x height and the container frame count, recorded, never a selection input."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,nb_frames", "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, timeout=120).stdout.strip()
        return out.replace(",", "x") or "unknown"
    except Exception:
        return "unknown"


def build_census(workdir: Path, repo: Path, evidence: Path):
    pod = [dict(parse_census_line(ln), side="pod")
           for ln in (workdir / "pod_census.txt").read_text().splitlines() if ln.strip()]
    loc = [dict(r, side="local") for r in local_census(repo)]
    rows = pod + loc
    lines = [CENSUS_COLS]
    for r in rows:
        lines.append("%s,%s,%s,%s,%s,%s" % (r["side"], r["path"], pad6(r["bytes"]),
                                            r["mtime"], r["sha256"], r["stem"]))
    (evidence / "census.csv").write_text("\n".join(lines) + "\n", encoding="ascii")
    return rows


def report_census(rows, workdir: Path):
    pod = [r for r in rows if r["side"] == "pod"]
    loc = [r for r in rows if r["side"] == "local"]
    print("CENSUS n_total=%s n_pod=%s n_local=%s distinct_sha=%s" % (
        pad6(len(rows)), pad6(len(pod)), pad6(len(loc)),
        pad6(len({r["sha256"] for r in rows}))))
    print("PREMISE", "TRUE" if premise_holds(rows) else "FALSE")
    general = [r for r in rows if r["stem"] == "-" and r["path"].endswith("pano_enhanced.png")]
    gen_sha = general[0]["sha256"] if general else ""
    for g in collisions(rows):
        tag = "IDENTICAL-TO-GENERAL-FALLBACK" if g["sha256"] == gen_sha else "IDENTICAL-PAIR"
        print("  group %s size=%s distinct_stems=%s bytes=%s %s" % (
            g["sha256"][:16], pad6(g["size"]), pad6(len(g["stems"])), pad6(g["bytes"]), tag))
    stems_path = workdir / "ledger_stems.txt"
    if stems_path.is_file() and gen_sha:
        ledgered = [s.strip() for s in stems_path.read_text().splitlines() if s.strip()]
        by_stem = {r["stem"]: r for r in rows if r["side"] == "pod" and r["stem"] != "-"}
        have = [s for s in ledgered if s in by_stem]
        fell = [s for s in have if by_stem[s]["sha256"] == gen_sha]
        print("LEDGER ledgered=%s with_pano_file=%s registered_against_general_fallback=%s" % (
            pad6(len(ledgered)), pad6(len(have)), frac(len(fell), len(have))))
    return gen_sha


def arm_row(section, arm, source, sha, frames, feet_per_frame, pano, note=""):
    """Run one arm over the shared frames and shared detector output."""
    import numpy as np
    from src.pipeline.unified_pipeline import UnifiedPipeline as _UP  # read-only import
    import cv2
    import src.pipeline.unified_pipeline as up
    M1 = np.load(Path("resources") / "Rectify1.npy")
    map_img = cv2.imread(str(Path("resources") / "2d_map.png"))
    map_h, map_w = (map_img.shape[:2] if map_img is not None else (500, 940))
    if not _UP._pano_valid(pano):
        note = (note + "; panorama fails the route validity gate").strip("; ")
    # The route pads the panorama with 100 black rows before SIFT (_load_pano lines 866, 877).
    pano = np.vstack((pano, np.zeros((100, pano.shape[1], 3), dtype=pano.dtype)))
    sift, kp1, des1 = sift_reference(pano)
    good_t = inl_t = valid = feet_eval = feet_in = 0
    for frame, feet in zip(frames, feet_per_frame):
        good, inl, M = match_frame(frame, sift, kp1, des1)
        good_t += good
        inl_t += inl
        if M is None or inl < up._H_MIN_INLIERS:
            continue
        valid += 1
        feet_eval += len(feet)
        feet_in += inside_court(feet, M, M1, map_w, map_h)
    feet_total = sum(len(f) for f in feet_per_frame)
    return ("%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s" % (
        section, arm, source, sha, pad6(len(frames)), pad6(feet_total), pad6(good_t),
        pad6(inl_t), frac(inl_t, good_t), pad6(valid), frac(valid, len(frames)),
        pad6(feet_eval), pad6(feet_in), frac(feet_in, feet_eval), note))


def run_section(workdir: Path, stem: str, model, out_lines):
    video = workdir / ("%s.mp4" % stem)
    armf = workdir / ("armF_%s.png" % stem)
    import cv2
    print("SECTION %s props=%s" % (stem, ffprobe_props(video)))
    frames = eval_frames(video, STRIDE, LIMIT)
    feet_per_frame = []
    for frame in frames:
        res = list(model(frame, classes=[0], conf=0.3, verbose=False, imgsz=640,
                         device="cpu", stream=True))
        boxes = res[0].boxes.xyxy.cpu().numpy() if res[0].boxes is not None else []
        feet_per_frame.append(feet_from_boxes(boxes, frame.shape))
    print("  frames=%s feet=%s" % (pad6(len(frames)),
                                   pad6(sum(len(f) for f in feet_per_frame))))
    pano_f = cv2.imread(str(armf))
    out_lines.append(arm_row(stem, "F", armf.name, sha256_of(armf), frames, feet_per_frame,
                             pano_f, "panorama the pod route used"))
    print("  ARM F done")
    pano_v, reason = build_arm_v(video, model)
    if pano_v is None:
        out_lines.append("%s,V,built_from_section,-,%s,%s,-,-,-,-,-,-,-,-,NOT BUILDABLE: %s" % (
            stem, pad6(len(frames)), pad6(sum(len(f) for f in feet_per_frame)), reason))
        print("  ARM V NOT BUILDABLE: %s" % reason)
        return
    out_lines.append(arm_row(stem, "V", "built_from_section", "-", frames, feet_per_frame,
                             pano_v, reason))
    print("  ARM V done: %s" % reason)


def main(argv):
    t0 = time.time()
    workdir, evidence = Path(argv[1]), Path(argv[2])
    evidence.mkdir(parents=True, exist_ok=True)
    repo = Path(".").resolve()
    rows = build_census(workdir, repo, evidence)
    report_census(rows, workdir)
    if not premise_holds(rows):
        print("PREMISE FALSE -- stopping before any arm is run")
        return 0
    from ultralytics import YOLO
    model = YOLO(str(repo / "yolov8n.pt"))
    out_lines = [PROXY_COLS]
    for stem in sorted(p.stem for p in workdir.glob("*.mp4")):
        run_section(workdir, stem, model, out_lines)
    (evidence / "proxies.csv").write_text("\n".join(out_lines) + "\n", encoding="ascii")
    print("WALL_SECONDS %s" % pad6(int(time.time() - t0)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
