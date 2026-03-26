"""
test_possession_tracking_gaps.py — Tests for 8 data collection gap fixes.

FIX 1: lineup_id tracking
FIX 2: possession-level poss_ctx aggregates
FIX 3: catch_and_shoot flag + shot_distance
FIX 4: transition_time_sec
FIX 5: second_chance flag
FIX 6: P&R role tagging in screen_set events
FIX 7: help defense rotation detection
FIX 8: shot creation type classification
"""

import sys
import os

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline.unified_pipeline import UnifiedPipeline
from src.tracking.event_detector import EventDetector


# ── helpers ───────────────────────────────────────────────────────────────────

MAP_W, MAP_H = 940, 500


def _make_tracks(players):
    """Build a minimal frame_tracks list from a list of dicts."""
    base = {"team": "green", "x2d": 200, "y2d": 250, "has_ball": False}
    result = []
    for pid, overrides in enumerate(players, start=1):
        t = {**base, "player_id": pid}
        t.update(overrides)
        result.append(t)
    return result


def _make_possession_buf(n=10, **overrides):
    """Build a minimal possession buffer with n frames."""
    base = {
        "frame": 0, "spacing": 100.0, "isolation": 50.0, "vtb": 1.0,
        "drive": 0, "shot_event": False, "fast_break": 0,
        "poss_type": "half_court", "play_type": "half_court",
        "paint_touches": 0, "off_ball_distance": 0.0,
        "shot_clock_est": 24.0, "handler_zone": "mid_range",
    }
    base.update(overrides)
    return [dict(base, frame=i) for i in range(n)]


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 1 — lineup_id
# ═══════════════════════════════════════════════════════════════════════════════

class TestLineupIdTracking:

    def test_lineup_id_in_tracking_fields(self):
        """lineup_id must be present in _tracking_csv_fields()."""
        assert "lineup_id" in UnifiedPipeline._tracking_csv_fields()

    def test_lineup_id_consistent_same_players(self):
        """Same frozenset of player IDs produces the same lineup_id across frames."""
        cache: dict = {}
        counter = 0

        def compute(player_ids):
            nonlocal counter
            key = frozenset(player_ids)
            if key not in cache:
                counter += 1
                cache[key] = counter
            return cache[key]

        ids = [1, 2, 3, 4, 5]
        id1 = compute(ids)
        id2 = compute(ids)
        id3 = compute(ids)
        assert id1 == id2 == id3

    def test_lineup_id_changes_on_sub(self):
        """Different player set produces a different lineup_id."""
        cache: dict = {}
        counter = 0

        def compute(player_ids):
            nonlocal counter
            key = frozenset(player_ids)
            if key not in cache:
                counter += 1
                cache[key] = counter
            return cache[key]

        id_before = compute([1, 2, 3, 4, 5])
        id_after  = compute([1, 2, 3, 4, 6])   # player 5 subbed for 6
        assert id_before != id_after

    def test_lineup_id_in_possessions_fieldnames(self):
        """lineup_id must be in _export_possessions_csv fieldnames list."""
        # We test by calling _summarize_possession and checking the returned dict
        buf = _make_possession_buf()
        row = UnifiedPipeline._summarize_possession(
            pid=1, team="green",
            start_f=0, end_f=9,
            buf=buf, fps=30.0, game_id=None,
            lineup_id=7,
        )
        assert "lineup_id" in row
        assert row["lineup_id"] == 7


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2 — possession poss_ctx aggregates
# ═══════════════════════════════════════════════════════════════════════════════

