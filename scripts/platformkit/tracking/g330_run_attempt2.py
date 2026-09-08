"""G330 attempt-2 driver -- census.csv, proxies.csv and heldout.csv from a sealed snapshot.

Usage:
    python -m scripts.platformkit.tracking.g330_run_attempt2 <workdir> <evidence_dir>

<workdir> holds the read-only snapshot: `pod_census.txt` (lines 'sha256|bytes|mtime|path'),
`pano_enhanced.png` (the panorama the route used) and the three sections named by the sealed
selection rule. Each section's sha256 is checked against the value sealed in
`docs/evidence/tracking/g330_prereg_attempt2_2026-09-08.md` before any arm runs. Nothing is written
outside <evidence_dir>; nothing under `src/` is touched and no panorama cache path is written.
"""
from __future__ import annotations

import importlib.machinery
import os
import sys
import time
import types
from pathlib import Path

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")   # CPU only, per the spec
os.environ.setdefault("COURTV_NO_LOFTR", "1")
os.environ.setdefault("OMP_NUM_THREADS", "2")


def _shim_onnx():
    """Local-box workaround carried from attempt 1, not a G330 finding: an onnx/ml_dtypes pairing
    makes `import torchvision` raise AttributeError, which torch's guarded import does not catch.
    A stub named onnx turns that into an ImportError. Nothing in this row uses onnx.
    ponytail: stub, not an env repair.
    """
    if "onnx" in sys.modules:
        return
    stub = types.ModuleType("onnx")
    stub.__spec__ = importlib.machinery.ModuleSpec("onnx", None)
    stub.__getattr__ = lambda name: None
    sys.modules["onnx"] = stub


_shim_onnx()

from scripts.platformkit.tracking.g330_attempt2 import (  # noqa: E402
    ArmTally, MatchRecorder, eval_indices, make_arm, step_arm,
)
from scripts.platformkit.tracking.g330_panorama_identity import (  # noqa: E402
    build_arm_v, collisions, feet_from_boxes, frac, group_by_sha, inside_court, local_census,
    pad6, parse_census_line, premise_holds, route, sha256_of,
)

# Sealed in the prereg, section 1: stem -> (sha256 of the scored copy, container frame count).
SEALED = {
    "basketball__nbl-WTEUwPcy7X8_s90":
        ("225ada2044bf0d6b530ddef7d3cdddec38521b8a546771e6736ac659dca763fb", 6527),
    "nba__0022500081_s4812":
        ("03e66b6b172a494f0df5857a9394bbeec15c65868a6db15bcaae03cf9322b997", 3941),
    "nba__0022401198_s2784":
        ("444325a05cdb375990b621fc8870ddc774d4f0af4dad456f0b329b03a6552485", 3957),
}
CENSUS_COLS = "side,path,bytes,mtime,sha256,claimed_stem"
PROXY_COLS = ("section,arm,pano_source,pano_sha256,n_frames,feet_total,fit_frames,"
              "good_matches_total,fit_corr_total,fit_inliers_total,fit_inlier_ratio_in_sample,"
              "heldout_corr_total,heldout_inliers_total,heldout_inlier_ratio,"
              "heldout_median_px,valid_homography_frames,valid_homography_share,feet_evaluated,"
              "feet_inside,feet_inside_share,note")
HELDOUT_COLS = ("section,arm,frame_index,good_matches,n_fit,fit_inliers,n_heldout,"
                "heldout_inliers,heldout_median_px")


def peak_rss_mb() -> str:
    try:
        import resource
        return "%.1f" % (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0)
    except Exception:
        return "unknown"


