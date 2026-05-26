"""Smoke tests for the 4 R16-missing event detectors in event_detector.py.

Each detector gets a "happy path" test (event fires) plus a "rejection" test
(precondition violated → no event). Synthetic frame_tracks at 30 fps stride 1.

These are SMOKE tests — not exhaustive. They verify wiring, event-shape, and
the headline gate conditions, not every edge case in the detector logic.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.tracking.event_detector import EventDetector


# ─── helpers ─────────────────────────────────────────────────────────────────

MAP_W = 940     # ~typical court-map pixel width
MAP_H = 500


def _ed() -> EventDetector:
    """Build a fresh EventDetector configured at 30fps / stride 1."""
    e = EventDetector(MAP_W, MAP_H)
    e.configure(fps=30.0, stride=1)
    return e


def _track(pid: int, team: str, x: float, y: float, has_ball: bool = False) -> dict:
    return {
        "player_id": pid,
        "team":      team,
        "x2d":       float(x),
        "y2d":       float(y),
        "has_ball":  bool(has_ball),
    }


def _events_of(ed: EventDetector, kind: str) -> list:
    return [e for e in ed.events if e.get("type") == kind]


# ─── steal ───────────────────────────────────────────────────────────────────

class TestSteal:
    def test_fires_when_defender_closes_from_far(self):
        ed = _ed()
        # Frames 0-7: thief (pid=2, team B) sits 12 ft away from handler (pid=1, team A).
        # Frame 8: thief teleports to handler position, takes ball — possessor flips
        #          A->B with ball moving fast.
        feet = ed._ft
        far_x = 500.0 + 12.0 * feet
        # Warm up histories — possession on A, thief far away.
        for f in range(8):
            ed.update(
                frame_idx=f,
                ball_pos=(500.0, 250.0),
                frame_tracks=[
                    _track(1, "home", 500.0, 250.0, has_ball=True),
                    _track(2, "away", far_x, 250.0, has_ball=False),
                ],
                pixel_vel=2.0,
            )
        # Frame 8: thief grabs ball at handler position; ball moved a lot (fast vel).
        ed.update(
            frame_idx=8,
            ball_pos=(540.0, 250.0),    # ball lurched ~40 px → triggers _PASS_MIN_VEL
            frame_tracks=[
                _track(1, "home", 500.0, 250.0, has_ball=False),
                _track(2, "away", 540.0, 250.0, has_ball=True),
            ],
            pixel_vel=8.0,
        )
        steals = _events_of(ed, "steal")
        assert len(steals) == 1, f"expected 1 steal, got {len(steals)}: {ed.events}"
        s = steals[0]
        assert s["thief_id"]  == 2
        assert s["victim_id"] == 1
        assert s["thief_team"] != s["victim_team"]

    def test_no_steal_when_same_team(self):
        ed = _ed()
        feet = ed._ft
        # Both players on team "home" — ball flip should be pass / hand-off, not steal.
        for f in range(8):
            ed.update(
                frame_idx=f,
                ball_pos=(500.0, 250.0),
                frame_tracks=[
                    _track(1, "home", 500.0, 250.0, has_ball=True),
                    _track(2, "home", 500.0 + 12.0 * feet, 250.0, has_ball=False),
                ],
                pixel_vel=2.0,
            )
        ed.update(
            frame_idx=8,
            ball_pos=(540.0, 250.0),
            frame_tracks=[
                _track(1, "home", 500.0, 250.0, has_ball=False),
                _track(2, "home", 540.0, 250.0, has_ball=True),
            ],
            pixel_vel=8.0,
        )
        assert _events_of(ed, "steal") == []


# ─── block ───────────────────────────────────────────────────────────────────

class TestBlock:
    def test_fires_when_defender_close_and_ball_reverses(self):
        ed = _ed()
        # Pre-seed shooter/defender histories and shot bookkeeping so _detect_block
        # has what it needs without going through the full shot pipeline.
        feet = ed._ft
        shooter_x, shooter_y = 600.0, 250.0
        defender_x = shooter_x + 2.0 * feet   # 2 ft away (< 3 ft block range)
        # Build a few frames of stable positions so _phist has entries
        # and _team_of cache is populated.
        for f in range(3):
            ed.update(
                frame_idx=f,
                ball_pos=(shooter_x, shooter_y),
                frame_tracks=[
                    _track(10, "home", shooter_x,  shooter_y, has_ball=True),
                    _track(20, "away", defender_x, shooter_y, has_ball=False),
                ],
                pixel_vel=0.0,
            )
        # Manually set up the "just shot" state so _detect_block has shooter id.
        ed._last_shot_shooter = 10
        ed._last_shot_frame = 3
        # Pre-shot ball direction: upward and toward basket-right.
        # _ball_buf is a deque populated by update() — push synthetic samples.
        ed._ball_buf.clear()
        ed._ball_buf.append((1, shooter_x,        shooter_y))
        ed._ball_buf.append((2, shooter_x + 10.0, shooter_y - 10.0))
        ed._ball_buf.append((3, shooter_x + 20.0, shooter_y - 20.0))   # pre @ shot frame
        # Post-shot ball: reverses sharply (opposite direction).
        ed._ball_buf.append((4, shooter_x + 10.0, shooter_y - 10.0))
        ed._ball_buf.append((5, shooter_x,        shooter_y))
        ed._team_of = {10: "home", 20: "away"}
        # Frame_tracks reflect shot frame.
        tracks = [
            _track(10, "home", shooter_x,  shooter_y, has_ball=False),
            _track(20, "away", defender_x, shooter_y, has_ball=False),
        ]
        ed._detect_block(frame_idx=3, frame_tracks=tracks, ball_pos=(shooter_x + 20.0, shooter_y - 20.0))
        blocks = _events_of(ed, "block")
        assert len(blocks) == 1, f"expected 1 block, got {len(blocks)}: {ed.events}"
        b = blocks[0]
        assert b["blocker_id"] == 20
        assert b["shooter_id"] == 10
        assert b["blocker_dist"] <= 3.0 * feet + 1e-3

    def test_no_block_when_defender_too_far(self):
        ed = _ed()
        feet = ed._ft
        shooter_x, shooter_y = 600.0, 250.0
        defender_x = shooter_x + 10.0 * feet   # 10 ft away (way outside block range)
        for f in range(3):
            ed.update(
                frame_idx=f,
                ball_pos=(shooter_x, shooter_y),
                frame_tracks=[
                    _track(10, "home", shooter_x,  shooter_y, has_ball=True),
                    _track(20, "away", defender_x, shooter_y, has_ball=False),
                ],
                pixel_vel=0.0,
            )
        ed._last_shot_shooter = 10
        ed._last_shot_frame = 3
        ed._ball_buf.append((1, shooter_x,        shooter_y))
        ed._ball_buf.append((2, shooter_x + 10.0, shooter_y - 10.0))
        ed._ball_buf.append((3, shooter_x + 20.0, shooter_y - 20.0))
        ed._ball_buf.append((4, shooter_x + 10.0, shooter_y - 10.0))
        ed._ball_buf.append((5, shooter_x,        shooter_y))
        ed._team_of = {10: "home", 20: "away"}
        tracks = [
            _track(10, "home", shooter_x,  shooter_y, has_ball=False),
            _track(20, "away", defender_x, shooter_y, has_ball=False),
        ]
        ed._detect_block(frame_idx=3, frame_tracks=tracks, ball_pos=(shooter_x + 20.0, shooter_y - 20.0))
        assert _events_of(ed, "block") == []


# ─── rebound ─────────────────────────────────────────────────────────────────

class TestRebound:
    def test_defensive_rebound_when_opponent_closest(self):
        ed = _ed()
        # Stage a pending shot manually and step _detect_rebound forward.
        basket = ed._baskets[1]   # right basket
        shot_frame = 5
        ed._pending_shots.append({
            "shot_frame":   shot_frame,
            "shooter_id":   100,
            "shooter_team": "home",
            "basket":       basket,
        })
        # Warm up _phist + _team_of via a couple of dummy update() calls
        # (also satisfies _team_of cache).
        for f in range(shot_frame, shot_frame + 5):
            ed.update(
                frame_idx=f,
                ball_pos=(float(basket[0]), float(basket[1])),
                frame_tracks=[
                    _track(100, "home", float(basket[0]) - 50.0, float(basket[1]), has_ball=False),
                    _track(200, "away", float(basket[0]),         float(basket[1]), has_ball=False),
                ],
                pixel_vel=0.0,
            )
        # Step to the resolution frame (shot_frame + 30 source frames / stride=1).
        resolve_frame = shot_frame + 35
        ed.update(
            frame_idx=resolve_frame,
            ball_pos=(float(basket[0]), float(basket[1])),
            frame_tracks=[
                _track(100, "home", float(basket[0]) - 50.0, float(basket[1]), has_ball=False),
                _track(200, "away", float(basket[0]),         float(basket[1]), has_ball=True),
            ],
            pixel_vel=0.0,
        )
        rebs = _events_of(ed, "rebound")
        assert len(rebs) == 1, f"expected 1 rebound, got {len(rebs)}: {ed.events}"
        r = rebs[0]
        assert r["subtype"] == "defensive_rebound"
        assert r["player_id"] == 200
        assert r["team"] == "away"
        assert r["shot_frame"] == shot_frame

    def test_offensive_rebound_when_teammate_closest(self):
        ed = _ed()
        basket = ed._baskets[1]
        shot_frame = 5
        ed._pending_shots.append({
            "shot_frame":   shot_frame,
            "shooter_id":   100,
            "shooter_team": "home",
            "basket":       basket,
        })
        # Teammate (101) sits right under the basket; opponent (200) is far.
        for f in range(shot_frame, shot_frame + 5):
            ed.update(
                frame_idx=f,
                ball_pos=(float(basket[0]), float(basket[1])),
                frame_tracks=[
                    _track(100, "home", float(basket[0]) - 100.0, float(basket[1]), has_ball=False),
                    _track(101, "home", float(basket[0]),          float(basket[1]), has_ball=False),
                    _track(200, "away", float(basket[0]) - 200.0,  float(basket[1]), has_ball=False),
                ],
                pixel_vel=0.0,
            )
        resolve_frame = shot_frame + 35
        ed.update(
            frame_idx=resolve_frame,
            ball_pos=(float(basket[0]), float(basket[1])),
            frame_tracks=[
                _track(100, "home", float(basket[0]) - 100.0, float(basket[1]), has_ball=False),
                _track(101, "home", float(basket[0]),          float(basket[1]), has_ball=True),
                _track(200, "away", float(basket[0]) - 200.0,  float(basket[1]), has_ball=False),
            ],
            pixel_vel=0.0,
        )
        rebs = _events_of(ed, "rebound")
        assert len(rebs) == 1
        r = rebs[0]
        assert r["subtype"] == "offensive_rebound"
        assert r["player_id"] == 101
        assert r["team"] == "home"


# ─── post_up ─────────────────────────────────────────────────────────────────

class TestPostUp:
    def test_fires_when_handler_camps_near_basket_with_defender(self):
        ed = _ed()
        feet = ed._ft
        basket = ed._baskets[1]
        # Position handler 5 ft from basket on the basket-side; opponent 3 ft away.
        # Each frame, handler "backs down" 0.3 px AWAY from basket → vtb < 0.
        STREAK_NEEDED = max(30, int(2.0 * ed._fps / max(1, ed._stride)))  # 60 frames at 30fps
        # Run STREAK_NEEDED + a buffer frames.
        # Place handler slightly to the LEFT of basket, then drift further left
        # each frame (away from basket on the right side).
        hx0 = float(basket[0]) - 5.0 * feet
        hy  = float(basket[1])
        defender_x = hx0 - 2.0 * feet   # 2 ft away from handler (well within 5 ft)
        last_event_count = 0
        for f in range(STREAK_NEEDED + 5):
            hx = hx0 - 0.3 * f   # back AWAY from basket each frame
            dx = defender_x - 0.3 * f
            ed.update(
                frame_idx=f,
                ball_pos=(hx, hy),
                frame_tracks=[
                    _track(7, "home", hx, hy, has_ball=True),
                    _track(8, "away", dx, hy, has_ball=False),
                ],
                pixel_vel=0.5,
            )
        postups = _events_of(ed, "post_up")
        assert len(postups) >= 1, f"expected ≥1 post_up, got {len(postups)}: events={ed.events[-5:]}"
        p = postups[0]
        assert p["player_id"] == 7
        assert p["team"] == "home"
        assert p["defender_dist"] <= 5.0 * feet + 1e-3
        assert p["dist_to_basket"] <= 8.0 * feet + 1e-3

    def test_no_post_up_when_no_defender_nearby(self):
        ed = _ed()
        feet = ed._ft
        basket = ed._baskets[1]
        STREAK_NEEDED = max(30, int(2.0 * ed._fps / max(1, ed._stride)))
        hx0 = float(basket[0]) - 5.0 * feet
        hy  = float(basket[1])
        # Defender 20 ft away — gate fails.
        defender_x = hx0 - 20.0 * feet
        for f in range(STREAK_NEEDED + 5):
            hx = hx0 - 0.3 * f
            ed.update(
                frame_idx=f,
                ball_pos=(hx, hy),
                frame_tracks=[
                    _track(7, "home", hx, hy, has_ball=True),
                    _track(8, "away", defender_x, hy, has_ball=False),
                ],
                pixel_vel=0.5,
            )
        assert _events_of(ed, "post_up") == []
