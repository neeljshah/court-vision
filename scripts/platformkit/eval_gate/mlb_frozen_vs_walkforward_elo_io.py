"""scripts.platformkit.eval_gate.mlb_frozen_vs_walkforward_elo_io -- S448 AMENDMENT 1
schema/identity helpers, split out to keep mlb_frozen_vs_walkforward_elo.py <=300 LOC.
Row-level validation runs BEFORE either replay (1(a)): no non-final, tied, negative,
non-numeric, mis-dated, mis-keyed or duplicate row ever reaches one, refused with a
specific order-independent reason (1(b)/12(a): schema checked PER RECORD, never
first-record-only). clean_games_asof()/clean_games_window() scope EVERY refusal to
one as-of slice / window ALONE (5(a)/9(c)) -- *games* is per-row records, date-sliced
BEFORE any DataFrame is built (8(b)/9(a)). Also carries the rating/Brier helpers and
snapshot_entries() (2(d)). REQUIRED_COLUMNS is refresh_ratings._SCHEMA itself.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from domains.mlb.refresh_ratings import _SCHEMA
from scripts.platformkit.eval_gate.mlb_frozen_vs_walkforward_elo_validate import filter_records, json_safe_event_id
from scripts.platformkit.proof_mlb.beat_the_close_ml import _INIT, _p_home

REQUIRED_COLUMNS = tuple(_SCHEMA)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_schema(games) -> None:
    """Raise ValueError if *games* is missing any refresh_ratings._SCHEMA column.
    Accepts a DataFrame (.columns) or an iterable of record dicts, checked PER
    RECORD (FIX 12/AMENDMENT 12(a)/(b)): a non-empty record list raises only
    when NOT ONE record carries every REQUIRED_COLUMNS key -- never via a
    first-record check, matching _clean_records()'s own rule."""
    if isinstance(games, pd.DataFrame):
        cols = set(games.columns)
        missing = [c for c in REQUIRED_COLUMNS if c not in cols]
        if missing:
            raise ValueError(f"games table missing required columns: {missing}")
        return
    records = list(games)
    if any(isinstance(r, dict) and all(c in r for c in REQUIRED_COLUMNS) for r in records):
        return
    cols = set(records[0]) if records and isinstance(records[0], dict) else set()
    missing = [c for c in REQUIRED_COLUMNS if c not in cols]
    if missing:
        raise ValueError(f"games table missing required columns: {missing}")


def _is_missing_scalar(value) -> bool:
    """Scalar-safe missing-value check -- pd.isna() on a container (list, dict,
    array) returns an elementwise result whose truthiness raises ValueError;
    only a true scalar NaN/None/NaT counts as missing (AMENDMENT 8(a)); a
    malformed container falls through to _finite_nonneg_int instead."""
    if not pd.api.types.is_scalar(value):
        return False
    return bool(pd.isna(value))


def _to_records(games) -> List[dict]:
    """Row-preserving view of *games*: a DataFrame's rows become dict records;
    an iterable of record dicts is used AS-IS, never forced through one shared
    pandas column dtype (AMENDMENT 8(b)) -- each row keeps its own scalar type."""
    if isinstance(games, pd.DataFrame):
        return games.to_dict("records")
    return list(games)


def _int_like(value) -> bool:
    """game_seq must be a real integer -- non-boolean int or numpy integer only;
    a float, numpy float or numeric string is refused, never coerced (AMENDMENT 5(c))."""
    return isinstance(value, (int, np.integer)) and not isinstance(value, bool)


def _finite_nonneg_int(value) -> bool:
    """A score must be a real, non-boolean int/np.integer (AMENDMENT 13(b): a
    float or numeric string like 3.0/'2' is refused, never coerced) -- reuses
    _int_like, which already excludes non-scalars too (9(b)); overflow fails
    closed (11(b))."""
    if not _int_like(value):
        return False
    try:
        f = float(value)
    except (TypeError, ValueError, OverflowError):   # AMENDMENT 11(b): 10**1000 etc.
        return False
    return np.isfinite(f) and f >= 0


def _valid_event_id(value) -> bool:
    """A deterministic game key must be a non-blank string -- never None, blank, or numeric."""
    return isinstance(value, str) and value.strip() != ""


def _valid_team(value) -> bool:
    """A team code must be a non-blank string -- never None/blank/numeric (4(a));
    identical home/away codes are refused separately in _clean_records()."""
    return isinstance(value, str) and value.strip() != ""


