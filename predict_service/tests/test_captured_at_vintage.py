"""predict_service.tests.test_captured_at_vintage -- per-file test suite.

BE7-2-captured-at-vintage acceptance criteria:
  V1. Unchanged price keeps prior captured_at (not now()).
  V2. Changed price advances captured_at (uses the new row's timestamp).
  V3. post/Final game_state -> is_close=True on every output row.
  V4. Absent history -> passthrough (no crash; captured_at unmodified).
  V5. is_post_game() returns True only for post/Final vocabulary words.
  V6. vintage_key() returns (book, market_type, side); None for non-dicts / missing fields.
  V7. No $ field on any output.
  V8. normalize_markets NEVER raises on garbage inputs.
  V9. Pre/live game_state -> is_close unchanged (never falsely closed).
  V10. Multiple rows: only the unchanged-price rows keep prior ts; changed rows advance.
  V11. History row with no captured_at -> passthrough (no crash; no fabricated ts).
  V12. Row with no captured_at -> passthrough (no crash; is_close still set if post).

Run (per-file only -- never run the full suite, it freezes the box)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/tests/test_captured_at_vintage.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.captured_at_vintage import (  # noqa: E402
    HONEST_NOTE,
    is_post_game,
    normalize_markets,
    vintage_key,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ORIG_TS = "2026-06-18T20:00:00Z"
_NEW_TS = "2026-06-19T02:30:00Z"


def _row(book="draftkings", market_type="moneyline", side="home",
         odds=1.91, line=None, captured_at=_NEW_TS, is_close=False):
    return {
        "book": book,
        "market_type": market_type,
        "side": side,
        "odds": odds,
        "line": line,
        "captured_at": captured_at,
        "is_close": is_close,
    }


def _hist_row(book="draftkings", market_type="moneyline", side="home",
              odds=1.91, line=None, captured_at=_ORIG_TS, is_close=False):
    return {
        "book": book,
        "market_type": market_type,
        "side": side,
        "odds": odds,
        "line": line,
        "captured_at": captured_at,
        "is_close": is_close,
    }


def _has_dollar_key(d: object) -> bool:
    if isinstance(d, dict):
        return any("$" in str(k) or _has_dollar_key(v) for k, v in d.items())
    if isinstance(d, list):
        return any(_has_dollar_key(i) for i in d)
    return False


# ---------------------------------------------------------------------------
# V1: Unchanged price keeps prior captured_at (not now()).
# ---------------------------------------------------------------------------

def test_v1_unchanged_price_keeps_original_timestamp():
    current = [_row(odds=1.91, captured_at=_NEW_TS)]
    history = [_hist_row(odds=1.91, captured_at=_ORIG_TS)]
    result = normalize_markets(current, history, game_state="pre")
    assert len(result) == 1
    row = result[0]
    assert row["captured_at"] == _ORIG_TS, (
        "V1: unchanged price must keep the ORIGINAL ingest timestamp %r; got %r"
        % (_ORIG_TS, row["captured_at"])
    )


# ---------------------------------------------------------------------------
# V2: Changed price advances captured_at.
# ---------------------------------------------------------------------------

def test_v2_changed_price_advances_timestamp():
    current = [_row(odds=1.85, captured_at=_NEW_TS)]   # price changed
    history = [_hist_row(odds=1.91, captured_at=_ORIG_TS)]
    result = normalize_markets(current, history, game_state="pre")
    assert len(result) == 1
    row = result[0]
    assert row["captured_at"] == _NEW_TS, (
        "V2: changed price must advance to the new fetch timestamp; got %r" % row
    )


# ---------------------------------------------------------------------------
# V3: post/Final game_state -> is_close=True.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gs", ["post", "final", "ft", "complete", "finished", "closed",
                                  "Post", "FINAL", "Final"])
def test_v3_post_game_state_sets_is_close(gs):
    current = [_row(is_close=False)]
    result = normalize_markets(current, [], game_state=gs)
    assert len(result) == 1
    assert result[0]["is_close"] is True, (
        "V3: game_state=%r must set is_close=True; got %r" % (gs, result[0])
    )


# ---------------------------------------------------------------------------
# V4: Absent history -> passthrough (no crash).
# ---------------------------------------------------------------------------

def test_v4_absent_history_passthrough_no_crash():
    current = [_row(captured_at=_NEW_TS)]
    for hist in [None, [], {}]:
        try:
            result = normalize_markets(current, hist, game_state="pre")
            assert len(result) == 1
            assert result[0]["captured_at"] == _NEW_TS, (
                "V4: absent history must leave captured_at unchanged; got %r" % result
            )
        except Exception as exc:
            pytest.fail("V4: normalize_markets raised with history=%r: %s" % (hist, exc))


# ---------------------------------------------------------------------------
# V5: is_post_game() returns True only for post/Final vocabulary.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gs,expected", [
    ("post", True), ("final", True), ("ft", True),
    ("complete", True), ("finished", True), ("closed", True),
    ("Final", True), ("POST", True),
    ("pre", False), ("live", False), ("in_progress", False),
    (None, False), ("", False), (42, False), (object(), False),
])
def test_v5_is_post_game(gs, expected):
    assert is_post_game(gs) == expected, (
        "V5: is_post_game(%r) -> expected %s" % (gs, expected)
    )


# ---------------------------------------------------------------------------
# V6: vintage_key() returns (book, market_type, side) or None.
# ---------------------------------------------------------------------------

def test_v6_vintage_key_valid():
    row = {"book": "dk", "market_type": "moneyline", "side": "home",
           "odds": 1.9, "captured_at": _ORIG_TS}
    assert vintage_key(row) == ("dk", "moneyline", "home"), (
        "V6: valid row must return (book, market_type, side)"
    )


@pytest.mark.parametrize("bad", [
    None,
    "not-a-dict",
    {},
    {"book": "", "market_type": "ml", "side": "home"},
    {"book": "dk", "market_type": "", "side": "home"},
    {"book": "dk", "market_type": "ml", "side": ""},
])
def test_v6_vintage_key_none_on_bad_input(bad):
    result = vintage_key(bad)
    assert result is None, "V6: bad input must return None; got %r for %r" % (result, bad)


# ---------------------------------------------------------------------------
# V7: No $ field on any output.
# ---------------------------------------------------------------------------

def test_v7_no_dollar_key():
    current = [_row(), _row(side="away", odds=2.10)]
    history = [_hist_row(), _hist_row(side="away", odds=2.10)]
    result = normalize_markets(current, history, game_state="pre")
    # No output dict key may contain '$' (the no-dollar-field rule applies to data keys).
    assert not _has_dollar_key(result), "V7: no $ key allowed in output data"


# ---------------------------------------------------------------------------
# V8: NEVER raises on garbage inputs.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("markets,history,game_state", [
    (None, None, None),
    ([], None, "post"),
    ([None, "bad", 42], None, None),
    ([{"book": None}], [{"book": None}], "final"),
    ([{}], [{}], object()),
    ("not-a-list", "not-a-list", None),
])
def test_v8_never_raises(markets, history, game_state):
    try:
        result = normalize_markets(markets, history, game_state)
        assert isinstance(result, list), (
            "V8: must return a list; got %r" % type(result)
        )
    except Exception as exc:
        pytest.fail("V8: normalize_markets raised on garbage: %s" % exc)


# ---------------------------------------------------------------------------
# V9: pre/live game_state -> is_close unchanged.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gs", ["pre", "live", "in_progress", None])
def test_v9_non_post_state_does_not_flip_is_close(gs):
    current = [_row(is_close=False)]
    result = normalize_markets(current, [], game_state=gs)
    assert len(result) == 1
    assert result[0]["is_close"] is False, (
        "V9: game_state=%r must NOT set is_close=True; got %r" % (gs, result[0])
    )


# ---------------------------------------------------------------------------
# V10: Mixed rows -- only unchanged-price rows keep prior ts; changed advance.
# ---------------------------------------------------------------------------

def test_v10_mixed_unchanged_and_changed():
    markets = [
        _row(book="dk", side="home", odds=1.91, captured_at=_NEW_TS),   # unchanged
        _row(book="dk", side="away", odds=2.20, captured_at=_NEW_TS),   # changed
        _row(book="fd", side="home", odds=1.88, captured_at=_NEW_TS),   # new book (no hist)
    ]
    history = [
        _hist_row(book="dk", side="home", odds=1.91, captured_at=_ORIG_TS),
        _hist_row(book="dk", side="away", odds=2.10, captured_at=_ORIG_TS),  # price diff
        # "fd" not in history -> passthrough
    ]
    result = normalize_markets(markets, history, game_state="pre")
    assert len(result) == 3

    # Row 0: unchanged -> keeps _ORIG_TS
    assert result[0]["captured_at"] == _ORIG_TS, (
        "V10: unchanged-price row must keep original ts; got %r" % result[0]
    )
    # Row 1: changed -> keeps _NEW_TS
    assert result[1]["captured_at"] == _NEW_TS, (
        "V10: changed-price row must advance to new ts; got %r" % result[1]
    )
    # Row 2: not in history -> keeps _NEW_TS
    assert result[2]["captured_at"] == _NEW_TS, (
        "V10: row absent from history must keep current ts; got %r" % result[2]
    )


# ---------------------------------------------------------------------------
# V11: History row with no captured_at -> passthrough (no crash, no fabrication).
# ---------------------------------------------------------------------------

def test_v11_history_row_without_captured_at():
    hist = {"book": "dk", "market_type": "moneyline", "side": "home",
            "odds": 1.91, "line": None, "is_close": False}
    # history row has no captured_at -- must not fabricate one
    current = [_row(odds=1.91, captured_at=_NEW_TS)]
    try:
        result = normalize_markets(current, [hist], game_state="pre")
        assert len(result) == 1
        # Price matched but history captured_at is None -> can't use it -> keep current
        assert result[0]["captured_at"] == _NEW_TS, (
            "V11: history with no captured_at must not fabricate; current ts kept; got %r"
            % result[0]
        )
    except Exception as exc:
        pytest.fail("V11: raised when history has no captured_at: %s" % exc)


# ---------------------------------------------------------------------------
# V12: Row with no captured_at -> passthrough; is_close still set if post.
# ---------------------------------------------------------------------------

def test_v12_row_without_captured_at_is_close_set_on_post():
    current = [{"book": "dk", "market_type": "moneyline", "side": "home",
                "odds": 1.91, "line": None, "is_close": False}]
    try:
        result = normalize_markets(current, [], game_state="final")
        assert len(result) == 1
        assert result[0]["is_close"] is True, (
            "V12: post game must set is_close=True even when captured_at absent; got %r"
            % result[0]
        )
        assert "captured_at" not in result[0] or result[0].get("captured_at") is None, (
            "V12: must not fabricate captured_at when row had none"
        )
    except Exception as exc:
        pytest.fail("V12: raised on row without captured_at: %s" % exc)
