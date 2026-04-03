"""Quick script to check FPS and duration of pending game videos."""
import cv2
import os

games = [
    '0022401183', '0022401185', '0022401198',
    '0022400625', '0022400921', '0022400923',
    '0022401175', '0022401190', '0022401194',
    '0022401196', '0022400710', '0022400689',
    '0022400690', '0022400687',
]
base = r'C:\Users\neelj\nba-ai-system\data\videos\full_games'
for gid in games:
    path = os.path.join(base, f'{gid}.mp4')
    if not os.path.exists(path):
        print(f'{gid}: MISSING')
        continue
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    dur_min = total / fps / 60 if fps > 0 else 0
    print(f'{gid}: fps={fps:.0f}  frames={total}  duration={dur_min:.1f}min')
