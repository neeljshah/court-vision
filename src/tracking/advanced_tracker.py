"""
advanced_tracker.py — Enhanced basketball player tracking

Improvements over baseline FeetDetector:
  - Kalman filtering: predicts player position when detection fails (handles occlusion)
  - Hungarian algorithm: globally optimal assignment (eliminates greedy ID switches)
  - Appearance embeddings: HSV histogram per player for re-identification
  - Lost-track gallery: re-IDs players who leave and re-enter the frame
  - Confidence scoring: per-track quality metric

Drop-in replacement: AdvancedFeetDetector has the same interface as FeetDetector.
"""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from .player_detection import FeetDetector, COLORS, hsv2bgr, PAD, _adaptive_colors

try:
    from scipy.optimize import linear_sum_assignment
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

try:
    from .jersey_ocr import dominant_hsv_cluster as _dominant_hsv
    _HAS_OCR = True
except ImportError:
    _HAS_OCR = False

try:
    from .player_identity import JerseyVotingBuffer as _JerseyVotingBuffer
    _HAS_VOTING = True
except ImportError:
    _HAS_VOTING = False

# ── Tuning constants ──────────────────────────────────────────────────────────
COST_GATE       = 0.80   # reject any assignment with cost above this
APPEARANCE_W    = 0.25   # weight of appearance vs IoU in cost matrix
MAX_LOST        = 90     # frames before evicting a lost track (~3 s at 30 fps)
GALLERY_TTL     = 300    # frames a gallery entry stays valid (~10 s at 30 fps)
REID_THRESH     = 0.45   # max appearance distance to accept a re-ID
REID_TIE_BAND   = 0.05   # appearance-distance window for jersey-number tiebreaker
HIST_BINS       = 32     # bins per channel for HSV histogram
KF_PROC_NOISE   = 5e-2
KF_MEAS_NOISE   = 1e-1
APPEAR_ALPHA    = 0.7    # EMA weight for appearance update (higher = more stable)
MAX_2D_JUMP     = 250    # max court pixels a player can move between frames (~2× court width/sec at 30fps)


# ── Kalman filter helpers ─────────────────────────────────────────────────────

def _make_kf(bbox: Tuple) -> cv2.KalmanFilter:
    """6D state [cx, cy, vx, vy, w, h], 4D measurement [cx, cy, w, h]."""
    kf = cv2.KalmanFilter(6, 4)
    y1, x1, y2, x2 = bbox
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    w,  h  = float(x2 - x1), float(y2 - y1)

    kf.transitionMatrix = np.array([
        [1, 0, 1, 0, 0, 0],
        [0, 1, 0, 1, 0, 0],
        [0, 0, 1, 0, 0, 0],
        [0, 0, 0, 1, 0, 0],
        [0, 0, 0, 0, 1, 0],
        [0, 0, 0, 0, 0, 1],
    ], dtype=np.float32)
    kf.measurementMatrix = np.array([
        [1, 0, 0, 0, 0, 0],
        [0, 1, 0, 0, 0, 0],
        [0, 0, 0, 0, 1, 0],
        [0, 0, 0, 0, 0, 1],
    ], dtype=np.float32)
    kf.processNoiseCov     = np.eye(6, dtype=np.float32) * KF_PROC_NOISE
    kf.measurementNoiseCov = np.eye(4, dtype=np.float32) * KF_MEAS_NOISE
    kf.errorCovPost        = np.eye(6, dtype=np.float32)
    kf.statePost = np.array([cx, cy, 0, 0, w, h], dtype=np.float32).reshape(6, 1)
    return kf


def _kf_predict_bbox(kf: cv2.KalmanFilter) -> Tuple:
    """Advance Kalman state and return predicted (y1, x1, y2, x2)."""
    pred = kf.predict()
    cx, cy = pred[0, 0], pred[1, 0]
    w,  h  = abs(pred[4, 0]) or 40.0, abs(pred[5, 0]) or 80.0
    return (cy - h / 2, cx - w / 2, cy + h / 2, cx + w / 2)


def _kf_correct(kf: cv2.KalmanFilter, bbox: Tuple):
    """Update Kalman with a confirmed measurement."""
    y1, x1, y2, x2 = bbox
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    w,  h  = float(x2 - x1), float(y2 - y1)
    kf.correct(np.array([cx, cy, w, h], dtype=np.float32).reshape(4, 1))


