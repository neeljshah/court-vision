"""
test_context_classifiers.py — Tests for ScoreboardOCR, PossessionClassifier,
and PlayTypeClassifier.

All tests use synthetic data — NO video processing, NO NBA API calls.
Follows the existing patterns from test_phase2.py (importorskip guards,
monkeypatching, synthetic player/frame dicts).
"""

from __future__ import annotations

import copy
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── ScoreboardOCR ─────────────────────────────────────────────────────────────

scoreboard_ocr_mod = pytest.importorskip(
    "src.tracking.scoreboard_ocr",
    reason="scoreboard_ocr not yet implemented",
)

_EXPECTED_KEYS = {
    "game_clock_sec", "shot_clock", "home_score", "away_score",
    "period", "home_timeouts", "away_timeouts", "home_fouls",
    "away_fouls", "score_diff",
}


def _blank_frame(w: int = 640, h: int = 360) -> np.ndarray:
    """Minimal BGR frame — no real image content needed."""
    return np.zeros((h, w, 3), dtype=np.uint8)


def test_scoreboard_read_returns_all_keys():
    """read() returns a dict with all expected scoreboard keys."""
    ocr = scoreboard_ocr_mod.ScoreboardOCR(frame_width=640, frame_height=360)
    result = ocr.read(_blank_frame())
    missing = _EXPECTED_KEYS - set(result.keys())
    assert not missing, f"Missing keys: {missing}"


def test_scoreboard_cache_returned_on_non_ocr_frames():
    """Injected last_state is returned verbatim on non-OCR frames."""
    ocr = scoreboard_ocr_mod.ScoreboardOCR(frame_width=640, frame_height=360)
    # Inject known state
    ocr._last_state["home_score"] = 77
    ocr._last_state["away_score"] = 65
    # frame_counter becomes 1 after first read(); 1 % 30 != 0 → cache path
    result = ocr.read(_blank_frame())
    assert result["home_score"] == 77
    assert result["away_score"] == 65


def test_scoreboard_no_ocr_triggered_mid_interval():
    """frame_counter % _OCR_INTERVAL != 0 returns cached period without calling OCR."""
    ocr = scoreboard_ocr_mod.ScoreboardOCR(frame_width=640, frame_height=360)
    ocr._frame_counter = 13   # next read() → counter=14, 14%15!=0 → cached
    ocr._last_state["period"] = 2
    result = ocr.read(_blank_frame())
    assert result["period"] == 2


def test_parse_scoreboard_period_q3():
    """_parse_scoreboard_text parses Q3 as period=3."""
    state = scoreboard_ocr_mod._parse_scoreboard_text("Q3 3:15 BOS 98 LAL 94")
    assert state["period"] == 3


def test_parse_scoreboard_scores():
    """_parse_scoreboard_text extracts home_score=98, away_score=94.

    Uses 'Q3 3:15 BOS 98 LAL 94' — the clock digits 3 and 15 are both
    below 30 so they are filtered out, leaving 98 and 94 as the first two
    candidates in [30, 175].
    """
    state = scoreboard_ocr_mod._parse_scoreboard_text("Q3 3:15 BOS 98 LAL 94")
    assert state["home_score"] == 98
    assert state["away_score"] == 94


def test_parse_scoreboard_clock_valid():
    """_parse_scoreboard_text parses 7:45 → game_clock_sec=465."""
    state = scoreboard_ocr_mod._parse_scoreboard_text("Q2 7:45 GSW 110 BOS 108")
    assert state["game_clock_sec"] == pytest.approx(7 * 60 + 45)


def test_parse_scoreboard_clock_out_of_range():
    """_parse_scoreboard_text returns -1.0 for a clock with minutes > 12."""
    state = scoreboard_ocr_mod._parse_scoreboard_text("Q3 47:32 BOS 98 LAL 94")
    assert state["game_clock_sec"] == -1.0


def test_parse_scoreboard_unparseable_fields():
    """All integer/float fields default to -1/-1.0 for unparseable input."""
    state = scoreboard_ocr_mod._parse_scoreboard_text("NBA Basketball Game Live")
    for key in ("period", "home_score", "away_score",
                "home_timeouts", "away_timeouts", "home_fouls", "away_fouls"):
        assert state[key] == -1, f"Expected -1 for '{key}', got {state[key]}"
    assert state["game_clock_sec"] == -1.0
    assert state["score_diff"] == 0


def test_parse_scoreboard_empty_string_no_raise():
    """_parse_scoreboard_text does not raise on empty input."""
    state = scoreboard_ocr_mod._parse_scoreboard_text("")
    assert isinstance(state, dict)
    assert _EXPECTED_KEYS.issubset(state.keys())


