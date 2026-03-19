"""
Court homography — maps broadcast pixel coordinates to real NBA court coordinates.

NBA court: 94ft × 50ft
Origin: top-left corner of court
X: 0 (left baseline) → 94 (right baseline)
Y: 0 (top sideline) → 50 (bottom sideline)

Detection strategy for broadcast video:
  Rather than looking for 4 corners (never all visible), detect the actual
  white court lines and match them to known NBA court geometry:
    - Two sidelines  (long near-horizontal lines)
    - Free-throw lines at x=19ft and x=75ft (shorter near-vertical lines)
    - Half-court line at x=47ft
  Intersections of these lines give reliable pixel↔feet correspondences.
"""
import cv2
import numpy as np
from typing import List, Optional, Tuple

# NBA court dimensions (feet)
_W, _H = 94.0, 50.0

# Known x-positions of near-vertical court lines (feet from left baseline)
_VERT_LINE_FT = {
    "baseline_l":  0.0,
    "ft_l":       19.0,
    "half":       47.0,
    "ft_r":       75.0,
    "baseline_r": 94.0,
}

# Candidate hypotheses: which vertical lines are visible, ordered left→right
# Each tuple is a list of keys from _VERT_LINE_FT
_HYPOTHESES = [
    ("ft_l", "half",       "ft_r"),           # full court, 3 lines
    ("ft_l", "ft_r"),                          # full court, FT lines only
    ("baseline_l", "ft_l", "half"),            # left-half broadcast
    ("half",       "ft_r", "baseline_r"),      # right-half broadcast
    ("ft_l", "half", "ft_r", "baseline_r"),    # full + right baseline
    ("baseline_l", "ft_l", "half", "ft_r"),    # full + left baseline
]


class CourtHomography:
    """Computes and applies perspective homography from pixel space to court feet."""

    def __init__(self):
        self._H:     Optional[np.ndarray] = None
        self._H_inv: Optional[np.ndarray] = None

    # ── Calibration ───────────────────────────────────────────────────────────

    def calibrate(self, pixel_corners: np.ndarray) -> bool:
        """Compute H from 4 pixel corners ordered [TL, TR, BR, BL]."""
        if pixel_corners is None or pixel_corners.shape != (4, 2):
            return False
        court_ft = np.array([[0,0],[_W,0],[_W,_H],[0,_H]], dtype=np.float32)
        H, _ = cv2.findHomography(pixel_corners.astype(np.float32), court_ft,
                                  cv2.RANSAC, 5.0)
        return self._set_H(H)

    def calibrate_from_points(self,
                              src: np.ndarray,
                              dst: np.ndarray) -> bool:
        """Compute H from N≥4 pixel↔feet correspondences using RANSAC."""
        if src is None or dst is None or len(src) < 4:
            return False
        H, mask = cv2.findHomography(src.astype(np.float32),
                                     dst.astype(np.float32),
                                     cv2.RANSAC, 3.0)
        if H is None:
            return False
        # Require at least 4 inliers
        if mask is not None and int(mask.sum()) < 4:
            return False
        return self._set_H(H)

    def _set_H(self, H: Optional[np.ndarray]) -> bool:
        if H is None:
            return False
        self._H = H
        try:
            self._H_inv = np.linalg.inv(H)
        except np.linalg.LinAlgError:
            self._H_inv = None
        return True

    # ── Coordinate transforms ─────────────────────────────────────────────────

    def to_feet(self, x_px: float, y_px: float) -> Tuple[float, float]:
        if self._H is None:
            return x_px, y_px
        pt  = np.array([[[x_px, y_px]]], dtype=np.float32)
        out = cv2.perspectiveTransform(pt, self._H)
        return float(out[0,0,0]), float(out[0,0,1])

    def to_pixels(self, x_ft: float, y_ft: float) -> Tuple[float, float]:
        if self._H_inv is None:
            return x_ft, y_ft
        pt  = np.array([[[x_ft, y_ft]]], dtype=np.float32)
        out = cv2.perspectiveTransform(pt, self._H_inv)
        return float(out[0,0,0]), float(out[0,0,1])

    def on_court(self, x_ft: float, y_ft: float, margin: float = 5.0) -> bool:
        return (-margin <= x_ft <= _W + margin) and (-margin <= y_ft <= _H + margin)

    @property
    def is_calibrated(self) -> bool:
        return self._H is not None


# ── Court line detection ───────────────────────────────────────────────────────