# ── Appearance embedding ──────────────────────────────────────────────────────

def _compute_appearance(crop_bgr: np.ndarray) -> np.ndarray:
    """
    Compute appearance embedding from a player bounding-box crop.

    Returns a 99-dim vector when jersey_ocr is available (96-dim L1-normalised
    HSV histogram concatenated with a 3-dim normalised dominant-HSV-cluster vector),
    or a 96-dim vector as fallback when jersey_ocr is not importable.

    Note: k-means clustering is called here (gallery writes), NOT in the per-frame
    matching loop, to keep inference latency low.

    Args:
        crop_bgr: BGR crop of a player bounding box.

    Returns:
        float32 ndarray, shape (99,) or (96,).
    """
    if crop_bgr is None or crop_bgr.size == 0:
        return np.zeros(HIST_BINS * 3, dtype=np.float32)
    roi = crop_bgr[: max(1, int(crop_bgr.shape[0] * 0.70))]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    parts = []
    for ch, (lo, hi) in enumerate([(0, 180), (0, 256), (0, 256)]):
        hist = cv2.calcHist([hsv], [ch], None, [HIST_BINS], [lo, hi]).flatten()
        s = hist.sum()
        parts.append(hist / s if s > 0 else hist)
    hist_emb = np.concatenate(parts).astype(np.float32)
    if _HAS_OCR:
        cluster = _dominant_hsv(crop_bgr)                # shape (3,)
        cluster_norm = cluster / (cluster.max() + 1e-6)  # normalise to [0, 1]
        return np.concatenate([hist_emb, cluster_norm])  # shape (99,)
    return hist_emb                                       # shape (96,) — unchanged fallback


