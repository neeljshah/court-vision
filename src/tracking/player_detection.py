import cv2
import numpy as np
from operator import itemgetter

from .utils.plot_tools import plt_plot

COLORS = {  # HSV format: [lower], [upper], [representative for BGR conversion]
    # 'green' = any colored (non-white, non-dark) jersey — covers all team colors
    # across any NBA matchup (purple, blue, gold, wine, etc.)
    'green':   ([0,  30,  40], [179, 255, 220], [50,   30, 180]),
    # 'white' = bright low-saturation jerseys (white home kits)
    'white':   ([0,   0, 160], [179,  25, 255], [255,   0, 255]),
    # referee: dark/grey uniforms
    'referee': ([0,   0,   0], [255,  35,  70], [120,   0,   0]),
}

IOU_TH = 0.2
PAD = 15

# ── Adaptive HSV helpers ──────────────────────────────────────────────────────

def _frame_brightness(frame: np.ndarray) -> float:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 2].mean())


def _adaptive_colors(frame: np.ndarray) -> dict:
    brightness = _frame_brightness(frame)
    dark_factor   = max(0.0, (128 - brightness) / 128)
    bright_factor = max(0.0, (brightness - 128) / 127)
    white_v_lo  = max(130, int(170 - dark_factor * 50))
    green_s_lo  = max(40,  int(60  - dark_factor * 20))
    green_v_lo  = max(20,  int(40  - dark_factor * 20))
    ref_v_hi    = min(90,  int(70  + bright_factor * 20))
    return {
        # Any colored jersey — S floor adjusts for dark lighting, H covers all hues
        'green':   ([0,  max(20, green_s_lo - 10), green_v_lo], [179, 255, 220], COLORS['green'][2]),
        'referee': ([0,  0,                         0],          [255, 35, ref_v_hi], COLORS['referee'][2]),
        'white':   ([0,  0,                         white_v_lo], [179, 25, 255], COLORS['white'][2]),
    }


def hsv2bgr(color_hsv):
    color_bgr = np.array(cv2.cvtColor(np.uint8([[color_hsv]]), cv2.COLOR_HSV2BGR)).ravel()
    return (int(color_bgr[0]), int(color_bgr[1]), int(color_bgr[2]))


class FeetDetector:

    def __init__(self, players):
        from ultralytics import YOLO
        import torch
        self.model = YOLO("yolov8n.pt")
        self._use_half = torch.cuda.is_available()
        self.players = players
        # Warmup — eliminates JIT/CUDA init latency on first real frame
        self.model(np.zeros((640, 640, 3), dtype=np.uint8), verbose=False, half=self._use_half)

    @staticmethod
    def count_non_black(image):
        return int(np.count_nonzero(image))

    @staticmethod
    def bb_intersection_over_union(boxA, boxB):
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])
        interArea = max(0, xB - xA + 1) * max(0, yB - yA + 1)
        boxAArea = (boxA[2] - boxA[0] + 1) * (boxA[3] - boxA[1] + 1)
        boxBArea = (boxB[2] - boxB[0] + 1) * (boxB[3] - boxB[1] + 1)
        iou = interArea / float(boxAArea + boxBArea - interArea)
        return iou

    def get_players_pos(self, M, M1, frame, timestamp, map_2d):
        results = self.model(frame, classes=[0], conf=0.3, verbose=False, imgsz=1280, half=self._use_half)
        boxes   = results[0].boxes.xyxy.cpu().numpy() if results[0].boxes is not None else []

        adaptive_colors = _adaptive_colors(frame)
        warped_kpts = []

        for box in boxes:
            x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
            y1c = max(0, y1);  y2c = min(frame.shape[0], y2)
            x1c = max(0, x1);  x2c = min(frame.shape[1], x2)
            bbox = (y1 - PAD, x1 - PAD, y2 + PAD, x2 + PAD)

            bgr_crop = frame[y1c:y2c, x1c:x2c]
            if bgr_crop.size == 0:
                continue

            jersey_h = max(1, int(bgr_crop.shape[0] * 0.70))
            crop_hsv = cv2.cvtColor(bgr_crop[:jersey_h], cv2.COLOR_BGR2HSV)
            best_mask = [0, '']
            for color in adaptive_colors:
                mask = cv2.inRange(crop_hsv,
                                   np.array(adaptive_colors[color][0]),
                                   np.array(adaptive_colors[color][1]))
                n = self.count_non_black(mask)
                if n > best_mask[0]:
                    best_mask = [n, color]

            if not best_mask[1]:
                continue

            head_x = (x1c + x2c) // 2
            foot_y = y2c
            kpt  = np.array([head_x, foot_y, 1])
            homo = M1 @ (M @ kpt.reshape((3, -1)))
            homo = np.int32(homo / homo[-1]).ravel()

            color_bgr = hsv2bgr(COLORS[best_mask[1]][2])
            warped_kpts.append((homo, color_bgr, best_mask[1], bbox))
            cv2.circle(frame, (head_x, foot_y), 2, color_bgr, 5)

        for homo, color_bgr, color_key, bbox in warped_kpts:
            if not (0 <= homo[0] < map_2d.shape[1] and 0 <= homo[1] < map_2d.shape[0]):
                continue
            iou_scores = []
            for player in self.players:
                if player.team == color_key and player.previous_bb is not None:
                    iou_val = self.bb_intersection_over_union(bbox, player.previous_bb)
                    if iou_val >= IOU_TH:
                        iou_scores.append((iou_val, player))

            if iou_scores:
                best = max(iou_scores, key=itemgetter(0))
                best[1].previous_bb = bbox
                best[1].positions[timestamp] = (homo[0], homo[1])
            else:
                for player in self.players:
                    if player.team == color_key and player.previous_bb is None:
                        player.previous_bb = bbox
                        player.positions[timestamp] = (homo[0], homo[1])
                        break

        for player in self.players:
            if player.positions and (timestamp - max(player.positions)) >= 7:
                player.positions = {}
                player.previous_bb = None
                player.has_ball = False

        return self._render(frame, map_2d, timestamp)

    def _render(self, frame, map_2d, timestamp):
        map_2d_text = map_2d.copy()
        for p in self.players:
            if p.team == 'referee' or timestamp not in p.positions:
                continue
            pos = p.positions[timestamp]
            try:
                cv2.circle(map_2d,      pos, 10, p.color, 7)
                cv2.circle(map_2d,      pos, 13, (0, 0, 0), 3)
                cv2.circle(map_2d_text, pos, 25, p.color, -1)
                cv2.circle(map_2d_text, pos, 27, (0, 0, 0), 5)
                tw, th = cv2.getTextSize(str(p.ID), cv2.FONT_HERSHEY_SIMPLEX, 1.5, 3)[0]
                orig = (pos[0] - tw // 2, pos[1] + th // 2)
                cv2.putText(map_2d_text, str(p.ID), orig,
                            cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3, cv2.LINE_AA)
            except Exception:
                pass
        return frame, map_2d, map_2d_text
