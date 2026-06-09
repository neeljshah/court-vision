#!/usr/bin/env python3
"""diagnose_pose_pipeline.py — Direct test of the YOLOv8-pose engine at
imgsz=640 vs imgsz=960 on real broadcast frames from a game video.

Outputs the per-keypoint confidence distribution so we can pick a
_CONF_MIN threshold that unlocks ankle/contest_arm signals at the right
imgsz.

Designed to run on the pod (where TRT + CUDA are).

Usage (on pod):
    python3 scripts/diagnose_pose_pipeline.py \\
        --video /root/nba_videos/0022500280.mp4 \\
        --frames 5 --start 30000
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

# COCO-17 keypoint indices used by feature extractor
KP_NAMES = {
    0:  "nose",
    5:  "L_shoulder",
    6:  "R_shoulder",
    9:  "L_wrist",
    10: "R_wrist",
    11: "L_hip",
    12: "R_hip",
    15: "L_ankle",
    16: "R_ankle",
}


def run_pose_at_imgsz(video_path: str, imgsz: int,
                      start_frame: int, n_frames: int) -> dict:
    """Load pose model, run on n_frames sampled from the video at given imgsz.
    Returns per-keypoint conf stats aggregated across all detections."""
    import cv2
    from ultralytics import YOLO
    import torch

    use_half = torch.cuda.is_available()
    device = 0 if use_half else "cpu"

    # Find pose engine (prefer .engine, fallback .pt)
    pose_path = Path("resources/yolov8n-pose.engine")
    if not pose_path.exists():
        pose_path = Path("yolov8n-pose.pt")
    print(f"  loading {pose_path} for imgsz={imgsz}...", flush=True)
    model = YOLO(str(pose_path))

    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    all_confs = {idx: [] for idx in KP_NAMES}
    n_detections_total = 0
    n_frames_with_dets = 0

    for i in range(n_frames):
        ok, frame = cap.read()
        if not ok:
            break
        # Skip ahead 100 frames between samples for variety
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame + (i + 1) * 100)

        results = model(
            frame, classes=[0], conf=0.22,
            verbose=False, imgsz=imgsz, half=use_half, device=device,
        )
        r = results[0]
        if r.keypoints is None or r.keypoints.conf is None:
            continue
        conf = r.keypoints.conf.cpu().numpy()  # (N, 17)
        if conf.shape[0] == 0:
            continue
        n_detections_total += conf.shape[0]
        n_frames_with_dets += 1
        for idx in KP_NAMES:
            all_confs[idx].extend(conf[:, idx].tolist())

    cap.release()

    out = {
        "imgsz": imgsz,
        "video": video_path,
        "n_frames_sampled": n_frames,
        "n_frames_with_detections": n_frames_with_dets,
        "n_detections_total": n_detections_total,
        "per_keypoint": {},
    }
    for idx, name in KP_NAMES.items():
        arr = np.array(all_confs[idx])
        if len(arr) == 0:
            out["per_keypoint"][name] = {"n": 0}
            continue
        out["per_keypoint"][name] = {
            "n": int(len(arr)),
            "mean": round(float(arr.mean()), 3),
            "median": round(float(np.median(arr)), 3),
            "p25":  round(float(np.percentile(arr, 25)), 3),
            "p75":  round(float(np.percentile(arr, 75)), 3),
            "max":  round(float(arr.max()), 3),
            "pct_above_0.3": round(100 * (arr >= 0.3).mean(), 1),
            "pct_above_0.5": round(100 * (arr >= 0.5).mean(), 1),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--frames", type=int, default=5)
    ap.add_argument("--start", type=int, default=30000,
                    help="Start frame (avoid intro/commercials; mid-game)")
    ap.add_argument("--imgsz", default="640,960",
                    help="Comma-separated imgsz values to test")
    args = ap.parse_args()

    imgsz_list = [int(x) for x in args.imgsz.split(",")]
    all_results = []
    for sz in imgsz_list:
        print(f"\n{'='*60}\n=== imgsz={sz} ===\n{'='*60}", flush=True)
        try:
            r = run_pose_at_imgsz(args.video, sz, args.start, args.frames)
            all_results.append(r)
            print(f"  n_detections: {r['n_detections_total']}", flush=True)
            print(f"  {'kp':12s} {'n':>5s} {'mean':>6s} {'median':>6s} "
                  f"{'>=0.3%':>7s} {'>=0.5%':>7s}")
            for name, kp in r["per_keypoint"].items():
                if kp.get("n", 0) == 0:
                    print(f"  {name:12s} (no detections)")
                    continue
                print(f"  {name:12s} {kp['n']:5d} {kp['mean']:6.3f} "
                      f"{kp['median']:6.3f} {kp['pct_above_0.3']:6.1f}% "
                      f"{kp['pct_above_0.5']:6.1f}%")
        except Exception as e:
            print(f"  FAIL: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
