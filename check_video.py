import cv2, sys
path = sys.argv[1]
cap = cv2.VideoCapture(path)
frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS) or 30
print(f"frames: {frames}, fps: {fps:.1f}, duration: {frames/fps:.1f}s")
cap.release()
