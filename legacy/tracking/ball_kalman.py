"""
Kalman filter for ball tracking.

Smooths noisy YOLO detections and interpolates ball position across frames
where the basketball is not detected (occluded, out of frame, etc.).

State: [x, y, vx, vy] — court coordinates and velocity
Observation: [x, y]
"""
import numpy as np
from typing import Optional, Tuple


class BallKalman:
    """Constant-velocity Kalman filter for basketball."""

    MAX_MISS = 15   # frames without detection before resetting
    Q_POS    = 2.0  # process noise — position
    Q_VEL    = 15.0 # process noise — velocity (ball can accelerate rapidly)
    R_POS    = 4.0  # observation noise — YOLO detection jitter

    def __init__(self, fps: float = 30.0):
        dt = 1.0 / max(fps, 1.0)

        # State transition (constant velocity model)
        self._F = np.array([
            [1, 0, dt, 0 ],
            [0, 1, 0,  dt],
            [0, 0, 1,  0 ],
            [0, 0, 0,  1 ],
        ], dtype=np.float64)

        self._H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float64)
        self._Q = np.diag([self.Q_POS, self.Q_POS, self.Q_VEL, self.Q_VEL])
        self._R = np.eye(2) * self.R_POS
        self._I = np.eye(4)

        self._x: Optional[np.ndarray] = None
        self._P: Optional[np.ndarray] = None
        self._miss = 0

    def update(
        self, detection: Optional[Tuple[float, float]]
    ) -> Optional[Tuple[float, float, float, float]]:
        """
        Step the filter. detection=(x,y) or None if not detected this frame.
        Returns (x, y, vx, vy) estimated state, or None if filter is uninitialized.
        """
        # Initialize on first detection
        if self._x is None:
            if detection is None:
                return None
            self._x = np.array([detection[0], detection[1], 0.0, 0.0])
            self._P = np.eye(4) * 200.0
            self._miss = 0
            return (float(self._x[0]), float(self._x[1]), 0.0, 0.0)

        # Predict
        self._x = self._F @ self._x
        self._P = self._F @ self._P @ self._F.T + self._Q

        if detection is None:
            self._miss += 1
            if self._miss > self.MAX_MISS:
                self.reset()
                return None
            # Return propagated estimate
            return (float(self._x[0]), float(self._x[1]),
                    float(self._x[2]), float(self._x[3]))

        # Update
        self._miss = 0
        z = np.array([detection[0], detection[1]])
        S = self._H @ self._P @ self._H.T + self._R
        K = self._P @ self._H.T @ np.linalg.inv(S)
        self._x = self._x + K @ (z - self._H @ self._x)
        self._P = (self._I - K @ self._H) @ self._P

        return (float(self._x[0]), float(self._x[1]),
                float(self._x[2]), float(self._x[3]))

    def reset(self):
        self._x = None
        self._P = None
        self._miss = 0
