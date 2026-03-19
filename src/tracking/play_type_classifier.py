"""
play_type_classifier.py — Synergy-equivalent play type classifier.

Classifies the current possession into Synergy-style play types using only
the geometry of the last 90 frames of player positions.  No ML required.

Play types
----------
    isolation     — handler stationary ≥ 15 frames, teammates spread wide
    pick_and_roll — screener converges to handler then rolls toward basket
    pick_and_pop  — screener converges to handler then pops to 3-pt area
    spot_up       — pass received, shot within ~2 sec (60 frames)
    off_screen    — off-ball player runs past stationary teammate then gets ball
    cut           — off-ball player makes sharp direction change toward basket
    hand_off      — two players converge; possession changes at contact point
    post_up       — passed through from possession_classifier
    transition    — passed through from possession_classifier
    fast_break    — passed through from possession_classifier
    unclassified  — default

Public API
----------
    PlayTypeClassifier()
    .update(frame_history, possession_type) -> str

frame_history items must be dicts: {"frame": int, "tracks": [...]}
Each track: {"player_id": int, "x2d": float, "y2d": float,
             "has_ball": bool, "team": str, "event": str (optional)}
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Tuple

import numpy as np

_BUFFER_FRAMES   = 90     # sliding window depth
_ISO_SPD_MAX     = 2.0    # px/frame — handler "stationary" below this
_ISO_MIN_FRAMES  = 15     # consecutive slow frames to confirm isolation
_ISO_MATE_DIST_N = 0.38   # normalised — teammates farther than this = spread

_SCREEN_RAD_N    = 0.048  # normalised radius — screener "on" handler
_SCREEN_ROLL_N   = 0.06   # normalised — screener must move this far after screen
_BASKET_XN_INNER = 0.28   # roll destination must be within this of a basket

_SPOT_MAX_FRAMES = 60     # max frames between pass and shot for spot-up
_CUT_ANGLE_MIN   = 85.0   # degrees of direction change to call a cut
_CUT_LEN_MIN_N   = 0.04   # normalised — minimum movement length to analyse

_HO_RADIUS_N     = 0.045  # normalised — hand-off contact radius


class PlayTypeClassifier:
    """
    Classifies the current possession play type from frame history.

    Uses a rolling buffer of the last _BUFFER_FRAMES frames.  The result is
    updated once per call and cached until a new play pattern is detected.

    Args:
        None — map dimensions are inferred dynamically from track coordinates.
    """

    def __init__(self) -> None:
        self._buffer: deque = deque(maxlen=_BUFFER_FRAMES)
        self._current: str  = "unclassified"

    def update(
        self,
        frame_history: List[Dict],
        possession_type: str,
    ) -> str:
        """
        Classify the current play type.

        Args:
            frame_history: Recent frame dicts from unified_pipeline.
                           Each entry: {"frame": int, "tracks": [...]}
            possession_type: Current type from PossessionClassifier.

        Returns:
            Play type string.
        """
        for entry in frame_history:
            self._buffer.append(entry)

        # Pass through possession-level overrides directly
        if possession_type in ("transition", "post_up", "fast_break"):
            self._current = possession_type
            return self._current

        buf = list(self._buffer)
        if len(buf) < 10:
            return self._current

        play = self._classify(buf)
        if play != "unclassified":
            self._current = play
        return self._current

    # ── classification ────────────────────────────────────────────────────

    def _classify(self, buf: List[Dict]) -> str:
        """Run all detectors in priority order and return first match."""
        handler_seq = self._handler_seq(buf)
        if not handler_seq:
            return "unclassified"

        if self._is_isolation(buf, handler_seq):
            return "isolation"
        if self._is_pick_and_roll(buf):
            return "pick_and_roll"
        if self._is_pick_and_pop(buf):
            return "pick_and_pop"
        if self._is_hand_off(buf):
            return "hand_off"
        if self._is_cut(buf):
            return "cut"
        if self._is_spot_up(buf):
            return "spot_up"
        if self._is_off_screen(buf):
            return "off_screen"
        return "unclassified"

    # ── helpers ───────────────────────────────────────────────────────────

    def _map_size(self, buf: List[Dict]) -> Tuple[float, float]:
        """Estimate map (w, h) from max observed 2D coordinates."""
        xs = [t.get("x2d", 0) for e in buf for t in e.get("tracks", [])]
        ys = [t.get("y2d", 0) for e in buf for t in e.get("tracks", [])]
        return max(max(xs, default=940) * 1.05, 200), max(max(ys, default=500) * 1.05, 100)

    def _handler_seq(self, buf: List[Dict]) -> List[Tuple[int, float, float, float]]:
        """Return [(frame, x, y, speed)] for the ball handler across the buffer."""
        seq, prev = [], None
        for e in buf:
            t = next((t for t in e.get("tracks", []) if t.get("has_ball")), None)
            if t:
                x, y = float(t.get("x2d", 0)), float(t.get("y2d", 0))
                spd  = float(np.hypot(x - prev[0], y - prev[1])) if prev else 0.0
                seq.append((e["frame"], x, y, spd))
                prev = (x, y)
        return seq

    # ── play detectors ────────────────────────────────────────────────────

    def _is_isolation(self, buf: List[Dict], handler_seq: List[Tuple]) -> bool:
        """Handler slow for ≥ _ISO_MIN_FRAMES with teammates spread far."""
        if len(handler_seq) < _ISO_MIN_FRAMES:
            return False
        if np.mean([s[3] for s in handler_seq[-_ISO_MIN_FRAMES:]]) > _ISO_SPD_MAX:
            return False
        # Check spread in latest frame
        mw, _ = self._map_size(buf)
        latest = buf[-1]
        h = next((t for t in latest.get("tracks", []) if t.get("has_ball")), None)
        if not h:
            return False
        hx, hy = h.get("x2d", 0), h.get("y2d", 0)
        mates = [t for t in latest.get("tracks", [])
                 if t.get("team") == h.get("team") and not t.get("has_ball")]
        if not mates:
            return True
        avg_n = np.mean([np.hypot(t.get("x2d", 0) - hx, t.get("y2d", 0) - hy) / mw
                         for t in mates])
        return float(avg_n) > _ISO_MATE_DIST_N

    def _screener_convergence(self, buf: List[Dict]) -> Optional[Tuple[Dict, Dict, int]]:
        """Find (handler, screener_track, frame_idx) where screener touched handler."""
        mw, _ = self._map_size(buf)
        rad = _SCREEN_RAD_N * mw
        for i, e in enumerate(buf):
            h = next((t for t in e.get("tracks", []) if t.get("has_ball")), None)
            if not h:
                continue
            hx, hy = h.get("x2d", 0), h.get("y2d", 0)
            for t in e.get("tracks", []):
                if t.get("player_id") == h.get("player_id"):
                    continue
                if t.get("team") != h.get("team"):
                    continue
                if np.hypot(t.get("x2d", 0) - hx, t.get("y2d", 0) - hy) < rad:
                    return h, t, i
        return None

    def _is_pick_and_roll(self, buf: List[Dict]) -> bool:
        """Screener converges to handler then rolls toward a basket."""
        hit = self._screener_convergence(buf)
        if hit is None:
            return False
        _, screener, si = hit
        mw, _ = self._map_size(buf)
        sid = screener.get("player_id")
        for e in buf[si + 1: si + 16]:
            s_later = next((t for t in e.get("tracks", []) if t.get("player_id") == sid), None)
            if s_later:
                dist_n = np.hypot(s_later.get("x2d", 0) - screener.get("x2d", 0),
                                  s_later.get("y2d", 0) - screener.get("y2d", 0)) / mw
                xn = s_later.get("x2d", 0) / mw
                if dist_n > _SCREEN_ROLL_N and (xn < _BASKET_XN_INNER or xn > 1 - _BASKET_XN_INNER):
                    return True
        return False

    def _is_pick_and_pop(self, buf: List[Dict]) -> bool:
        """Screener converges to handler then pops to 3-point area."""
        hit = self._screener_convergence(buf)
        if hit is None:
            return False
        _, screener, si = hit
        mw, _ = self._map_size(buf)
        sid = screener.get("player_id")
        for e in buf[si + 1: si + 16]:
            s_later = next((t for t in e.get("tracks", []) if t.get("player_id") == sid), None)
            if s_later:
                dist_n = np.hypot(s_later.get("x2d", 0) - screener.get("x2d", 0),
                                  s_later.get("y2d", 0) - screener.get("y2d", 0)) / mw
                xn = s_later.get("x2d", 0) / mw
                # Pop = moved to mid-range/3pt arc zone (not paint, not backcourt)
                in_pop_zone = (_BASKET_XN_INNER < xn < 0.42) or (0.58 < xn < 1 - _BASKET_XN_INNER)
                if dist_n > _SCREEN_ROLL_N and in_pop_zone:
                    return True
        return False

    def _is_cut(self, buf: List[Dict]) -> bool:
        """Off-ball player makes a sharp direction change (>= _CUT_ANGLE_MIN deg)."""
        mw, _ = self._map_size(buf)
        seen: Dict[int, List[Tuple[float, float]]] = {}
        for e in buf:
            for t in e.get("tracks", []):
                if not t.get("has_ball"):
                    pid = t.get("player_id", -1)
                    seen.setdefault(pid, []).append(
                        (float(t.get("x2d", 0)), float(t.get("y2d", 0)))
                    )
        for pid, pts in seen.items():
            if len(pts) < 8:
                continue
            mid = len(pts) // 2
            v1 = np.array([pts[mid][0] - pts[0][0], pts[mid][1] - pts[0][1]], dtype=float)
            v2 = np.array([pts[-1][0] - pts[mid][0], pts[-1][1] - pts[mid][1]], dtype=float)
            n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
            if n1 / mw < _CUT_LEN_MIN_N or n2 / mw < _CUT_LEN_MIN_N:
                continue
            cos_a = float(np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0))
            if float(np.degrees(np.arccos(cos_a))) >= _CUT_ANGLE_MIN:
                return True
        return False

    def _is_hand_off(self, buf: List[Dict]) -> bool:
        """Two players converge; possession changes at contact point."""
        mw, _ = self._map_size(buf)
        rad = _HO_RADIUS_N * mw
        for i in range(4, len(buf)):
            now  = buf[i]
            prev = buf[i - 4]
            h_now  = next((t for t in now.get("tracks",  []) if t.get("has_ball")), None)
            h_prev = next((t for t in prev.get("tracks", []) if t.get("has_ball")), None)
            if not h_now or not h_prev:
                continue
            if h_now.get("player_id") == h_prev.get("player_id"):
                continue
            # Possession changed — were they close?
            d = np.hypot(h_now.get("x2d", 0) - h_prev.get("x2d", 0),
                         h_now.get("y2d", 0) - h_prev.get("y2d", 0))
            if d < rad:
                return True
        return False

    def _is_spot_up(self, buf: List[Dict]) -> bool:
        """Pass received, shot taken within _SPOT_MAX_FRAMES."""
        events: List[Tuple[int, str]] = []
        for e in buf:
            for t in e.get("tracks", []):
                ev = t.get("event", "none")
                if ev in ("pass", "shot"):
                    events.append((e["frame"], ev))
                    break
        for i in range(len(events) - 1):
            if (events[i][1] == "pass" and events[i + 1][1] == "shot"
                    and events[i + 1][0] - events[i][0] <= _SPOT_MAX_FRAMES):
                return True
        return False

    def _is_off_screen(self, buf: List[Dict]) -> bool:
        """Off-ball player runs past stationary teammate then receives the ball."""
        mw, _ = self._map_size(buf)
        screen_rad = _SCREEN_RAD_N * mw * 1.5

        for i in range(10, len(buf)):
            e    = buf[i]
            prev = buf[i - 10]
            h = next((t for t in e.get("tracks", []) if t.get("has_ball")), None)
            if not h:
                continue
            pid = h.get("player_id")
            # Was this player NOT the handler 10 frames ago?
            had_ball = any(t.get("player_id") == pid and t.get("has_ball")
                           for t in prev.get("tracks", []))
            if had_ball:
                continue
            # Did their path pass near a same-team stationary player?
            path = [(t.get("x2d", 0), t.get("y2d", 0))
                    for ee in buf[max(0, i - 10):i]
                    for t in ee.get("tracks", [])
                    if t.get("player_id") == pid]
            if len(path) < 3:
                continue
            mid_x = float(np.mean([p[0] for p in path]))
            mid_y = float(np.mean([p[1] for p in path]))
            for other in e.get("tracks", []):
                if other.get("player_id") == pid:
                    continue
                if other.get("team") != h.get("team"):
                    continue
                if np.hypot(other.get("x2d", 0) - mid_x,
                            other.get("y2d", 0) - mid_y) < screen_rad:
                    return True
        return False