def build_census(workdir: Path, repo: Path, evidence: Path) -> list:
    pod = [dict(parse_census_line(line), side="pod")
           for line in (workdir / "pod_census.txt").read_text().splitlines() if line.strip()]
    rows = pod + [dict(r, side="local") for r in local_census(repo)]
    lines = [CENSUS_COLS]
    for r in rows:
        lines.append("%s,%s,%s,%s,%s,%s" % (r["side"], r["path"], pad6(r["bytes"]),
                                            r["mtime"], r["sha256"], r["stem"]))
    (evidence / "census.csv").write_text("\n".join(lines) + "\n", encoding="ascii")
    return rows


def report_census(rows) -> str:
    """Print EVERY sha256 group, including groups whose distinct claimed video count is zero."""
    pod = [r for r in rows if r["side"] == "pod"]
    groups = group_by_sha(rows)
    print("CENSUS n_total=%s n_pod=%s n_local=%s distinct_sha=%s" % (
        pad6(len(rows)), pad6(len(pod)), pad6(len(rows) - len(pod)), pad6(len(groups))))
    general = [r for r in rows if r["stem"] == "-" and r["path"].endswith("pano_enhanced.png")]
    gen_sha = general[0]["sha256"] if general else ""
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    for sha, members in ordered:
        stems = sorted({m["stem"] for m in members if m["stem"] != "-"})
        print("  GROUP %s files=%s claimed_videos=%s bytes=%s %s" % (
            sha[:16], pad6(len(members)), pad6(len(stems)), pad6(members[0]["bytes"]),
            "general-fallback" if sha == gen_sha else "-"))
    print("PREMISE", "TRUE" if premise_holds(rows) else "FALSE")
    print("COLLISION_GROUPS", pad6(len(collisions(rows))))
    return gen_sha


def verify_snapshot(workdir: Path) -> list:
    """Refuse to score anything whose bytes differ from the sealed sha256."""
    stems = []
    for stem, (want, _frames) in sorted(SEALED.items()):
        got = sha256_of(workdir / ("%s.mp4" % stem))
        print("SNAPSHOT %s sealed=%s got=%s %s" % (stem, want[:16], got[:16],
                                                   "MATCH" if got == want else "MISMATCH"))
        if got != want:
            raise SystemExit("snapshot sha256 mismatch for %s" % stem)
        stems.append(stem)
    return stems


def detect_feet(model, frame):
    result = list(model(frame, classes=[0], conf=0.3, verbose=False, imgsz=640,
                        device="cpu", stream=True))[0]
    boxes = result.boxes.xyxy.cpu().numpy() if result.boxes is not None else []
    return feet_from_boxes(boxes, frame.shape)


def proxy_row(section, arm_name, source, sha, tally, note):
    return ",".join([
        section, arm_name, source, sha, pad6(tally.n_frames), pad6(tally.feet_total),
        pad6(tally.fit_frames), pad6(tally.good), pad6(tally.n_fit), pad6(tally.fit_inliers),
        frac(tally.fit_inliers, tally.n_fit), pad6(tally.n_held), pad6(tally.held_inliers),
        frac(tally.held_inliers, tally.n_held), tally.median_px(), pad6(tally.valid),
        frac(tally.valid, tally.n_frames), pad6(tally.feet_eval), pad6(tally.feet_in),
        frac(tally.feet_in, tally.feet_eval), note])


def heldout_rows(section, arm_name, rows):
    out = []
    for frame_index, n_good, stats in rows:
        if stats is None:
            out.append("%s,%s,%s,%s,-,-,-,-,-" % (section, arm_name, pad6(frame_index),
                                                  pad6(n_good)))
            continue
        out.append("%s,%s,%s,%s,%s,%s,%s,%s,%.3f" % (
            section, arm_name, pad6(frame_index), pad6(n_good), pad6(stats["n_fit"]),
            pad6(stats["fit_inliers"]), pad6(stats["n_held"]), pad6(stats["held_inliers"]),
            stats["held_median_px"]))
    return out


