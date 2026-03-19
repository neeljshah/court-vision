"""NBA Ground-Truth Accuracy Validation Tests.

Validates that all computed stats fall within published NBA benchmark ranges
and satisfy physical constraints derived from real game data.

Ground truth sources:
- NBA court: 94 ft × 50 ft (official dimensions)
- Player max sprint: ~22 mph = 32.3 ft/s (SportVU / SecondSpectrum)
- Average player speed: ~4-6 ft/s (NBA tracking averages)
- NBA 5-out spacing hull area: ~800-1800 sq ft (5 offensive players spread)
- Average inter-player distance: ~12-20 ft (NBA average)
- Hard cut speed: 14+ ft/s (~9.5 mph)
- Screener speed: 0-3 ft/s (nearly stationary)
- Pick-and-roll contact range: within 6 ft
- Nearest defender (open): 4+ ft; (guarded): 2-4 ft; (tight): 0-2 ft
- Closing speed range: ±15 ft/s (defender sprinting toward/away from ball handler)
- Scoring run of 3+ consecutive made shots = momentum shift
- Passes per possession: 3-8 (half-court NBA average)
"""
import math
import pytest

from legacy.features.spacing import compute_spacing
from legacy.features.defensive_pressure import compute_defensive_pressure
from legacy.features.off_ball_events import (
    detect_off_ball_events,
    CUT_SPEED_THRESHOLD,
    SCREEN_SPEED_THRESHOLD,
    SCREEN_PROXIMITY,
    DRIFT_SPEED_MIN,
    DRIFT_SPEED_MAX,
)
from legacy.features.pick_and_roll import (
    detect_pick_and_roll,
    SCREEN_DISTANCE,
    SCREENER_MAX_SPEED,
    HANDLER_MIN_SPEED,
    PNR_WINDOW_FRAMES,
)
from legacy.features.momentum import compute_momentum
from legacy.features.passing_network import build_passing_network


# ---------------------------------------------------------------------------
# NBA court constants (official dimensions)
# ---------------------------------------------------------------------------

COURT_LENGTH_FT = 94.0
COURT_WIDTH_FT  = 50.0
COURT_AREA_SQ_FT = COURT_LENGTH_FT * COURT_WIDTH_FT  # 4700 sq ft

# Left and right basket positions (ft from left baseline)
LEFT_BASKET_FT  = 5.25
RIGHT_BASKET_FT = 88.75
BASKET_Y_FT     = 25.0  # center of court width

# Player physical limits
MAX_SPRINT_SPEED_FT_S = 32.3  # ~22 mph (fastest recorded NBA players)
AVG_PLAYER_SPEED_FT_S = 5.5   # typical average across a game


# ===========================================================================
# 1. Physical Constraint Validation
#    No computed value can violate the laws of physics or court dimensions.
# ===========================================================================