def detect_court_corners(frame: np.ndarray) -> Optional[np.ndarray]:
    """
    Legacy interface — returns 4 pixel corners [TL,TR,BR,BL] or None.
    Internally uses line-based detection; falls back to floor-contour method.
    """
    src, dst = detect_court_lines(frame)
    if src is not None and len(src) >= 4:
        # Derive 4 virtual corners from the computed homography
        H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
        if H is not None and mask is not None and int(mask.sum()) >= 4:
            H_inv = np.linalg.inv(H)
            corners_ft = np.array([[[0,0]],[[_W,0]],[[_W,_H]],[[0,_H]]],
                                  dtype=np.float32)
            corners_px = cv2.perspectiveTransform(corners_ft, H_inv)
            return corners_px.reshape(4,2).astype(np.float32)

    return _detect_floor_contour(frame)


def detect_court_lines(frame: np.ndarray
                       ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Detect court lines and return (src_px, dst_ft) correspondence arrays.
    Returns (None, None) on failure.

    Call homography.calibrate_from_points(src, dst) directly for best results.
    """
    h, w = frame.shape[:2]

    floor_mask = _floor_mask(frame)
    line_mask  = _white_line_mask(frame, floor_mask)

    raw = cv2.HoughLinesP(line_mask, 1, np.pi / 180,
                          threshold=50,
                          minLineLength=int(w * 0.06),
                          maxLineGap=20)
    if raw is None or len(raw) < 3:
        return None, None

    segs = raw.reshape(-1, 4).astype(np.float64)

    # Compute angle (0=horizontal … 90=vertical) and midpoints
    dx  = segs[:,2] - segs[:,0]
    dy  = segs[:,3] - segs[:,1]
    ang = np.abs(np.degrees(np.arctan2(dy, dx)))
    ang[ang > 90] = 180 - ang[ang > 90]          # fold to 0–90
    lens = np.hypot(dx, dy)
    mx   = (segs[:,0] + segs[:,2]) / 2
    my   = (segs[:,1] + segs[:,3]) / 2

    h_mask = ang < 28
    v_mask = ang > 62

    h_segs = segs[h_mask];  h_lens = lens[h_mask];  h_my = my[h_mask]
    v_segs = segs[v_mask];  v_lens = lens[v_mask];  v_mx = mx[v_mask]

    if len(h_segs) < 2 or len(v_segs) < 2:
        return None, None

    # Merge nearby co-linear segments into representative lines
    h_lines = _merge_lines(h_segs, h_lens, h_my,  band=h*0.04)
    v_lines = _merge_lines(v_segs, v_lens, v_mx,  band=w*0.04)

    if len(h_lines) < 2 or len(v_lines) < 2:
        return None, None

    # Sort: h_lines top→bottom, v_lines left→right
    h_lines.sort(key=lambda l: (l[1]+l[3])/2)
    v_lines.sort(key=lambda l: (l[0]+l[2])/2)

    # The outermost h_lines are the sidelines
    top_line = h_lines[0]
    bot_line = h_lines[-1]

    # Try each hypothesis to match v_lines to known court x-positions
    best_src, best_dst, best_inliers = None, None, 0

    for hyp in _HYPOTHESES:
        if len(v_lines) < len(hyp):
            continue

        # Select v_lines evenly spaced to match hypothesis length
        idxs   = _select_indices(len(v_lines), len(hyp))
        chosen = [v_lines[i] for i in idxs]
        court_xs = [_VERT_LINE_FT[k] for k in hyp]

        src_pts, dst_pts = [], []
        for vl, cx in zip(chosen, court_xs):
            pt_top = _intersect(top_line, vl)
            pt_bot = _intersect(bot_line, vl)
            if pt_top and _in_frame(*pt_top, w, h, pad=w*0.1):
                src_pts.append(pt_top);  dst_pts.append((cx, 0.0))
            if pt_bot and _in_frame(*pt_bot, w, h, pad=w*0.1):
                src_pts.append(pt_bot);  dst_pts.append((cx, _H))

        if len(src_pts) < 4:
            continue

        # Validate: compute homography and check reprojection + court bounds
        sp = np.array(src_pts, dtype=np.float32)
        dp = np.array(dst_pts, dtype=np.float32)
        H, mask = cv2.findHomography(sp, dp, cv2.RANSAC, 4.0)
        if H is None or mask is None:
            continue
        inliers = int(mask.sum())
        if inliers < 4:
            continue
        if not _validate_H(H, w, h):
            continue
        if inliers > best_inliers:
            best_src, best_dst, best_inliers = sp, dp, inliers

    return best_src, best_dst


# ── Helpers ────────────────────────────────────────────────────────────────────

def _floor_mask(frame: np.ndarray) -> np.ndarray:
    """HSV mask for wood-tone court floor."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    ranges = [
        ((6,  20,  80),  (36, 255, 255)),
        ((5,  10, 100),  (32, 200, 255)),
        ((10, 40,  50),  (42, 255, 220)),
    ]
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    for lo, hi in ranges:
        mask |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  k)
    return mask


