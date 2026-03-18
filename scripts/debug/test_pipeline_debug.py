"""Debug why pipeline produces 0 tracking rows."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
os.chdir('c:/Users/neelj/nba-ai-system')

import cv2, numpy as np
from src.pipeline.unified_pipeline import UnifiedPipeline, TOPCUT, MIN_GAMEPLAY_PERSONS, _H_MIN_INLIERS

print(f'TOPCUT={TOPCUT}  MIN_GAMEPLAY_PERSONS={MIN_GAMEPLAY_PERSONS}  _H_MIN_INLIERS={_H_MIN_INLIERS}')

video = 'data/videos/gsw_lakers_2025.mp4'
p = UnifiedPipeline(video, max_frames=2200)

cap = cv2.VideoCapture(video)
gameplay_count = 0
M_none_count = 0
tracking_count = 0

for frame_idx in range(2200):
    ok, frame = cap.read()
    if not ok:
        break
    frame = frame[TOPCUT:]

    is_gp = p._is_gameplay(frame, frame_idx)
    if not is_gp:
        if frame_idx in [750, 900, 1000, 1200]:
            print(f'  frame {frame_idx}: _is_gameplay=False')
        continue

    gameplay_count += 1
    M = p._get_homography(frame)
    if M is None:
        M_none_count += 1
        if M_none_count <= 3:
            print(f'  frame {frame_idx}: M is None')
        continue

    tracking_count += 1
    if tracking_count <= 2:
        print(f'  frame {frame_idx}: TRACKING OK (gameplay={gameplay_count} M_none={M_none_count})')

    if tracking_count >= 5:
        break

cap.release()
print(f'Done: gameplay_frames={gameplay_count} M_none={M_none_count} tracking_ok={tracking_count}')
