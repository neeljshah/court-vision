"""scripts.platformkit.ingame.kbo_naver_relay -- Naver Sports per-game KBO relay
(read-only reference probe, wave-22 lane 5).

THE GAP THIS CLOSES: npb_kbo_live_state.py's KBO path (koreabaseball.com
GetScheduleList) only gives a COARSE same/same-0-0 in-progress marker -- no
inning, no base state, no ball/strike/out count (see that module's docstring).
This module adds a genuinely FINE-GRAINED per-game relay discovered by probing
api-gw.sports.naver.com (~10 min timeboxed probe, wave-22 lane 5): the
schedule list endpoint's gameId, fed into a per-game relay path, returns a
rich live text-relay payload with a real base-out state.

RECIPE (probed live 2026-07-04, read-only via resilient_get_json):
  1. Slate:  https://api-gw.sports.naver.com/schedule/games
             ?fields=basic&fromDate=YYYY-MM-DD&toDate=YYYY-MM-DD
             &upperCategoryId=kbaseball&categoryId=kbo
     -> {"result": {"games": [{"gameId": "20260703HHLG02026", "statusCode":
        "RESULT"|..., "homeTeamCode", "awayTeamCode", "homeTeamScore",
        "awayTeamScore", ...}]}}. gameId shape = YYYYMMDD + AWAY(2) + HOME(2)
        + seq(2digit season) -- e.g. "20260703HHLG02026" = 2026-07-03,
        away=HH (Hanwha), home=LG, seq 02026. No auth/session needed.
  2. Relay:  https://api-gw.sports.naver.com/schedule/games/{gameId}/relay
     -> {"result": {"textRelayData": {"currentGameState": {homeScore,
        awayScore, homeHit, awayHit, homeBallFour, awayBallFour, homeError,
        awayError, pitcher, batter, strike, ball, out, base1, base2, base3},
        "inningScore": {"home": {"1":.., ..}, "away": {...}}, "textRelays":
        [...]}}}. base1/base2/base3 are runner-id strings ("0" = empty, else
        the on-base runner's player id) -- a REAL base-out state, finer than
        anything npb_kbo_live_state.py's coarse bridge can see. No Referer
        header required (verified: identical response with/without it).
  3. Also confirmed: https://api-gw.sports.naver.com/schedule/games/{gameId}
     (singular, no /relay) returns the same per-game summary as the slate row
     (statusCode, scores, gameCenterUrl) -- useful as a cheap existence check
     before pulling the heavier /relay payload (204KB vs 2.4KB).

HONEST LIMITS (this wave): probed against COMPLETED (statusCode RESULT) games
only -- no genuinely in-progress KBO game was live at probe time (single
game slate today, already final by check time) so an in-progress relay
payload's exact currentGameState shape during play is UNCONFIRMED (structure
is stable/typed enough across a finished game's snapshot that it should carry
through, but this is not yet LIVE-verified mid-game). Do NOT claim mid-game
verification beyond this. `/schedule/games/{gameId}/record` (box-score-shaped,
19KB) also returns 200 but was not parsed this wave -- unexplored, not blocked.

This module is READ-ONLY: fetch + parse only, no write to any grading path,
no wiring into npb_kbo_live_state.py or inplay_capture_loop.py (forbidden
files for this lane). Uses the existing stealth-capable transport
(scripts.platformkit.odds_provider.transport.resilient_get_json) so a future
WAF wall on api-gw degrades the same way every other odds-provider fetch does.

INVARIANTS: <=300 LOC; ASCII only; no $/edge fields; never raises (best-effort
None/[] on any failure); network isolated via injectable http_get.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_kbo_naver_relay.py -q
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional
from urllib.parse import urlencode

from scripts.platformkit.odds_provider.transport import resilient_get_json

logger = logging.getLogger(__name__)

_SLATE_URL = "https://api-gw.sports.naver.com/schedule/games"
_RELAY_URL = "https://api-gw.sports.naver.com/schedule/games/{gid}/relay"
_TIMEOUT = 15.0


def slate_url(from_date: str, to_date: str) -> str:
    """Build the KBO slate URL for [from_date, to_date] (YYYY-MM-DD each)."""
    params = {
        "fields": "basic",
        "fromDate": from_date,
        "toDate": to_date,
        "upperCategoryId": "kbaseball",
        "categoryId": "kbo",
    }
    return f"{_SLATE_URL}?{urlencode(params)}"


def fetch_slate(from_date: str, to_date: str,
                 http_get: Optional[Callable] = None) -> List[Dict]:
    """Today's (or [from_date, to_date]'s) KBO games: [{gameId, statusCode,
    homeTeamCode, awayTeamCode, homeTeamScore, awayTeamScore, ...}, ...].
    [] on any failure (network, non-JSON, unexpected shape) -- never raises."""
    getter = http_get or resilient_get_json
    try:
        payload = getter(slate_url(from_date, to_date), _TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        logger.debug("kbo_naver_relay slate fetch failed: %s", exc)
        return []
    if not isinstance(payload, dict):
        return []
    games = ((payload.get("result") or {}).get("games")) or []
    return [g for g in games if isinstance(g, dict) and g.get("gameId")]


def fetch_relay(game_id: str, http_get: Optional[Callable] = None) -> Optional[Dict]:
    """Raw textRelayData dict for one game_id, or None on any failure
    (network, non-JSON, missing textRelayData key) -- never raises."""
    getter = http_get or resilient_get_json
    try:
        payload = getter(_RELAY_URL.format(gid=game_id), _TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        logger.debug("kbo_naver_relay relay fetch failed gid=%s: %s", game_id, exc)
        return None
    if not isinstance(payload, dict):
        return None
    trd = (payload.get("result") or {}).get("textRelayData")
    return trd if isinstance(trd, dict) else None


def extract_base_out_state(relay: Dict) -> Optional[Dict]:
    """PURE: textRelayData -> a compact base-out state dict, or None if
    currentGameState is absent/malformed. base1/2/3 are truthy iff a runner
    occupies that base ("0" or missing = empty); never fabricates a value
    the feed did not provide."""
    cgs = relay.get("currentGameState")
    if not isinstance(cgs, dict):
        return None

    def _on_base(key: str) -> bool:
        v = cgs.get(key)
        return v is not None and str(v) not in ("0", "")

    def _int_or_none(key: str) -> Optional[int]:
        v = cgs.get(key)
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    return {
        "home_score": _int_or_none("homeScore"),
        "away_score": _int_or_none("awayScore"),
        "balls": _int_or_none("ball"),
        "strikes": _int_or_none("strike"),
        "outs": _int_or_none("out"),
        "base1": _on_base("base1"),
        "base2": _on_base("base2"),
        "base3": _on_base("base3"),
    }


def main() -> None:
    import datetime as _dt
    import json
    today = _dt.date.today().isoformat()
    games = fetch_slate(today, today)
    print(json.dumps({"date": today, "n_games": len(games), "games": games}, indent=2))


if __name__ == "__main__":
    main()


__all__ = ["slate_url", "fetch_slate", "fetch_relay", "extract_base_out_state"]
