"""Bridge the placed-bet ledger to the captured line history.

A bet row carries an ``event_id`` / ``game_id`` but usually NOT its closing
line; the line-snapshot daemon meanwhile captures every game's quotes into
``line_store`` keyed by the SAME id. This module looks the close up by that id
so moneyline CLV becomes measurable instead of stuck at INSUFFICIENT_DATA.

HONEST RAILS: local files only (no network), never raises, never fabricates a
close (returns None when no at-lock/last quote exists), reads-only, no $ field,
no edge claim. A close found OUTSIDE the lock window is flagged is_true=False
(proxy), never silently promoted.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

try:
    from scripts.platformkit.odds_provider import line_store as _ls
    _OK = True
except Exception:  # noqa: BLE001 -- a missing line_store must never break enrich
    _OK = False


def _join_id(row: Dict[str, Any]) -> Optional[str]:
    """The line-history join key carried by the bet: game_id, else event_id."""
    for k in ("game_id", "event_id"):
        v = row.get(k)
        if v not in (None, ""):
            return str(v)
    return None


def lookup_close_legs(row: Dict[str, Any]) -> Optional[Tuple[float, float, bool]]:
    """``(close_home_decimal, close_away_decimal, is_true_close)`` for a
    moneyline bet, fetched from the captured line history by event_id/game_id.

    Returns None when line_store is unavailable, the row has no join id, there
    is no history for that game, or no usable two-way moneyline close. Never
    raises.
    """
    if not _OK:
        return None
    jid = _join_id(row)
    if jid is None:
        return None
    try:
        res = _ls.get_close(jid)
    except Exception:  # noqa: BLE001
        return None
    if not res:
        return None
    closes, is_true = res
    home = closes.get(("moneyline", "home"))
    away = closes.get(("moneyline", "away"))
    if not home or not away:
        return None
    try:
        h = float(home.get("odds"))
        a = float(away.get("odds"))
    except (TypeError, ValueError):
        return None
    if h > 1.0 and a > 1.0:
        return (h, a, bool(is_true))
    return None


__all__ = ["lookup_close_legs"]
