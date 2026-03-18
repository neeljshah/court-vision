"""Test SIFT inliers between video frames and pano."""
import cv2, sys, numpy as np
sys.stdout.reconfigure(encoding='utf-8')

TOPCUT = 60
pano = cv2.imread('resources/panos/pano_gsw_lakers_2025.png')
if pano is None:
    print('pano not found'); exit()
print(f'Pano: {pano.shape[1]}x{pano.shape[0]}')

sift = cv2.xfeatures2d.SIFT_create()
FLANN = cv2.FlannBasedMatcher({'algorithm': 1, 'trees': 5}, {'checks': 50})
kp1, des1 = sift.compute(pano, sift.detect(pano))
print(f'Pano keypoints: {len(kp1)}')

cap = cv2.VideoCapture('data/videos/gsw_lakers_2025.mp4')
for fno in [750, 1000, 1500, 2000, 5000]:
    cap.set(cv2.CAP_PROP_POS_FRAMES, fno)
    ok, frame = cap.read()
    if not ok:
        print(f'Frame {fno}: could not read'); continue
    frame = frame[TOPCUT:]
    kp2, des2 = sift.compute(frame, sift.detect(frame))
    if des2 is None or len(des2) < 4:
        print(f'Frame {fno}: no features'); continue
    matches = FLANN.knnMatch(des1, des2, k=2)
    good = [m for m,n in matches if m.distance < 0.7*n.distance]
    if len(good) >= 4:
        src = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1,1,2)
        dst = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1,1,2)
        M, mask = cv2.findHomography(dst, src, cv2.RANSAC, 5.0)
        inliers = int(mask.sum()) if mask is not None else 0
    else:
        inliers = 0
    print(f'Frame {fno}: {len(kp2)} kpts, {len(good)} matches, {inliers} inliers')
cap.release()