def _valid_date_value(value):
    """Accept only an ISO calendar-day string or a pandas Timestamp / datetime.date
    (covers datetime.datetime too); an int or float (e.g. an epoch/ordinal) is
    refused, never silently coerced -- runs BEFORE any pd.to_datetime
    normalisation (AMENDMENT 2(b)). AMENDMENT 8(c): a timezone-AWARE Timestamp
    normalises to midnight of its OWN local calendar day, tz stripped (never
    converted to another zone, which could shift the date)."""
    if isinstance(value, datetime.date):
        ts = pd.Timestamp(value).normalize()
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        return ts
    if isinstance(value, str) and _ISO_DATE_RE.match(value.strip()):
        try:
            return pd.Timestamp(value.strip()).normalize()
        except (ValueError, TypeError):
            return pd.NaT
    return pd.NaT


def _sort_key(event_id) -> str:
    """A total-order string key for sorting mixed event_id values (None/str/...)."""
    return "" if event_id is None else str(event_id)


def _clean_records(records: List[dict]) -> Tuple[pd.DataFrame, List[dict]]:
    """Refuse every malformed record while its OWN scalar types are still intact
    (AMENDMENT 11(a)): every check -- schema, event_id, date, team, game_seq,
    score -- runs on the raw dict, never on a shared pandas column, so one
    malformed sibling record can never coerce or refuse a valid record beside
    it, regardless of input order. A DataFrame is built ONLY from the accepted
    records, at the very end. Reasons: schema_missing_key, invalid_event_id,
    duplicate_game_key, invalid_date, invalid_team, invalid_game_seq,
    missing_final, tie_or_malformed. Both lists sort deterministically (2(c)).

    AMENDMENT 12(a)/(b): schema validity is checked PER RECORD before any other
    field access -- never just the first record; a failing record refuses
    schema_missing_key and every valid sibling is still processed. FIX 12: the
    ValueError fires only when *records* is NON-EMPTY and none of them is
    schema-valid -- a legitimately empty slice (e.g. an as-of cutoff strictly
    before any game exists) is a cold start, not a schema violation."""
    schema_ok: List[dict] = []
    refused: List[dict] = []
    for rec in records:
        if isinstance(rec, dict) and all(col in rec for col in REQUIRED_COLUMNS):
            schema_ok.append(rec)
            continue
        eid = rec.get("event_id") if isinstance(rec, dict) else None
        d0 = _valid_date_value(rec.get("date")) if isinstance(rec, dict) else pd.NaT
        refused.append({"event_id": json_safe_event_id(eid), "date": None if pd.isna(d0) else str(d0.date()),
                         "reason": "schema_missing_key"})
    if records and not schema_ok:
        raise ValueError(f"games table missing required columns: {list(REQUIRED_COLUMNS)}")

    dates = [_valid_date_value(rec.get("date")) for rec in schema_ok]
    # AMENDMENT 6(e): duplicates are computed ONLY among event_ids that already
    # validated as str -- an unhashable value (e.g. a list) is never hashed here.
    valid_ids = [rec.get("event_id") for rec in schema_ok if _valid_event_id(rec.get("event_id"))]
    dup_keys = {eid for eid, n in Counter(valid_ids).items() if n > 1}

    accepted: List[dict] = []
    for rec, d in zip(schema_ok, dates):
        event_id = rec.get("event_id")
        home_team, away_team = rec.get("home_team"), rec.get("away_team")
        game_seq = rec.get("game_seq")
        home_runs, away_runs = rec.get("home_runs"), rec.get("away_runs")
        reason = None
        if not _valid_event_id(event_id):
            reason = "invalid_event_id"
        elif event_id in dup_keys:
            reason = "duplicate_game_key"
        elif pd.isna(d):
            reason = "invalid_date"
        elif not _valid_team(home_team) or not _valid_team(away_team):
            reason = "invalid_team"
        elif home_team.strip() == away_team.strip():
            reason = "invalid_team"
        elif not _int_like(game_seq):
            reason = "invalid_game_seq"
        elif _is_missing_scalar(home_runs) or _is_missing_scalar(away_runs):
            reason = "missing_final"
        elif not _finite_nonneg_int(home_runs) or not _finite_nonneg_int(away_runs):
            reason = "tie_or_malformed"
        elif float(home_runs) == float(away_runs):
            reason = "tie_or_malformed"
        if reason:
            refused.append({"event_id": json_safe_event_id(event_id),
                             "date": None if pd.isna(d) else str(d.date()),
                             "reason": reason})
        else:
            accepted.append({**rec, "date": d})
    clean = pd.DataFrame(accepted, columns=REQUIRED_COLUMNS)
    clean = clean.sort_values("event_id", kind="mergesort").reset_index(drop=True)
    refused.sort(key=lambda r: (_sort_key(r["event_id"]), _sort_key(r["date"]), r["reason"]))
    return clean, refused


