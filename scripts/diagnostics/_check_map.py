import numpy as np
import cv2
import os

rect = np.load('resources/Rectify1.npy')
print('Rectify1 shape:', rect.shape)
print('Rectify1:', rect)

map_files = [f for f in os.listdir('resources/') if any(x in f.lower() for x in ['court', 'pano', 'map', 'rect'])]
print('Resources:', map_files)

# Check court_map if it exists
for ext in ['.jpg', '.png', '.npy']:
    for name in ['court_map', 'pano_enhanced', 'court']:
        path = f'resources/{name}{ext}'
        if os.path.exists(path):
            print(f'Found: {path}')
            if ext == '.npy':
                arr = np.load(path)
                print(f'  Shape: {arr.shape}')
            else:
                img = cv2.imread(path)
                if img is not None:
                    print(f'  Shape: {img.shape}')
