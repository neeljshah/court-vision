"""Quick preflight check — sample 10 YOLO frames to find the best start region for long videos."""
import os
import sys
import cv2
import statistics

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

try:
    from ultralytics import YOLO
    model = YOLO(os.path.join(PROJECT_DIR, "yolov8n.pt"))
except Exception as e:
    print(f"YOLO unavailable: {e}")
    sys.exit(1)

# Games where we need to find good start frame (full game downloads > 30 min)
LONG_GAMES = {
    "0022401183": 30,
    "0022401185": 60,
    "0022401198": 30,
    "0022401175": 30,
    "0022401190": 30,
    "0022401194": 30,
    "0022401196": 30,
    "0022400625": 60,
    "0022400921": 60,
    "0022400923": 60,
}

base = r"C:\Users\neelj\nba-ai-system\data\videos\full_games"

def sample_region(cap, start_frame, n_frames, fps, n_samples=5):
    """Sample n_samples frames from [start_frame, start_frame+n_frames], return median person count."""
    counts = []
    for i in range(n_samples):
        fi = start_frame + int(n_frames * i / max(1, n_samples - 1))
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ret, frame = cap.read()
        if not ret:
            continue
        results = model(frame, classes=[0], verbose=False)
        n = len(results[0].boxes) if results and results[0].boxes is not None else 0
        counts.append(n)
    return statistics.median(counts) if counts else 0

for gid, fps in LONG_GAMES.items():
    path = os.path.join(base, f"{gid}.mp4")
    if not os.path.exists(path):
        print(f"{gid}: MISSING")
        continue
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS) or fps

    # Test candidate start regions: 0, 10, 20, 30, 45, 60 min
    window_frames = int(18000 * actual_fps / 30)  # FPS-adjusted 10-min window
    print(f"\n{gid} ({actual_fps:.0f}fps, {total/actual_fps/60:.0f}min total):")

    best_median = 0
    best_start = 0
    for start_min in [0, 10, 20, 30, 45, 60]:
        start_frame = int(start_min * 60 * actual_fps)
        if start_frame + window_frames > total:
            break
        med = sample_region(cap, start_frame, window_frames, actual_fps)
        print(f"  {start_min:3d}min start (frame {start_frame}): median_persons={med:.1f}")
        if med > best_median:
            best_median = med
            best_start = start_frame

    if best_median >= 3:
        print(f"  => BEST START: frame {best_start} ({best_start/actual_fps/60:.0f}min) median={best_median:.1f}")
    else:
        print(f"  => WARNING: no region found with median >= 3 persons")
    cap.release()

print("\nDone.")
