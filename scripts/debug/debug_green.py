"""
debug_green.py — Find actual jersey HSV values in this clip.
Lowers conf to 0.25, samples more frames, prints dominant hue clusters.
Saves: data/debug_green.png (annotated frame) + data/debug_hues.png (hue histogram)
"""
import cv2
import numpy as np
import sys

VIDEO = r"C:\Users\neelj\coding\Untitled video - Made with Clipchamp.mp4"
# Sample a spread of frames across the clip
SAMPLE_FRAMES = list(range(0, 300, 15))

def jersey_hsv_stats(crop_bgr):
    """Return median HSV of upper-70% jersey area, excluding floor/background."""
    if crop_bgr is None or crop_bgr.size == 0:
        return None
    h = max(1, int(crop_bgr.shape[0] * 0.70))
    roi = crop_bgr[:h]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    # Exclude very dark pixels (floor/shadow) and very desaturated (skin in bright light)
    mask = (hsv[:,:,2] > 40)  # V > 40 (not pure black)
    pixels = hsv[mask]
    if len(pixels) < 10:
        return None
    return pixels  # return all valid pixels for histogram

cap = cv2.VideoCapture(VIDEO)
if not cap.isOpened():
    print(f"Cannot open: {VIDEO}")
    sys.exit(1)

total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"Video: {total} frames")

from ultralytics import YOLO
import torch
model = YOLO("yolov8n.pt")
use_half = torch.cuda.is_available()

all_pixels = []   # all jersey HSV pixels collected
annotated_frames = []

for frame_idx in SAMPLE_FRAMES:
    if frame_idx >= total:
        break
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    if not ret:
        continue

    results = model(frame, classes=[0], conf=0.25, verbose=False, imgsz=640, half=use_half)
    boxes = results[0].boxes.xyxy.cpu().numpy() if results[0].boxes is not None else []

    ann = frame.copy()
    for box in boxes:
        x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
        y1c = max(0, y1); y2c = min(frame.shape[0], y2)
        x1c = max(0, x1); x2c = min(frame.shape[1], x2)
        crop = frame[y1c:y2c, x1c:x2c]
        pixels = jersey_hsv_stats(crop)
        if pixels is not None:
            all_pixels.append(pixels)
            med_h = int(np.median(pixels[:,0]))
            med_s = int(np.median(pixels[:,1]))
            med_v = int(np.median(pixels[:,2]))
            cv2.rectangle(ann, (x1c,y1c),(x2c,y2c),(0,255,0),2)
            cv2.putText(ann, f"H:{med_h} S:{med_s}", (x1c, y1c-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,255,255), 1)

    if len(boxes) >= 3:  # save frames with enough detections
        annotated_frames.append((frame_idx, ann))

cap.release()

# Save annotated frame
if annotated_frames:
    best_frame_idx, best_ann = annotated_frames[len(annotated_frames)//2]
    small = cv2.resize(best_ann, (960, 540))
    cv2.imwrite("data/debug_green.png", small)
    print(f"Saved annotated frame {best_frame_idx}: data/debug_green.png")

# Build hue histogram across all collected jersey pixels
if all_pixels:
    combined = np.vstack(all_pixels)
    print(f"\nTotal jersey pixels sampled: {len(combined)}")

    # Hue histogram (0-180 OpenCV scale)
    hist = np.zeros(180, dtype=int)
    for h_val in combined[:,0]:
        hist[int(h_val)] += 1

    # Find top hue peaks
    from scipy.signal import find_peaks
    peaks, props = find_peaks(hist, height=len(combined)*0.005, distance=10)
    peaks_sorted = sorted(peaks, key=lambda p: hist[p], reverse=True)

    print("\nTop hue peaks (OpenCV H scale 0-180):")
    print(f"  {'H (OpenCV)':>10}  {'H (degrees)':>11}  {'pixel count':>12}  {'likely color'}")
    print("  " + "-"*55)
    color_guess = {
        range(0,10):   "red/brown",   range(170,180): "red",
        range(10,25):  "orange/skin", range(25,35):   "yellow",
        range(35,55):  "yellow-green",range(55,85):   "green",
        range(85,100): "teal",        range(100,130): "blue/navy",
        range(130,160):"purple/blue", range(160,170): "pink/magenta",
    }
    for p in peaks_sorted[:8]:
        deg = int(p * 2)  # OpenCV H is 0-180, degrees is 0-360
        guess = next((v for r,v in color_guess.items() if p in r), "unknown")
        print(f"  {p:>10}  {deg:>11}°  {hist[p]:>12}  {guess}")

    # Build visual hue histogram image
    hist_img = np.zeros((200, 360, 3), dtype=np.uint8)
    max_h = hist.max()
    for i in range(180):
        bar_h = int(hist[i] / max_h * 190)
        color_hsv = np.uint8([[[i, 255, 255]]])
        color_bgr = cv2.cvtColor(color_hsv, cv2.COLOR_HSV2BGR)[0][0]
        cv2.rectangle(hist_img, (i*2, 200-bar_h), (i*2+1, 200),
                      (int(color_bgr[0]), int(color_bgr[1]), int(color_bgr[2])), -1)
    for p in peaks_sorted[:5]:
        cv2.line(hist_img, (p*2, 0), (p*2, 200), (255,255,255), 1)
        cv2.putText(hist_img, str(p), (p*2-8, 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255,255,255), 1)
    cv2.imwrite("data/debug_hues.png", hist_img)
    print("\nSaved hue histogram: data/debug_hues.png")
    print("The two tallest non-skin peaks are your two team colors.")
    print("Skin tone peak is typically H:10-20.")