def _white_line_mask(frame: np.ndarray, floor_mask: np.ndarray) -> np.ndarray:
    """Detect bright white pixels within the floor region."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # Adaptive threshold to handle varying brightness across the frame
    blur  = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blur, 200, 255, cv2.THRESH_BINARY)
    # Only keep white pixels that lie on the floor
    white_on_floor = cv2.bitwise_and(thresh, thresh, mask=floor_mask)
    # Thin the lines for cleaner Hough detection
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    return cv2.morphologyEx(white_on_floor, cv2.MORPH_ERODE, k)


def _merge_lines(segs: np.ndarray, lens: np.ndarray,
                 positions: np.ndarray, band: float) -> List[np.ndarray]:
    """
    Merge line segments that are parallel and within `band` pixels of each other.
    Returns list of representative line segments (longest in each group),
    extended to span the full group's range.
    """
    if len(segs) == 0:
        return []

    order  = np.argsort(positions)
    groups: List[List[int]] = []
    cur    = [order[0]]

    for idx in order[1:]:
        if abs(positions[idx] - positions[cur[-1]]) < band:
            cur.append(idx)
        else:
            groups.append(cur)
            cur = [idx]
    groups.append(cur)

    result = []
    for g in groups:
        best = g[np.argmax([lens[i] for i in g])]
        result.append(segs[best])
    return result


def _select_indices(n: int, k: int) -> List[int]:
    """Select k evenly-spaced indices from n items."""
    if k >= n:
        return list(range(n))
    return [int(round(i * (n - 1) / (k - 1))) for i in range(k)]


def _intersect(l1, l2) -> Optional[Tuple[float, float]]:
    """Intersection of two line segments (extended to full lines)."""
    x1, y1, x2, y2 = l1
    x3, y3, x4, y4 = l2
    denom = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
    if abs(denom) < 1e-6:
        return None
    t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / denom
    return (x1 + t*(x2-x1), y1 + t*(y2-y1))


def _in_frame(x: float, y: float, w: int, h: int, pad: float = 0) -> bool:
    return (-pad <= x <= w+pad) and (-pad <= y <= h+pad)


def _validate_H(H: np.ndarray, w: int, h: int) -> bool:
    """
    Check that the homography maps the frame corners to something
    that looks like a court (x in 0-94, y in 0-50, not too distorted).
    """
    corners = np.array([[[0,0]],[[w,0]],[[w,h]],[[0,h]]], dtype=np.float32)
    try:
        mapped = cv2.perspectiveTransform(corners, H).reshape(4,2)
    except Exception:
        return False
    xs, ys = mapped[:,0], mapped[:,1]
    # Court must span reasonable range of x and y
    if (xs.max() - xs.min()) < 20:
        return False
    if (ys.max() - ys.min()) < 15:
        return False
    # Mapped corners should be roughly within extended court bounds
    if xs.min() > 30 or xs.max() < 60:
        return False
    return True


def _detect_floor_contour(frame: np.ndarray) -> Optional[np.ndarray]:
    """Original fallback: largest floor-colored contour → 4-point approx."""
    h, w = frame.shape[:2]
    mask = _floor_mask(frame)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < h * w * 0.15:
        return None
    peri = cv2.arcLength(largest, True)
    for eps in [0.02, 0.03, 0.04, 0.05, 0.07, 0.09]:
        approx = cv2.approxPolyDP(largest, eps * peri, True)
        if len(approx) == 4:
            return _order_corners(approx.reshape(4,2).astype(np.float32))
    x, y, rw, rh = cv2.boundingRect(largest)
    return _order_corners(np.array([[x,y],[x+rw,y],[x+rw,y+rh],[x,y+rh]],
                                    dtype=np.float32))


def _order_corners(pts: np.ndarray) -> np.ndarray:
    s = pts.sum(axis=1);  d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)],
                     pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)