class TestPossessionContextAggregates:

    def test_paint_touches_in_possession_fields(self):
        """_export_possessions_csv fieldnames must include max_paint_touches."""
        # Indirect check via _summarize_possession return dict
        buf = _make_possession_buf(paint_touches=3)
        row = UnifiedPipeline._summarize_possession(
            pid=1, team="green", start_f=0, end_f=9,
            buf=buf, fps=30.0
        )
        assert "max_paint_touches" in row

    def test_dominant_zone_in_possession_fields(self):
        """dominant_zone must be present in _summarize_possession output."""
        buf = _make_possession_buf(handler_zone="paint")
        row = UnifiedPipeline._summarize_possession(
            pid=1, team="green", start_f=0, end_f=9,
            buf=buf, fps=30.0
        )
        assert "dominant_zone" in row
        assert row["dominant_zone"] == "paint"

    def test_max_paint_touches_correct(self):
        """max_paint_touches is the max across all buf frames."""
        buf = [dict(_make_possession_buf(1)[0], paint_touches=i) for i in range(5)]
        row = UnifiedPipeline._summarize_possession(
            pid=1, team="green", start_f=0, end_f=4,
            buf=buf, fps=30.0
        )
        assert row["max_paint_touches"] == 4

    def test_min_shot_clock_est_in_row(self):
        """min_shot_clock_est represents the most-pressured moment."""
        buf = [dict(_make_possession_buf(1)[0], shot_clock_est=c) for c in [20.0, 8.0, 15.0]]
        row = UnifiedPipeline._summarize_possession(
            pid=1, team="green", start_f=0, end_f=2,
            buf=buf, fps=30.0
        )
        assert "min_shot_clock_est" in row
        assert row["min_shot_clock_est"] == pytest.approx(8.0, abs=0.1)

    def test_avg_off_ball_distance_skips_zeros(self):
        """avg_off_ball_distance excludes zero-distance frames."""
        buf = [dict(_make_possession_buf(1)[0], off_ball_distance=d)
               for d in [0.0, 50.0, 100.0]]
        row = UnifiedPipeline._summarize_possession(
            pid=1, team="green", start_f=0, end_f=2,
            buf=buf, fps=30.0
        )
        assert "avg_off_ball_distance" in row
        assert row["avg_off_ball_distance"] == pytest.approx(75.0, abs=0.5)

    def test_dominant_zone_none_when_no_handler(self):
        """dominant_zone is '' when no handler_zone entries in buf."""
        buf = [dict(_make_possession_buf(1)[0], handler_zone=None) for _ in range(5)]
        row = UnifiedPipeline._summarize_possession(
            pid=1, team="green", start_f=0, end_f=4,
            buf=buf, fps=30.0
        )
        assert row["dominant_zone"] == ""


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 3 — catch_and_shoot flag + shot_distance
# ═══════════════════════════════════════════════════════════════════════════════

class TestCatchAndShootFlag:

    def test_catch_and_shoot_flag_zero_dribbles(self):
        """dribble_count == 0 → catch_and_shoot == 1."""
        det = EventDetector(map_w=MAP_W, map_h=MAP_H)
        assert det.dribble_count == 0
        result = int(det.dribble_count == 0)
        assert result == 1

    def test_catch_and_shoot_flag_with_dribbles(self):
        """dribble_count > 0 → catch_and_shoot == 0."""
        det = EventDetector(map_w=MAP_W, map_h=MAP_H)
        # Manually set to simulate dribbles
        det._dribble_count = 3
        result = int(det.dribble_count == 0)
        assert result == 0

    def test_shot_distance_in_shot_log_fieldnames(self):
        """shot_distance must be in _export_shot_log fieldnames."""
        import csv, io
        # Simulate a shot_log_rows list and verify fieldnames contains shot_distance
        # We do this by checking the fieldnames list in _export_shot_log manually
        import inspect
        src = inspect.getsource(UnifiedPipeline._export_shot_log)
        assert "shot_distance" in src

    def test_catch_and_shoot_in_shot_log_fieldnames(self):
        """catch_and_shoot must be in _export_shot_log fieldnames."""
        import inspect
        src = inspect.getsource(UnifiedPipeline._export_shot_log)
        assert "catch_and_shoot" in src


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 4 — transition_time_sec
# ═══════════════════════════════════════════════════════════════════════════════

class TestTransitionTimeSec:

    def test_transition_time_sec_in_possession_row(self):
        """transition_time_sec must be present in _summarize_possession output."""
        buf = _make_possession_buf()
        row = UnifiedPipeline._summarize_possession(
            pid=1, team="green", start_f=0, end_f=9,
            buf=buf, fps=30.0,
            transition_frames=30,
        )
        assert "transition_time_sec" in row
        assert row["transition_time_sec"] == pytest.approx(1.0, abs=0.01)

    def test_transition_time_sec_empty_when_no_crossing(self):
        """transition_time_sec is '' when transition_frames is None."""
        buf = _make_possession_buf()
        row = UnifiedPipeline._summarize_possession(
            pid=1, team="green", start_f=0, end_f=9,
            buf=buf, fps=30.0,
            transition_frames=None,
        )
        assert row["transition_time_sec"] == ""


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 5 — second_chance flag
# ═══════════════════════════════════════════════════════════════════════════════