def clean_games(games) -> Tuple[pd.DataFrame, List[dict]]:
    """Refuse every malformed row in the WHOLE corpus BEFORE it can reach a
    replay -- used for window/report purposes only (5(a): no longer feeds a
    snapshot replay -- see clean_games_asof())."""
    return _clean_records(_to_records(games))


def _merge_refused(pre_refused: List[dict], refused: List[dict]) -> List[dict]:
    """pre-slice refusals (AMENDMENT 13(a)) + _clean_records()'s own, one sort order."""
    merged = pre_refused + refused
    merged.sort(key=lambda r: (_sort_key(r["event_id"]), _sort_key(r["date"]), r["reason"]))
    return merged


def clean_games_asof(games, cutoff, inclusive: bool = False) -> Tuple[pd.DataFrame, List[dict]]:
    """AMENDMENT 5(a)/8(b): every row-level refusal runs ONLY on records dated
    before *cutoff* (on/before when inclusive=True) -- *games* is date-sliced
    into per-row records BEFORE any DataFrame is built, so a record dated
    on/after cutoff can never alter a prior training game. AMENDMENT 13(a): a
    record failing schema/date validation refuses via filter_records(),
    never silently dropped by the cutoff test."""
    cutoff_ts = pd.Timestamp(cutoff)
    keep = lambda d: d <= cutoff_ts if inclusive else d < cutoff_ts  # noqa: E731
    kept, pre_refused = filter_records(_to_records(games), REQUIRED_COLUMNS, _valid_date_value, keep)
    clean, refused = _clean_records(kept)
    return clean, _merge_refused(pre_refused, refused)


def clean_games_window(games, start, end) -> Tuple[pd.DataFrame, List[dict]]:
    """AMENDMENT 9(c): every row-level refusal for THE SCORING WINDOW runs ONLY
    on records dated within [start, end], excluded BEFORE duplicate detection.
    Same AMENDMENT 13(a) pre-slice refusal as clean_games_asof()."""
    kept, pre_refused = filter_records(_to_records(games), REQUIRED_COLUMNS, _valid_date_value,
                                        lambda d: start <= d <= end)
    clean, refused = _clean_records(kept)
    return clean, _merge_refused(pre_refused, refused)


def default_window_end(clean: pd.DataFrame, refused: List[dict]):
    """Default window_end when the caller passes none: the max normalised date
    across BOTH clean and refused rows (AMENDMENT 3(b)) -- a row refused only
    for lacking a final still counts, so the end never retreats behind a real,
    later, unscored row. pd.NaT if neither side has a valid date."""
    dates = list(clean["date"]) if len(clean) else []
    dates += [pd.Timestamp(r["date"]) for r in refused if r["date"] is not None]
    return max(dates) if dates else pd.NaT


def default_window_end_records(records: List[dict]):
    """Like default_window_end() but on RAW records BEFORE validation (9(c),
    matches 3(b)); AMENDMENT 13(a): a non-mapping record is ignored safely
    instead of raising AttributeError on .get()."""
    dates = [d for d in (_valid_date_value(r.get("date")) for r in records if isinstance(r, dict))
             if pd.notna(d)]
    return max(dates) if dates else pd.NaT


def file_identity(path, role: str) -> dict:
    """Resolved absolute path, size and sha256 for one opened input (A9)."""
    p = Path(path).resolve()
    data = p.read_bytes()
    return {"role": role, "path": str(p), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def ratings_digest(ratings: Dict[str, float]) -> str:
    """A durable digest of a final-ratings snapshot (A9)."""
    payload = json.dumps({k: ratings[k] for k in sorted(ratings)},
                          sort_keys=True, allow_nan=False)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _rating_of(ratings: Dict[str, float], team: str) -> float:
    """A team absent from *ratings* gets _INIT -- the same default _replay itself uses."""
    return ratings.get(str(team), _INIT)


def _p_home_of(ratings: Dict[str, float], home: str, away: str) -> float:
    return _p_home(_rating_of(ratings, home), _rating_of(ratings, away))


def _brier(p: float, y: float) -> float:
    return (p - y) ** 2


def snapshot_entries(games, ratings_by_date: Dict[str, Dict[str, float]]) -> List[dict]:
    """One cutoff-ordered walk-forward entry per scoring date: cutoff, training
    max date, ratings digest, games_trained (2(d)) -- *games* is RAW; each
    entry's training facts come from the SAME clean_games_asof() slice (5(a))
    that trained ratings_by_date's snapshot."""
    entries = []
    for date_str in sorted(ratings_by_date):
        train, _ = clean_games_asof(games, date_str, inclusive=False)
        entries.append({
            "kind": "walk_forward",
            "cutoff": date_str,
            "training_max_date": str(train["date"].max().date()) if len(train) else None,
            "ratings_digest": ratings_digest(ratings_by_date[date_str]),
            "games_trained": int(len(train)),
        })
    return entries
