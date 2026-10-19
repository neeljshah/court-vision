"""scripts.platformkit.eval_gate.mlb_frozen_vs_walkforward_elo_kalshi -- S448 AMENDMENT 5(b)/6

The optional Kalshi pre-first-pitch mid, split out of the main module to keep it
<= 300 LOC. REPORT ONLY: the selected values are descriptive -- score_window() only
ever does a dict .get(event_id); nothing on this path feeds a Brier, a bootstrap
draw, or a verdict (spec ACCEPTANCE case 8).

CAPTURE SCHEMA: event_id, receipt (a venue-time-parseable instant), yes_mid (a
probability in [0.0, 1.0], never a raw price or a vig-inclusive number), and an
OPTIONAL side ("home" or "away") binding which team's win YES represents. Every
receipt AND every first-pitch reference is parsed with
scripts.platformkit.execution.venue_time.parse_venue_time -- never assumed
already-numeric. Each capture row must itself be a mapping -- a non-dict row (e.g.
a bare int) is refused as kalshi_malformed_row, never dereferenced (AMENDMENT
6(c)). The Kalshi JSON file's only defined shape is {"captures": [...],
"first_pitch": {event_id: <venue-time value>}}; a bare event-to-value mapping (no
"captures" list) has no defined schema and is refused outright.

SELECTION: per event, among captures whose receipt parses, whose event has a
parseable first-pitch reference, and whose receipt is AT OR BEFORE that first pitch,
the SELECTED capture is the one nearest first pitch (the maximum such receipt); ties
are broken by the full row identity (event_id, receipt, normalised side, yes_mid,
row ordinal -- AMENDMENT 7(a)) -- never by physical list position alone, so
re-ordering the input list can never change the result even when rows differ only
by side. A capture with a later receipt, a non-finite or out-of-range yes_mid, or no
parseable receipt/first-pitch reference is excluded from selection and counted under
a named reason -- never silently dropped.

AMENDMENT 6(a) -- NO SIDE IS ASSUMED: select_kalshi_mid() returns the YES-side value
(kalshi_yes_mid, always populated when a capture was selected) SEPARATELY from a
home-oriented value (kalshi_mid_home), which is populated ONLY when the SELECTED
capture's own "side" field validates as exactly "home" (value used as-is) or "away"
(1 - value); any other/missing side means kalshi_mid_home is never guessed.

AMENDMENT 7(b) -- EVENT IDS ARE VALIDATED BEFORE ANY LOOKUP: a capture row whose
event_id is not a non-blank str (a list, a dict, blank, None, ...) is refused as
kalshi_malformed_row BEFORE first_pitch_by_event.get() or candidate-dict insertion
ever runs -- an unhashable event_id can therefore never raise TypeError here.

AMENDMENT 9(d) -- price IS A YES_MID ALTERNATIVE: a capture may carry EXACTLY ONE
of yes_mid/price as its probability field, normalised to yes_mid before any other
validation. Both present and DIFFERENT refuses kalshi_ambiguous_price (counted,
never guessed which one is right); both present and EQUAL is accepted once.

AMENDMENT 13(c) -- NO BOOL/STRING COERCION: the resolved probability value must
already be a non-boolean int or float BEFORE float() ever runs on it (True/False
and numeric strings like '0.6' are refused kalshi_non_finite, counted, never
silently coerced by float()'s own leniency).

AMENDMENT 14(a) -- EACH DUAL FIELD IS VALIDATED BEFORE COMPARISON: when both
yes_mid and price are present, EACH is independently validated and normalised
to a finite float FIRST; only then are the two normalised values compared.
An invalid sibling (bool, string, non-finite, overflow) is refused
kalshi_non_finite and never reaches the comparison, so it can neither be
silently accepted (a valid field masking an invalid one) nor miscounted as
kalshi_ambiguous_price (two equally-invalid values, e.g. NaN and NaN, are not
"genuinely different").
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from scripts.platformkit.execution.venue_time import parse_venue_time

COUNTER_REASONS = (
    "kalshi_missing_receipt", "kalshi_non_finite", "kalshi_out_of_range",
    "kalshi_after_first_pitch", "kalshi_malformed_row", "kalshi_ambiguous_price",
)
_VALID_SIDES = ("home", "away")


def _validated_numeric(value: object) -> Optional[float]:
    """Validate and normalise ONE probability field to a finite float, or None
    if it must be refused (bool, non-numeric type, overflow, non-finite) --
    AMENDMENT 14(a): every present field is checked entirely on its own,
    before it is ever compared with a sibling field."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError, OverflowError):   # AMENDMENT 11(c): 10**1000 etc.
        return None
    return num if math.isfinite(num) else None


