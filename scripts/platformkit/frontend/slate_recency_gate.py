"""slate_recency_gate.py -- drop or mark stale any slate row/game past tipoff.

QA-ISSUE (iter 9/10 P1+P2): :8098/api/slate returned the completed NYK@SAS NBA
Finals game (tipoff 2026-06-14, ~150 h in the past) with status='ok' and
freshness.as_of showing today, implying live data while the game is long complete.
A Polymarket Yes/No binary (tipoff 2025-07-02, ev=683.2) appeared in soccer_intl.
Stale-never-green: a game that is too far past tipoff must not be served as live
pregame. Non-sports binaries (Yes/No) must always be excluded.

Behaviour (pure function over a slate payload + now):
  DROP   -- row/game whose tipoff is > STALE_DROP_HOURS past (default 6 h);
            OR is a non-sports Yes/No binary (regardless of hours).
  STAMP  -- row/game whose tipoff is past but within STALE_DROP_HOURS (e.g. 0-6 h
            past): adds stale=True, hours_old=<float>, clears status to 'stale'.
  PASS   -- row/game whose tipoff is in the future: returned unchanged.

Two payload shapes are handled:
  * {"games": [...]}  -- predict_service.store / snapshot path (nested edges).
  * {"rows": [...]}   -- slate.build_slate live-compute path (flat rows).
Both paths look for tipoff in any of: tipoff_utc, tipoff, game_datetime,
commence_time -- the same keys _tipoff_in_past uses.

RAILS:
  - Pure: no network, no global state; reads the wall clock only for the
    tipoff check (injectable for deterministic tests).
  - Returns a NEW payload; never mutates the input dict / nested lists.
  - No $ / ROI / PnL field added.
  - ASCII only; <= 300 LOC.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \\
    tests/platformkit/test_slate_recency_gate.py -q
"""
from __future__ import annotations

