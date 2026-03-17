import cv2
import os
import numpy as np

path = os.path.join('data', 'videos', '[FULL GAME] Cleveland Cavaliers vs. Golden State Warriors \uff5c 2016 NBA Finals Game 7 \uff5c NBA on ESPN.mp4')
cap = cv2.VideoCapture(path)
# Jump to frame 100 (should be in gameplay)
cap.set(cv2.CAP_PROP_POS_FRAMES, 100)
ret, f = cap.read()
cap.release()

if ret:
    print('Full frame shape:', f.shape)
    # Check what a TOPCUT of 320 looks like vs smaller values
    print('With TOPCUT=320, remaining height:', f.shape[0] - 320, '(', 320/f.shape[0]*100, '% cut)')
    print('With TOPCUT=60, remaining height:', f.shape[0] - 60, '(', 60/f.shape[0]*100, '% cut)')
    print('With TOPCUT=100, remaining height:', f.shape[0] - 100, '(', 100/f.shape[0]*100, '% cut)')

    # Save frame slices to inspect
    cv2.imwrite('data/frame_full.png', f)
    cv2.imwrite('data/frame_topcut320.png', f[320:])
    cv2.imwrite('data/frame_topcut60.png', f[60:])
    print('Saved frame images for inspection')

    # Check the top 320 pixels - look for scoreboard/TV graphics
    top_region = f[:320]
    print('Top 320px - average brightness:', np.mean(top_region))

    # Check rows 0-50, 50-100, 100-200, 200-320
    for y1, y2 in [(0,50),(50,100),(100,200),(200,320),(320,400)]:
        region = f[y1:y2]
        print(f'  rows {y1}-{y2}: avg brightness={np.mean(region):.1f}, avg green channel={np.mean(region[:,:,1]):.1f}')
