"""scripts.platformkit.pm_trading.pm_game_date_guard -- team-name matching + the
phantom-matchup date guard for pm_game_placer, split out (LOC-rail: placer was
already 346 lines, over the 300 cap) to keep pm_game_placer.py under it. Pure
move/addition, no behavior change to the pre-existing team-matching pieces.

PHANTOM-MATCHUP GUARD: pm_game_placer._model_games() previously returned games
with NO date field, and match_model_game() paired Kalshi sides to a model game
by loose substring team-name matching ALONE -- so a Kalshi ticker for one
calendar date could pair to a model game on a DIFFERENT date whenever the two
games' team names happened to substring-collide (10 paper_pm ledger rows record
exactly this). match_hits() below requires the model game's own date_candidates
(derived from its tipoff) to contain the Kalshi ticker's parsed date BEFORE
team-name matching runs, and returns ALL matches so the caller can honestly skip
0-or-2+-candidate ambiguity instead of silently taking the first hit.

EXACT-DATE TIGHTENING: _et_date_candidates() used to hedge {UTC calendar date, UTC date
- 1 day} as BOTH acceptable targets. Any two games one calendar day apart -- an MLB
SERIES! -- always have overlapping hedge windows regardless of actual game time, so if
the correct-date game was simply absent from the model board, the adjacent-date same-
teams game could single-hit bind on the wrong date. It now derives the ONE exact US-
Eastern calendar date via the already-shared, zoneinfo-exact et_day helper (reused, not
reinvented -- same module paper_today/bankroll/pnl_series already trust for this exact
UTC->ET conversion) and returns it as a 0/1-element frozenset, so match_hits' existing
containment check becomes an exact match with no code change needed there.

Per-file test (covered via the importer's own suite):
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/pm_trading/test_pm_game_placer.py -q
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

# National-team naming differs Kalshi vs model/ESPN (e.g. "Korea Republic" vs "South Korea").
# Each variant -> a UNIQUE code so two known countries match ONLY when the same nation (never
# cross-match by substring, e.g. Congo vs DR Congo). Keys are _norm()'d (lower alphanumeric).
_COUNTRY_ALIASES: Dict[str, str] = {
    "southkorea": "kr", "korearepublic": "kr", "korea": "kr", "republicofkorea": "kr",
    "northkorea": "kp", "koreadpr": "kp", "dprkorea": "kp", "usa": "us", "us": "us",
    "unitedstates": "us", "unitedstatesofamerica": "us", "iran": "ir", "iriran": "ir",
    "islamicrepublicofiran": "ir", "turkey": "tr", "turkiye": "tr", "czechia": "cz",
    "czechrepublic": "cz", "bosnia": "ba", "bosniaherzegovina": "ba", "china": "cn",
    "bosniaandherzegovina": "ba", "congodr": "cd", "drcongo": "cd", "drcgo": "cd",
    "democraticrepublicofcongo": "cd", "congo": "cg", "congorepublic": "cg", "chinapr": "cn",
    "republicofthecongo": "cg", "ivorycoast": "ci", "cotedivoire": "ci",
    "capeverde": "cv", "caboverde": "cv",
}


def _norm(s: Any) -> str:
    """Lowercase alphanumeric token (drops spaces/punct) for loose team matching."""
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _name_matches(a: str, b: str) -> bool:
    """Loose team match. When BOTH names are known national teams, require the SAME nation
    (exact canonical code) so 'South Korea' == 'Korea Republic' but Congo != DR Congo.
    Otherwise fall back to substring so Kalshi city sides ('Toronto') still bridge to model
    full names ('Toronto Blue Jays')."""
    na, nb = _norm(a), _norm(b)
    ca, cb = _COUNTRY_ALIASES.get(na), _COUNTRY_ALIASES.get(nb)
    if ca is not None and cb is not None:
        return ca == cb
    if len(na) < 3 or len(nb) < 3:
        return na == nb and bool(na)
    return na in nb or nb in na


def _et_date_candidates(tipoff: Any) -> frozenset:
    """The model game's single EXACT US-Eastern calendar date *tipoff* (ISO-8601, any
    offset/naive-as-UTC, or a bare date) falls on -- Kalshi's game tickers are ET-dated.
    Returned as a 0/1-element frozenset (see module docstring: EXACT-DATE TIGHTENING).
    Empty (honest 'no info', the date guard then degrades to a no-op instead of a false-
    positive reject) when *tipoff* is missing/unparseable."""
    from scripts.platformkit.paper.et_day import et_day_of
    s = str(tipoff or "").strip()
    if not s:
        return frozenset()
    try:
        return frozenset({date.fromisoformat(et_day_of(s))})
    except ValueError:
        return frozenset()


def _roles_for_candidates(team_sides: Sequence[str], candidates: Sequence[Dict[str, Any]]
                          ) -> List[Dict[str, Any]]:
    """Every *candidate* whose {home,away} map 1:1 onto the two *team_sides* by loose
    substring team-name matching. Shared by _match_hits (date-gated substring path) and
    pm_game_match's resolver path (a single already-identified candidate -> role labels
    only, so this never re-decides WHICH game, only who is home/away within it)."""
    hits: List[Dict[str, Any]] = []
    for g in candidates:
        home, away = str(g.get("home") or ""), str(g.get("away") or "")
        roles: Dict[str, str] = {}
        for side in team_sides:
            if _name_matches(side, home) and not _name_matches(side, away):
                roles[side] = "home"
            elif _name_matches(side, away) and not _name_matches(side, home):
                roles[side] = "away"
        if set(roles.values()) == {"home", "away"}:
            out = dict(g)
            out["_roles"] = roles
            hits.append(out)
    return hits


def _match_hits(team_sides: Sequence[str], model_games: Sequence[Dict[str, Any]],
               *, kalshi_date: Optional[date] = None) -> List[Dict[str, Any]]:
    """Every model game whose {home,away} map to the two Kalshi team sides.

    When *kalshi_date* is known, a model game is only a candidate if *kalshi_date* is one
    of ITS OWN date_candidates (from _et_date_candidates) -- so loose team-name substring
    matching (by design, city vs full name) can never bridge two DIFFERENT dates' games.
    kalshi_date absent, or a candidate with no date_candidates of its own, degrades to no
    date filtering for that side (honest 'no info', never a false-positive reject)."""
    if len(team_sides) != 2:
        return []
    candidates = model_games
    if kalshi_date is not None:
        candidates = [g for g in model_games
                      if not (g.get("date_candidates")) or kalshi_date in g["date_candidates"]]
    return _roles_for_candidates(team_sides, candidates)


__all__ = ["_norm", "_name_matches", "_et_date_candidates", "_match_hits", "_roles_for_candidates"]
