"""Quick 300-frame fps timer. Runs the tracker directly (no subprocess capture)."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np

VIDEO = "data/videos/cavs_vs_celtics_2025.mp4"
GAME_ID = "0022400710"
WARMUP = 50   # frames to discard before timing starts
MEASURE = 300  # frames to time

from src.pipeline.unified_pipeline import UnifiedPipeline

print("Initialising pipeline...")
t0 = time.time()
pipe = UnifiedPipeline(
    video_path=VIDEO,
    game_id=GAME_ID,
    show=False,
    max_frames=WARMUP + MEASURE,
)
print(f"Init done in {time.time()-t0:.1f}s")

cap = cv2.VideoCapture(VIDEO)
fps_video = cap.get(cv2.CAP_PROP_FPS) or 30.0
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
cap.release()
print(f"Video: {total_frames} frames @ {fps_video:.1f}fps ({total_frames/fps_video/60:.1f} min)")

from src.tracking import TOPCUT

# -- patch run() to time just MEASURE gameplay frames after WARMUP --
cap = cv2.VideoCapture(VIDEO)
frame_idx = 0
gameplay = 0
times = []

print(f"Warming up {WARMUP} gameplay frames, then timing {MEASURE}...")
t_start = None

while cap.isOpened():
    ok, frame = cap.read()
    if not ok:
        break
    frame = frame[TOPCUT:]

    if not pipe._is_gameplay(frame, frame_idx):
        frame_idx += 1
        continue

    pipe._try_recover_court_M1(frame)
    M = pipe._get_homography(frame)
    if M is None:
        frame_idx += 1
        continue

    map_snap = pipe.map_2d.copy()
    t_frame = time.perf_counter()

    # Core per-frame work
    frame, map_snap, _ = pipe.feet_det.get_players_pos(M, pipe.M1, frame, frame_idx, map_snap)
    frame, _ = pipe.ball_det.ball_tracker(M, pipe.M1, frame, map_snap.copy(), None, frame_idx)

    elapsed_frame = time.perf_counter() - t_frame

    gameplay += 1
    if gameplay <= WARMUP:
        if gameplay == WARMUP:
            print(f"Warmup done. Timing next {MEASURE} frames...")
            t_start = time.perf_counter()
    else:
        times.append(elapsed_frame)
        if (gameplay - WARMUP) % 50 == 0:
            recent_fps = 50 / sum(times[-50:]) if len(times) >= 50 else (gameplay - WARMUP) / sum(times)
            print(f"  Frame {gameplay - WARMUP}/{MEASURE}: {recent_fps:.1f} fps")

    frame_idx += 1
    if gameplay >= WARMUP + MEASURE:
        break

cap.release()

if times:
    total_t = sum(times)
    avg_fps = len(times) / total_t
    p50 = sorted(times)[len(times)//2]
    p95 = sorted(times)[int(len(times)*0.95)]
    print(f"\n=== RESULTS ({len(times)} frames) ===")
    print(f"Avg fps:   {avg_fps:.1f}")
    print(f"Median ms/frame: {p50*1000:.0f}ms")
    print(f"p95 ms/frame:    {p95*1000:.0f}ms")
    print(f"Total wall time (full 17.9min clip): ~{total_frames/fps_video/avg_fps/60:.0f} min")
    print(f"\nBenchmark: {avg_fps:.1f} fps, {len(times)} timed frames")
