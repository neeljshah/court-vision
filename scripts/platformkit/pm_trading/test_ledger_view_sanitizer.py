"""test_ledger_view_sanitizer.py -- per-file tests for ledger_view_sanitizer.

Acceptance criteria (BE7-6 iter3/4):
  1. Rows with sport containing 'test_' are dropped.
  2. Rows with bet_id containing 'test_' are dropped.
  3. Rows with game_id='gg' (single-token, <6 chars) are dropped.
  4. Legitimate nba/mlb rows with well-formed game_id are retained.
  5. Input list is NEVER mutated (read-only invariant).
  6. Empty input -> empty output, no crash.
  7. SanitizeResult.dropped carries bet_id/sport/game_id/reason for each drop.
  8. A row matching multiple drop rules reports all reasons joined by '|'.
  9. game_id absent (key missing or None) -> row is NOT dropped on that basis.
  10. Structured game_ids (8+ digit numeric, slug-with-separator) are retained.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \\
    scripts/platformkit/pm_trading/test_ledger_view_sanitizer.py -q
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# ---------------------------------------------------------------------------
# Hermetic import: insert repo root then use package path
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.platformkit.pm_trading.ledger_view_sanitizer import (
    SanitizeResult,
    sanitize_rows,
)


# ---------------------------------------------------------------------------
# Row-builder helpers
# ---------------------------------------------------------------------------

def _row(
    bet_id: str = "BET_001",
    sport: str = "nba",
    matchup: str = "Lakers @ Celtics",
    game_id: str | None = "0042500401",
    status: str = "open",
) -> Dict[str, Any]:
    """Build a minimal ledger-row dict."""
    row: Dict[str, Any] = {
        "bet_id": bet_id,
        "sport": sport,
        "matchup": matchup,
        "status": status,
        "stake_units": 1.0,
        "executed": False,
    }
    if game_id is not None:
        row["game_id"] = game_id
    return row


def _test_sport_row(
    bet_id: str = "BET_T01",
    sport: str = "test_none_path_no_raise",
    matchup: str = "Lakers @ Celtics",
) -> Dict[str, Any]:
    return _row(bet_id=bet_id, sport=sport, matchup=matchup, game_id="gg")


def _real_nba_row(bet_id: str = "BET_N01") -> Dict[str, Any]:
    return _row(bet_id=bet_id, sport="nba", matchup="BOS@NYK",
                game_id="0042500401")


def _real_mlb_row(bet_id: str = "BET_M01") -> Dict[str, Any]:
    return _row(bet_id=bet_id, sport="mlb", matchup="NYY@BOS",
                game_id="401767834")


# ---------------------------------------------------------------------------
# Test 1: sport containing 'test_' -> dropped
# ---------------------------------------------------------------------------

def test_test_sport_prefix_dropped():
    """Rows whose sport starts with 'test_' must be dropped."""
    rows = [_row(sport="test_none_path_no_raise", game_id="0042500401")]
    clean, result = sanitize_rows(rows)

    assert clean == [], "test-sport row must be dropped"
    assert result.total_out == 0
    assert len(result.dropped) == 1
    assert "test_sport" in result.dropped[0]["reason"]


def test_test_sport_substring_dropped():
    """sport='my_test_run' containing 'test_' as substring -> dropped."""
    rows = [_row(sport="my_test_run", game_id="0042500401")]
    clean, result = sanitize_rows(rows)

    assert clean == []
    assert len(result.dropped) == 1
    assert "test_sport" in result.dropped[0]["reason"]


# ---------------------------------------------------------------------------
# Test 2: bet_id containing 'test_' -> dropped
# ---------------------------------------------------------------------------

def test_test_bet_id_dropped():
    """Rows whose bet_id contains 'test_' must be dropped."""
    rows = [_row(bet_id="test_abc_001", sport="nba", game_id="0042500401")]
    clean, result = sanitize_rows(rows)

    assert clean == [], "test-bet_id row must be dropped"
    assert len(result.dropped) == 1
    assert "test_bet_id" in result.dropped[0]["reason"]


# ---------------------------------------------------------------------------
# Test 3: game_id='gg' (single-token, too short) -> dropped
# ---------------------------------------------------------------------------

def test_single_char_game_id_gg_dropped():
    """game_id='gg' is too short to be a real game id; row must be dropped."""
    rows = [_row(sport="nba", game_id="gg")]
    clean, result = sanitize_rows(rows)

    assert clean == [], "row with game_id='gg' must be dropped"
    assert len(result.dropped) == 1
    assert "malformed_game_id" in result.dropped[0]["reason"]


def test_single_char_game_id_g_dropped():
    """game_id='g' (single char) is malformed; must be dropped."""
    rows = [_row(sport="nba", game_id="g")]
    clean, result = sanitize_rows(rows)

    assert clean == []
    assert "malformed_game_id" in result.dropped[0]["reason"]


def test_five_char_no_separator_game_id_dropped():
    """game_id with fewer than 6 chars and no separator -> malformed -> dropped."""
    rows = [_row(sport="mlb", game_id="abc12")]
    clean, result = sanitize_rows(rows)

    assert clean == []
    assert "malformed_game_id" in result.dropped[0]["reason"]


# ---------------------------------------------------------------------------
# Test 4: legitimate nba/mlb rows are retained
# ---------------------------------------------------------------------------

def test_legit_nba_row_retained():
    """A well-formed NBA row must pass through untouched."""
    rows = [_real_nba_row()]
    clean, result = sanitize_rows(rows)

    assert len(clean) == 1, "legit NBA row must be retained"
    assert result.total_out == 1
    assert result.dropped == []


def test_legit_mlb_row_retained():
    """A well-formed MLB row must pass through untouched."""
    rows = [_real_mlb_row()]
    clean, result = sanitize_rows(rows)

    assert len(clean) == 1
    assert result.dropped == []


def test_mixed_rows_only_bad_dropped():
    """With clean and dirty rows mixed, only the dirty ones are dropped."""
    real1 = _real_nba_row(bet_id="REAL_001")
    real2 = _real_mlb_row(bet_id="REAL_002")
    bad_sport = _row(bet_id="BAD_001", sport="test_none_path_no_raise",
                     game_id="0042500401")
    bad_gid = _row(bet_id="BAD_002", sport="nba", game_id="gg")

    rows = [real1, bad_sport, real2, bad_gid]
    clean, result = sanitize_rows(rows)

    assert len(clean) == 2
    assert result.total_in == 4
    assert result.total_out == 2
    assert len(result.dropped) == 2
    dropped_bids = {d["bet_id"] for d in result.dropped}
    assert dropped_bids == {"BAD_001", "BAD_002"}


# ---------------------------------------------------------------------------
# Test 5: input list is NEVER mutated
# ---------------------------------------------------------------------------

def test_input_not_mutated():
    """sanitize_rows must not mutate the input list or its dicts."""
    rows = [
        _row(sport="test_none_path_no_raise", game_id="gg"),
        _real_nba_row(),
    ]
    original = copy.deepcopy(rows)

    sanitize_rows(rows)

    assert rows == original, "sanitize_rows must not mutate input rows"


# ---------------------------------------------------------------------------
# Test 6: empty input -> empty output, no crash
# ---------------------------------------------------------------------------

def test_empty_input_no_crash():
    """Empty input must produce empty output without raising."""
    clean, result = sanitize_rows([])

    assert clean == []
    assert result.total_in == 0
    assert result.total_out == 0
    assert result.dropped == []


# ---------------------------------------------------------------------------
# Test 7: SanitizeResult.dropped carries the expected fields
# ---------------------------------------------------------------------------

def test_dropped_entry_structure():
    """Each dropped entry must carry bet_id, sport, game_id, reason."""
    rows = [_row(bet_id="BAD_BID", sport="test_cv_probe", game_id="gg")]
    _, result = sanitize_rows(rows)

    assert len(result.dropped) == 1
    entry = result.dropped[0]
    assert "bet_id" in entry
    assert "sport" in entry
    assert "game_id" in entry
    assert "reason" in entry
    assert entry["bet_id"] == "BAD_BID"
    assert entry["sport"] == "test_cv_probe"
    assert entry["game_id"] == "gg"


# ---------------------------------------------------------------------------
# Test 8: row matching multiple rules reports all reasons joined by '|'
# ---------------------------------------------------------------------------

def test_multi_reason_row_reports_all():
    """A row matching sport+bet_id+game_id rules must report all reasons."""
    rows = [
        _row(bet_id="test_multi", sport="test_cv_probe", game_id="gg")
    ]
    _, result = sanitize_rows(rows)

    assert len(result.dropped) == 1
    reason = result.dropped[0]["reason"]
    # All three reasons must appear
    assert "test_sport" in reason
    assert "test_bet_id" in reason
    assert "malformed_game_id" in reason
    # They are joined by '|'
    assert "|" in reason


# ---------------------------------------------------------------------------
# Test 9: game_id absent (missing key or None) -> row NOT dropped on that basis
# ---------------------------------------------------------------------------

def test_missing_game_id_key_not_dropped():
    """Row with no game_id key at all must not be dropped for game_id reasons."""
    row: Dict[str, Any] = {
        "bet_id": "BET_NOGAMEID",
        "sport": "nba",
        "matchup": "BOS@NYK",
        "status": "open",
        "stake_units": 1.0,
    }
    rows = [row]
    clean, result = sanitize_rows(rows)

    assert len(clean) == 1, "row without game_id key must not be dropped"
    assert result.dropped == []


def test_none_game_id_not_dropped():
    """Row with game_id=None must not be dropped for game_id reasons."""
    rows = [_row(sport="nba", game_id=None)]
    clean, result = sanitize_rows(rows)

    assert len(clean) == 1
    assert result.dropped == []


def test_blank_game_id_not_dropped():
    """Row with game_id='' (empty string) must not be dropped for game_id reasons."""
    rows = [_row(sport="mlb", game_id="")]
    clean, result = sanitize_rows(rows)

    assert len(clean) == 1
    assert result.dropped == []


# ---------------------------------------------------------------------------
# Test 10: well-formed game_ids are accepted
# ---------------------------------------------------------------------------

def test_8digit_numeric_game_id_accepted():
    """8+ digit numeric game_id (e.g. '00425001') -> structured -> retained."""
    rows = [_row(sport="nba", game_id="00425001")]
    clean, result = sanitize_rows(rows)

    assert len(clean) == 1
    assert result.dropped == []


def test_long_numeric_game_id_accepted():
    """10-digit NBA-style game_id ('0042500401') -> retained."""
    rows = [_row(sport="nba", game_id="0042500401")]
    clean, result = sanitize_rows(rows)

    assert len(clean) == 1


def test_slug_with_hyphen_game_id_accepted():
    """Hyphenated slug ('KALSHI-NBA-2026-BOS') -> retained."""
    rows = [_row(sport="nba", game_id="KALSHI-NBA-2026-BOS")]
    clean, result = sanitize_rows(rows)

    assert len(clean) == 1
    assert result.dropped == []


def test_slug_with_underscore_game_id_accepted():
    """Underscore slug ('pm_nba_20260614') -> retained."""
    rows = [_row(sport="nba", game_id="pm_nba_20260614")]
    clean, result = sanitize_rows(rows)

    assert len(clean) == 1
    assert result.dropped == []


# ---------------------------------------------------------------------------
# Test 11: total_in / total_out accounting
# ---------------------------------------------------------------------------

def test_total_accounting():
    """total_in and total_out correctly reflect input and clean count."""
    rows = [
        _real_nba_row(bet_id="A"),
        _real_nba_row(bet_id="B"),
        _row(sport="test_cv", game_id="0042500401"),
    ]
    clean, result = sanitize_rows(rows)

    assert result.total_in == 3
    assert result.total_out == 2
    assert len(result.dropped) == 1


# ---------------------------------------------------------------------------
# Test 12: no dollar/pnl/roi key in SanitizeResult
# ---------------------------------------------------------------------------

def test_no_dollar_keys_in_result():
    """SanitizeResult must not contain money/ROI fields."""
    rows = [_real_nba_row(), _row(sport="test_flow", game_id="gg")]
    _, result = sanitize_rows(rows)

    result_str = str(result).lower()
    banned = ("dollar", "roi", "pnl", "profit", "revenue", "bankroll")
    for bad_word in banned:
        assert bad_word not in result_str, (
            "Banned field %r found in SanitizeResult: %s" % (bad_word, result_str)
        )


# ---------------------------------------------------------------------------
# Test 13: returned clean rows are same dict objects (no deep copy bloat)
# ---------------------------------------------------------------------------

def test_clean_rows_are_same_objects():
    """Retained rows in the clean list must be the same dict object references."""
    r1 = _real_nba_row(bet_id="REF_001")
    r2 = _real_mlb_row(bet_id="REF_002")
    rows = [r1, r2]
    clean, _ = sanitize_rows(rows)

    assert clean[0] is r1
    assert clean[1] is r2


# ---------------------------------------------------------------------------
# Test 14: exact repro of the reported leaked row
# ---------------------------------------------------------------------------

def test_exact_leaked_row_is_dropped():
    """Exact structure of the reported leaked test row must be dropped."""
    leaked = {
        "bet_id": "test_none_path_no_raise_BET",
        "sport": "test_none_path_no_raise",
        "matchup": "Lakers @ Celtics",
        "game_id": "gg",
        "status": "open",
        "stake_units": 1.0,
        "executed": False,
    }
    clean, result = sanitize_rows([leaked])

    assert clean == [], "Leaked test row must be dropped"
    assert len(result.dropped) == 1
    entry = result.dropped[0]
    assert "test_sport" in entry["reason"]
    assert "test_bet_id" in entry["reason"]
    assert "malformed_game_id" in entry["reason"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print("PASS", fn.__name__)
            passed += 1
        except Exception as exc:
            print("FAIL", fn.__name__, "->", exc)
    print("%d/%d green" % (passed, len(fns)))
    if passed < len(fns):
        sys.exit(1)
