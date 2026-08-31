"""scripts.platformkit.paper.finals_fetch -- FINAL score by ESPN event_id.

The logged paper predictions carry an ``event_id`` (and a commence_time in the past),
so they are graded against the FINAL of that specific game -- fetched from ESPN's
keyless public ``summary`` endpoint, NOT today's scoreboard. The HTTP getter is
INJECTABLE so tests never touch the network.

HONESTY (binding): a final is returned ONLY when the feed reports the game as
completed (state in {post, final}) with both scores present. Anything else -> None
(the bet stays OPEN -- never fabricated). One bad fetch never raises.

final_for_event(event_id, sport, *, http_get=...) ->
  {"state","home","away","home_score","away_score"} | None

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets;
no network at import time / in tests.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/paper/test_grade_predictions.py -q
"""
from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# platform sport id -> ESPN summary path (site_path).
_ESPN_SUMMARY_PATH: Dict[str, str] = {
    "mlb": "baseball/mlb",
    "nba": "basketball/nba",
    "soccer_intl": "soccer/fifa.world",
    "soccer": "soccer/eng.1",
}
_SUMMARY_BASE = (
    "https://site.api.espn.com/apis/site/v2/sports/{path}/summary?event={eid}")
_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_TIMEOUT = 12
_FINAL_STATES = ("post", "final")

HttpGet = Callable[[str], Dict[str, Any]]


def _default_http_get(url: str) -> Dict[str, Any]:
    """Keyless GET (urllib + browser UA + timeout). Returns {} on any error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # nosec - GET only
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as http_exc:
            if http_exc.code != 403:
                raise
            # Datacenter IPs (RunPod) get 403 on browser UAs but 200 on plain
            # ones -- verified 2026-08-31. Retry once with a plain UA.
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # nosec - GET only
                return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # pragma: no cover - network guard
        logger.warning("ESPN summary GET failed %s: %s", url, exc)
        return {}


def _to_int(v: Any) -> Optional[int]:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def parse_summary(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract the final from an ESPN summary payload, or None if not final.

    Pure (no I/O). Reads header.competitions[0].competitors; requires both scores
    and a completed status; returns home/away display names + scores. None when the
    game is not final or the payload is malformed -- never fabricates.
    """
    try:
        comps = (payload.get("header") or {}).get("competitions") or []
        if not comps:
            return None
        comp = comps[0]
        status = ((comp.get("status") or {}).get("type") or {})
        state = str(status.get("state") or "").lower()
        completed = bool(status.get("completed"))
        if state not in _FINAL_STATES and not completed:
            return None
        home = away = None
        for c in comp.get("competitors") or []:
            team = c.get("team") or {}
            name = team.get("displayName") or team.get("name") or team.get("abbreviation")
            score = _to_int(c.get("score"))
            entry = {"name": name, "score": score, "abbr": team.get("abbreviation")}
            if str(c.get("homeAway") or "").lower() == "home":
                home = entry
            elif str(c.get("homeAway") or "").lower() == "away":
                away = entry
        if not home or not away:
            return None
        if home["score"] is None or away["score"] is None:
            return None
        return {
            "state": "post",
            "home": home["name"], "away": away["name"],
            "home_abbr": home["abbr"], "away_abbr": away["abbr"],
            "home_score": home["score"], "away_score": away["score"],
        }
    except Exception:  # noqa: BLE001 - one bad payload never sinks the pass
        logger.debug("parse_summary failed", exc_info=True)
        return None


def final_for_event(
    event_id: str, sport: str, *, http_get: Optional[HttpGet] = None
) -> Optional[Dict[str, Any]]:
    """Fetch + parse the FINAL for one ESPN event_id. None if not final/unknown sport.

    *http_get* is injectable (url -> dict) so tests never hit the network.
    """
    eid = str(event_id or "").strip()
    if not eid:
        return None
    path = _ESPN_SUMMARY_PATH.get(str(sport or "").lower())
    if path is None:
        return None
    getter = http_get if http_get is not None else _default_http_get
    url = _SUMMARY_BASE.format(path=path, eid=eid)
    try:
        payload = getter(url)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict) or not payload:
        return None
    return parse_summary(payload)


__all__ = ["final_for_event", "parse_summary"]
