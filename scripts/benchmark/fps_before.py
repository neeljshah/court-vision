"""Before-fps: temporarily use imgsz=1280 for 100 frames to get baseline."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np

# Monkey-patch to force imgsz=1280 without editing the file
import src.tracking.advanced_tracker as _at

_orig_gpp = _at.AdvancedFeetDetector.get_players_pos

def _patched_gpp(self, M, M1, frame, timestamp, map_2d):
    # Temporarily force imgsz=1280 on the non-pose branch
    _orig = self.model
    class _Wrapper:
        def __init__(self, m): self._m = m
        def __call__(self, *args, **kwargs):
            kwargs['imgsz'] = 1280
            return self._m(*args, **kwargs)
        def __getattr__(self, name): return getattr(self._m, name)
    self.model = _Wrapper(self.model)
    result = _orig_gpp(self, M, M1, frame, timestamp, map_2d)
    self.model = _orig
    return result

_at.AdvancedFeetDetector.get_players_pos = _patched_gpp

from src.pipeline.unified_pipeline import UnifiedPipeline
from src.tracking import TOPCUT

VIDEO = "data/videos/cavs_vs_celtics_2025.mp4"
GAME_ID = "0022400710"
MEASURE = 100

print("Before-benchmark (imgsz=1280)...")
pipe = UnifiedPipeline(video_path=VIDEO, game_id=GAME_ID, show=False, max_frames=MEASURE + 50)

cap = cv2.VideoCapture(VIDEO)
frame_idx = 0
gameplay = 0
times = []

while cap.isOpened() and gameplay < 50 + MEASURE:
    ok, frame = cap.read()
    if not ok:
        break
    frame = frame[TOPCUT:]
    if not pipe._is_gameplay(frame, frame_idx):
        frame_idx += 1
        continue
    M = pipe._get_homography(frame)
    if M is None:
        frame_idx += 1
        continue
    map_snap = pipe.map_2d.copy()
    t = time.perf_counter()
    frame, map_snap, _ = pipe.feet_det.get_players_pos(M, pipe.M1, frame, frame_idx, map_snap)
    pipe.ball_det.ball_tracker(M, pipe.M1, frame, map_snap.copy(), None, frame_idx)
    elapsed = time.perf_counter() - t
    gameplay += 1
    if gameplay > 50:
        times.append(elapsed)
    frame_idx += 1

cap.release()

if times:
    avg_fps = len(times) / sum(times)
    print(f"Before (imgsz=1280): {avg_fps:.1f} fps  ({1000/avg_fps:.0f}ms/frame)")
