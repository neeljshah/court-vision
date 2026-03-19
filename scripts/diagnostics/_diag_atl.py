"""Diagnose atl_ind_2025 FPS regression — check court detection timing."""
import sys, time
sys.path.insert(0, '.')
import cv2

# Video properties
cap = cv2.VideoCapture('data/videos/atl_ind_2025.mp4')
print(f'Resolution  : {int(cap.get(3))}x{int(cap.get(4))}')
print(f'Total frames: {int(cap.get(7))}')
print(f'FPS (video) : {cap.get(5):.1f}')
frames = []
for _ in range(10):
    ret, f = cap.read()
    if ret:
        frames.append(f)
cap.release()
print(f'Sampled     : {len(frames)} frames')

# Time court detection
from src.tracking.rectify_court import detect_court_homography
t0 = time.perf_counter()
M = detect_court_homography(frames[:5])
elapsed = time.perf_counter() - t0
print(f'\ndetect_court_homography (5 frames): {elapsed:.2f}s  found={M is not None}')

# Time a second call (cold vs warm)
t0 = time.perf_counter()
M2 = detect_court_homography(frames[5:])
elapsed2 = time.perf_counter() - t0
print(f'detect_court_homography (5 more)  : {elapsed2:.2f}s  found={M2 is not None}')