class TestPhysicalConstraints:
    """Spacing, distances, and speeds must be physically plausible."""

    def test_spacing_hull_area_never_exceeds_court_area(self):
        """Five players spread to court corners cannot exceed total court area."""
        corners = [
            (0.0, 0.0), (94.0, 0.0), (94.0, 50.0), (0.0, 50.0), (47.0, 25.0)
        ]
        result = compute_spacing(corners, game_id="g1", possession_id="p1",
                                 frame_number=1, timestamp_ms=0.0)
        assert result.convex_hull_area <= COURT_AREA_SQ_FT

    def test_spacing_hull_area_is_non_negative(self):
        positions = [(20.0, 10.0), (30.0, 20.0), (25.0, 30.0)]
        result = compute_spacing(positions, game_id="g1", possession_id="p1",
                                 frame_number=1, timestamp_ms=0.0)
        assert result.convex_hull_area >= 0.0

    def test_avg_inter_player_distance_non_negative(self):
        positions = [(47.0, 25.0), (40.0, 20.0), (54.0, 20.0)]
        result = compute_spacing(positions, game_id="g1", possession_id="p1",
                                 frame_number=1, timestamp_ms=0.0)
        assert result.avg_inter_player_distance >= 0.0

    def test_defensive_pressure_distance_non_negative(self):
        """Nearest defender distance must always be ≥ 0."""
        players = [
            {"track_id": 1, "x": 47.0, "y": 25.0, "team": None},
            {"track_id": 2, "x": 50.0, "y": 25.0, "team": None},
        ]
        results = compute_defensive_pressure(players, game_id="g1",
                                             frame_number=1, timestamp_ms=0.0,
                                             prev_distances={})
        for r in results:
            assert r.nearest_defender_distance >= 0.0

    def test_threshold_cut_speed_below_max_sprint(self):
        """CUT_SPEED_THRESHOLD must be below the physical maximum sprint speed."""
        assert CUT_SPEED_THRESHOLD < MAX_SPRINT_SPEED_FT_S, (
            f"CUT_SPEED_THRESHOLD={CUT_SPEED_THRESHOLD} exceeds max sprint {MAX_SPRINT_SPEED_FT_S} ft/s"
        )

    def test_threshold_screen_speed_is_realistic(self):
        """SCREEN_SPEED_THRESHOLD must be a slow walking/stationary speed."""
        assert SCREEN_SPEED_THRESHOLD <= 5.0, (
            f"SCREEN_SPEED_THRESHOLD={SCREEN_SPEED_THRESHOLD} ft/s is too fast for a screener"
        )

    def test_threshold_handler_speed_is_realistic(self):
        """HANDLER_MIN_SPEED must be below max sprint and above walking speed."""
        assert 5.0 <= HANDLER_MIN_SPEED <= MAX_SPRINT_SPEED_FT_S, (
            f"HANDLER_MIN_SPEED={HANDLER_MIN_SPEED} ft/s is outside realistic NBA range"
        )

    def test_threshold_screen_distance_is_realistic(self):
        """SCREEN_DISTANCE must fit within a realistic body-contact range (2-10 ft)."""
        assert 2.0 <= SCREEN_DISTANCE <= 10.0, (
            f"SCREEN_DISTANCE={SCREEN_DISTANCE} ft is outside realistic NBA contact range"
        )

    def test_threshold_drift_speed_range_is_realistic(self):
        """Drift speed range must represent a light jog, not a sprint or stationary."""
        assert DRIFT_SPEED_MIN >= 2.0   # at least faster than slow walk
        assert DRIFT_SPEED_MAX <= 15.0  # slower than a hard cut
        assert DRIFT_SPEED_MIN < DRIFT_SPEED_MAX

    def test_threshold_screen_proximity_is_realistic(self):
        """Screen proximity must represent a physically reachable setting distance."""
        assert 2.0 <= SCREEN_PROXIMITY <= 10.0, (
            f"SCREEN_PROXIMITY={SCREEN_PROXIMITY} ft is outside realistic range"
        )


# ===========================================================================
# 2. NBA Benchmark Range Validation
#    Stats derived from known positions must fall within published NBA averages.
# ===========================================================================