import copy
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# Default thresholds.
STALE_DROP_HOURS: float = 6.0   # tipoff older than this -> drop
# Tipoff keys to search (matches board_sanitizer._TIPOFF_KEYS).
_TIPOFF_KEYS = ("tipoff_utc", "tipoff", "game_datetime", "commence_time")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_utc(raw: Any) -> Optional[datetime]:
    """Parse a datetime or ISO-8601 string to a UTC-aware datetime; None on fail."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            return None
    return None


def _get_tipoff(row: Dict[str, Any]) -> Optional[datetime]:
    """Return the first parseable tipoff datetime in *row*, else None."""
    for key in _TIPOFF_KEYS:
        tip = _parse_utc(row.get(key))
        if tip is not None:
            return tip
    return None


def _is_non_sports_binary(row: Dict[str, Any]) -> bool:
    """True when home/away or matchup indicates a Polymarket Yes/No binary."""
    # Check explicit home/away team fields.
    home = str(row.get("home") or "").strip().lower()
    away = str(row.get("away") or "").strip().lower()
    if {home, away} == {"yes", "no"}:
        return True
    # Check matchup string (covers flat rows that carry a pre-built matchup label).
    matchup = str(row.get("matchup") or "").lower()
    return "yes vs no" in matchup or "no vs yes" in matchup


def _recency_verdict(
    row: Dict[str, Any],
    now: datetime,
    stale_drop_hours: float,
) -> Tuple[str, Optional[float]]:
    """Return ('keep'|'stamp'|'drop', hours_old_or_None).

    'keep'  -- tipoff in the future or not present (do not block on missing tipoff).
    'stamp' -- tipoff is past but within stale_drop_hours of now.
    'drop'  -- tipoff is > stale_drop_hours in the past.
    """
    tip = _get_tipoff(row)
    if tip is None:
        return "keep", None
    age = (now - tip).total_seconds() / 3600.0
    if age <= 0.0:
        return "keep", None
    if age <= stale_drop_hours:
        return "stamp", age
    return "drop", age


# ---------------------------------------------------------------------------
# Per-row / per-game processing
# ---------------------------------------------------------------------------

def _apply_row(
    row: Dict[str, Any],
    now: datetime,
    stale_drop_hours: float,
) -> Optional[Dict[str, Any]]:
    """Apply recency gate to a single flat row.

    Returns None (drop), or a (possibly annotated) copy of the row.
    """
    if not isinstance(row, dict):
        return None
    if _is_non_sports_binary(row):
        return None
    verdict, hours_old = _recency_verdict(row, now, stale_drop_hours)
    if verdict == "drop":
        return None
    if verdict == "stamp":
        out = dict(row)
        out["stale"] = True
        out["hours_old"] = round(hours_old, 2) if hours_old is not None else None
        out["status"] = "stale"
        return out
    return dict(row)   # 'keep': shallow copy, unchanged


def _apply_game(
    game: Dict[str, Any],
    now: datetime,
    stale_drop_hours: float,
) -> Optional[Dict[str, Any]]:
    """Apply recency gate to a nested game object (games-list payload shape).

    Returns None (drop), or a (possibly annotated) shallow copy.
    """
    if not isinstance(game, dict):
        return None
    if _is_non_sports_binary(game):
        return None
    verdict, hours_old = _recency_verdict(game, now, stale_drop_hours)
    if verdict == "drop":
        return None
    if verdict == "stamp":
        out = dict(game)
        out["stale"] = True
        out["hours_old"] = round(hours_old, 2) if hours_old is not None else None
        out["status"] = "stale"
        return out
    return dict(game)  # 'keep'


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_recency_gate(
    payload: Dict[str, Any],
    now: Optional[datetime] = None,
    *,
    stale_drop_hours: float = STALE_DROP_HOURS,
) -> Dict[str, Any]:
    """Return a NEW slate payload with past-tipoff rows/games dropped or stamped stale.

    Handles two payload shapes:
      - {"games": [...]}  -- predict_service.store / snapshot path.
      - {"rows": [...]}   -- slate.build_slate live-compute path.

    Parameters
    ----------
    payload:
        Slate dict as produced by serve._read_ps_store_slate, build_slate, or
        slate_dead_market_filter.sanitize_slate.
    now:
        UTC reference time for the tipoff check. Defaults to datetime.now(utc).
        Injectable for deterministic tests.
    stale_drop_hours:
        Threshold (hours) past tipoff beyond which a game is dropped.
        Games between 0 and stale_drop_hours hours past tipoff are STAMPED stale.

    Returns
    -------
    Dict[str, Any]
        New payload dict. "games" / "rows" replaced with the filtered list.
        "recency_dropped" key added when at least one entry was dropped.
        "recency_stamped" key added when at least one entry was stamped.
        Original dict not mutated.
    """
    if not isinstance(payload, dict):
        return payload
    if now is None:
        now = datetime.now(tz=timezone.utc)

    # Determine which list key this payload uses.
    if "games" in payload and isinstance(payload["games"], list):
        list_key = "games"
        apply_fn = _apply_game
    elif "rows" in payload and isinstance(payload["rows"], list):
        list_key = "rows"
        apply_fn = _apply_row
    else:
        return payload   # no recognised list -- pass through unchanged

    raw: List[Dict[str, Any]] = payload[list_key]
    kept: List[Dict[str, Any]] = []
    n_dropped = 0
    n_stamped = 0

    for item in raw:
        result = apply_fn(item, now, stale_drop_hours)
        if result is None:
            n_dropped += 1
        else:
            if result.get("stale"):
                n_stamped += 1
            kept.append(result)

    out = dict(payload)
    out[list_key] = kept
    if n_dropped:
        out["recency_dropped"] = n_dropped
    if n_stamped:
        out["recency_stamped"] = n_stamped
    return out


__all__ = ["STALE_DROP_HOURS", "apply_recency_gate"]