def test_scoreboard_score_diff_computed_on_ocr_frame(monkeypatch):
    """score_diff = home_score - away_score is set on the frame that runs OCR."""
    from src.tracking.scoreboard_ocr import _DEFAULT_STATE

    ocr = scoreboard_ocr_mod.ScoreboardOCR(frame_width=640, frame_height=360)
    fake_parsed = dict(_DEFAULT_STATE)
    fake_parsed["home_score"] = 105
    fake_parsed["away_score"] = 97

    monkeypatch.setattr(ocr, "_ocr_frame", lambda _frame: copy.copy(fake_parsed))
    ocr._frame_counter = 29       # next call: counter=30, 30%30==0 → OCR runs
    result = ocr.read(_blank_frame())
    assert result["score_diff"] == 8    # 105 - 97


def test_scoreboard_score_diff_zero_when_scores_unknown():
    """score_diff stays 0 when home_score or away_score is still -1."""
    ocr = scoreboard_ocr_mod.ScoreboardOCR(frame_width=640, frame_height=360)
    result = ocr.read(_blank_frame())   # first call, no OCR — all defaults
    assert result["score_diff"] == 0


def test_parse_scoreboard_pipe_separated_espn_style():
    """_parse_scoreboard_text handles '4:32 | 18 | GSW 98 BOS 104' format.

    The pipe-separated ESPN/TNT layout: game clock | shot clock | team score.
    OCR strips the pipes and leaves space-separated tokens.
    Valid game clock must have minutes ≤ 12.
    """
    # Use seconds < 30 so clock digits don't pollute the score candidates (range 30-175)
    state = scoreboard_ocr_mod._parse_scoreboard_text("4:05 | 18 | GSW 98 BOS 104")
    assert state["game_clock_sec"] == pytest.approx(4 * 60 + 5)
    assert state["shot_clock"] == pytest.approx(18.0)
    assert state["home_score"] == 98
    assert state["away_score"] == 104


def test_parse_scoreboard_decimal_shot_clock():
    """_parse_scoreboard_text parses 'xx.x' decimal shot clock (e.g. 14.3)."""
    state = scoreboard_ocr_mod._parse_scoreboard_text("Q4 0:52 | 14.3 | MIA 88 BOS 91")
    assert state["shot_clock"] == pytest.approx(14.3)


def test_parse_scoreboard_decimal_shot_clock_sub_one():
    """_parse_scoreboard_text handles 0.x shot clock (under 1 second)."""
    # 0.8 is valid shot clock — last-second shot scenario
    state = scoreboard_ocr_mod._parse_scoreboard_text("Q3 11:04 | 0.8 | LAL 72 GSW 70")
    assert state["shot_clock"] == pytest.approx(0.8)


# ── PossessionClassifier ──────────────────────────────────────────────────────

poss_mod = pytest.importorskip(
    "src.tracking.possession_classifier",
    reason="possession_classifier not yet implemented",
)


def _make_player(
    pid: int,
    x: float,
    y: float,
    team: str,
    has_ball: bool = False,
    speed: float = 0.0,
) -> dict:
    return {
        "player_id": pid,
        "x":         x,
        "y":         y,
        "team":      team,
        "has_ball":  has_ball,
        "speed":     speed,
    }


def test_poss_half_court_no_players():
    """Returns 'half_court' when player list is empty (no handler → default path)."""
    clf = poss_mod.PossessionClassifier()
    result = clf.update([], ball_pos=(470, 250), frame_num=0)
    assert result["possession_type"] == "half_court"


def test_poss_double_team():
    """Returns 'double_team' when 2+ defenders are within the double-team radius."""
    # rad_px = _DBL_TEAM_RAD_N * 940 ≈ 41.4 px
    clf    = poss_mod.PossessionClassifier()
    handler  = _make_player(0, x=470, y=250, team="A", has_ball=True, speed=1.0)
    def1     = _make_player(1, x=475, y=252, team="B")   # within ~5.8 px
    def2     = _make_player(2, x=465, y=248, team="B")   # within ~7.2 px
    off_mate = _make_player(3, x=700, y=250, team="A")
    result   = clf.update([handler, def1, def2, off_mate], ball_pos=(470, 250), frame_num=0)
    assert result["possession_type"] == "double_team"


def test_poss_fast_break():
    """Returns 'fast_break' when 3 attackers near handler but only 1 defender."""
    # att_n=3, def_n=1, surplus=2 > _FAST_BRK_ADV(1)
    clf     = poss_mod.PossessionClassifier()
    handler = _make_player(0, x=600, y=250, team="A", has_ball=True, speed=1.0)
    att1    = _make_player(1, x=580, y=200, team="A")
    att2    = _make_player(2, x=620, y=300, team="A")
    def1    = _make_player(3, x=610, y=245, team="B")
    result  = clf.update([handler, att1, att2, def1], ball_pos=(600, 250), frame_num=0)
    assert result["possession_type"] == "fast_break"