def _appear_dist(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> float:
    """Histogram intersection distance in [0, 1]. 0 = identical."""
    if a is None or b is None:
        return 0.5  # neutral when unknown
    return float(1.0 - np.minimum(a, b).sum())


# ── IoU ───────────────────────────────────────────────────────────────────────

def _iou(a: Tuple, b: Tuple) -> float:
    ay1, ax1, ay2, ax2 = a
    by1, bx1, by2, bx2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    return inter / (area_a + area_b - inter)


# ── Hungarian / greedy assignment ─────────────────────────────────────────────

def _assign(cost: np.ndarray) -> List[Tuple[int, int]]:
    """Return (row, col) pairs that minimise total cost."""
    if cost.size == 0:
        return []
    if _HAS_SCIPY:
        rows, cols = linear_sum_assignment(cost)
        return list(zip(rows.tolist(), cols.tolist()))
    # Greedy fallback
    used: set = set()
    pairs = []
    for r in range(cost.shape[0]):
        best_c, best_v = -1, float("inf")
        for c in range(cost.shape[1]):
            if c not in used and cost[r, c] < best_v:
                best_v, best_c = cost[r, c], c
        if best_c >= 0:
            pairs.append((r, best_c))
            used.add(best_c)
    return pairs


# ── AdvancedFeetDetector ──────────────────────────────────────────────────────

class AdvancedFeetDetector(FeetDetector):
    """
    Drop-in replacement for FeetDetector.

    Same interface (get_players_pos returns frame, map_2d, map_2d_text).
    Internally replaces IoU-greedy matching with:
      1. Kalman prediction per player slot
      2. Hungarian assignment (IoU + appearance cost)
      3. Appearance-based re-ID from lost-track gallery
    """

    def __init__(self, players):
        super().__init__(players)
        from .tracker_config import load_config
        _cfg = load_config()
        self._conf_threshold    = _cfg["conf_threshold"]
        self._appearance_w      = _cfg["appearance_w"]
        self._max_lost          = _cfg["max_lost_frames"]
        self._reid_thresh       = _cfg.get("reid_threshold",     REID_THRESH)
        self._gallery_ttl       = _cfg.get("gallery_ttl",        GALLERY_TTL)
        self._kalman_fill_win   = _cfg.get("kalman_fill_window", 5)

        n = len(players)
        self._kalmans:      Dict[int, cv2.KalmanFilter] = {}
        self._appearances:  Dict[int, np.ndarray]       = {}
        self._lost_ages:    Dict[int, int]              = {i: 0 for i in range(n)}
        self._gallery:      Dict[int, np.ndarray]       = {}  # slot → appearance snapshot
        self._gallery_ages: Dict[int, int]              = {}  # slot → frames since archived
        self._kf_pred:      Dict[int, Tuple]            = {}  # predicted bboxes this frame
        self._jersey_buf:   Optional[object]            = None  # set externally after construction

    # ── helpers ───────────────────────────────────────────────────────────

    def _slot(self, player) -> int:
        return self.players.index(player)

    def _update_appearance(self, slot: int, crop_bgr: np.ndarray):
        emb = _compute_appearance(crop_bgr)
        if slot in self._appearances:
            self._appearances[slot] = (APPEAR_ALPHA * self._appearances[slot]
                                       + (1 - APPEAR_ALPHA) * emb)
        else:
            self._appearances[slot] = emb

    def _activate_slot(self, slot: int, det: dict, timestamp: int):
        """
        Assign a detection to a player slot and update all state.

        Resets the jersey voting buffer for the slot when it was previously
        occupied, preventing stale vote counts from a prior occupant carrying
        over to a new player (RESEARCH.md Pitfall 3).
        """
        # Reset jersey voting state for evicted slot (RESEARCH.md Pitfall 3)
        if (_HAS_VOTING
                and hasattr(self, "_jersey_buf")
                and self._jersey_buf is not None
                and self.players[slot].previous_bb is not None):
            self._jersey_buf.reset_slot(slot)

        p = self.players[slot]
        p.previous_bb = det["bbox"]
        new_pos = (det["homo"][0], det["homo"][1])
        # Velocity clamp: if projected position jumps > MAX_2D_JUMP from the last
        # known position, the SIFT homography is noisy — keep the last known position.
        # After eviction p.positions is cleared to {}, so the clamp never fires for
        # freshly re-IDed players (they start with no position history).
        if p.positions:
            last_pos = p.positions[max(p.positions)]
            dist = float(np.hypot(new_pos[0] - last_pos[0], new_pos[1] - last_pos[1]))
            if dist > MAX_2D_JUMP:
                new_pos = last_pos
        p.positions[timestamp] = new_pos
        if slot in self._kalmans:
            _kf_correct(self._kalmans[slot], det["bbox"])
        else:
            self._kalmans[slot] = _make_kf(det["bbox"])
        self._update_appearance(slot, det["crop_bgr"])
        self._lost_ages[slot] = 0
        self._gallery.pop(slot, None)
        self._gallery_ages.pop(slot, None)

    # ── per-team Hungarian matching ───────────────────────────────────────

    def _match_team(
        self, team: str, detections: List[dict]
    ) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        """
        Returns (matched slot-det pairs, unmatched slots, unmatched det indices).
        Cost = (1-IoU)*(1-APPEARANCE_W) + appearance_dist*APPEARANCE_W
        """
        slots = [self._slot(p) for p in self.players if p.team == team]
        dets  = [i for i, d in enumerate(detections) if d["team"] == team]

        if not slots or not dets:
            return [], slots, dets

        cost = np.ones((len(slots), len(dets)), dtype=np.float32) * 2.0

        for ri, slot in enumerate(slots):
            pred = self._kf_pred.get(slot)
            for ci, di in enumerate(dets):
                det_bbox = detections[di]["bbox"]
                iou_val  = _iou(pred, det_bbox) if pred is not None else 0.0
                app_dist = _appear_dist(
                    self._appearances.get(slot),
                    _compute_appearance(detections[di]["crop_bgr"])
                    if detections[di]["crop_bgr"] is not None else None,
                )
                cost[ri, ci] = ((1.0 - iou_val) * (1 - self._appearance_w)
                                + app_dist * self._appearance_w)

        matched, unmatched_slots, unmatched_dets = [], list(range(len(slots))), list(range(len(dets)))
        for ri, ci in _assign(cost):
            if cost[ri, ci] <= COST_GATE:
                matched.append((slots[ri], dets[ci]))
                unmatched_slots.remove(ri)
                unmatched_dets.remove(ci)

        return matched, [slots[i] for i in unmatched_slots], [dets[i] for i in unmatched_dets]

    # ── re-ID from gallery ────────────────────────────────────────────────

    def _reid(
        self,
        det: dict,
        confirmed_jerseys: Optional[Dict[int, int]] = None,
        det_slot: Optional[int] = None,
    ) -> Optional[int]:
        """
        Match an unmatched detection against the lost-track gallery.

        When confirmed_jerseys is provided and the top two gallery candidates are
        within REID_TIE_BAND appearance distance, the candidate whose confirmed
        jersey number matches the detection's confirmed jersey is preferred
        (jersey-number tiebreaker).

        Args:
            det: Detection dict with keys 'team', 'bbox', 'crop_bgr'.
            confirmed_jerseys: Optional mapping of slot → confirmed jersey number.
                               When provided, used as tiebreaker for ambiguous matches.
            det_slot: Optional tracker slot associated with this detection's prior
                      identity (used to look up det_jersey in confirmed_jerseys).

        Returns:
            Gallery slot index if re-ID succeeds, else None.
        """
        det_app = (_compute_appearance(det["crop_bgr"])
                   if det["crop_bgr"] is not None else None)

        # Build sorted candidate list: [(slot, dist), ...] ascending by dist
        candidates = []
        for slot, gal_app in self._gallery.items():
            if self.players[slot].team != det["team"]:
                continue
            dist = _appear_dist(det_app, gal_app)
            candidates.append((slot, dist))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[1])

        # Jersey number tiebreaker for ambiguous appearance matches.
        # When top two candidates are within REID_TIE_BAND, prefer the one whose
        # confirmed jersey matches the detection's confirmed jersey (RESEARCH.md Pattern 4).
        if (confirmed_jerseys is not None
                and len(candidates) >= 2
                and abs(candidates[0][1] - candidates[1][1]) < REID_TIE_BAND):
            det_jersey = confirmed_jerseys.get(det_slot) if det_slot is not None else None
            for cand_slot, _dist in candidates[:2]:
                cand_jersey = confirmed_jerseys.get(cand_slot)
                if det_jersey is not None and cand_jersey == det_jersey:
                    return cand_slot   # prefer jersey-number match

        best_slot, best_dist = candidates[0]
        if best_dist > self._reid_thresh:
            return None
        return best_slot

    # ── main override ─────────────────────────────────────────────────────

    def get_players_pos(self, M, M1, frame, timestamp, map_2d):
        # ── Step 1: Advance all Kalman filters → store predictions ────────
        self._kf_pred = {}
        for slot, kf in self._kalmans.items():
            self._kf_pred[slot] = _kf_predict_bbox(kf)
            # Update previous_bb with predicted position so ball tracker stays accurate
            if self.players[slot].previous_bb is not None:
                self.players[slot].previous_bb = self._kf_pred[slot]

        # ── Step 2: YOLOv8 inference ──────────────────────────────────────
        yolo_results = self.model(frame, classes=[0], conf=self._conf_threshold, verbose=False, imgsz=1280, half=self._use_half)
        boxes_xyxy   = (yolo_results[0].boxes.xyxy.cpu().numpy()
                        if yolo_results[0].boxes is not None else [])

        if len(boxes_xyxy) == 0:
            self._age_all(timestamp)
            return self._render(frame, map_2d, timestamp)

        # ── Step 3: Build detection list (bbox, team, crop, court pos) ────
        adaptive_colors = _adaptive_colors(frame)
        detections: List[dict] = []
        for box in boxes_xyxy:
            x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
            y1c = max(0, y1);  y2c = min(frame.shape[0], y2)
            x1c = max(0, x1);  x2c = min(frame.shape[1], x2)
            bbox     = (y1 - PAD, x1 - PAD, y2 + PAD, x2 + PAD)
            bgr_crop = frame[y1c:y2c, x1c:x2c]
            if bgr_crop.size == 0:
                continue

            # Team classification via HSV
            jersey_h = max(1, int(bgr_crop.shape[0] * 0.70))
            hsv_crop = cv2.cvtColor(bgr_crop[:jersey_h], cv2.COLOR_BGR2HSV)
            team, best_n = "", 0
            for color_key in adaptive_colors:
                mask_c = cv2.inRange(hsv_crop,
                                     np.array(adaptive_colors[color_key][0]),
                                     np.array(adaptive_colors[color_key][1]))
                n = int(cv2.countNonZero(mask_c))
                if n > best_n:
                    best_n, team = n, color_key

            if not team:
                continue

            # Unify all non-referee players into the "green" pool so all 10
            # unified player slots can be used regardless of jersey color.
            if team == "white":
                team = "green"

            # 2D court projection
            head_x = (x1c + x2c) // 2
            foot_y = y2c
            kpt  = np.array([head_x, foot_y, 1])
            homo = M1 @ (M @ kpt.reshape(3, 1))
            homo = np.int32(homo / homo[-1]).ravel()

            if not (0 <= homo[0] < map_2d.shape[1] and 0 <= homo[1] < map_2d.shape[0]):
                continue

            color_bgr = hsv2bgr(COLORS[team][2])
            cv2.circle(frame, (head_x, foot_y), 2, color_bgr, 5)

            detections.append({
                "bbox":     bbox,
                "team":     team,
                "homo":     homo,
                "color":    color_bgr,
                "crop_bgr": bgr_crop if bgr_crop.size > 0 else None,
            })

        # ── Step 4: Hungarian matching per team ───────────────────────────
        all_unmatched_dets: List[int] = []

        for team in ("green", "white", "referee"):
            matched, unmatched_slots, unmatched_dets = self._match_team(team, detections)

            for slot, di in matched:
                self._activate_slot(slot, detections[di], timestamp)

            for slot in unmatched_slots:
                self._lost_ages[slot] = self._lost_ages.get(slot, 0) + 1
                if self._lost_ages[slot] >= self._max_lost:
                    # Archive appearance before evicting
                    if slot in self._appearances:
                        self._gallery[slot] = self._appearances[slot].copy()
                        self._gallery_ages[slot] = 0
                    p = self.players[slot]
                    p.previous_bb = None
                    p.positions   = {}
                    p.has_ball    = False
                    self._kalmans.pop(slot, None)
                    self._appearances.pop(slot, None)
                    self._lost_ages[slot] = 0

            all_unmatched_dets.extend(unmatched_dets)

        # ── Age gallery entries and evict stale ones ──────────────────────
        for slot in list(self._gallery_ages.keys()):
            self._gallery_ages[slot] += 1
            if self._gallery_ages[slot] >= self._gallery_ttl:
                self._gallery.pop(slot, None)
                self._gallery_ages.pop(slot, None)

        # ── Step 5: Re-ID unmatched detections from lost-track gallery ────
        truly_new: List[int] = []
        for di in all_unmatched_dets:
            slot = self._reid(detections[di])
            if slot is not None:
                self._activate_slot(slot, detections[di], timestamp)
            else:
                truly_new.append(di)

        # ── Step 6: Assign genuinely new detections to free slots ─────────
        for di in truly_new:
            det  = detections[di]
            for p in self.players:
                if p.team == det["team"] and p.previous_bb is None:
                    self._activate_slot(self._slot(p), det, timestamp)
                    break

        # ── Step 7: Kalman fill for briefly-lost players (lost_age ≤ 5) ──
        # When YOLO misses a player for 1-5 frames, inject the Kalman-predicted
        # court position so the track stays continuous — eliminates short gaps
        # that would otherwise become raw id_switches in the evaluator.
        for p in self.players:
            slot = self._slot(p)
            lost_age = self._lost_ages.get(slot, 0)
            if (0 < lost_age <= self._kalman_fill_win
                    and slot in self._kf_pred
                    and p.previous_bb is not None
                    and timestamp not in p.positions):
                pred_bbox = self._kf_pred[slot]
                y1p, x1p, y2p, x2p = pred_bbox
                hx = int((x1p + x2p) / 2)
                hy = int(y2p)
                if 0 <= hx < frame.shape[1] and 0 <= hy < frame.shape[0]:
                    kpt  = np.array([hx, hy, 1], dtype=np.float64)
                    try:
                        homo = M1 @ (M @ kpt.reshape(3, 1))
                        if abs(homo[2, 0]) > 1e-6:
                            homo = np.int32(homo / homo[2, 0]).ravel()
                            if (0 <= homo[0] < map_2d.shape[1]
                                    and 0 <= homo[1] < map_2d.shape[0]):
                                p.positions[timestamp] = (homo[0], homo[1])
                    except Exception:
                        pass

        # ── Step 8: Same-team duplicate suppression ───────────────────────
        # If two players on the same team project to within DUPLICATE_DIST of
        # each other, the lower-confidence track (higher lost_age) is likely
        # a stale/frozen position from the velocity clamp — remove it so it
        # doesn't corrupt spatial metrics or inflate duplicate_detections.
        _DUP_DIST = 130  # matches evaluate.py DUPLICATE_DIST
        for team in ("green", "white", "referee"):
            team_slots = [
                (self._slot(p), p)
                for p in self.players
                if p.team == team and timestamp in p.positions
            ]
            for i in range(len(team_slots)):
                slot_i, pi = team_slots[i]
                if timestamp not in pi.positions:
                    continue
                xi, yi = pi.positions[timestamp]
                for j in range(i + 1, len(team_slots)):
                    slot_j, pj = team_slots[j]
                    if timestamp not in pj.positions:
                        continue
                    xj, yj = pj.positions[timestamp]
                    if float(np.hypot(xi - xj, yi - yj)) < _DUP_DIST:
                        # Keep the track with lower lost_age (fresher detection)
                        age_i = self._lost_ages.get(slot_i, 0)
                        age_j = self._lost_ages.get(slot_j, 0)
                        if age_i >= age_j:
                            del pi.positions[timestamp]
                            break  # pi removed; stop checking pi vs others
                        else:
                            del pj.positions[timestamp]

        return self._render(frame, map_2d, timestamp)

    # ── housekeeping ──────────────────────────────────────────────────────

    def _age_all(self, timestamp: int):
        """Age all tracks when a frame produces zero detections."""
        for i, p in enumerate(self.players):
            if p.previous_bb is not None:
                self._lost_ages[i] = self._lost_ages.get(i, 0) + 1
                if self._lost_ages[i] >= MAX_LOST:
                    if i in self._appearances:
                        self._gallery[i] = self._appearances[i].copy()
                        self._gallery_ages[i] = 0
                    p.previous_bb = None
                    p.positions   = {}
                    p.has_ball    = False
                    self._kalmans.pop(i, None)
                    self._lost_ages[i] = 0
        for slot in list(self._gallery_ages.keys()):
            self._gallery_ages[slot] += 1
            if self._gallery_ages[slot] >= self._gallery_ttl:
                self._gallery.pop(slot, None)
                self._gallery_ages.pop(slot, None)


