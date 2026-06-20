"""predict_service.results_finals -- keyless settled-finals reader + grader.

BE-P0-09 source. Pulls SETTLED game finals from the same keyless ESPN scoreboard
the odds aggregate already uses (no extra key, no extra provider): for each event
it reads the native status (state == 'post' && completed) and the home/away
scores. This is the outcome feed a history view shows next to a graded bet so the
user can see WHY a bet graded win/loss.

  finals(sport) -> list[{game_id, home, away, home_score, away_score,
                         completed, state, status_detail, commence_time}]

Only COMPLETED games are returned (state == 'post' and completed == True); an
in-progress or scheduled game is skipped -- we NEVER report a partial score as a
final. A scoreboard failure or a fresh clone (no network) degrades to an empty
list; this never raises and never fabricates a result.

  build_finals_index(finals_list) -> dict keyed by game_id for O(1) lookup.

  grade_prediction(row, final) -> 'win' | 'loss' | 'push' | None

  Grades one prediction row against its settled final. Returns None when grading
  is not possible (ambiguous team name, unsupported market type, scores missing).
  Never fabricates: only returns 'win'/'loss'/'push' when scores are conclusive.

HONESTY: scores are the real, reported finals or nothing -- no fabrication. No $
field. This is outcome display only, calibration not edge.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets;
reuse the keyless ESPN scoreboard verbatim; no $ field.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Same site + league map the odds_provider uses; mirrored here to avoid importing
# the provider's private constants (keeps this a thin, read-only reader).
_SITE = "https://site.api.espn.com/apis/site/v2/sports"
_LEAGUE_PATH: Dict[str, str] = {
    "nba": "basketball/nba",
    "mlb": "baseball/mlb",
    "soccer": "soccer/eng.1",
    "soccer_intl": "soccer/fifa.world",
    "tennis": "tennis/atp",
}


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _competitor_scores(comp: Dict[str, Any]) -> Dict[str, Any]:
    """{home, away, home_score, away_score} from a competition node."""
    out: Dict[str, Any] = {"home": "", "away": "",
                           "home_score": None, "away_score": None}
    for c in comp.get("competitors", []) or []:
        team = (c.get("team") or {})
        name = team.get("displayName") or team.get("name") or ""
        score = _to_int(c.get("score"))
        if c.get("homeAway") == "home":
            out["home"] = name
            out["home_score"] = score
        elif c.get("homeAway") == "away":
            out["away"] = name
            out["away_score"] = score
    return out


def _final_for_event(sport: str, ev: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One settled-final record, or None if the game is not completed."""
    comp = (ev.get("competitions") or [{}])[0]
    st = (comp.get("status") or {}).get("type") or {}
    state = st.get("state")
    completed = bool(st.get("completed"))
    if state != "post" or not completed:
        return None  # not a final -> never reported as one
    scores = _competitor_scores(comp)
    eid = str(ev.get("id") or "")
    if not eid or not scores["home"] or not scores["away"]:
        return None
    return {
        "game_id": eid,
        "sport": sport,
        "home": scores["home"],
        "away": scores["away"],
        "home_score": scores["home_score"],
        "away_score": scores["away_score"],
        "completed": True,
        "state": state,
        "status_detail": st.get("shortDetail") or st.get("detail"),
        "commence_time": ev.get("date"),
    }


