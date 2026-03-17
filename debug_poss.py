"""Debug why possession is 0%."""
import sys, cv2, numpy as np
sys.path.insert(0, 'C:/Users/neelj/nba-ai-system')
from src.pipeline.unified_pipeline import UnifiedPipeline

pipe = UnifiedPipeline(
    video_path='data/videos/bos_mia_2025.mp4',
    max_frames=50, show=False,
)

# Patch ball_tracker to log scores
orig = pipe.ball_det.ball_tracker.__func__
import src.tracking.ball_detect_track as bdt

orig_ball_tracker = bdt.BallDetectTrack.ball_tracker
poss_count = [0]
frame_count = [0]

def patched(self, M, M1, frame, map_2d, map_2d_text, timestamp):
    frame_count[0] += 1
    # Count players with positions
    n_with_pos = sum(1 for p in self.players if p.team != 'referee' and p.previous_bb is not None and timestamp in p.positions)
    n_has_ball = sum(1 for p in self.players if p.has_ball)
    if frame_count[0] % 10 == 0:
        print(f"Frame {timestamp}: players_with_pos={n_with_pos}, n_players={len(self.players)}")
    result = orig_ball_tracker(self, M, M1, frame, map_2d, map_2d_text, timestamp)
    n_has_ball_after = sum(1 for p in self.players if p.has_ball)
    if n_has_ball_after > 0:
        poss_count[0] += 1
    return result

bdt.BallDetectTrack.ball_tracker = patched
pipe.ball_det.ball_tracker = patched.__get__(pipe.ball_det, bdt.BallDetectTrack)

pipe.run()
print(f"\nPossession frames: {poss_count[0]}/{frame_count[0]}")