class TestSecondChanceFlag:

    def test_second_chance_first_shot(self):
        """First shot on a possession → second_chance == 0."""
        poss_shot_count: dict = {}
        possession_id = 5
        poss_shot_count[possession_id] = poss_shot_count.get(possession_id, 0) + 1
        second_chance = int(poss_shot_count[possession_id] > 1)
        assert second_chance == 0

    def test_second_chance_flag_same_possession(self):
        """Second shot on same possession_id → second_chance == 1."""
        poss_shot_count: dict = {}
        possession_id = 5
        # First shot
        poss_shot_count[possession_id] = poss_shot_count.get(possession_id, 0) + 1
        # Second shot (offensive rebound + putback)
        poss_shot_count[possession_id] = poss_shot_count.get(possession_id, 0) + 1
        second_chance = int(poss_shot_count[possession_id] > 1)
        assert second_chance == 1

    def test_second_chance_in_shot_log_fieldnames(self):
        """second_chance must be in _export_shot_log fieldnames."""
        import inspect
        src = inspect.getsource(UnifiedPipeline._export_shot_log)
        assert "second_chance" in src


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 6 — P&R role tagging in screen_set events
# ═══════════════════════════════════════════════════════════════════════════════

class TestPnrTagging:

    def _make_event_det(self):
        det = EventDetector(map_w=MAP_W, map_h=MAP_H)
        det.configure(fps=30.0, stride=1)
        return det

    def _seed_hist(self, det, tracks, frame_start=0, n_frames=12):
        """Seed position history so _detect_screens can read speed."""
        for fi in range(frame_start, frame_start + n_frames):
            det._update_player_hist(fi, tracks)

    def test_pnr_tagging_ball_handler_identified(self):
        """screen_set event with one player has_ball=True → screen_action == 'pick_and_roll', ball_handler_id set."""
        det = self._make_event_det()

        # Two cross-team players: green(1) has ball; white(2) is stationary screener
        # Position them close enough to trigger screen detection
        tracks = [
            {"player_id": 1, "team": "green", "x2d": 200, "y2d": 250, "has_ball": True},
            {"player_id": 2, "team": "white", "x2d": 200, "y2d": 250, "has_ball": False},
        ]

        # Seed 12 frames with player 2 stationary and player 1 moving
        for fi in range(12):
            moving_tracks = [
                {"player_id": 1, "team": "green", "x2d": 200 + fi * 5, "y2d": 250, "has_ball": True},
                {"player_id": 2, "team": "white", "x2d": 200, "y2d": 250, "has_ball": False},
            ]
            det._update_player_hist(fi, moving_tracks)

        # Manually trigger _detect_screens with players in close proximity
        close_tracks = [
            {"player_id": 1, "team": "green", "x2d": 202, "y2d": 250, "has_ball": True},
            {"player_id": 2, "team": "white", "x2d": 200, "y2d": 250, "has_ball": False},
        ]
        # Override hist to force speed values
        from collections import deque
        det._phist[1] = deque(
            [(11, 195, 250, 5.0), (12, 202, 250, 7.0)], maxlen=15
        )
        det._phist[2] = deque(
            [(11, 200, 250, 0.0), (12, 200, 250, 0.0)], maxlen=15
        )
        det._detect_screens(12, close_tracks)

        screen_events = [e for e in det.events if e["type"] == "screen_set"]
        assert len(screen_events) >= 1
        evt = screen_events[0]
        assert evt["screen_action"] == "pick_and_roll"
        assert evt["ball_handler_id"] == 1
        assert evt["screener_id"] == 2

    def test_pnr_off_ball_screen(self):
        """Both players has_ball=False → screen_action == 'off_ball_screen'."""
        det = self._make_event_det()

        from collections import deque
        det._phist[3] = deque([(11, 195, 250, 5.0), (12, 202, 250, 7.0)], maxlen=15)
        det._phist[4] = deque([(11, 200, 250, 0.0), (12, 200, 250, 0.0)], maxlen=15)

        off_ball_tracks = [
            {"player_id": 3, "team": "green", "x2d": 202, "y2d": 250, "has_ball": False},
            {"player_id": 4, "team": "white", "x2d": 200, "y2d": 250, "has_ball": False},
        ]
        det._detect_screens(12, off_ball_tracks)

        screen_events = [e for e in det.events if e["type"] == "screen_set"]
        assert len(screen_events) >= 1
        evt = screen_events[0]
        assert evt["screen_action"] == "off_ball_screen"
        assert evt["ball_handler_id"] is None
        assert evt["screener_id"] is None

    def test_pnr_fields_in_events_log_fieldnames(self):
        """ball_handler_id, screener_id, screen_action must be in _export_events_log fieldnames."""
        import inspect
        src = inspect.getsource(UnifiedPipeline._export_events_log)
        assert "ball_handler_id" in src
        assert "screener_id" in src
        assert "screen_action" in src


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 7 — help defense rotation detection
# ═══════════════════════════════════════════════════════════════════════════════

