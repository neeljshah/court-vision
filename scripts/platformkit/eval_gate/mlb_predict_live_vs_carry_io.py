"""scripts.platformkit.eval_gate.mlb_predict_live_vs_carry_io -- S447 AMENDMENT 1 fix 1b.

Loader + A9-identity + as-of-corpus helpers split out of mlb_predict_live_vs_carry.py to
keep both files under the 300-LOC cap (S447_spec.md Amendment 1 candidate-file note).
Import-only from domains/mlb/predictor.py; no edits there. ASCII; no network; never writes
under data/; `load_historical`'s `root` param defaults to the real corpus path but tests
pass a tmp_path so this lane never reads under data/cache (worktree rule).
"""
from __future__ import annotations

import glob
import hashlib
import json
import math
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from scripts.platformkit.eval_gate.cpcv_engine import EMBARGO_DAYS
from scripts.platformkit.eval_gate.cpcv_engine import _purged as _shared_purge_route

HIST_ROOT = "data/cache/ingame_grade_joined"
HIST_CORPUS = "mlb_segmented_r3"
REASON_NON_ASCII = "non_ascii_byte_refused"
REASON_BAD_ROW = "unparseable_historical_row"
REASON_UNPARSEABLE = "unparseable_state"

_STATE_RE = re.compile(
    r"home_score=(\d+\.?\d*)\s+away_score=(\d+\.?\d*)\s+inning=(\d+)\s+half=(\w+)")
_LOADER_HALVES = {"top": "top", "bot": "bottom", "bottom": "bottom"}


class CorpusStartBeforeTick(ValueError):
    """A tick whose as-of cutoff is on/before the corpus's first date (item i NEW GAP):
    MLBPredictor(games_df=empty) raises IndexError; get_asof_predictor refuses instead of
    ever constructing a predictor from an empty slice."""


