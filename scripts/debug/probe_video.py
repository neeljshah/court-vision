"""probe_video.py — print duration and save sample frames to find gameplay start."""
import cv2, os, sys

VIDEO = os.path.join(os.path.dirname(__file__), "data", "videos",
    "[FULL GAME] Cleveland Cavaliers vs. Golden State Warriors \uff5c 2016 NBA Finals Game 7 \uff5c NBA on ESPN.mp4")

cap   = cv2.VideoCapture(VIDEO)
fps   = cap.get(cv2.CAP_PROP_FPS)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"FPS: {fps:.1f}  |  Frames: {total}  |  Duration: {total/fps/60:.1f} min")

# Sample one frame every 2 minutes and save as JPEG
out_dir = os.path.join(os.path.dirname(__file__), "data", "probe_frames")
os.makedirs(out_dir, exist_ok=True)

interval = int(fps * 120)   # every 2 minutes
for i, frame_no in enumerate(range(0, total, interval)):
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
    ok, frame = cap.read()
    if not ok:
        break
    t_min = frame_no / fps / 60
    fname = os.path.join(out_dir, f"t{t_min:05.1f}min_f{frame_no}.jpg")
    cv2.imwrite(fname, frame)
    print(f"  saved {fname}")

cap.release()
print("Done — open data/probe_frames/ to find where gameplay starts.")
