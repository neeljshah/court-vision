"""scripts.platformkit.paper.prediction_close_attach -- true-close CLV for the
prediction ledger, same pattern as odds_provider.line_store + the paper_pm channel.

grade_predictions.py's _clv_from_proxy only ever produces clv_status='proxy' (a
same-cycle book snapshot at LOG time) or 'no_close'. This module adds the
PRECEDING, higher-quality tier: at grade time, look up our own captured line
history (data/cache/line_history/<sport>/<date>.jsonl, written by the snapshot
daemon) for a moneyline quote captured inside the LOCK WINDOW before tipoff ->
clv_status='true_close' (mirrors line_store's own is_true_close contract and
clv_scoreboard._is_measurable's true_close-only aggregate).

WHY NOT line_store.get_close(event_id) DIRECTLY: a bare game_id game_key has no
sport hint (parse_game_key sets sport=None for any no-'|' string), so get_close
falls back to scanning EVERY sport dir's every file -- measured ~8s/call on the
real corpus. We already know the row's sport, so this module scans only
data/cache/line_history/<sport>/*.jsonl for the matching game_id (same JSONL
shape + _within_lock lock-window rule line_store uses, just sport-scoped).

Scope: moneyline-selection rows only (selection == home_team or away_team) --
compute_clv is a two-way home/away devig, same scope _clv_from_proxy already
uses. Derived/spread/total rows are untouched (no market_type this module can
price against with the same two-way math).

HONESTY (binding):
  * A row's event_id must have a moneyline (home, away) pair BOTH captured
    inside the lock window, or we do not claim a true close -- falls back to
    the caller's existing proxy/no_close precedence. Never fabricates.
  * Historical rows logged before the snapshot daemon existed / before
    line_history's retention window simply have no stored quotes -- they stay
    'no_close' or 'proxy' honestly, never backfilled.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/paper/test_prediction_close_attach.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.clv_ledger import compute_clv
from scripts.platformkit.odds_provider.snapshot import DEFAULT_HISTORY_DIR

_MONEYLINE = "moneyline"
_HOME, _AWAY = "home", "away"
# Mirrors odds_provider.line_store.DEFAULT_LOCK_WINDOW_MIN exactly (same lock
# rule, sport-scoped scan -- see module docstring for why this isn't a call
# straight into line_store.get_close).
_LOCK_WINDOW_MIN = 30

# Same shape as grade_predictions._NO_CLOSE; kept local so this module has no
# no-close-found return path that silently differs from the caller's default.
NO_TRUE_CLOSE = {"clv_pct": None, "beat_close": None,
                 "clv_status": "no_close", "clv_is_proxy": False}


def _moneyline_side(row: Dict[str, Any], home_team: str, away_team: str
                    ) -> Optional[str]:
    """'home' | 'away' | None -- only a literal moneyline-team selection qualifies."""
    selection = row.get("selection")
    if selection == home_team:
        return _HOME
    if selection == away_team:
        return _AWAY
    return None


def _parse_ts(iso_ts: Any) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(iso_ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _within_lock(row: Dict[str, Any], captured: Optional[datetime]) -> bool:
    """True iff *captured* falls in [tip - _LOCK_WINDOW_MIN, tip]. Never raises."""
    commence = _parse_ts(row.get("commence_time"))
    if commence is None or captured is None:
        return False
    return (commence - timedelta(minutes=_LOCK_WINDOW_MIN)) <= captured <= commence


def _moneyline_pair_at_lock(sport: str, event_id: str, base: Optional[Path]
                            ) -> Optional[Dict[str, Dict[str, Any]]]:
    """Latest AT-LOCK moneyline quote per side for *event_id*, sport-scoped so
    this is one small directory glob, never the whole corpus. {} entries missing
    -> None. Never raises."""
    root = Path(base) if base is not None else DEFAULT_HISTORY_DIR
    sport_dir = root / str(sport).lower()
    if not sport_dir.exists():
        return None
    best: Dict[str, Dict[str, Any]] = {}
    best_ts: Dict[str, datetime] = {}
    for f in sorted(sport_dir.glob("*.jsonl")):
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (not isinstance(row, dict)
                    or str(row.get("game_id", "")) != event_id
                    or str(row.get("market_type", "")) != _MONEYLINE):
                continue
            side = str(row.get("side", ""))
            if side not in (_HOME, _AWAY):
                continue
            ts = _parse_ts(row.get("captured_at"))
            if ts is None or not _within_lock(row, ts):
                continue
            if side not in best_ts or ts >= best_ts[side]:
                best[side] = row
                best_ts[side] = ts
    if _HOME not in best or _AWAY not in best:
        return None
    return best


def attach_true_close(
    row: Dict[str, Any], home_team: str, away_team: str,
    *, line_history_base: Any = None,
) -> Dict[str, Any]:
    """clv_status='true_close' dict when our own line history proves BOTH
    moneyline sides were captured inside the lock window before tipoff;
    NO_TRUE_CLOSE otherwise (never raises, never fabricates). Caller
    (grade_one_pred) tries this FIRST, then falls back to the existing
    close_proxy path on NO_TRUE_CLOSE.
    """
    event_id = str(row.get("event_id") or "").strip()
    sport = str(row.get("sport") or "").strip()
    if not event_id or not sport:
        return dict(NO_TRUE_CLOSE)
    side = _moneyline_side(row, home_team, away_team)
    if side is None:
        return dict(NO_TRUE_CLOSE)  # non-moneyline selection -> out of scope here
    dec = row.get("fair_odds")
    if not dec or float(dec) <= 1.0:
        return dict(NO_TRUE_CLOSE)

    try:
        pair = _moneyline_pair_at_lock(sport, event_id, line_history_base)
    except Exception:  # noqa: BLE001 -- read-only scan must never crash grading
        return dict(NO_TRUE_CLOSE)
    if pair is None:
        return dict(NO_TRUE_CLOSE)
    ch, ca = pair[_HOME].get("odds"), pair[_AWAY].get("odds")
    if ch is None or ca is None or float(ch) <= 1.0 or float(ca) <= 1.0:
        return dict(NO_TRUE_CLOSE)

    try:
        clv = compute_clv(side, float(dec), float(ch), float(ca))
    except Exception:  # noqa: BLE001 -- degenerate devig (booksum<1); no CLV
        return dict(NO_TRUE_CLOSE)
    return {"clv_pct": clv["clv_pct"], "beat_close": clv["clv_pct"] > 0.0,
            "clv_status": "true_close", "clv_is_proxy": False}


__all__ = ["attach_true_close", "NO_TRUE_CLOSE"]
