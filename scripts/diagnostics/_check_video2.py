import cv2
clips = ['bos_mia_playoffs']
for c in clips:
    cap = cv2.VideoCapture(f'data/videos/{c}.mp4')
    fc = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f'{c}: frame_count={fc}, fps={fps:.1f}')
    # Also check actual detection rate at ball_x2d>0
    cap.release()

import pandas as pd
df = pd.read_csv('data/ball_tracking.csv')
print('ball_tracking rows:', len(df))
print('detected=1:', (df.detected==1).sum())
print('ball_x2d > 0:', (df.ball_x2d.fillna(0).astype(float) > 0).sum())
# look at detected=1 but ball_x2d not>0
d1 = df[df.detected==1]
print('detected=1 with ball_x2d <= 0 or NaN:', (d1.ball_x2d.fillna(0).astype(float) <= 0).sum())
