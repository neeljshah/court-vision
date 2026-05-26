"""
tests/test_scoreboard_ocr_corrections.py
Tests for BUG 1–3 fixes in scoreboard_ocr.py.

Covers:
  - Score monotonic enforcement (BUG 1)
  - Both-in-shot-clock-range rejection (BUG 2)
  - Period regex widening (BUG 3)

All tests are pure-logic (no frame/OCR required): they call
_parse_scoreboard_text() for BUG 3, and exercise ScoreboardOCR's
score-validation logic via monkey-patching _ocr_frame() for BUGs 1+2.
"""

import pytest

scoreboard_ocr = pytest.importorskip(
    "src.tracking.scoreboard_ocr",
    reason="src.tracking.scoreboard_ocr not importable — skip",
)

ScoreboardOCR        = scoreboard_ocr.ScoreboardOCR
_parse_scoreboard_text = scoreboard_ocr._parse_scoreboard_text

import numpy as np


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_ocr(home: int, away: int):
    """Build a ScoreboardOCR that always 'reads' the given scores."""
    ocr = ScoreboardOCR(frame_width=1920, frame_height=1080)
    # Advance counter so next call to read() triggers OCR
    ocr._frame_counter = ocr._ocr_interval - 1

    def _fake_ocr_frame(_frame):
        state = dict(scoreboard_ocr._DEFAULT_STATE)
        state["home_score"] = home
        state["away_score"] = away
        return state

    ocr._ocr_frame = _fake_ocr_frame
    return ocr


def _blank_frame():
    return np.zeros((1080, 1920, 3), dtype=np.uint8)


# ── BUG 1: score decrease must be rejected ────────────────────────────────────

def test_score_decrease_rejected():
    """home_score 50 → 45 on the next OCR frame must be rejected; stays 50."""
    ocr = _make_ocr(50, 80)
    frame = _blank_frame()

    result1 = ocr.read(frame)
    assert result1["home_score"] == 50, "first read should be accepted"

    # Advance counter to trigger next OCR scan, now with a lower home_score
    ocr._frame_counter = ocr._ocr_interval - 1
    ocr._ocr_frame = lambda _f: {**dict(scoreboard_ocr._DEFAULT_STATE),
                                  "home_score": 45, "away_score": 82}
    result2 = ocr.read(frame)

    # Cache should still hold the last valid home_score=50
    assert result2["home_score"] == 50, (
        f"home_score decreased 50→45 should have been rejected; got {result2['home_score']}"
    )


def test_score_normal_increase_accepted():
    """home_score 50 → 52 on the next OCR frame must be accepted."""
    ocr = _make_ocr(50, 80)
    frame = _blank_frame()

    ocr.read(frame)  # prime with 50

    ocr._frame_counter = ocr._ocr_interval - 1
    ocr._ocr_frame = lambda _f: {**dict(scoreboard_ocr._DEFAULT_STATE),
                                  "home_score": 52, "away_score": 82}
    result2 = ocr.read(frame)

    assert result2["home_score"] == 52, (
        f"home_score increase 50→52 should be accepted; got {result2['home_score']}"
    )


def test_initial_score_zero_does_not_block_first_update():
    """First real score read (e.g. home=2 early Q1) must always be accepted."""
    ocr = _make_ocr(2, 0)
    frame = _blank_frame()
    result = ocr.read(frame)

    assert result["home_score"] == 2, (
        f"First home_score=2 should be accepted (prev=-1); got {result['home_score']}"
    )


# ── BUG 2: both scores in shot-clock range → reject both ─────────────────────

def test_score_both_in_shot_clock_range_rejected():
    """When both scores are in [1,24] treat as shot-clock misread; return prev valid (None on first)."""
    ocr = _make_ocr(14, 18)   # both in [1,24]
    frame = _blank_frame()

    result = ocr.read(frame)

    # No prior valid score exists → cache still holds -1 (unknown)
    assert result["home_score"] == -1, (
        f"Both scores in shot-clock range on first read; expected home_score=-1, got {result['home_score']}"
    )
    assert result["away_score"] == -1, (
        f"Both scores in shot-clock range on first read; expected away_score=-1, got {result['away_score']}"
    )


def test_score_both_in_shot_clock_range_returns_prev_valid():
    """After a valid read, a subsequent both-in-[1,24] frame keeps the previous valid scores."""
    ocr = _make_ocr(75, 68)   # valid scores
    frame = _blank_frame()
    ocr.read(frame)            # prime cache

    # Next OCR scan returns shot-clock digits as scores
    ocr._frame_counter = ocr._ocr_interval - 1
    ocr._ocr_frame = lambda _f: {**dict(scoreboard_ocr._DEFAULT_STATE),
                                  "home_score": 14, "away_score": 18}
    result2 = ocr.read(frame)

    assert result2["home_score"] == 75, (
        f"Shot-clock misread frame should preserve prev home_score=75; got {result2['home_score']}"
    )
    assert result2["away_score"] == 68, (
        f"Shot-clock misread frame should preserve prev away_score=68; got {result2['away_score']}"
    )


# ── BUG 3: period regex variants ─────────────────────────────────────────────

@pytest.mark.parametrize("text,expected_period", [
    ("Q1 14:32 24",      1),
    ("Q 1 10:00",        1),
    ("Q-1 08:45",        1),
    ("1st 11:30",        1),
    ("1ST 09:00",        1),
    ("1 ST 07:22",       1),
    ("FIRST quarter",    1),
    ("first QTR 06:00",  1),
])
def test_period_regex_matches_q1_variants(text, expected_period):
    state = _parse_scoreboard_text(text)
    assert state["period"] == expected_period, (
        f"Expected period=1 for text={text!r}; got {state['period']}"
    )


@pytest.mark.parametrize("text,expected_period", [
    ("Q2 08:00 14",  2),
    ("2nd 06:30",    2),
    ("SECOND QTR",   2),
    ("Q3 05:15",     3),
    ("3rd quarter",  3),
    ("THIRD",        3),
    ("Q4 01:00",     4),
    ("4th 00:30",    4),
    ("FOURTH",       4),
    ("OT 03:00",     5),
    ("OT1 02:30",    5),
])
def test_period_regex_matches_q2_q3_q4(text, expected_period):
    state = _parse_scoreboard_text(text)
    assert state["period"] == expected_period, (
        f"Expected period={expected_period} for text={text!r}; got {state['period']}"
    )
