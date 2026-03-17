import csv
import os

import cv2
import numpy as np

from .advanced_tracker import AdvancedFeetDetector
from .player_detection import COLORS, hsv2bgr
from .utils.plot_tools import plt_plot

TOPCUT = 60   # remove scoreboard only; 320 cut off far-end players on 720p broadcast
_RESOURCES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "resources")

FLANN_INDEX_KDTREE = 1
flann = cv2.FlannBasedMatcher(
    dict(algorithm=FLANN_INDEX_KDTREE, trees=5),
    dict(checks=50),
)

_H_EMA_ALPHA   = 0.35
_H_MIN_INLIERS = 8


class VideoHandler:

    def __init__(self, pano, video, ball_detector, feet_detector, map_2d):
        self.M1 = np.load(os.path.join(_RESOURCES_DIR, "Rectify1.npy"))
        self.sift = cv2.xfeatures2d.SIFT_create()
        self.pano = pano
        self.video = video
        self.feet_detector = feet_detector
        self.ball_detector = ball_detector
        self.map_2d = map_2d
        self.kp1, self.des1 = self.sift.compute(pano, self.sift.detect(pano))
        self._M_ema = None  # smoothed homography state

    def run_detectors(self, max_frames: int = None, show: bool = True) -> list:
        """
        Main processing loop.

        Args:
            max_frames: Stop after this many frames (None = full video).
            show:       Display live visualisation window.

        Returns:
            List of per-frame tracking dicts (also written to CSV).
        """
        tracking_rows = []
        predictions   = []
        frame_idx     = 0
        fps           = self.video.get(cv2.CAP_PROP_FPS) or 25.0
        prev_positions: dict = {}  # player_id → (x, y) from last frame

        while self.video.isOpened():
            ok, frame = self.video.read()
            if not ok:
                break
            if max_frames is not None and frame_idx >= max_frames:
                break

            frame = frame[TOPCUT:]
            M = self._get_homography(frame)
            if M is None:
                frame_idx += 1
                continue

            frame, self.map_2d, map_2d_text = self.feet_detector.get_players_pos(
                M, self.M1, frame, frame_idx, self.map_2d
            )
            frame, _ = self.ball_detector.ball_tracker(
                M, self.M1, frame, self.map_2d.copy(), map_2d_text, frame_idx
            )

            # Collect tracking data
            timestamp_sec = round(frame_idx / fps, 3)
            frame_tracks = []
            for player in self.feet_detector.players:
                if frame_idx not in player.positions:
                    continue
                x_pos, y_pos = player.positions[frame_idx]
                slot = self.feet_detector.players.index(player)
                confidence = max(
                    0.0,
                    1.0 - self.feet_detector._lost_ages.get(slot, 0) / 15
                ) if isinstance(self.feet_detector, AdvancedFeetDetector) else 1.0

                prev = prev_positions.get(player.ID)
                velocity = round(float(np.hypot(x_pos - prev[0], y_pos - prev[1])), 2) if prev else 0.0
                prev_positions[player.ID] = (x_pos, y_pos)

                row = {
                    "frame":           frame_idx,
                    "timestamp":       timestamp_sec,
                    "player_id":       player.ID,
                    "team":            player.team,
                    "x_position":      x_pos,
                    "y_position":      y_pos,
                    "velocity":        velocity,
                    "ball_possession": int(player.has_ball),
                    "confidence":      round(confidence, 3),
                }
                tracking_rows.append(row)
                frame_tracks.append({
                    "player_id":  player.ID,
                    "team":       player.team,
                    "bbox":       player.previous_bb,
                    "x2d":        int(x_pos),
                    "y2d":        int(y_pos),
                    "velocity":   velocity,
                    "confidence": round(confidence, 3),
                })

            predictions.append({"frame": frame_idx, "tracks": frame_tracks})

            if show:
                vis = np.vstack((
                    frame,
                    cv2.resize(map_2d_text, (frame.shape[1], frame.shape[1] // 2))
                ))
                cv2.imshow("NBA AI — Tracking", vis)
                if cv2.waitKey(1) & 0xFF == 27:
                    break

            frame_idx += 1
            print(f"\r Tracking frame {frame_idx}...", end="", flush=True)

        self.video.release()
        cv2.destroyAllWindows()
        print()

        self._export_csv(tracking_rows)
        return predictions

    def _get_homography(self, frame) -> np.ndarray:
        """SIFT homography with EMA smoothing and inlier quality gate."""
        kp2, des2 = self.sift.compute(frame, self.sift.detect(frame))
        if des2 is None or len(des2) < 4:
            return self._M_ema
        matches = flann.knnMatch(self.des1, des2, k=2)
        good = [m for m, n in matches if m.distance < 0.7 * n.distance]
        if len(good) < 4:
            return self._M_ema
        src = np.float32([self.kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        M, mask = cv2.findHomography(dst, src, cv2.RANSAC, 5.0)
        if M is None:
            return self._M_ema
        inliers = int(mask.sum()) if mask is not None else 0
        if inliers < _H_MIN_INLIERS:
            return self._M_ema
        if self._M_ema is None:
            self._M_ema = M
        else:
            self._M_ema = _H_EMA_ALPHA * M + (1 - _H_EMA_ALPHA) * self._M_ema
        return self._M_ema

    def _export_csv(self, rows: list):
        if not rows:
            print("No tracking data collected.")
            return
        out_path = os.path.join(_RESOURCES_DIR, "..", "data", "tracking_data.csv")
        out_path = os.path.normpath(out_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fieldnames = ["frame", "timestamp", "player_id", "team",
                      "x_position", "y_position", "velocity",
                      "ball_possession", "confidence"]
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Tracking data saved → {out_path}  ({len(rows)} rows)")