def run_section(workdir: Path, stem: str, model, pano_f, pano_f_sha, proxies, held_lines):
    """Both arms in lockstep over the SAME decoded frames; the only difference is the panorama."""
    import cv2
    pipeline = route()
    video = workdir / ("%s.mp4" % stem)
    pano_v, reason = build_arm_v(video, model)
    print("  ARM V build: %s" % reason)
    arms = {"F": (make_arm(pano_f), "pano_enhanced.png", pano_f_sha,
                  "panorama the route used")}
    if pano_v is not None:
        arms["V"] = (make_arm(pano_v), "built_from_section", "-", reason)
    tallies = {name: ArmTally() for name in arms}
    picked = {name: [] for name in arms}
    wanted = set(eval_indices(SEALED[stem][1]))
    capture = cv2.VideoCapture(str(video))
    index = 0
    with MatchRecorder() as recorder:
        while True:
            ok, raw = capture.read()
            if not ok:
                break
            frame = raw[pipeline.TOPCUT:]
            feet = detect_feet(model, frame) if index in wanted else None
            for name, (arm, _src, _sha, _note) in arms.items():
                tally = tallies[name]
                homography = step_arm(arm, frame, recorder, tally, 5.0,
                                      rows=picked[name], tag=(index,))
                if feet is None:
                    continue
                tally.n_frames += 1
                tally.feet_total += len(feet)
                if homography is None:
                    continue
                tally.valid += 1
                tally.feet_eval += len(feet)
                tally.feet_in += inside_court(feet, homography, arm.M1,
                                              arm.map_2d.shape[1], arm.map_2d.shape[0])
            index += 1
    capture.release()
    print("  decoded=%s eval_frames=%s" % (pad6(index), pad6(tallies["F"].n_frames)))
    for name, (_arm, source, sha, note) in arms.items():
        proxies.append(proxy_row(stem, name, source, sha, tallies[name], note))
        held_lines.extend(heldout_rows(stem, name, picked[name]))
        print("  ARM %s done: %s" % (name, proxies[-1]))
    if "V" not in arms:
        proxies.append("%s,V,built_from_section,-,%s,%s,%s" % (
            stem, pad6(tallies["F"].n_frames), pad6(tallies["F"].feet_total),
            ",".join(["-"] * 14) + ",NOT BUILDABLE: " + reason))
        print("  ARM V NOT BUILDABLE: %s" % reason)


def main(argv):
    started = time.time()
    workdir, evidence = Path(argv[1]), Path(argv[2])
    evidence.mkdir(parents=True, exist_ok=True)
    repo = Path(".").resolve()
    stage = argv[3] if len(argv) > 3 else "all"
    if stage in ("all", "census"):
        rows = build_census(workdir, repo, evidence)
        report_census(rows)
        if not premise_holds(rows):
            print("PREMISE FALSE -- stopping before any arm is run")
            return 0
        if stage == "census":
            print("WALL_SECONDS %s" % pad6(int(time.time() - started)))
            return 0
    else:
        print("CENSUS stage ran separately; the premise gate passed there before this stage")
    stems = verify_snapshot(workdir)
    import cv2
    pano_f_path = workdir / "pano_enhanced.png"
    pano_f = cv2.imread(str(pano_f_path))
    pano_f_sha = sha256_of(pano_f_path)
    print("ARM F panorama %s %s" % (pano_f_path.name, pano_f_sha[:16]))
    from ultralytics import YOLO
    model = YOLO(str(repo / "yolov8n.pt"))
    proxies, held_lines = [PROXY_COLS], [HELDOUT_COLS]
    for stem in stems:
        print("SECTION %s" % stem)
        run_section(workdir, stem, model, pano_f, pano_f_sha, proxies, held_lines)
    (evidence / "proxies.csv").write_text("\n".join(proxies) + "\n", encoding="ascii")
    (evidence / "heldout.csv").write_text("\n".join(held_lines) + "\n", encoding="ascii")
    print("PEAK_RSS_MB %s" % peak_rss_mb())
    print("WALL_SECONDS %s" % pad6(int(time.time() - started)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
