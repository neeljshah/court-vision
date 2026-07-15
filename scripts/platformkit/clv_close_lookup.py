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

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    from scripts.platformkit.odds_provider import line_store as _ls
    _OK = True
except Exception:  # noqa: BLE001 -- a missing line_store must never break enrich
    _OK = False

# ---------------------------------------------------------------------------
# Persistent memo for close lookups (PERF 2026-07-15, re-applied after an
# external git-restore wiped it; audit-hardened). line_store.get_close scans a
# multi-GB history corpus per game_key (seconds per miss) and every enrichment
# consumer pays that per row per request.
# Audit rules (cv CLV audit 2026-07-15):
#   - HITS are cached forever: a captured close for a game is immutable.
#   - MISSES expire after MISS_TTL_S (24h): a bet enriched before its close is
#     captured/backfilled must not read no_close forever.
# Append-only JSONL under data/cache/; corrupt/missing cache degrades to slow
# lookups, never to a wrong answer.
# ---------------------------------------------------------------------------
_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "cache" / "clv_close_legs_cache.jsonl"
_MISS_TTL_S = 24 * 3600.0
_MEM: Dict[str, Tuple[Optional[Tuple[float, float, bool]], float]] = {}
_MEM_LOADED = False


def _mem_load() -> None:
    global _MEM_LOADED
    if _MEM_LOADED:
        return
    _MEM_LOADED = True
    try:
        with _CACHE_PATH.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                jid = rec.get("jid")
                if jid is None:
                    continue
                legs = rec.get("legs")
                # Legacy entries lack ts: treat as fresh-at-load. They were
                # computed post-settlement (offline warm), so their misses are
                # final; expiring them re-triggers the full scan storm whose
                # GIL-bound JSON parsing starves the event loop (the wedge).
                ts = float(rec.get("ts") or time.time())
                _MEM[str(jid)] = (
                    tuple(legs) if isinstance(legs, list) and len(legs) == 3 else None,
                    ts,
                )
    except OSError:
        pass  # no cache yet -> cold start


def _mem_get(jid: str) -> Optional[Tuple[Optional[Tuple[float, float, bool]], float]]:
    """Cached (legs, ts) or None on miss/expired-miss. Hits never expire."""
    ent = _MEM.get(jid)
    if ent is None:
        return None
    legs, ts = ent
    if legs is None and (time.time() - ts) > _MISS_TTL_S:
        return None  # expired miss -> recompute (close may exist by now)
    return ent


def _mem_put(jid: str, legs: Optional[Tuple[float, float, bool]]) -> None:
    ts = time.time()
    _MEM[jid] = (legs, ts)
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _CACHE_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"jid": jid, "ts": ts,
                                 "legs": list(legs) if legs is not None else None})
                     + "\n")
    except OSError:
        pass  # cache write failure degrades to in-memory only


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
    _mem_load()
    hit = _mem_get(jid)
    if hit is not None:
        return hit[0]
    try:
        res = _ls.get_close(jid)
    except Exception:  # noqa: BLE001
        return None
    if not res:
        _mem_put(jid, None)
        return None
    closes, is_true = res
    home = closes.get(("moneyline", "home"))
    away = closes.get(("moneyline", "away"))
    if not home or not away:
        _mem_put(jid, None)
        return None
    try:
        h = float(home.get("odds"))
        a = float(away.get("odds"))
    except (TypeError, ValueError):
        _mem_put(jid, None)
        return None
    if h > 1.0 and a > 1.0:
        legs = (h, a, bool(is_true))
        _mem_put(jid, legs)
        return legs
    _mem_put(jid, None)
    return None


__all__ = ["lookup_close_legs"]