def test_poss_paint_touch():
    """Returns 'paint_touch' when ball is inside the paint lane."""
    # Paint zone: xn < 0.15 → x < 141; yn 0.28–0.72 → y ∈ [140, 360]
    clf     = poss_mod.PossessionClassifier()
    ball    = (80, 250)
    handler = _make_player(0, x=80, y=250, team="A", has_ball=True, speed=1.0)
    defense = _make_player(1, x=500, y=250, team="B")
    result  = clf.update([handler, defense], ball_pos=ball, frame_num=0)
    assert result["possession_type"] == "paint_touch"


def test_poss_duration_increases():
    """possession_duration_sec grows with each successive frame call."""
    clf     = poss_mod.PossessionClassifier(fps=30)
    handler = _make_player(0, x=470, y=250, team="A", has_ball=True)
    defense = _make_player(1, x=100, y=250, team="B")
    r0 = clf.update([handler, defense], ball_pos=(470, 250), frame_num=0)
    r1 = clf.update([handler, defense], ball_pos=(470, 250), frame_num=15)
    r2 = clf.update([handler, defense], ball_pos=(470, 250), frame_num=30)
    assert r1["possession_duration_sec"] >= r0["possession_duration_sec"]
    assert r2["possession_duration_sec"] > r1["possession_duration_sec"]


def test_poss_paint_touches_reset_on_team_change():
    """_paint_n resets to 0 when the possessing team changes."""
    clf       = poss_mod.PossessionClassifier()
    ball_paint = (80, 250)
    handler_a  = _make_player(0, x=80, y=250, team="A", has_ball=True, speed=0.5)
    defense_b  = _make_player(1, x=500, y=250, team="B")
    clf.update([handler_a, defense_b], ball_pos=ball_paint, frame_num=0)
    assert clf._paint_n >= 1

    # Team B takes possession
    handler_b = _make_player(1, x=500, y=250, team="B", has_ball=True, speed=0.5)
    offense_a = _make_player(0, x=80, y=250, team="A")
    clf.update([handler_b, offense_a], ball_pos=(500, 250), frame_num=1)
    assert clf._paint_n == 0, "paint_touches must reset when possession changes"


def test_poss_shot_clock_at_start():
    """shot_clock_est is 24.0 at the very first frame of a new possession."""
    clf     = poss_mod.PossessionClassifier(fps=30)
    handler = _make_player(0, x=470, y=250, team="A", has_ball=True)
    defense = _make_player(1, x=100, y=250, team="B")
    result  = clf.update([handler, defense], ball_pos=(470, 250), frame_num=0)
    assert result["shot_clock_est"] == pytest.approx(24.0, abs=0.1)


def test_poss_shot_clock_decrements():
    """shot_clock_est decrements by elapsed time since possession start."""
    clf     = poss_mod.PossessionClassifier(fps=30)
    handler = _make_player(0, x=470, y=250, team="A", has_ball=True)
    defense = _make_player(1, x=100, y=250, team="B")
    clf.update([handler, defense], ball_pos=(470, 250), frame_num=0)
    # 60 frames at 30 fps = 2 seconds elapsed → 24 - 2 = 22
    result = clf.update([handler, defense], ball_pos=(470, 250), frame_num=60)
    assert result["shot_clock_est"] == pytest.approx(22.0, abs=0.2)


def test_poss_off_ball_distance_accumulates():
    """off_ball_distance grows as off-ball teammates move between frames."""
    clf      = poss_mod.PossessionClassifier(fps=30)
    handler  = _make_player(0, x=470, y=250, team="A", has_ball=True)
    off_ball = _make_player(1, x=300, y=200, team="A")
    defense  = _make_player(2, x=100, y=250, team="B")

    clf.update([handler, off_ball, defense], ball_pos=(470, 250), frame_num=0)
    # Move off-ball player 10 px to the right
    r1 = clf.update(
        [handler, _make_player(1, x=310, y=200, team="A"), defense],
        ball_pos=(470, 250), frame_num=1,
    )
    r2 = clf.update(
        [handler, _make_player(1, x=320, y=200, team="A"), defense],
        ball_pos=(470, 250), frame_num=2,
    )
    assert r1["off_ball_distance"] > 0
    assert r2["off_ball_distance"] > r1["off_ball_distance"]


# ── PlayTypeClassifier ────────────────────────────────────────────────────────

play_mod = pytest.importorskip(
    "src.tracking.play_type_classifier",
    reason="play_type_classifier not yet implemented",
)


