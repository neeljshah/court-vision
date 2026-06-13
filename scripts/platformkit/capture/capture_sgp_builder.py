"""capture_sgp_builder.py — Row builder, kind classifier, and seen-key loader for capture_sgp.

Provides classify_kind, _now_ts, _build_sgp_rows, and _load_seen_keys.
Extracted from capture_sgp.py to keep each file ≤300 LOC.
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from ledger_schema import record_key, validate  # noqa: E402
from ledger_writer import read_all  # noqa: E402

_SPORT = "nba"
_SOURCE = "odds_api_sgp"

_CLOSE_MIN = 5   # minutes before tip → "close"
_MOVE_MIN  = 60  # minutes before tip → "move"


# ---------------------------------------------------------------------------
# Kind classification (mirrors capture_nba.classify_kind)
# ---------------------------------------------------------------------------

def classify_kind(
    event_id: str,
    market: str,
    book: str,
    side: str,
    seen: Set[Tuple],
    commence_time: Optional[str],
    now_utc: Optional[datetime.datetime] = None,
) -> str:
    """Return ``open`` / ``move`` / ``close`` for a snapshot row.

    First-seen → ``open``.  Already open → time-window determines
    ``move`` (T-60) or ``close`` (T-5).

    Args:
        event_id: Odds API event identifier.
        market: Ledger market string (e.g. ``sgp:player_points+player_rebounds``).
        book: Bookmaker key.
        side: Outcome side string.
        seen: Set of already-written record_key tuples.
        commence_time: ISO-8601 UTC commence time string, or ``None``/empty.
        now_utc: Injected current time for deterministic classification.

    Returns:
        One of ``"open"``, ``"move"``, ``"close"``.
    """
    open_key = (_SPORT, event_id, market, book, side, "open")
    if open_key not in seen:
        return "open"
    if commence_time and commence_time.strip():
        now = now_utc or datetime.datetime.now(datetime.timezone.utc)
        try:
            tip_str = (commence_time.rstrip("Z") + "+00:00"
                       if commence_time.endswith("Z") else commence_time)
            tip = datetime.datetime.fromisoformat(tip_str)
            mins = (tip - now).total_seconds() / 60.0
            if mins <= _CLOSE_MIN:
                return "close"
            if mins <= _MOVE_MIN:
                return "move"
        except (ValueError, OverflowError):
            pass
    return "open"


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

def _now_ts() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_sgp_market_tag(legs: Tuple[str, ...]) -> str:
    """Return the canonical ledger market tag for an SGP combo.

    Args:
        legs: Ordered sequence of Odds API market key strings.

    Returns:
        String of the form ``sgp:<leg1>+<leg2>[+...]``.
    """
    if not legs:
        raise ValueError("SGP market tag requires at least one leg.")
    return "sgp:" + "+".join(legs)


def _build_sgp_rows(
    event_id: str,
    commence: str,
    legs: Tuple[str, ...],
    bookmakers: List[Dict[str, Any]],
    ts: str,
    seen: Set[Tuple],
    now_utc: Optional[datetime.datetime] = None,
) -> Iterator[dict]:
    """Yield validated ledger rows from one SGP combo response.

    An SGP row's ``side`` encodes the outcome label plus player (if any)
    and line point so it is fully self-describing:
    ``<direction>:<description>:<point>`` or ``<name>`` for non-player legs.

    Args:
        event_id: Odds API event identifier.
        commence: ISO-8601 UTC commence time string.
        legs: Tuple of market keys forming the SGP combo.
        bookmakers: Bookmakers list from the API response.
        ts: ISO-8601 UTC observation timestamp string.
        seen: Set of already-written record_key tuples (mutated in-place).
        now_utc: Injected current time for kind classification.

    Yields:
        Validated ledger record dicts.
    """
    market_tag = make_sgp_market_tag(legs)
    for bm in bookmakers:
        book = bm.get("key", "").strip()
        if not book:
            continue
        for mkt_obj in bm.get("markets", []):
            for out in mkt_obj.get("outcomes", []):
                name = (out.get("name") or "").strip().lower()
                description = (out.get("description") or "").strip()
                price = out.get("price")
                point = out.get("point")
                if price is None or not name:
                    continue
                # Build a self-describing side string.
                if description and point is not None:
                    side = f"{name}:{description}:{point}"
                elif description:
                    side = f"{name}:{description}"
                elif point is not None:
                    side = f"{name}:{point}"
                else:
                    side = name
                kind = classify_kind(
                    event_id, market_tag, book, side, seen, commence, now_utc
                )
                rec = dict(
                    sport=_SPORT,
                    event_id=event_id,
                    market=market_tag,
                    book=book,
                    price=float(price),
                    side=side,
                    kind=kind,
                    ts_utc_observed=ts,
                    source=_SOURCE,
                )
                try:
                    validate(rec)
                    yield rec
                except ValueError:
                    pass


# ---------------------------------------------------------------------------
# Seen-keys loader
# ---------------------------------------------------------------------------

def _load_seen_keys(ledger_root: Optional[Path]) -> Set[Tuple]:
    """Load all existing record keys from the ledger (SGP sport dir only).

    Args:
        ledger_root: Ledger root directory override, or ``None`` for default.

    Returns:
        Set of ``(sport, event_id, market, book, side, kind)`` tuples.
    """
    from ledger_writer import _DEFAULT_ROOT as _dr  # noqa: PLC0415
    root = ledger_root if ledger_root is not None else _dr
    sport_dir = Path(root) / _SPORT
    seen: Set[Tuple] = set()
    if not sport_dir.exists():
        return seen
    for jf in sport_dir.glob("*.jsonl"):
        try:
            for row in read_all(_SPORT, jf.stem, root):
                k = record_key(row)
                # Only load SGP-tagged rows to avoid false positives from
                # mainline rows sharing the same (event, book, side, kind).
                if row.get("market", "").startswith("sgp:"):
                    seen.add(k)
        except Exception:
            pass
    return seen
