"""scripts.platformkit.eval_gate.mlb_frozen_vs_walkforward_elo_validate -- S448 AMENDMENT 13(a)

Schema/date validation BEFORE any date-slice comparison, factored out of
mlb_frozen_vs_walkforward_elo_io.py (at the 300-line cap). Round-13 verifier
finding: clean_games_asof()/clean_games_window() compared rec.get("date")
against a cutoff/window BEFORE checking *rec* was even a mapping carrying every
required key -- a non-dict record (a bare int) or one with a missing/invalid
date simply failed that comparison and silently vanished from `kept`, never
reaching _clean_records()'s own refusal counting (sol probe: [valid,
missing-date, invalid-date, 7] -> ACCEPTED ['ok'], REFUSED [] ; a record list
with no explicit window end raised AttributeError inferring it).

No import from io.py here -- io.py must call this module, so importing io.py
back would be circular. *required_columns* and *parse_date* are passed in by
the caller instead (dependency injection, not module coupling).
"""
from __future__ import annotations

import math
import re
from typing import Callable, List, Optional, Sequence, Tuple

import pandas as pd

_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def json_safe_event_id(eid):
    """AMENDMENT 15(a): the shared normaliser for every refusal record's
    event_id, used by both refusal paths (this module and io.py's
    _clean_records()). A non-finite float (nan/inf, e.g. an unvalidated numeric
    id) or any value outside {str, int, bool, None, finite float} becomes None
    -- the row stays counted under its refusal reason, but the id itself can
    never break json.dumps(..., allow_nan=False)."""
    if isinstance(eid, float):
        return eid if math.isfinite(eid) else None
    if isinstance(eid, (str, int, type(None))):
        return eid
    return None


def pre_slice_refusal(rec: object, required_columns: Sequence[str],
                       parse_date: Callable) -> Optional[dict]:
    """A refusal dict (schema_missing_key/invalid_date) if *rec* is not safe to
    date-compare against a cutoff/window; None if it is a mapping carrying
    every required column AND a parseable date. Matches _clean_records()'s own
    convention: the date is still reported when it happens to parse, even on a
    schema_missing_key refusal."""
    if not isinstance(rec, dict) or not all(c in rec for c in required_columns):
        eid = rec.get("event_id") if isinstance(rec, dict) else None
        d0 = parse_date(rec.get("date")) if isinstance(rec, dict) else pd.NaT
        return {"event_id": json_safe_event_id(eid), "date": None if pd.isna(d0) else str(d0.date()),
                "reason": "schema_missing_key"}
    if pd.isna(parse_date(rec.get("date"))):
        return {"event_id": json_safe_event_id(rec.get("event_id")), "date": None,
                "reason": "invalid_date"}
    return None


def filter_records(
    records: List[dict], required_columns: Sequence[str], parse_date: Callable,
    keep: Callable[[object], bool],
) -> Tuple[List[dict], List[dict]]:
    """Split *records* into (kept, pre_refused): a malformed record refuses via
    pre_slice_refusal() BEFORE *keep* (the cutoff/window date test) ever runs on
    it; a well-formed record outside the window is simply excluded from both
    lists (unchanged behaviour -- being out of window is not malformed)."""
    kept, pre_refused = [], []
    for rec in records:
        bad = pre_slice_refusal(rec, required_columns, parse_date)
        if bad:
            pre_refused.append(bad)
            continue
        if keep(parse_date(rec.get("date"))):
            kept.append(rec)
    return kept, pre_refused


def validate_window(window_start: str, frozen_asof: str) -> pd.Timestamp:
    """S448 Opus tier-2 final-pass correction (finding 1, not a numbered spec
    amendment): frozen_asof=2026-07-17 with window_start=2026-07-13 let the
    frozen arm train on the scored games' own results and still returned a
    REJECT verdict -- nothing enforced frozen_asof strictly before
    window_start. A timed window_start (e.g. '2026-07-13T12:00') also let
    that day's finals fall out of both score_window()'s scored and refused
    lists silently, breaking NON-TAUTOLOGY. Raises ValueError naming the
    refusal reason; called in place of the bare `pd.Timestamp(window_start)`
    at the top of score_window(), whose own `start` value this returns."""
    if not _DAY_RE.match(window_start):
        raise ValueError(
            f"window_start_not_midnight: window_start {window_start!r} must be "
            "a bare calendar day (YYYY-MM-DD), not a timed bound"
        )
    start = pd.Timestamp(window_start)
    if not pd.Timestamp(frozen_asof) < start:
        raise ValueError(
            f"frozen_asof_not_before_window: frozen_asof {frozen_asof!r} is not "
            f"strictly before window_start {window_start!r}"
        )
    return start


def verdict_of(lo: Optional[float], hi: Optional[float], n_dates: int, min_dates: int = 5) -> str:
    """Moved here from mlb_frozen_vs_walkforward_elo.py (Opus final-pass
    correction) to make room for validate_window() under the 300 LOC cap;
    *min_dates* is an injected parameter (dependency injection, not module
    coupling -- matches filter_records()'s own convention above), not a
    constant imported back from the caller's module (which would be
    circular). Default 5 mirrors the caller's own MIN_DATES (spec case 7,
    the bootstrap floor) so pre-existing 3-arg call sites are unchanged."""
    if lo is None or hi is None or n_dates < min_dates:
        return "UNDERPOWERED"
    if hi < 0:
        return "ACCEPT"
    if lo > 0:
        return "REJECT"
    return "NULL"
