import cv2
import os
import numpy as np

path = os.path.join('data', 'videos', '[FULL GAME] Cleveland Cavaliers vs. Golden State Warriors \uff5c 2016 NBA Finals Game 7 \uff5c NBA on ESPN.mp4')
cap = cv2.VideoCapture(path)

fps = cap.get(cv2.CAP_PROP_FPS)
print(f'FPS: {fps}')
print(f'Total frames: {cap.get(cv2.CAP_PROP_FRAME_COUNT)}')

# Try frame around 3 minutes in (likely actual gameplay)
target_frame = int(fps * 180)  # 3 minutes
cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
ret, f = cap.read()

if ret:
    print(f'Frame {target_frame} shape:', f.shape)
    cv2.imwrite('data/frame_gameplay_full.png', f)
    cv2.imwrite('data/frame_gameplay_topcut320.png', f[320:])
    cv2.imwrite('data/frame_gameplay_topcut60.png', f[60:])

    # Check green channel intensity per row band (court is bright green)
    print('Row band analysis (green channel avg):')
    for y1, y2 in [(0,30),(30,60),(60,100),(100,150),(150,200),(200,280),(280,360),(360,420)]:
        if y2 <= f.shape[0]:
            region = f[y1:y2]
            green_avg = np.mean(region[:,:,1])
            print(f'  rows {y1}-{y2}: green={green_avg:.1f}')

cap.release()