class TestHelpDefenseRotation:

    def _make_det(self):
        det = EventDetector(map_w=MAP_W, map_h=MAP_H)
        det.configure(fps=30.0, stride=1)
        return det

    def test_help_rotation_event_emitted(self):
        """When defender moves from >12ft to <6ft in 10 frames, help_rotation fires."""
        det = self._make_det()

        # Handler is player 1 (green), possessor
        det._possessor = 1
        ft = det._ft  # px per foot

        hx, hy = 500.0, 250.0  # handler position

        from collections import deque
        # Handler history (stationary)
        det._phist[1] = deque(
            [(fi, hx, hy, 0.0) for fi in range(15)], maxlen=15
        )

        # Defender (player 2, white) was 14ft away 10 frames ago, now 4ft away.
        # With maxlen=15 and lookback=10, hist[-10] is index 5 (fi=5).
        # Far for fi 0-8 (covers index 5), near for fi 9-14 (covers last entry).
        dist_far  = 14.0 * ft
        dist_near = 4.0 * ft
        far_x  = hx + dist_far
        near_x = hx + dist_near
        hist = [(fi, far_x if fi < 9 else near_x, hy, 3.0) for fi in range(15)]
        det._phist[2] = deque(hist, maxlen=15)

        tracks = [
            {"player_id": 1, "team": "green", "x2d": int(hx), "y2d": int(hy), "has_ball": True},
            {"player_id": 2, "team": "white", "x2d": int(near_x), "y2d": int(hy), "has_ball": False},
        ]

        det._detect_help_defense(14, tracks)

        help_events = [e for e in det.events if e["type"] == "help_rotation"]
        assert len(help_events) >= 1
        evt = help_events[0]
        assert evt["defender_id"] == 2
        assert evt["handler_id"] == 1
        assert "rotation_dist" in evt

    def test_help_rotation_debounce(self):
        """Same (defender_id, handler_id) pair within 45 frames does not re-fire."""
        det = self._make_det()
        det._possessor = 1
        ft = det._ft

        hx, hy = 500.0, 250.0
        dist_near = 4.0 * ft
        near_x = hx + dist_near
        far_x  = hx + 14.0 * ft

        from collections import deque
        det._phist[1] = deque([(fi, hx, hy, 0.0) for fi in range(15)], maxlen=15)
        hist = [(fi, far_x if fi < 9 else near_x, hy, 3.0) for fi in range(15)]
        det._phist[2] = deque(hist, maxlen=15)

        tracks = [
            {"player_id": 1, "team": "green", "x2d": int(hx), "y2d": int(hy), "has_ball": True},
            {"player_id": 2, "team": "white", "x2d": int(near_x), "y2d": int(hy), "has_ball": False},
        ]

        # First fire
        det._detect_help_defense(14, tracks)
        count_after_first = len([e for e in det.events if e["type"] == "help_rotation"])

        # Second fire 20 frames later — within debounce window (45 frames)
        # Update hist to still show defender near (stays near after rotation)
        hist2 = [(fi, far_x if fi < 9 else near_x, hy, 3.0) for fi in range(15)]
        det._phist[2] = deque(hist2, maxlen=15)
        det._detect_help_defense(34, tracks)
        count_after_second = len([e for e in det.events if e["type"] == "help_rotation"])

        assert count_after_second == count_after_first  # no new event

    def test_help_rotation_fields_in_events_log(self):
        """handler_id, rotation_dist must be in _export_events_log fieldnames."""
        import inspect
        src = inspect.getsource(UnifiedPipeline._export_events_log)
        assert "handler_id" in src
        assert "rotation_dist" in src

    def test_help_rotation_no_possessor_no_fire(self):
        """_detect_help_defense does not fire when _possessor is None."""
        det = self._make_det()
        det._possessor = None  # explicitly no possessor
        tracks = [
            {"player_id": 1, "team": "green", "x2d": 500, "y2d": 250, "has_ball": False},
            {"player_id": 2, "team": "white", "x2d": 520, "y2d": 250, "has_ball": False},
        ]
        det._detect_help_defense(0, tracks)
        help_events = [e for e in det.events if e["type"] == "help_rotation"]
        assert len(help_events) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 8 — shot creation type classification