def _resolve_probability(row: dict) -> Tuple[Optional[float], bool]:
    """Normalise yes_mid/price to a single validated finite float (AMENDMENT
    9(d), fixed 14(a)). Returns (value, ambiguous): ambiguous=True means both
    fields were present, EACH validated independently, and genuinely
    different -- refused, never guessed which one is right. value=None
    (ambiguous False) means the resolved field was absent, a bool/string,
    non-finite, or overflowed -- the caller counts kalshi_non_finite.
    AMENDMENT 14(a): a present sibling is validated BEFORE any comparison, so
    an invalid field (e.g. price=True, or either side NaN) can never be
    compared away against a valid one and silently accepted, and two equally
    invalid siblings (NaN != NaN is True in Python) can never be mistaken for
    kalshi_ambiguous_price."""
    has_yes, has_price = "yes_mid" in row, "price" in row
    if has_yes and has_price:
        yes_num = _validated_numeric(row.get("yes_mid"))
        price_num = _validated_numeric(row.get("price"))
        if yes_num is None or price_num is None:
            return None, False   # an invalid sibling is refused, never compared
        return (None, True) if yes_num != price_num else (yes_num, False)
    raw = row.get("yes_mid") if has_yes else (row.get("price") if has_price else None)
    return _validated_numeric(raw), False


def _normalized_side(value) -> str:
    """A deterministic, always-comparable string for the tie-break identity and the
    home/away validity check -- side is normalised the same way whether present,
    absent, or of an unexpected (non-str) type (AMENDMENT 7(a))."""
    return value.strip().lower() if isinstance(value, str) else ""


def load_kalshi_captures(raw: object) -> Tuple[List[dict], Dict[str, object]]:
    """*raw* is the parsed Kalshi JSON. The only defined shape is
    {"captures": [...], "first_pitch": {...}} -- anything else, including a bare
    event-to-value mapping, is refused: returns ([], {}), never a raw pass-through."""
    if not isinstance(raw, dict) or not isinstance(raw.get("captures"), list):
        return [], {}
    first_pitch = raw.get("first_pitch")
    return raw["captures"], first_pitch if isinstance(first_pitch, dict) else {}


def select_kalshi_mid(
    captures: List[dict], first_pitch_by_event: Dict[str, object],
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, int]]:
    """Select ONE pre-first-pitch capture per event (AMENDMENT 5(b)/6(a)/6(c)).

    Returns (yes_mids, home_mids, counters): yes_mids maps event_id -> the selected
    side-unaware YES probability; home_mids maps event_id -> the home-oriented
    probability, present ONLY for an event whose selected capture carried a
    validated "side" field (never guessed, AMENDMENT 6(a)); counters maps each of
    COUNTER_REASONS to how many capture rows it excluded.
    """
    counters = {reason: 0 for reason in COUNTER_REASONS}
    candidates: Dict[object, List[tuple]] = {}
    for ordinal, row in enumerate(captures):
        if not isinstance(row, dict):
            counters["kalshi_malformed_row"] += 1
            continue
        event_id = row.get("event_id")
        if not (isinstance(event_id, str) and event_id.strip() != ""):
            counters["kalshi_malformed_row"] += 1   # 7(b): before any lookup/hash of event_id
            continue
        receipt = parse_venue_time(row.get("receipt"))
        first_pitch = parse_venue_time(first_pitch_by_event.get(event_id))
        if receipt is None or first_pitch is None:
            counters["kalshi_missing_receipt"] += 1
            continue
        mid, ambiguous = _resolve_probability(row)
        if ambiguous:
            counters["kalshi_ambiguous_price"] += 1
            continue
        if mid is None:   # AMENDMENT 13(c)/14(a): bool/str/non-finite/overflow/absent
            counters["kalshi_non_finite"] += 1
            continue
        if not (0.0 <= mid <= 1.0):
            counters["kalshi_out_of_range"] += 1
            continue
        if receipt > first_pitch:
            counters["kalshi_after_first_pitch"] += 1
            continue
        side_norm = _normalized_side(row.get("side"))
        identity = (event_id, receipt, side_norm, mid, ordinal)   # 7(a): full, order-safe
        candidates.setdefault(event_id, []).append((receipt, identity, mid, side_norm))

    yes_mids: Dict[str, float] = {}
    home_mids: Dict[str, float] = {}
    for event_id, rows in candidates.items():
        rows.sort(key=lambda r: (-r[0], r[1]))   # nearest first pitch; ties by full identity
        _, _, mid, side_norm = rows[0]
        yes_mids[event_id] = mid
        if side_norm in _VALID_SIDES:
            home_mids[event_id] = mid if side_norm == "home" else 1.0 - mid
    return yes_mids, home_mids, counters
