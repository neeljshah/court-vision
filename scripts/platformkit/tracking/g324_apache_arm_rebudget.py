"""G324 SCREENING: Apache-2.0 RTMDet arm vs the production AGPL yolov8n arm, re-run
under a re-registered 3,600 s install premise (G311 closed at a 1,800 s bar it could
not meet against a measured 2,921 s build+install).

Two person-detection arms on IDENTICAL decoded frames. Image-space proxies only.
NO ground truth: no labels, no renders, no eye check. More boxes can mean more
players found OR more false boxes and this module cannot tell them apart. Nothing
here is recall, precision, registration or a pass, and neither arm may be called
better. G303/G296 are the rows that score recall against labelled frames.

Reads and imports src/ ; never edits it. Writes only under the given --out dir and
the --target prefix given to the install premise.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import pathlib
from pathlib import Path

from scripts.platformkit.tracking.g311_apache_detector_arm import (  # inherited, not copied
    decode, probe, sha256,
)
from scripts.platformkit.tracking.g311_proxies import IOU_LINK, IOU_MATCH, agreement, summarize
from scripts.platformkit.tracking.g324_arms import BATCH, measure, rows_to_csv, rtmdet_call, yolo_call

PREMISE_LIMIT_S = 3600.0  # SEALED in g324_prereg_2026-09-07.md. NEVER LENGTHENED (contract Q3).
WHEEL_SHA256 = "608637e5600ec15708acf451aa2e067d3e7b1e8c6dc40856e6f42d2e8ffaa9a1"
# SEALED in g324_prereg_2026-09-07.md:60 (G324-CKPT-HASH-GUARD, verifier NEW GAP).
CKPT_SHA256 = "229f527ca88498e8894a778a62a878a322b4a3ea2cae09ea537d34b7e907792b"
GATE = (
    "import platform, numpy, cv2, torch, mmcv, mmdet, mmengine; "
    "from mmcv.ops import batched_nms; "
    "print('python=' + platform.python_version()); "
    "print('numpy=' + numpy.__version__); "
    "print('cv2=' + cv2.__version__); "
    "print('torch=' + torch.__version__); "
    "print('mmcv=' + mmcv.__version__); "
    "print('mmdet=' + mmdet.__version__); "
    "print('mmengine=' + mmengine.__version__)"
)  # labeled resolved-version block (verifier: g324_preflight1.txt:25-26 was unlabeled)
ROUTE_FILES = ("scripts/platformkit/tracking/g324_apache_arm_rebudget.py",
               "scripts/platformkit/tracking/g324_arms.py",
               "scripts/platformkit/tracking/g311_apache_detector_arm.py",
               "scripts/platformkit/tracking/g311_proxies.py")


def sh(cmd: list[str], budget: float, env: dict | None = None) -> dict:
    """One premise step, with the REMAINING sealed budget as a hard timeout so an
    over-run is a RECORDED OUTCOME, never a hang. env=None inherits the current
    process environment (unchanged default behaviour)."""
    t = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=max(budget, 1.0), env=env)
        rc, tail = p.returncode, (p.stdout + p.stderr)[-1200:]
    except subprocess.TimeoutExpired:
        rc, tail = 124, "TIMEOUT at the sealed premise limit"
    return {"cmd": " ".join(cmd), "rc": rc, "elapsed_s": round(time.time() - t, 1), "tail": tail}


def source_build_step(target: str, constraints: str, budget: float) -> dict:
    """G324-REUSE-FALLBACK (verifier NEW GAP): the module always DECLARED that a
    wheel-hash mismatch builds from source inside the same sealed clock, but no
    code ever called it -- a mismatch just returned REUSE REFUSED. This is that
    call: build mmcv 2.1.0 from its sdist (pip does the build) with the SAME
    TORCH_CUDA_ARCH_LIST=8.6 G311's inherited manual build used, under the
    REMAINING budget as the hard timeout. A real invocation is untested by this
    fix (no rerun of the arms); tests mock this function directly."""
    pip = [sys.executable, "-m", "pip", "install", "--target", target,
           "--no-warn-script-location", "--no-binary", "mmcv", "-c", constraints,
           "mmcv==2.1.0", "mmdet==3.3.0", "mmengine==0.10.7"]
    return sh(pip, budget, env={**os.environ, "TORCH_CUDA_ARCH_LIST": "8.6"})


def install_premise(wheel: str, target: str, constraints: str) -> dict:
    """The row's ONE bar: the import gate clears within PREMISE_LIMIT_S of wall clock.

    The wheel is REUSED only when its SHA-256 matches the value sealed in the prereg;
    reuse measures INSTALLABILITY, not buildability, and the rebuild-from-source cost
    is reported separately by the memo. A mismatch means no reuse: the caller BUILDS
    FROM SOURCE inside this same sealed clock via source_build_step (verifier
    NEW GAP G324-REUSE-FALLBACK -- this used to dead-end at REUSE REFUSED instead).
    """
    t0 = time.time()
    got = sha256(wheel)
    out = {"limit_s": PREMISE_LIMIT_S, "wheel": wheel, "wheel_bytes": Path(wheel).stat().st_size,
           "wheel_sha256": got, "wheel_sha256_expected": WHEEL_SHA256,
           "wheel_reused": got == WHEEL_SHA256, "source_build_fallback": False, "steps": []}
    pip = [sys.executable, "-m", "pip", "install", "--target", target, "--no-warn-script-location"]
    gate_target = target
    build_ok = True
    if out["wheel_reused"]:
        for cmd in ([*pip, "--no-deps", "--force-reinstall", wheel],
                    [*pip, "-c", constraints, "mmdet==3.3.0", "mmengine==0.10.7"]):
            out["steps"].append(sh(cmd, PREMISE_LIMIT_S - (time.time() - t0)))
    else:
        # B2 (verifier fix 1c): keep the old REUSE REFUSED status ALIVE as an
        # additive field instead of dropping it -- fix 1b removed the status
        # outright when it wired up the fallback.
        out["premise_status"] = "REUSE REFUSED -> SOURCE BUILD FALLBACK"
        print("PREMISE_STATUS", out["premise_status"])
        out["source_build_fallback"] = True
        # G324-FALLBACK-INSTALL-IDENTITY (verifier NEW GAP, fix 1c): build into a
        # FRESH prefix, never the (possibly already-populated) reuse target, so a
        # stale import surviving from an earlier run can never mask a failed build.
        gate_target = "%s_fallback_%d" % (target, int(t0))
        out["fallback_target"] = gate_target
        build = source_build_step(gate_target, constraints, PREMISE_LIMIT_S - (time.time() - t0))
        out["steps"].append(build)
        build_ok = build["rc"] == 0
    gate = sh([sys.executable, "-c", "import sys; sys.path.insert(0, %r); %s" % (gate_target, GATE)],
              PREMISE_LIMIT_S - (time.time() - t0))
    out["steps"].append(gate)
    out["elapsed_s"] = round(time.time() - t0, 1)
    # gate_ok now honours the build step's own rc (verifier NEW GAP): a failed
    # source build must never be masked by a stale import clearing the gate.
    out["gate_ok"] = build_ok and gate["rc"] == 0 and out["elapsed_s"] <= PREMISE_LIMIT_S
    out["verdict"] = ("PREMISE MET" if out["gate_ok"] else
                      "CLOSED AT LIMIT at %.1f s of %.0f s" % (out["elapsed_s"], PREMISE_LIMIT_S))
    return out


def provenance(gated_src: str, videos: list[str]) -> dict:
    """A9 source byte sizes + A11 SHA-256 of every route file AS DEPLOYED ON THE POD,
    computed inside the run -- G311 could not reconstruct either afterwards."""
    return {"route_sha256": {f: (sha256(f) if Path(f).exists() else "ABSENT") for f in ROUTE_FILES},
            "source_bytes": {v: Path(v).stat().st_size for v in videos},
            "gated_src_sha256": sha256(gated_src)}


def run_game(vid: str, nframes: int, cfg: str, ckpt: str, score: float, out: Path) -> dict:
    meta = probe(vid)
    meta["bytes"] = Path(vid).stat().st_size
    frames, idxs = decode(vid, meta["nb_frames"], nframes)
    stem = Path(vid).stem
    t0 = time.time()
    import torch
    arms = {}
    for tag, factory in (("Y_yolov8n_AGPL", lambda: yolo_call(0.3)),
                         ("R_rtmdet_Apache2.0", lambda: rtmdet_call(cfg, ckpt, score))):
        call, holder = factory()
        m = measure(call, frames)
        csv = out / ("g324_boxes_%s_%s.csv" % (stem, tag.split("_")[0]))
        m["raw_rows"] = rows_to_csv(m["rows"], idxs, csv)
        m["raw_csv"] = csv.name
        arms[tag] = m
        del call, holder
        torch.cuda.empty_cache()
    boxes = {t: [r[0] for r in m["rows"]] for t, m in arms.items()}
    g = {"game": stem, "source": meta, "frame_indices": idxs, "decoded": len(frames),
         "wall_s": round(time.time() - t0, 1), "batch_size": BATCH}
    for tag, m in arms.items():
        s = summarize(tag, boxes[tag], [], m["peak_vram_mb"], m["vram_method"])
        s.update({k: m[k] for k in ("ms_per_frame", "ms_per_frame_batch8", "batch_size",
                                    "warmup_frames_excluded", "batch_vs_single", "raw_rows",
                                    "raw_csv")})
        g["arm_" + tag[0]] = s
    g["agreement"] = agreement(boxes["Y_yolov8n_AGPL"], boxes["R_rtmdet_Apache2.0"])
    return g


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", nargs="+", required=True)
    ap.add_argument("--frames", type=int, default=40)
    ap.add_argument("--wheel", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--constraints", required=True)
    ap.add_argument("--extra-syspath", default="", help="prepended to sys.path; no ENV= prefix")
    ap.add_argument("--rtmdet-config", required=True)
    ap.add_argument("--rtmdet-ckpt", required=True)
    ap.add_argument("--rtmdet-score", type=float, default=0.3)
    ap.add_argument("--gated-src", default="src/tracking/player_detection.py")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    # Paths arrive POD-RELATIVE: Git Bash rewrites a leading-slash argv token into a
    # Windows path (it turned /workspace/... into C:/Program Files/Git/workspace/...).
    # Resolve here so every recorded path is the absolute pod path the prereg declares.
    a.videos = [str(pathlib.Path(v).resolve()) for v in a.videos]
    for k in ("wheel", "target", "constraints", "rtmdet_config", "rtmdet_ckpt", "extra_syspath"):
        if getattr(a, k):
            setattr(a, k, str(pathlib.Path(getattr(a, k)).resolve()))

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for v in a.videos:  # pre-create so a CLOSED AT LIMIT run still has fetchable artifacts
        for tag in ("Y", "R"):
            (out / ("g324_boxes_%s_%s.csv" % (Path(v).stem, tag))).write_text(
                "frame_index,x1,y1,x2,y2,score,class\n")
    print("SCREENING ONLY -- no labels, no renders, no eye check; neither arm is better.")
    report = {"screening_only": True, "ground_truth": "NONE", "iou_match": IOU_MATCH,
              "iou_link": IOU_LINK, "batch_size": BATCH,
              "premise": install_premise(a.wheel, a.target, a.constraints)}
    print("PREMISE", json.dumps(report["premise"], default=str))
    if not report["premise"]["gate_ok"]:
        (out / "g324_summary.json").write_text(json.dumps(report, indent=2, default=str))
        print("WROTE", out / "g324_summary.json")
        return 0  # CLOSED AT LIMIT is a recorded outcome, not an error exit

    if a.extra_syspath:
        sys.path.insert(0, a.extra_syspath)
    report["ckpt_sha256"] = sha256(a.rtmdet_ckpt)
    report["ckpt_bytes"] = Path(a.rtmdet_ckpt).stat().st_size
    if report["ckpt_sha256"] != CKPT_SHA256:  # G324-CKPT-HASH-GUARD: raise BEFORE load
        raise RuntimeError(
            "G324-CKPT-HASH-GUARD: checkpoint SHA-256 %s does not match the sealed "
            "value %s (g324_prereg_2026-09-07.md:60) -- refusing to load" %
            (report["ckpt_sha256"], CKPT_SHA256))
    report["provenance"] = provenance(a.gated_src, a.videos)
    report["games"] = []
    for vid in a.videos:
        g = run_game(vid, a.frames, a.rtmdet_config, a.rtmdet_ckpt, a.rtmdet_score, out)
        report["games"].append(g)
        print(json.dumps({k: v for k, v in g.items() if k != "frame_indices"}, default=str))
    report["gated_src_sha256_after"] = sha256(a.gated_src)
    report["gated_src_unchanged"] = (
        report["gated_src_sha256_after"] == report["provenance"]["gated_src_sha256"])
    (out / "g324_summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", out / "g324_summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
