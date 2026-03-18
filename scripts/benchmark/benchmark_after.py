"""After-benchmark: measure fps with imgsz=640 fix applied."""
import time
import sys
import subprocess
import re

video = "data/videos/cavs_vs_celtics_2025.mp4"
game_id = "0022400710"

print(f"After-benchmark (imgsz=640): {video}")
start = time.time()
result = subprocess.run(
    [
        sys.executable,
        "src/pipeline/unified_pipeline.py",
        "--video", video,
        "--game-id", game_id,
        "--no-show",
    ],
    capture_output=True,
    text=True,
)
elapsed = time.time() - start

lines = (result.stdout + result.stderr).strip().split('\n')
for line in lines[-40:]:
    print(line)

# Extract max frame index from \r Frame {n}... outputs
frame_matches = re.findall(r'[Ff]rame\s+(\d+)', result.stdout + result.stderr)
frame_count = max((int(x) for x in frame_matches), default=0)

# Also check tracking rows for gameplay frames
row_match = re.search(r'Tracking data.*\((\d+) rows\)', result.stdout + result.stderr)
tracking_rows = int(row_match.group(1)) if row_match else 0
gameplay_approx = tracking_rows // 10  # ~10 players per gameplay frame

if frame_count:
    fps = frame_count / elapsed
    gfps = gameplay_approx / elapsed if gameplay_approx else fps
    print(f"\nAfter-benchmark: {fps:.1f} fps (total), ~{gfps:.1f} gameplay fps")
    print(f"Total frames: {frame_count}, Wall time: {elapsed:.1f}s ({elapsed/60:.1f}min)")
else:
    print(f"\nWall time: {elapsed:.1f}s ({elapsed/60:.1f}min), rc={result.returncode}")
