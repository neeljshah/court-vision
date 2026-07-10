"""scripts.platformkit.pm_trading.mlb_dh_stamp -- MLB doubleheader (DH) exposure
fix (seed D6): at PREGAME placement time, resolve and stamp game_number/game_pk
onto a new MLB paper row so a DH date can be disambiguated at settle time (the
settler is unchanged this lane -- it can use the stamp once present).

REUSE, not a new fetch path: the SAME statsapi schedule URL + HTTP GET + team-
pair-key resolver the live 3-way id bridge (ingame.game_pk_bridge_live) already
uses for today's slate -- imported, not re-derived.

FORWARD-ONLY: historical ledger rows are never touched; this only stamps rows
recorded from here on. Fail-closed: any lookup miss, unresolved team pair,
missing/unparseable commence_time, or a tied doubleheader-leg distance returns
{} rather than guess -- a bare miss is honest, a wrong guess is not.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no secrets; ponytail --
game_number disambiguation only, settle-side consumption is a separate lane.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/pm_trading/test_mlb_dh_stamp.py -q
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

# REUSE (not a new fetch path): the SAME statsapi schedule URL + HTTP GET +
# pair-key resolver the live 3-way id bridge already uses for today's slate.
from scripts.platformkit.ingame.game_pk_bridge_live import (
    _SCHEDULE_URL, _http_get_json, _pair_key)

logger = logging.getLogger(__name__)


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    """Lenient ISO-8601 parse ('Z' or offset suffix); None on any bad/missing value."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def mlb_schedule_pairs(date_str: str, *, http: Callable[[str], Any] = _http_get_json
                       ) -> Dict[str, List[Dict[str, Any]]]:
    """pair_key -> [{game_pk, game_number, game_date}, ...] for statsapi *date_str*.
    2+ entries = a real doubleheader (statsapi's own gameNumber is authoritative,
    never re-derived by ordering). {} on any feed failure, never raises."""
    data = http(_SCHEDULE_URL.format(date=date_str))
    if not isinstance(data, dict):
        return {}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for day in data.get("dates", []) or []:
        for g in day.get("games", []) or []:
            teams = g.get("teams", {}) or {}
            away = (teams.get("away", {}).get("team", {}) or {}).get("name")
            home = (teams.get("home", {}).get("team", {}) or {}).get("name")
            pk = g.get("gamePk")
            if pk is None or not away or not home:
                continue
            key = _pair_key(away, home)
            if key is None:
                continue
            out.setdefault(key, []).append({
                "game_pk": int(pk), "game_number": int(g.get("gameNumber") or 1),
                "game_date": g.get("gameDate"),
            })
    return out


def mlb_dh_stamp(home: str, away: str, event_day: str, commence_time: Optional[str],
                 *, http: Callable[[str], Any] = _http_get_json) -> Dict[str, Any]:
    """{'game_number': N, 'game_pk': pk} for an MLB game (D6 doubleheader fix).
    One scheduled game for the pair -> unambiguous, always stamped. 2+ games (a
    real DH) disambiguate by nearest commence_time; any lookup miss, missing/
    unparseable commence_time, or a tied distance -> {} (fail-closed, never
    guessed). Historical rows untouched; this only stamps NEW placements."""
    if not event_day:
        return {}
    try:
        pairs = mlb_schedule_pairs(event_day, http=http)
        key = _pair_key(away, home)
    except Exception as exc:  # noqa: BLE001 -- an unresolved lookup is an honest miss
        logger.debug("mlb_dh_stamp lookup failed %s@%s %s: %s", away, home, event_day, exc)
        return {}
    if key is None:
        return {}
    candidates = pairs.get(key) or []
    if len(candidates) == 1:
        c = candidates[0]
        return {"game_number": c["game_number"], "game_pk": c["game_pk"]}
    if len(candidates) < 2:
        return {}
    ct = _parse_iso(commence_time)
    if ct is None:
        return {}
    scored = []
    for c in candidates:
        gd = _parse_iso(c.get("game_date"))
        if gd is None:
            return {}  # a candidate with no parseable schedule time -> never guess
        scored.append((abs((gd - ct).total_seconds()), c))
    scored.sort(key=lambda t: t[0])
    if scored[0][0] == scored[1][0]:
        return {}  # tied distance -> genuinely ambiguous, fail closed
    best = scored[0][1]
    return {"game_number": best["game_number"], "game_pk": best["game_pk"]}


__all__ = ["mlb_schedule_pairs", "mlb_dh_stamp"]