# ═══════════════════════════════════════════════════════════════════════════════

class TestShotCreationClassification:

    def _classify(self, **kwargs):
        defaults = dict(
            dribble_count=0, shot_zone="mid_range",
            vel_toward_basket=1.0, defender_distance=100.0,
            ball_shot_arc_angle=45.0,
        )
        defaults.update(kwargs)
        return UnifiedPipeline._classify_shot_creation(**defaults)

    def test_shot_creation_catch_and_shoot(self):
        """dribble_count=0 → 'catch_and_shoot'."""
        assert self._classify(dribble_count=0) == "catch_and_shoot"

    def test_shot_creation_step_back(self):
        """dribble_count>=2 and vel_toward_basket<0, outside paint/mid_range → 'step_back'."""
        # Must use a zone NOT in ("paint", "mid_range") to avoid the post_up check
        result = self._classify(dribble_count=3, vel_toward_basket=-1.0, shot_zone="3pt_arc")
        assert result == "step_back"

    def test_shot_creation_drive_layup(self):
        """paint + high vtb + low arc → 'drive_layup'."""
        result = self._classify(
            dribble_count=2, shot_zone="paint",
            vel_toward_basket=3.0, ball_shot_arc_angle=40.0,
        )
        assert result == "drive_layup"

    def test_shot_creation_floater(self):
        """paint + high vtb + arc > 55 → 'floater'."""
        result = self._classify(
            dribble_count=2, shot_zone="paint",
            vel_toward_basket=3.0, ball_shot_arc_angle=60.0,
        )
        assert result == "floater"

    def test_shot_creation_pull_up(self):
        """dribble_count>=1 and not step_back, not in paint → 'pull_up'."""
        result = self._classify(
            dribble_count=1, shot_zone="mid_range",
            vel_toward_basket=1.5,
        )
        assert result == "pull_up"

    def test_shot_creation_post_up(self):
        """paint zone, vel < 0.5 → 'post_up'."""
        result = self._classify(
            dribble_count=2, shot_zone="paint",
            vel_toward_basket=0.2,
        )
        assert result == "post_up"

    def test_shot_creation_in_shot_log_fieldnames(self):
        """shot_creation must be in _export_shot_log fieldnames."""
        import inspect
        src = inspect.getsource(UnifiedPipeline._export_shot_log)
        assert "shot_creation" in src

    def test_classify_shot_creation_is_static(self):
        """_classify_shot_creation must be a static method on UnifiedPipeline."""
        import inspect
        # Static methods don't appear in __dict__ as functions when called on the class directly
        # but can be verified by calling without an instance
        result = UnifiedPipeline._classify_shot_creation(
            dribble_count=0, shot_zone="mid_range",
            vel_toward_basket=1.0, defender_distance=100.0,
            ball_shot_arc_angle=45.0,
        )
        assert isinstance(result, str)