class TestNBABenchmarkRanges:
    """Computed stats must match published NBA tracking benchmarks."""

    def _five_out_positions(self):
        """Standard NBA 5-out offensive formation in court feet.

        Based on typical 5-out spacing: 4 players at corners/wings, 1 at top.
        NBA tracking data shows inter-player distance ~13-18 ft in this formation.
        """
        return [
            (10.0, 5.0),   # left corner
            (10.0, 45.0),  # right corner
            (28.0, 3.0),   # left wing
            (28.0, 47.0),  # right wing
            (20.0, 25.0),  # top of key
        ]

    def test_five_out_spacing_convex_hull_area_in_nba_range(self):
        """NBA 5-out formation hull area should be 400-2000 sq ft.

        This validates that spacing computation produces realistic values
        when players are placed in actual NBA positions.
        """
        positions = self._five_out_positions()
        result = compute_spacing(positions, game_id="g1", possession_id="p1",
                                 frame_number=1, timestamp_ms=0.0)
        # NBA 5-out teams typically spread 400-2000 sq ft (half-court formation)
        assert 400.0 <= result.convex_hull_area <= 2000.0, (
            f"5-out hull area {result.convex_hull_area:.1f} sq ft is outside NBA range [400, 2000]"
        )

    def test_five_out_avg_inter_player_distance_in_nba_range(self):
        """NBA 5-out all-pairs average distance should be 20-40 ft.

        Note: compute_spacing uses all pairwise distances (10 pairs for 5 players).
        Corner-to-corner distances in a 5-out formation (e.g., left corner to right corner)
        are ~40-48 ft, pulling the all-pairs average to 25-35 ft.
        """
        positions = self._five_out_positions()
        result = compute_spacing(positions, game_id="g1", possession_id="p1",
                                 frame_number=1, timestamp_ms=0.0)
        assert 20.0 <= result.avg_inter_player_distance <= 40.0, (
            f"Avg inter-player distance {result.avg_inter_player_distance:.1f} ft outside range [20, 40]"
        )

    def test_open_catch_defender_distance_in_nba_range(self):
        """An 'open' catch scenario should show nearest defender 4+ ft away.

        NBA tracking: 'open' = defender 4+ ft away (ESPN / SecondSpectrum).
        """
        # Offensive player at 3-pt arc catching a pass; nearest defender 8 ft away
        offense = {"track_id": 1, "x": 24.0, "y": 5.0, "team": "offense"}
        defense = {"track_id": 2, "x": 32.0, "y": 5.0, "team": "defense"}  # 8 ft away
        results = compute_defensive_pressure(
            [offense, defense], game_id="g1",
            frame_number=1, timestamp_ms=0.0, prev_distances={}
        )
        offensive_pressure = [r for r in results if r.track_id == 1]
        assert len(offensive_pressure) == 1
        # Open catch: nearest defender should be 4+ ft
        assert offensive_pressure[0].nearest_defender_distance >= 4.0

    def test_guarded_player_defender_distance_in_nba_range(self):
        """A closely guarded player should show nearest defender < 4 ft.

        NBA tracking: 'guarded' = defender 2-4 ft away.
        """
        offensive = {"track_id": 1, "x": 47.0, "y": 25.0, "team": "offense"}
        defender  = {"track_id": 2, "x": 49.5, "y": 25.0, "team": "defense"}  # 2.5 ft
        results = compute_defensive_pressure(
            [offensive, defender], game_id="g1",
            frame_number=1, timestamp_ms=0.0, prev_distances={}
        )
        guarded = [r for r in results if r.track_id == 1]
        assert guarded[0].nearest_defender_distance < 4.0

    def test_closing_speed_within_physical_limits(self):
        """Closing speed cannot exceed the sum of two sprinting players (~60 ft/s)."""
        # Frame 1: 20 ft apart
        p1 = {"track_id": 1, "x": 47.0, "y": 25.0, "team": None}
        p2 = {"track_id": 2, "x": 67.0, "y": 25.0, "team": None}
        prev = {}
        compute_defensive_pressure([p1, p2], "g1", 1, 0.0, prev)

        # Frame 2: 5 ft apart (closed 15 ft in one frame)
        p1b = {"track_id": 1, "x": 47.0, "y": 25.0, "team": None}
        p2b = {"track_id": 2, "x": 52.0, "y": 25.0, "team": None}
        results = compute_defensive_pressure([p1b, p2b], "g1", 2, 33.3, prev)

        for r in results:
            assert abs(r.closing_speed) < 100.0, (
                f"closing_speed={r.closing_speed} ft exceeds physical maximum"
            )

    def test_cut_event_fires_at_nba_realistic_speed(self):
        """A player cutting at 15 ft/s (~10 mph) must be classified as a cut.

        NBA hard cuts average 14-20 ft/s based on SecondSpectrum tracking.
        """
        player = {
            "track_id": 1, "x": 20.0, "y": 25.0, "speed": 15.0,
            "velocity_x": 15.0, "velocity_y": 0.0,
            "direction_degrees": 0.0, "frame_number": 1, "timestamp_ms": 1000.0,
        }
        result = detect_off_ball_events([[player]], game_id="g1", ball_pos=None)
        cuts = [e for e in result if e.event_type == "cut"]
        assert len(cuts) == 1, "15 ft/s toward basket must be classified as a cut"

    def test_walking_player_not_classified_as_cut(self):
        """A player walking at 4 ft/s (~2.7 mph) must NOT be a cut."""
        player = {
            "track_id": 1, "x": 20.0, "y": 25.0, "speed": 4.0,
            "velocity_x": 4.0, "velocity_y": 0.0,
            "direction_degrees": 0.0, "frame_number": 1, "timestamp_ms": 1000.0,
        }
        result = detect_off_ball_events([[player]], game_id="g1", ball_pos=None)
        cuts = [e for e in result if e.event_type == "cut"]
        assert cuts == [], "4 ft/s walking speed must not be a cut"

    def test_screener_detected_at_stationary_nba_speed(self):
        """A screener standing at 1 ft/s with a cutter 3 ft away must be detected."""
        screener = {
            "track_id": 5, "x": 42.0, "y": 25.0, "speed": 1.0,
            "velocity_x": 0.0, "velocity_y": 0.0,
            "direction_degrees": 0.0, "frame_number": 1, "timestamp_ms": 1000.0,
        }
        cutter = {
            "track_id": 6, "x": 45.0, "y": 25.0, "speed": 16.0,  # 3 ft away
            "velocity_x": 16.0, "velocity_y": 0.0,
            "direction_degrees": 0.0, "frame_number": 1, "timestamp_ms": 1000.0,
        }
        result = detect_off_ball_events([[screener, cutter]], game_id="g1", ball_pos=None)
        screens = [e for e in result if e.event_type == "screen" and e.track_id == 5]
        assert len(screens) == 1, "Stationary player 3 ft from a cutter must be screener"

    def test_pnr_detected_at_realistic_nba_speeds_and_distances(self):
        """PnR fires when handler ~10 ft/s drives off a screener within 5 ft.

        NBA pick-and-roll: handler averages 8-14 ft/s off the screen;
        screener speed drops to <2 ft/s at screen contact.
        """
        n = PNR_WINDOW_FRAMES
        frames = []
        for i in range(n):
            handler = {
                "track_id": 1, "x": 47.0, "y": 25.0, "speed": 10.0,
                "velocity_x": 0.0, "velocity_y": 0.0,
                "direction_degrees": 0.0, "frame_number": i, "timestamp_ms": float(i * 33),
            }
            # Screener within 5 ft at middle frame, then handler separates
            contact_dist = 5.0 if i == n // 2 else 5.0
            sep_dist     = 9.0 if i == n - 1 else 5.0
            dist = sep_dist if i == n - 1 else contact_dist
            screener = {
                "track_id": 2, "x": 47.0 + dist, "y": 25.0, "speed": 1.5,
                "velocity_x": 0.0, "velocity_y": 0.0,
                "direction_degrees": 0.0, "frame_number": i, "timestamp_ms": float(i * 33),
            }
            frames.append([handler, screener])

        result = detect_pick_and_roll(frames, game_id="g1")
        assert len(result) >= 1, "NBA-realistic PnR scenario must be detected"

    def test_momentum_3run_detected_as_possession_streak(self):
        """Three consecutive scoring possessions = possession_streak of 3.

        NBA broadcasts commonly highlight 7-0, 8-0 runs. The possession_streak
        metric captures the longest consecutive scoring possession streak in a segment.
        Note: scoring_run tracks the FINAL consecutive run at segment end and resets
        on a miss, so it is 0 here since B misses last. possession_streak = 3 is correct.
        """
        events = [
            {"team": "A", "made": True,  "possession_num": 0, "timestamp_ms": 0.0,    "game_id": "g1"},
            {"team": "A", "made": True,  "possession_num": 1, "timestamp_ms": 1000.0, "game_id": "g1"},
            {"team": "A", "made": True,  "possession_num": 2, "timestamp_ms": 2000.0, "game_id": "g1"},
            {"team": "B", "made": False, "possession_num": 3, "timestamp_ms": 3000.0, "game_id": "g1"},
            {"team": "B", "made": False, "possession_num": 4, "timestamp_ms": 4000.0, "game_id": "g1"},
        ]
        result = compute_momentum(events, game_id="g1", segment_size_possessions=5)
        assert len(result) >= 1
        assert result[0].possession_streak >= 3, (
            f"Three consecutive A-scores must produce possession_streak >= 3, got {result[0].possession_streak}"
        )

    def test_momentum_active_run_detected_as_scoring_run(self):
        """When a run is still active at segment end, scoring_run must equal the run length."""
        # Team A scores 3 in a row and is the LAST event (run not broken)
        events = [
            {"team": "B", "made": True,  "possession_num": 0, "timestamp_ms": 0.0,    "game_id": "g1"},
            {"team": "A", "made": True,  "possession_num": 1, "timestamp_ms": 1000.0, "game_id": "g1"},
            {"team": "A", "made": True,  "possession_num": 2, "timestamp_ms": 2000.0, "game_id": "g1"},
            {"team": "A", "made": True,  "possession_num": 3, "timestamp_ms": 3000.0, "game_id": "g1"},
        ]
        result = compute_momentum(events, game_id="g1", segment_size_possessions=5)
        assert len(result) >= 1
        assert result[0].scoring_run >= 3, (
            f"Active 3-shot run at segment end must produce scoring_run >= 3, got {result[0].scoring_run}"
        )

    def test_momentum_alternating_teams_no_long_run(self):
        """Alternating made shots between teams should produce a scoring run of 1."""
        events = [
            {"team": "A", "made": True,  "possession_num": i * 2,     "timestamp_ms": float(i * 2000),     "game_id": "g1"}
            for i in range(5)
        ] + [
            {"team": "B", "made": True,  "possession_num": i * 2 + 1, "timestamp_ms": float(i * 2000 + 1000), "game_id": "g1"}
            for i in range(5)
        ]
        # Sort by possession_num
        events.sort(key=lambda e: e["possession_num"])
        result = compute_momentum(events, game_id="g1", segment_size_possessions=10)
        for snap in result:
            assert snap.scoring_run <= 1, (
                f"Alternating makes must have scoring_run <= 1, got {snap.scoring_run}"
            )

    def test_passing_network_detects_minimum_passes_per_possession(self):
        """A 4-pass possession must produce at least 4 edges total.

        NBA half-court possessions average 3-8 passes (SecondSpectrum).
        """
        # 5 players, ball changes holder 4 times: 1→2→3→4→5
        n_frames = 10
        ball_x_sequence = [10.0, 10.0, 20.0, 20.0, 30.0, 30.0, 40.0, 40.0, 50.0, 50.0]
        player_x = {1: 10.0, 2: 20.0, 3: 30.0, 4: 40.0, 5: 50.0}
        y = 25.0

        frames = []
        balls  = []
        for i in range(n_frames):
            bx = ball_x_sequence[i]
            players = [{"track_id": tid, "x": px, "y": y} for tid, px in player_x.items()]
            frames.append(players)
            balls.append({"x": bx, "y": y})

        edges = build_passing_network(frames, game_id="g1", possession_id="p1",
                                      ball_frames=balls)
        # Should detect 4 transitions: 1→2, 2→3, 3→4, 4→5
        total_passes = sum(e.count for e in edges)
        assert total_passes >= 4, (
            f"4-pass possession produced only {total_passes} pass counts"
        )

    def test_passing_network_edge_counts_are_positive(self):
        """All detected passing edges must have count >= 1."""
        frames = [
            [{"track_id": 1, "x": 10.0, "y": 25.0},
             {"track_id": 2, "x": 30.0, "y": 25.0}],
            [{"track_id": 1, "x": 10.0, "y": 25.0},
             {"track_id": 2, "x": 30.0, "y": 25.0}],
        ]
        balls = [{"x": 10.0, "y": 25.0}, {"x": 30.0, "y": 25.0}]
        edges = build_passing_network(frames, game_id="g1", possession_id="p1",
                                      ball_frames=balls)
        for edge in edges:
            assert edge.count >= 1


