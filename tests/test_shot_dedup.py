"""
test_shot_dedup.py — ISSUE-054: Shot overcounting validation.

Feeds EventDetector a synthetic sequence with one true shot + duplicate
frames and asserts count == 1.
"""
import pytest

from src.tracking.event_detector import EventDetector


# ── Helpers ───────────────────────────────────────────────────────────────────

_MAP_W, _MAP_H = 940, 500   # standard 2D court map dimensions


def _make_detector(fps: float = 30.0) -> EventDetector:
    det = EventDetector(map_w=_MAP_W, map_h=_MAP_H)
    det.configure(fps=fps, stride=1)
    return det


def _track_with_ball(player_id: int = 1) -> list:
    """Minimal player track list — one player possessing the ball."""
    return [
        {
            "player_id": player_id,
            "team": "home",
            "x2d": _MAP_W * 0.7,
            "y2d": _MAP_H * 0.5,
            "has_ball": True,
        }
    ]


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestShotDedup:

    def test_single_shot_from_duplicate_frames(self):
        """One true shot + 9 duplicate frames → exactly 1 'shot' event."""
        det = _make_detector(fps=30.0)

        shot_ball_pos = (_MAP_W * 0.7, _MAP_H * 0.5)
        # High pixel_vel triggers the direct upward-velocity detector
        high_pvel = 60.0          # well above default threshold (~8)
        mid_height = _MAP_H * 0.5  # valid range: 15–75% of frame height

        shot_frames = []
        # Frame 0: true shot
        event = det.update(
            frame_idx=0,
            ball_pos=shot_ball_pos,
            frame_tracks=_track_with_ball(),
            pixel_vel=high_pvel,
            ball_y_pixel=mid_height,
            frame_height=_MAP_H * 2,   # pixel-space height (2× map height typical)
        )
        if event == "shot":
            shot_frames.append(0)

        # Frames 1-9: identical conditions (duplicate / near-duplicate frames)
        for i in range(1, 10):
            event = det.update(
                frame_idx=i,
                ball_pos=shot_ball_pos,
                frame_tracks=_track_with_ball(),
                pixel_vel=high_pvel,
                ball_y_pixel=mid_height,
                frame_height=_MAP_H * 2,
            )
            if event == "shot":
                shot_frames.append(i)

        assert len(shot_frames) == 1, (
            f"Expected exactly 1 shot, got {len(shot_frames)} on frames {shot_frames}"
        )
        assert shot_frames[0] == 0, f"Shot should fire on frame 0, fired on {shot_frames[0]}"

    def test_second_shot_allowed_after_debounce(self):
        """Two real shots separated by > SHOT_DEBOUNCE frames both fire."""
        fps = 30.0
        det = _make_detector(fps=fps)
        debounce_frames = int(8.0 * fps)  # 240 frames at 30fps

        ball_pos = (_MAP_W * 0.7, _MAP_H * 0.5)
        mid_h = _MAP_H * 0.5
        frame_h = _MAP_H * 2
        pvel = 60.0

        shot_frames = []

        # Shot 1 at frame 0
        ev = det.update(0, ball_pos, _track_with_ball(), pvel, mid_h, frame_h)
        if ev == "shot":
            shot_frames.append(0)

        # Quiet frames in between (no pixel_vel trigger)
        for i in range(1, debounce_frames + 1):
            det.update(i, ball_pos, _track_with_ball(), 0.0, mid_h, frame_h)

        # Shot 2 at frame debounce_frames + 1
        shot2_frame = debounce_frames + 1
        ev2 = det.update(shot2_frame, ball_pos, _track_with_ball(), pvel, mid_h, frame_h)
        if ev2 == "shot":
            shot_frames.append(shot2_frame)

        assert len(shot_frames) == 2, (
            f"Expected 2 shots after debounce, got {len(shot_frames)}: {shot_frames}"
        )

    def test_debounce_resets_on_each_shot(self):
        """Debounce window resets from the *last* shot, not the first."""
        fps = 30.0
        det = _make_detector(fps=fps)
        debounce = int(8.0 * fps)

        ball_pos = (_MAP_W * 0.7, _MAP_H * 0.5)
        mid_h = _MAP_H * 0.5
        frame_h = _MAP_H * 2
        pvel = 60.0

        # Shot 1 at frame 0
        det.update(0, ball_pos, _track_with_ball(), pvel, mid_h, frame_h)

        # Shot attempt within debounce (should be blocked)
        early_attempt = debounce // 2
        ev = det.update(early_attempt, ball_pos, _track_with_ball(), pvel, mid_h, frame_h)
        assert ev != "shot", "Shot within debounce window should be blocked"

        # Shot 2 just after debounce from shot 1 (not from early_attempt)
        shot2 = debounce + 1
        ev2 = det.update(shot2, ball_pos, _track_with_ball(), pvel, mid_h, frame_h)
        assert ev2 == "shot", f"Shot after debounce should fire, got {ev2!r}"
