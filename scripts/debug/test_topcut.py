"""Quick test: compare YOLO player count at different topcut values."""
import cv2
import sys
sys.stdout.reconfigure(encoding='utf-8')
from ultralytics import YOLO

cap = cv2.VideoCapture('data/videos/gsw_lakers_2025.mp4')
model = YOLO('yolov8n.pt')

results = {}
for frame_no in [1000, 2000, 5000, 10000, 15000]:
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
    ok, frame = cap.read()
    if not ok:
        continue
    h, w = frame.shape[:2]
    counts = {}
    for tc in [0, 60, 100, 200, 320]:
        cropped = frame[tc:]
        r = model(cropped, classes=[0], conf=0.3, verbose=False, imgsz=1280)
        n = len(r[0].boxes) if r[0].boxes is not None else 0
        counts[tc] = n
    print(f"Frame {frame_no}: " + "  ".join(f"tc={k}→{v}" for k,v in counts.items()))

cap.release()