# ── Debug visualisation ───────────────────────────────────────────────────────

def visualize_tracking(
    video_path: str,
    predictions: List[dict],
    output_path: Optional[str] = None,
    trail_length: int = 30,
):
    """
    Render annotated video: bounding boxes, player IDs, confidence, and trails.

    Args:
        video_path:   Original input video.
        predictions:  From track_video()["predictions"].
        output_path:  Write annotated .mp4 here if provided.
        trail_length: Frames of trail to draw per player.
    """
    TOPCUT = 60   # remove scoreboard only; 320 cut off far-end players on 720p broadcast
    TEAM_COLORS = {"green": (0, 200, 0), "white": (200, 200, 200), "referee": (0, 0, 200)}

    pred_by_frame = {f["frame"]: f["tracks"] for f in predictions}
    trails: Dict[str, list] = defaultdict(list)

    cap    = cv2.VideoCapture(video_path)
    writer = None

    if output_path:
        _, f0 = cap.read()
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        if f0 is not None:
            h, w = f0[TOPCUT:].shape[:2]
            writer = cv2.VideoWriter(
                output_path, cv2.VideoWriter_fourcc(*"mp4v"), 25.0, (w, h)
            )

    frame_idx = 0
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        frame = frame[TOPCUT:]

        for t in pred_by_frame.get(frame_idx, []):
            key   = f"{t['team']}_{t['player_id']}"
            color = TEAM_COLORS.get(t["team"], (128, 128, 128))
            conf  = t.get("confidence", 1.0)
            bbox  = t.get("bbox")

            if bbox:
                y1, x1, y2, x2 = [int(v) for v in bbox]
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, max(1, int(conf * 3)))
                label = f"{t['team'][0].upper()}{t['player_id']} {conf:.2f}"
                cv2.putText(frame, label, (x1, max(0, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                trails[key].append((cx, cy))
            if len(trails[key]) > trail_length:
                trails[key].pop(0)
            pts = trails[key]
            for i in range(1, len(pts)):
                alpha = i / len(pts)
                c = tuple(int(v * alpha) for v in color)
                cv2.line(frame, pts[i - 1], pts[i], c, 2)

        cv2.imshow("Advanced Tracker — Debug", frame)
        if writer:
            writer.write(frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break
        frame_idx += 1

    cap.release()
    if writer:
        writer.release()
        print(f"Debug video saved → {output_path}")
    cv2.destroyAllWindows()