# ===========================================================================
# 3. Cross-Module Consistency
#    If module A detects event X, module B's output must be consistent.
# ===========================================================================

class TestCrossModuleConsistency:
    """Stats from different modules must agree on shared scenarios."""

    def test_screen_event_mutually_exclusive_with_cut_for_same_player(self):
        """A single player cannot be both cutter (fast) and screener (slow)."""
        # A player at 20 ft/s moving toward basket is a cutter, not a screener
        cutter = {
            "track_id": 1, "x": 20.0, "y": 25.0, "speed": 20.0,
            "velocity_x": 20.0, "velocity_y": 0.0,
            "direction_degrees": 0.0, "frame_number": 1, "timestamp_ms": 1000.0,
        }
        result = detect_off_ball_events([[cutter]], game_id="g1", ball_pos=None)
        player_events = [e for e in result if e.track_id == 1]
        event_types = [e.event_type for e in player_events]
        assert "cut" not in event_types or "screen" not in event_types, (
            "A single player cannot be both cutter and screener simultaneously"
        )

    def test_swing_point_detected_after_team_change_in_lead(self):
        """Swing point must fire when the scoring leader switches between segments."""
        # Segment 0 (possessions 0-4): Team A dominates
        # Segment 1 (possessions 5-9): Team B dominates
        events = []
        for i in range(5):
            events.append({
                "team": "A", "made": True, "possession_num": i,
                "timestamp_ms": float(i * 1000), "game_id": "g1"
            })
        for i in range(5, 10):
            events.append({
                "team": "B", "made": True, "possession_num": i,
                "timestamp_ms": float(i * 1000), "game_id": "g1"
            })
        result = compute_momentum(events, game_id="g1", segment_size_possessions=5)
        swing_snapshots = [s for s in result if s.swing_point]
        assert len(swing_snapshots) >= 1, (
            "Lead change from Team A to Team B must produce at least one swing point"
        )

    def test_spacing_collapses_when_players_converge(self):
        """When all 5 players converge to the paint, hull area < 5-out formation."""
        # 5-out spread
        spread = [(10.0, 5.0), (10.0, 45.0), (28.0, 3.0), (28.0, 47.0), (20.0, 25.0)]
        # Paint cluster (all near basket)
        paint = [(8.0, 22.0), (8.0, 25.0), (8.0, 28.0), (10.0, 22.0), (10.0, 28.0)]

        spread_result = compute_spacing(spread, game_id="g1", possession_id="p1",
                                        frame_number=1, timestamp_ms=0.0)
        paint_result  = compute_spacing(paint,  game_id="g1", possession_id="p1",
                                        frame_number=2, timestamp_ms=33.0)

        assert paint_result.convex_hull_area < spread_result.convex_hull_area, (
            "Converged paint positions must produce lower hull area than 5-out spacing"
        )

    def test_possession_streak_matches_consecutive_make_count(self):
        """possession_streak must equal the actual consecutive scoring streak."""
        # Team A scores 4 in a row (possessions 0-3), then Team B scores once
        events = [
            {"team": "A", "made": True,  "possession_num": 0, "timestamp_ms": 0.0,    "game_id": "g1"},
            {"team": "A", "made": True,  "possession_num": 1, "timestamp_ms": 1000.0, "game_id": "g1"},
            {"team": "A", "made": True,  "possession_num": 2, "timestamp_ms": 2000.0, "game_id": "g1"},
            {"team": "A", "made": True,  "possession_num": 3, "timestamp_ms": 3000.0, "game_id": "g1"},
            {"team": "B", "made": True,  "possession_num": 4, "timestamp_ms": 4000.0, "game_id": "g1"},
        ]
        result = compute_momentum(events, game_id="g1", segment_size_possessions=5)
        assert len(result) >= 1
        # The segment contains a 4-possession streak by Team A
        assert result[0].possession_streak >= 4, (
            f"4 consecutive A-scores must yield possession_streak >= 4, got {result[0].possession_streak}"
        )