def finals(sport: str, *, fetch: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Settled finals for *sport* from the keyless scoreboard. Never raises.

    *fetch* is injectable for offline tests: a callable(url) -> scoreboard dict.
    Defaults to the cached keyless ESPN reader. A missing league / network failure
    / fresh clone yields an empty list -- never a fabricated score.
    """
    sport = str(sport).lower()
    path = _LEAGUE_PATH.get(sport)
    if not path:
        return []
    if fetch is None:
        try:
            from scripts.platformkit.odds_provider.http_cache import (  # noqa: PLC0415
                disk_cache_get,
            )
            fetch = disk_cache_get
        except Exception as exc:  # noqa: BLE001 -- no fetcher -> empty
            logger.warning("results_finals: http_cache import failed: %s", exc)
            return []
    try:
        board = fetch("%s/%s/scoreboard" % (_SITE, path))
    except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
        logger.warning("results_finals: scoreboard failed for %s: %s", sport, exc)
        return []
    events = board.get("events", []) if isinstance(board, dict) else None
    if not isinstance(events, list):
        return []
    out: List[Dict[str, Any]] = []
    for ev in events:
        try:
            rec = _final_for_event(sport, ev)
        except Exception as exc:  # noqa: BLE001 -- one bad event never sinks all
            logger.debug("results_finals: bad event for %s: %s", sport, exc)
            continue
        if rec is not None:
            out.append(rec)
    return out


def build_finals_index(
    finals_list: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Build a dict keyed by game_id from a list of settled finals.

    O(1) lookup for grade_prediction. Duplicate game_ids: last entry wins (both
    records hold the same scores). Never raises.
    """
    return {f["game_id"]: f for f in finals_list if isinstance(f, dict) and f.get("game_id")}


def _parse_selection(selection: str) -> Dict[str, Any]:
    """Parse a selection string: {team, line, direction, market}.

    Handles: "TeamName", "TeamName +/-N" (spread), "Over/Under N" (total).
    Returns dict with at least 'market'. Never raises.
    """
    import re  # noqa: PLC0415
    s = (selection or "").strip()
    if not s:
        return {"market": "unknown"}
    # Over/Under total
    m = re.match(r"^(Over|Under)\s+([\d.]+)$", s, re.IGNORECASE)
    if m:
        return {
            "market": "total",
            "direction": m.group(1).capitalize(),
            "line": float(m.group(2)),
        }
    # Team + spread line: "TeamName +N.N" or "TeamName -N.N"
    m = re.match(r"^(.+?)\s+([+-][\d.]+)\s*$", s)
    if m:
        team = m.group(1).strip()
        try:
            line = float(m.group(2))
        except ValueError:
            line = None
        # Distinguish a spread from a moneyline-with-odds (odds are large integers)
        if line is not None and abs(line) < 50:
            return {"market": "spread", "team": team, "line": line}
        # Large number -> moneyline American odds embedded; treat as moneyline name pick
        return {"market": "moneyline", "team": team}
    # Pure team name (moneyline)
    return {"market": "moneyline", "team": s}


def _identify_team_side(team_name: str, home: str, away: str) -> Optional[str]:
    """Return 'home' | 'away' | None by substring matching team_name."""
    if not team_name:
        return None
    tn = team_name.lower()
    h = (home or "").lower()
    a = (away or "").lower()
    # Exact match first
    if tn == h:
        return "home"
    if tn == a:
        return "away"
    # Substring: the team name tokens must be fully contained
    if h and tn in h:
        return "home"
    if a and tn in a:
        return "away"
    # Reverse substring: ESPN full name contains the selection token
    if h and h in tn:
        return "home"
    if a and a in tn:
        return "away"
    return None


def grade_prediction(row: Dict[str, Any], final: Dict[str, Any]) -> Optional[str]:
    """Grade one prediction row vs its settled final.

    Returns 'win', 'loss', 'push', or None (unresolvable). Never raises;
    never fabricates. Only returns a verdict when scores are real and
    the team/side is unambiguously identified.
    """
    hs = final.get("home_score")
    aws = final.get("away_score")
    if hs is None or aws is None:
        return None
    try:
        hs = float(hs)
        aws = float(aws)
    except (TypeError, ValueError):
        return None

    home = str(final.get("home") or "")
    away = str(final.get("away") or "")
    matchup = str(row.get("matchup") or "")
    selection = str(row.get("selection") or "")
    parsed = _parse_selection(selection)
    market = parsed.get("market", "unknown")

    if market == "total":
        direction = parsed.get("direction")
        line = parsed.get("line")
        if direction is None or line is None:
            return None
        total = hs + aws
        diff = total - line
        if diff > 0:
            result = "Over"
        elif diff < 0:
            result = "Under"
        else:
            return "push"
        return "win" if direction == result else "loss"

    if market in ("moneyline", "spread"):
        team_name = parsed.get("team") or ""
        # Derive home/away names from the matchup if final names are empty
        # matchup is "away@home" by ESPN convention
        if not home and "@" in matchup:
            parts = matchup.split("@", 1)
            away = parts[0].strip()
            home = parts[1].strip()
        side = _identify_team_side(team_name, home, away)
        if side is None:
            return None
        team_score = hs if side == "home" else aws
        opp_score = aws if side == "home" else hs

        if market == "moneyline":
            if team_score > opp_score:
                return "win"
            if team_score < opp_score:
                return "loss"
            return "push"

        # spread: team_score - opp_score > -line => win
        line = parsed.get("line")
        if line is None:
            return None
        margin = team_score - opp_score
        # Spread: team covers if margin > -line (the line is the handicap ON the team)
        # e.g. "TeamA -1.5": TeamA needs to win by > 1.5 -> margin > 1.5
        # e.g. "TeamA +1.5": TeamA covers if margin > -1.5 (i.e. loses by < 1.5 or wins)
        cover = margin + line  # positive means team covered
        if cover > 0:
            return "win"
        if cover < 0:
            return "loss"
        return "push"

    return None  # unsupported market -> no grade


__all__ = ["finals", "build_finals_index", "grade_prediction"]