def _make_track(
    pid: int,
    x: float,
    y: float,
    team: str = "A",
    has_ball: bool = False,
    event: str = "none",
) -> dict:
    return {
        "player_id": pid,
        "x2d":       x,
        "y2d":       y,
        "team":      team,
        "has_ball":  has_ball,
        "event":     event,
    }


def _make_frame(frame_num: int, tracks: list) -> dict:
    return {"frame": frame_num, "tracks": tracks}


def test_play_type_unclassified_few_frames():
    """Returns 'unclassified' when the buffer has fewer than 10 frames."""
    clf    = play_mod.PlayTypeClassifier()
    frames = [_make_frame(i, [_make_track(0, 470, 250, has_ball=True)]) for i in range(5)]
    assert clf.update(frames, possession_type="half_court") == "unclassified"


def test_play_type_pass_through_transition():
    """possession_type='transition' is returned directly without classifier logic."""
    clf    = play_mod.PlayTypeClassifier()
    frames = [_make_frame(i, [_make_track(0, 470, 250, has_ball=True)]) for i in range(20)]
    assert clf.update(frames, possession_type="transition") == "transition"


def test_play_type_pass_through_post_up():
    """possession_type='post_up' is returned directly without classifier logic."""
    clf    = play_mod.PlayTypeClassifier()
    frames = [_make_frame(i, [_make_track(0, 470, 250, has_ball=True)]) for i in range(20)]
    assert clf.update(frames, possession_type="post_up") == "post_up"


def test_play_type_pass_through_fast_break():
    """possession_type='fast_break' is returned directly without classifier logic."""
    clf    = play_mod.PlayTypeClassifier()
    frames = [_make_frame(i, [_make_track(0, 470, 250, has_ball=True)]) for i in range(20)]
    assert clf.update(frames, possession_type="fast_break") == "fast_break"


def test_play_type_isolation_detected():
    """_is_isolation() returns True: handler slow ≥ 15 frames, teammates spread far.

    Inferred map_w from tracks ≈ 940. Mates placed 400 px away → dist_n ≈ 0.43 > 0.38.
    """
    clf = play_mod.PlayTypeClassifier()
    hx, hy = 470.0, 250.0
    frames = [
        _make_frame(i, [
            _make_track(0, hx, hy, team="A", has_ball=True),          # stationary handler
            _make_track(1, hx + 400, hy, team="A"),                   # spread right
            _make_track(2, hx - 400, hy, team="A"),                   # spread left
        ])
        for i in range(20)
    ]
    clf._buffer.extend(frames)
    buf          = list(clf._buffer)
    handler_seq  = clf._handler_seq(buf)
    assert clf._is_isolation(buf, handler_seq), (
        "_is_isolation should return True: handler stationary ≥ 15 frames, "
        "teammates > 0.38 × map_w away"
    )


def test_play_type_hand_off_detected():
    """_is_hand_off() returns True when possession changes at close range.

    Player 0 holds ball frames 0–4, player 1 holds it from frame 5+.
    Both players are within _HO_RADIUS_N × 940 ≈ 42 px of each other.
    """
    clf    = play_mod.PlayTypeClassifier()
    frames = [
        _make_frame(i, [
            _make_track(0, 470.0, 250.0, team="A", has_ball=(i < 5)),
            _make_track(1, 475.0, 250.0, team="A", has_ball=(i >= 5)),
        ])
        for i in range(10)
    ]
    assert clf._is_hand_off(frames), (
        "_is_hand_off should detect possession change within contact radius"
    )


def test_play_type_spot_up_detected():
    """_is_spot_up() returns True when a pass is followed by a shot within 60 frames."""
    clf    = play_mod.PlayTypeClassifier()
    frames = [
        _make_frame(0,  [_make_track(0, 470, 250, has_ball=True,  event="pass")]),
        _make_frame(10, [_make_track(1, 100, 250, has_ball=True,  event="none")]),
        _make_frame(30, [_make_track(1, 100, 250, has_ball=True,  event="shot")]),
    ] + [_make_frame(i + 40, [_make_track(0, 470, 250)]) for i in range(10)]
    assert clf._is_spot_up(frames), (
        "_is_spot_up should detect pass→shot within 60 frames"
    )


def test_play_type_buffer_maxlen():
    """Deque buffer respects maxlen=90 — oldest frames are dropped at capacity."""
    clf    = play_mod.PlayTypeClassifier()
    frames = [
        _make_frame(i, [_make_track(0, 470, 250, has_ball=True)])
        for i in range(95)
    ]
    clf.update(frames, possession_type="half_court")
    assert len(clf._buffer) == play_mod._BUFFER_FRAMES, (
        f"Buffer length {len(clf._buffer)} should equal "
        f"_BUFFER_FRAMES={play_mod._BUFFER_FRAMES}"
    )
