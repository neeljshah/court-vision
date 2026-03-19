import cv2
clips = ['bos_mia_playoffs', 'sac_por_2025', 'phi_tor_2025']
for c in clips:
    cap = cv2.VideoCapture(f'data/videos/{c}.mp4')
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(c, w, h, fps, total)
    cap.release()
