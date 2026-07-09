"""edge_engine -- ESPN injuries feed -> structured availability fact rows (rule-based, no LLM).

ESPN's public injuries endpoint is ALREADY structured (status / athlete / team / date per row),
so extracting it needs ZERO NLP -- that is the whole point: the market reads the same feed, but
we normalize and stamp it for the vintage-guarded pipeline. No LLM, no secret, no network in tests.

  GET https://site.api.espn.com/apis/site/v2/sports/<path>/injuries
  payload.injuries[]                       -> one entry per TEAM (id, displayName, injuries[])
    .injuries[]                            -> one entry per PLAYER injury:
       status ("Out"/"Day-To-Day"/"10-Day-IL"/...), date (ISO), shortComment/longComment,
       athlete.displayName, athlete.links[].href, type.abbreviation

Fact row (append-only JSONL, dedupe key = player_name|status|report_date):
  {sport, source, fetched_at, player_name, team, status, detail, report_date, source_url}

Stdlib only. <=300 LOC. Per-file test: test_injury_facts.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:  # package import
    from scripts.platformkit.edge_engine.facts_store import (  # type: ignore
        HttpGet, append_new, http_json, path_for, utc_now_iso,
    )
except ImportError:  # direct-script / per-file-test fallback
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.platformkit.edge_engine.facts_store import (  # type: ignore
        HttpGet, append_new, http_json, path_for, utc_now_iso,
    )

_SOURCE = "espn_injuries"
_BASE = "https://site.api.espn.com/apis/site/v2/sports/{path}/injuries"

# platform sport -> ESPN url path. Wired sports only; add a row to extend.
_SPORT_PATHS: Dict[str, str] = {
    "nba": "basketball/nba",
    "mlb": "baseball/mlb",
    "wnba": "basketball/wnba",
}

# Explicit normalizations; anything else falls through to the token transform in _norm_status.
_STATUS_MAP: Dict[str, str] = {
    "DAY-TO-DAY": "DAY_TO_DAY",
    "GAME-TIME-DECISION": "GTD",
    "GTD": "GTD",
}


def _norm_status(raw: Optional[str]) -> str:
    """ESPN status string -> a stable enum-ish token.

    IL variants ("10-Day-IL", "60-Day-IL") collapse to OUT (unavailable). Known phrases map
    explicitly; the fallback upper-cases and underscores so an unseen status is still legible.
    ponytail: heuristic map -- extend _STATUS_MAP when a genuinely new status appears.
    """
    s = (raw or "").strip().upper().replace(" ", "-")
    if not s:
        return "UNKNOWN"
    if s.endswith("-IL") or s == "IL":
        return "OUT"
    return _STATUS_MAP.get(s, s.replace("-", "_"))


def _athlete_url(athlete: Dict[str, Any]) -> str:
    for link in athlete.get("links", []) or []:
        href = link.get("href")
        if href:
            return str(href)
    return ""


def rows_from_payload(payload: Dict[str, Any], sport: str,
                      fetched_at: Optional[str] = None) -> List[Dict[str, Any]]:
    """Parse an ESPN injuries payload into fact rows. Pure -- no network, used by the test."""
    fetched_at = fetched_at or utc_now_iso()
    rows: List[Dict[str, Any]] = []
    for team in payload.get("injuries", []) or []:
        team_name = str(team.get("displayName", "") or "")
        for item in team.get("injuries", []) or []:
            athlete = item.get("athlete", {}) or {}
            player = str(athlete.get("displayName", "") or "")
            if not player:
                continue
            date = str(item.get("date", "") or "")
            rows.append({
                "sport": sport,
                "source": _SOURCE,
                "fetched_at": fetched_at,
                "player_name": player,
                "team": team_name,
                "status": _norm_status(item.get("status")),
                "detail": str(item.get("shortComment") or item.get("longComment") or ""),
                "report_date": date[:10],
                "source_url": _athlete_url(athlete),
            })
    return rows


def _dedupe_key(r: Dict[str, Any]) -> Tuple[str, str, str]:
    return (r["player_name"], r["status"], r["report_date"])


def fetch_injuries(sport: str, http_get: Optional[HttpGet] = None) -> List[Dict[str, Any]]:
    """Fetch + normalize the ESPN injuries feed for one sport. http_get injectable for tests."""
    if sport not in _SPORT_PATHS:
        raise ValueError(f"injuries not wired for sport {sport!r}; wired={list(_SPORT_PATHS)}")
    get = http_get or http_json
    payload = get(_BASE.format(path=_SPORT_PATHS[sport]))
    return rows_from_payload(payload, sport)


def store_injuries(sport: str, http_get: Optional[HttpGet] = None,
                   *, snapshot_date: Optional[str] = None) -> Tuple[int, int]:
    """Fetch, then append only new rows. Returns (n_fetched, n_added). Idempotent on re-run.

    When *snapshot_date* (YYYY-MM-DD) is given, stamp it on every row and fold it into
    the dedupe key -- so the SAME injury re-captured on a NEW day is a fresh AS-OF row
    (vintage-guarded history) while a same-day re-run still adds 0. Absent snapshot_date
    keeps the original flat behavior (dedupe on player|status|report_date)."""
    rows = fetch_injuries(sport, http_get=http_get)
    if snapshot_date:
        for r in rows:
            r["snapshot_date"] = snapshot_date
        # .get() not r[...]: legacy rows written before snapshot_date existed
        # (e.g. injury_facts_nba.jsonl pre-M39) must not KeyError the dedupe scan.
        keyfn = lambda r: (r["player_name"], r["status"], r.get("snapshot_date", ""))  # noqa: E731
    else:
        keyfn = _dedupe_key
    added = append_new(path_for("injury", sport), rows, keyfn)
    return len(rows), added


WIRED_SPORTS: Tuple[str, ...] = tuple(_SPORT_PATHS)
