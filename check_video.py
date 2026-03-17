import cv2
import os
path = os.path.join('data', 'videos', '[FULL GAME] Cleveland Cavaliers vs. Golden State Warriors \uff5c 2016 NBA Finals Game 7 \uff5c NBA on ESPN.mp4')
print('exists:', os.path.exists(path))
cap = cv2.VideoCapture(path)
print('opened:', cap.isOpened())
ret, f = cap.read()
print('ret:', ret)
if ret:
    print('shape:', f.shape)
    print('height:', f.shape[0])
    print('width:', f.shape[1])
cap.release()
