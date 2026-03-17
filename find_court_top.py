import cv2
import os
import numpy as np

path = os.path.join('data', 'videos', '[FULL GAME] Cleveland Cavaliers vs. Golden State Warriors \uff5c 2016 NBA Finals Game 7 \uff5c NBA on ESPN.mp4')
cap = cv2.VideoCapture(path)
fps = cap.get(cv2.CAP_PROP_FPS)

# Try a frame 5 minutes in (well into gameplay, wide angle court view)
for target_min in [5, 7, 10, 15]:
    target_frame = int(fps * target_min * 60)
    cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
    ret, f = cap.read()
    if ret:
        fname = f'data/frame_{target_min}min.png'
        cv2.imwrite(fname, f)
        print(f'Saved {fname}')

cap.release()