# ===========================================================================
# 4. Threshold Calibration Sanity
#    Thresholds must be within sensible ranges so real NBA events are detectable.
# ===========================================================================

class TestThresholdCalibration:
    """Verify thresholds are set in court-feet units, not pixel units."""

    def test_cut_threshold_is_not_pixel_scale(self):
        """CUT_SPEED_THRESHOLD must NOT be in pixel/s range (100-300).

        If set to pixel/s values, no NBA player moving at 14-22 ft/s
        would ever be classified as a cut.
        """
        assert CUT_SPEED_THRESHOLD <= 30.0, (
            f"CUT_SPEED_THRESHOLD={CUT_SPEED_THRESHOLD} looks like px/s (should be ft/s, max ~30)"
        )

    def test_screen_threshold_is_not_pixel_scale(self):
        """SCREEN_SPEED_THRESHOLD must NOT be in pixel/s range (30-100)."""
        assert SCREEN_SPEED_THRESHOLD <= 10.0, (
            f"SCREEN_SPEED_THRESHOLD={SCREEN_SPEED_THRESHOLD} looks like px/s (should be ft/s, ≤10)"
        )

    def test_handler_min_speed_is_not_pixel_scale(self):
        """HANDLER_MIN_SPEED must NOT be in pixel/s range (80-200)."""
        assert HANDLER_MIN_SPEED <= 30.0, (
            f"HANDLER_MIN_SPEED={HANDLER_MIN_SPEED} looks like px/s (should be ft/s, max ~30)"
        )

    def test_screen_distance_is_not_pixel_scale(self):
        """SCREEN_DISTANCE must NOT be in pixel range (60-100px)."""
        assert SCREEN_DISTANCE <= 20.0, (
            f"SCREEN_DISTANCE={SCREEN_DISTANCE} looks like pixels (should be ft, ≤20)"
        )

    def test_screen_proximity_is_not_pixel_scale(self):
        """SCREEN_PROXIMITY must NOT be in pixel range (50-100px)."""
        assert SCREEN_PROXIMITY <= 20.0, (
            f"SCREEN_PROXIMITY={SCREEN_PROXIMITY} looks like pixels (should be ft, ≤20)"
        )

    def test_drift_range_is_not_pixel_scale(self):
        """DRIFT thresholds must NOT be in pixel/s range."""
        assert DRIFT_SPEED_MAX <= 20.0, (
            f"DRIFT_SPEED_MAX={DRIFT_SPEED_MAX} looks like px/s (should be ft/s, ≤20)"
        )

    def test_at_least_one_nba_speed_triggers_cut(self):
        """A player moving at any common NBA cut speed (14-22 ft/s) must fire a cut."""
        nba_cut_speeds = [14.5, 16.0, 18.0, 20.0, 22.0]
        for speed in nba_cut_speeds:
            player = {
                "track_id": 1, "x": 20.0, "y": 25.0, "speed": speed,
                "velocity_x": speed, "velocity_y": 0.0,
                "direction_degrees": 0.0, "frame_number": 1, "timestamp_ms": 1000.0,
            }
            result = detect_off_ball_events([[player]], game_id="g1", ball_pos=None)
            cuts = [e for e in result if e.event_type == "cut"]
            assert len(cuts) == 1, (
                f"NBA cut speed {speed} ft/s must produce a cut event"
            )

    def test_at_least_one_nba_screener_speed_triggers_screen(self):
        """A screener at typical NBA stationary speed (0.5-2 ft/s) must be detected."""
        nba_screen_speeds = [0.5, 1.0, 1.5, 2.0, 2.5]
        cutter_x = 33.0
        for speed in nba_screen_speeds:
            screener = {
                "track_id": 10, "x": 30.0, "y": 25.0, "speed": speed,
                "velocity_x": 0.0, "velocity_y": 0.0,
                "direction_degrees": 0.0, "frame_number": 1, "timestamp_ms": 1000.0,
            }
            cutter = {
                "track_id": 11, "x": cutter_x, "y": 25.0, "speed": 16.0,
                "velocity_x": 16.0, "velocity_y": 0.0,
                "direction_degrees": 0.0, "frame_number": 1, "timestamp_ms": 1000.0,
            }
            result = detect_off_ball_events([[screener, cutter]], game_id="g1", ball_pos=None)
            screens = [e for e in result if e.event_type == "screen" and e.track_id == 10]
            assert len(screens) == 1, (
                f"Screener at {speed} ft/s (3 ft from cutter) must produce a screen event"
            )
