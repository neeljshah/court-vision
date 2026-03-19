import cv2
import os

panos = ['pano_Short4Mosaicing', 'pano_bos_mia_playoffs', 'pano_sac_por_2025', 'pano_phi_tor_2025', 'pano_enhanced']
for name in panos:
    for ext in ['.png', '.jpg']:
        path = f'resources/panos/{name}{ext}' if name != 'pano_enhanced' else f'resources/{name}{ext}'
        if not os.path.exists(path) and name == 'pano_enhanced':
            path = f'resources/panos/{name}{ext}'
        if os.path.exists(path):
            img = cv2.imread(path)
            if img is not None:
                print(f'{name}: {img.shape[1]}x{img.shape[0]} (WxH)')
