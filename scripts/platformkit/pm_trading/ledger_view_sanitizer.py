"""ledger_view_sanitizer.py -- read-time sanitizer for the paper-trail read path.

Problem (BE7-6 iter3/4): test rows leaked into the production CLV ledger and
were served by /api/paper/open as real open bets.  Leaked rows are identifiable
by two structural defects:
  1. sport or bet_id contains the substring 'test_'
     (e.g. sport='test_none_path_no_raise', bet_id='test_abc').
  2. game_id is a single-character string or otherwise non-structured
     (e.g. game_id='gg', which has len==2 but is clearly a stub;
     the rule is: game_id with no separator and fewer than MIN_GAME_ID_LEN chars).

CONTRACT (binding):
  * PURE FUNCTION over the loaded rows list.  Returns a NEW list (copy) with
    dropped rows -- does NOT mutate the input list (index positions, dicts).
  * Never writes to disk.  Never appends.  Never touches the on-disk ledger.
    HUMAN REVIEW required before any disk mutation (QA iter7 invariant).
  * UNITS ONLY -- no $/dollar/pnl/roi key introduced or reported.
  * Returns empty list when input is empty (no crash).
  * Dropped rows are surfaced via SanitizeResult.dropped so callers can log them.
  * ASCII only.  <=300 LOC.  Build only under scripts/platformkit/pm_trading/.

Typical usage on the read path (read-only -- no disk mutation):
    from scripts.platformkit.pm_trading.ledger_view_sanitizer import sanitize_rows
    clean_rows, result = sanitize_rows(raw_rows)
    # use clean_rows; log result.dropped if needed
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Substrings that mark a row as a test artifact when found in sport or bet_id.
_TEST_PREFIXES: Tuple[str, ...] = ("test_",)

# A structured game_id must be at least this many characters long.
# Single-char ('g') or two-char stubs ('gg', 'ab') are clearly non-structured.
_MIN_GAME_ID_LEN: int = 6

# A regex a well-formed game_id must match.  Accepts:
#   - NBA/ESPN numeric IDs (e.g. "0042500401", "401767834")
#   - Kalshi/Polymarket slugs with hyphens / underscores
#     (e.g. "KALSHI-NBA-2026-BOS", "pm_nba_20260614")
#   - Date-stamped IDs (e.g. "20260614_BOS_NYK")
# Must contain at least one separator char (-, _, .) OR be 8+ pure digits.
_GAME_ID_STRUCTURED_RE = re.compile(
    r"^(?:"
    r"[0-9]{8,}"           # 8+ digit numeric (e.g. NBA game id)
    r"|"
    r"[A-Za-z0-9]+[-_.][A-Za-z0-9].*"  # slug with at least one separator
    r")$"
)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class SanitizeResult:
    """Summary of what the sanitizer dropped and why.

    Attributes
    ----------
    total_in : int
        Number of rows supplied to sanitize_rows().
    total_out : int
        Number of rows returned in the clean view (total_in - len(dropped)).
    dropped : list of dict
        Each entry carries: bet_id, sport, game_id, reason.
        Reasons: 'test_sport', 'test_bet_id', 'malformed_game_id'.
        One entry per dropped row (a row may match multiple reasons;
        all matching reasons are joined with '|').
    """
    total_in: int = 0
    total_out: int = 0
    dropped: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core public API
# ---------------------------------------------------------------------------

def sanitize_rows(
    rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], SanitizeResult]:
    """Return a clean VIEW of *rows* with test/malformed rows removed.

    Parameters
    ----------
    rows :
        Raw list of ledger dicts as loaded from disk (or passed in by tests).
        NOT mutated.  Each dict is NOT copied -- clean rows are the SAME dict
        objects from the input (no deep copy overhead), so callers must not
        mutate them either.

    Returns
    -------
    (clean_rows, result) :
        clean_rows -- new list containing only non-dropped rows (same dict refs).
        result     -- SanitizeResult describing what was dropped and why.

    Drop rules
    ----------
    A row is dropped when ANY of the following hold:

    1. test_sport  : str(row['sport']).lower() contains any prefix in
                     _TEST_PREFIXES (e.g. 'test_none_path_no_raise').
    2. test_bet_id : str(row['bet_id']).lower() contains any prefix in
                     _TEST_PREFIXES (e.g. 'test_abc').
    3. malformed_game_id : row has a 'game_id' key AND the value is a
                           non-empty string that fails the structured-ID
                           criteria (len < _MIN_GAME_ID_LEN OR does not
                           match _GAME_ID_STRUCTURED_RE).
                           Absent game_id (key missing or value None/'') is
                           NOT penalised -- many legitimate rows omit game_id.

    Notes
    -----
    * Pure function: input list and its dicts are NEVER mutated.
    * Returns empty list when input is empty (no crash, no exception).
    * No disk I/O, no network I/O.
    * No $/dollar/pnl/roi keys introduced in SanitizeResult.
    """
    result = SanitizeResult(total_in=len(rows))
    clean: List[Dict[str, Any]] = []

    for row in rows:
        reasons = _classify_row(row)
        if reasons:
            result.dropped.append({
                "bet_id": row.get("bet_id"),
                "sport": row.get("sport"),
                "game_id": row.get("game_id"),
                "reason": "|".join(sorted(reasons)),
            })
        else:
            clean.append(row)

    result.total_out = len(clean)
    return clean, result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_test_field(value: Any) -> bool:
    """Return True when *value* (string) contains a test-sentinel prefix."""
    if value is None:
        return False
    s = str(value).lower()
    return any(s.startswith(prefix) or ("_" + prefix[:-1] + "_") in s
               or prefix in s
               for prefix in _TEST_PREFIXES)


def _is_malformed_game_id(game_id: Any) -> bool:
    """Return True when *game_id* is present but structurally malformed.

    Absent (None / empty string / key missing) -> NOT malformed (returns False).
    """
    if game_id is None:
        return False
    s = str(game_id).strip()
    if not s:
        return False  # absent / blank -> not penalised
    if len(s) < _MIN_GAME_ID_LEN:
        return True   # too short to be a real game id
    if not _GAME_ID_STRUCTURED_RE.match(s):
        return True   # does not have the structure of a real game id
    return False


def _classify_row(row: Dict[str, Any]) -> List[str]:
    """Return a list of reasons this row should be dropped (empty -> keep)."""
    reasons: List[str] = []

    sport_val = row.get("sport")
    if _is_test_field(sport_val):
        reasons.append("test_sport")

    bet_id_val = row.get("bet_id")
    if _is_test_field(bet_id_val):
        reasons.append("test_bet_id")

    if "game_id" in row and _is_malformed_game_id(row["game_id"]):
        reasons.append("malformed_game_id")

    return reasons


__all__ = [
    "sanitize_rows",
    "SanitizeResult",
]