def record_identity(path: str) -> Dict[str, Any]:
    """A9: absolute path (Path.resolve(strict=True) -- item h), byte size, sha256."""
    p = Path(path).resolve(strict=True)
    data = p.read_bytes()
    return {"path": str(p), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


_MAX_SAFE_INT_FLOAT = 2 ** 53  # largest magnitude a float64 still represents exactly


def parse_int_exact(value: Any) -> Optional[int]:
    """Integer-valued only (AMENDMENT 2 item b; AMENDMENT 4 item a; AMENDMENT 8 item b): a bool
    (True/False are ints in Python but never a valid score/inning) refuses. An `int` is
    returned directly -- NEVER routed through `float()`, so no magnitude can ever be corrupted
    (the bug this closes: `float("9007199254740993")` silently rounds to
    `9007199254740992.0`). A `str` is validated as a finite integral `Decimal`, exact at any
    magnitude ('9007199254740993' round-trips exactly). A `float` is accepted only when it is
    already integral AND within `+/- 2**53` (the largest magnitude a float64 can represent
    exactly) -- an unsafely large or fractional float, a non-finite value, or a non-numeric
    string ('bad') all refuse."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            d = Decimal(value)
        except (InvalidOperation, ValueError):
            return None
        if not d.is_finite() or d != d.to_integral_value():
            return None
        return int(d)
    if isinstance(value, float):
        if not math.isfinite(value) or value != int(value) or abs(value) > _MAX_SAFE_INT_FLOAT:
            return None
        return int(value)
    return None


_REQUIRED_INT_FIELDS = ("home_score", "away_score", "inning")
_VALID_HALVES = ("top", "bottom")


def validate_state(row: Any) -> Optional[Dict[str, Any]]:
    """Every field the predictor call needs, checked for FORM, not just presence, BEFORE any
    dict access or predictor call (AMENDMENT 2 item b; AMENDMENT 3 items b/c; AMENDMENT 4 item
    a): a non-mapping row (a list, None); a `game_id` that is missing, empty, a bool, or a
    non-scalar (list/dict); an empty/non-string `home` or `away`; a `half` other than exactly
    'top'/'bottom' (case-insensitive); a non-integer, negative, or boolean `home_score`/
    `away_score`; a non-integer, boolean, or sub-1 `inning`; or a missing/unparseable
    `game_date` -- all refuse here, never a KeyError/AttributeError/ValueError/TypeError
    raised downstream. Returns a NORMALISED copy of `row` holding the parsed integers, the
    lower-cased `half`, and a canonical `game_date`: every downstream use, including the
    predictor call, reads this row, never the raw values. None on any failure."""
    if not isinstance(row, dict):
        return None
    game_id = row.get("game_id")
    if isinstance(game_id, bool) or not isinstance(game_id, (str, int)) or game_id == "":
        return None
    for field in ("home", "away"):
        value = row.get(field)
        if not isinstance(value, str) or value == "":
            return None
    half = row.get("half")
    half = half.lower() if isinstance(half, str) else None
    if half not in _VALID_HALVES:
        return None
    if row.get("game_date") is None:
        return None
    parsed = {f: parse_int_exact(row.get(f)) for f in _REQUIRED_INT_FIELDS}
    if any(v is None for v in parsed.values()):
        return None
    if parsed["home_score"] < 0 or parsed["away_score"] < 0 or parsed["inning"] < 1:
        return None
    try:
        day = canonicalize_calendar_day(row["game_date"])
    except Exception:
        return None
    normalized = dict(row)
    normalized.update(parsed)
    normalized["half"] = half
    normalized["game_date"] = str(day.date())
    return normalized


def canonicalize_calendar_day(value: Any) -> pd.Timestamp:
    """Floor a date/timestamp-shaped value to its timezone-naive calendar day (AMENDMENT 2
    item c): tz-aware input (e.g. a Z-suffixed receipt used as a cutoff) is converted to UTC
    and stripped of tz before flooring, so it never compares tz-aware vs tz-naive against
    the corpus's naive game dates."""
    ts = pd.to_datetime(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.normalize()


def resolve_cutoff_date(row: Dict[str, Any]) -> str:
    """Elo as-of cutoff = the game's OWN stated date (case 11), never the tick receipt."""
    return str(row["game_date"])


_ASOF_CUTOFF_SENTINEL = {"home": "__asof_cutoff__", "away": "__asof_cutoff__"}  # never a real team


def games_asof(games_df: pd.DataFrame, cutoff_date: str) -> pd.DataFrame:
    """Games strictly before cutoff_date's calendar day AND outside the shared purge/embargo
    band (case 4, item g; AMENDMENT 2 item c; AMENDMENT 5 item c/Q4; AMENDMENT 7 item a/Q4):
    both sides canonicalised to timezone-naive calendar days so a timestamp-shaped or zoned
    cutoff never admits a same-day game and never raises on tz-aware vs tz-naive. The near-
    boundary exclusion is NOT a hand-built date-gap comparison against an imported constant:
    each strictly-past candidate is asked of the SHARED split route (`cpcv_engine._purged`,
    imported unedited as `_shared_purge_route`, itself sourced from `walkforward.py`'s
    EMBARGO_DAYS/PURGE_HOURS), never reinvented here. This query has no matchup of its own (an
    as-of Elo cutoff, not a specific test game), so a sentinel team pair that can never collide
    with a real code isolates the calendar-day embargo term that route implements without
    engaging its same-team/same-matchup terms."""
    cutoff = canonicalize_calendar_day(cutoff_date)
    d = games_df.copy()
    dates = pd.to_datetime(d["date"])
    if dates.dt.tz is not None:
        dates = dates.dt.tz_convert("UTC").dt.tz_localize(None)
    d["date"] = dates.dt.normalize()
    test_ts = cutoff.to_pydatetime()
    keep: List[bool] = []
    for _, row in d.iterrows():
        if row["date"] >= cutoff:
            keep.append(False)
            continue
        train_state = {"home": row["home_team"], "away": row["away_team"]}
        purged = _shared_purge_route(train_state, row["date"].to_pydatetime(),
                                      _ASOF_CUTOFF_SENTINEL, test_ts, EMBARGO_DAYS)
        keep.append(not purged)
    return d[keep].reset_index(drop=True)


def get_asof_predictor(games_df: pd.DataFrame, cutoff_date: str, cache: Dict[str, Any],
                        predictor_factory: Callable[[pd.DataFrame], Any]) -> Any:
    """One predictor per distinct as-of date, cached. Refuses corpus_start_before_tick
    (never constructs from an empty slice -- item i) instead of crashing on IndexError."""
    if cutoff_date not in cache:
        sliced = games_asof(games_df, cutoff_date)
        if sliced.empty:
            raise CorpusStartBeforeTick(str(cutoff_date))
        cache[cutoff_date] = predictor_factory(sliced)
    return cache[cutoff_date]


def decode_forward_row(raw_line: bytes) -> Optional[Dict[str, Any]]:
    """Decode one forward-capture JSONL line to a dict, else None (AMENDMENT 3 item c): bad
    ASCII, bad JSON, or a non-mapping payload (e.g. a bare list) are all refused here and
    counted by the caller as unparseable_state -- never a TypeError/AttributeError from
    `r["corpus"] = ...` on a non-dict payload."""
    try:
        r = json.loads(raw_line.decode("ascii", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return r if isinstance(r, dict) else None


def ingest_forward_bytes(raw: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """One forward-capture file's raw bytes -> (rows, refusal counts) (AMENDMENT 4 item c):
    the exact per-line decode/tag/count `_main` uses, extracted so the decoded-list refusal
    path is tested against raw bytes directly, never a pre-materialized list. AMENDMENT 6 item
    a: a validated `corpus_unit` (the served-night/window identifier the raw row carries) is
    preserved SEPARATELY from the `corpus` cell label ('forward', unchanged). AMENDMENT 7 item
    b / AMENDMENT 8 item c: canonicalised as `str(unit).strip()` -- int `1` and str `"1"` are
    one unit, and a whitespace-only or padded identifier (`'   '`, `' w1 '`) never survives as
    its own distinct unit; a row whose canonical form is empty (bool, non-scalar, blank, or
    whitespace-only) refuses here as unparseable_state, same as an undecodable line, so the
    real ingestion path can never collapse every forward row's identity down to the one
    constant 'forward' string, nor inflate one unit into two by representation or padding."""
    rows: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    for raw_line in raw.split(b"\n"):
        if not raw_line.strip():
            continue
        r = decode_forward_row(raw_line)  # type-checked, never a bare list/None reaching r["corpus"]
        if r is None:
            counts[REASON_UNPARSEABLE] = counts.get(REASON_UNPARSEABLE, 0) + 1
            continue
        unit = r.get("corpus_unit")
        if isinstance(unit, bool) or not isinstance(unit, (str, int)):
            counts[REASON_UNPARSEABLE] = counts.get(REASON_UNPARSEABLE, 0) + 1
            continue
        canonical_unit = str(unit).strip()
        if canonical_unit == "":
            counts[REASON_UNPARSEABLE] = counts.get(REASON_UNPARSEABLE, 0) + 1
            continue
        r["corpus"] = "forward"              # cell label, never the replication unit
        r["corpus_unit"] = canonical_unit    # stripped, canonical form stored
        rows.append(r)
    return rows, counts


def load_historical(corpus: str = HIST_CORPUS, root: str = HIST_ROOT
                     ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    """Best-effort adapter over the existing joined-tick schema (NOT VERIFIED against the
    real files -- see memo). Reads raw bytes and decodes per line so a non-ASCII byte is a
    counted refusal (items e/i), never a crash; a row that cannot be parsed is refused too;
    outcome is passed through raw (unsettled rows are refused by process_rows, not here)."""
    rows: List[Dict[str, Any]] = []
    identities: List[Dict[str, Any]] = []
    refusals: Dict[str, int] = {}
    for fp in sorted(glob.glob(f"{root}/{corpus}/*.jsonl")):
        identities.append(record_identity(fp))
        for raw_line in Path(fp).read_bytes().split(b"\n"):
            if not raw_line.strip():
                continue
            try:
                line = raw_line.decode("ascii", errors="strict").strip()
            except UnicodeDecodeError:
                refusals[REASON_NON_ASCII] = refusals.get(REASON_NON_ASCII, 0) + 1
                continue
            try:
                r = json.loads(line)
                m = _STATE_RE.search(str(r.get("state_summary", "")))
                gdate = r.get("game_date") or r.get("date")
                home, away = r.get("home"), r.get("away")
                if not m or gdate is None or home is None or away is None:
                    raise ValueError("missing field")
                hs, aw_s, inn = (parse_int_exact(m.group(1)), parse_int_exact(m.group(2)),
                                 parse_int_exact(m.group(3)))
                if hs is None or aw_s is None or inn is None:
                    raise ValueError("non_integer_state_field")  # never silently truncated
                half = _LOADER_HALVES.get(m.group(4).lower())
                if half is None:  # AMENDMENT 5 item d: only top/bot/bottom, never a silent top
                    raise ValueError("invalid_half_spelling")
                rows.append({
                    "game_id": r["game_id"], "receipt": r["ts"], "game_date": str(gdate),
                    "home_score": hs, "away_score": aw_s, "inning": inn,
                    "half": half,
                    "home": home, "away": away,
                    "outcome": r.get("outcome"), "carry": r.get("pregame_prior"),
                    "mid": r.get("market_prob"), "corpus": "historical_descriptive",
                })
            except Exception:
                refusals[REASON_BAD_ROW] = refusals.get(REASON_BAD_ROW, 0) + 1
    return rows, identities, refusals
