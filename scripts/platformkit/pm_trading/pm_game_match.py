"""scripts.platformkit.pm_trading.pm_game_match -- Kalshi-row grouping + Kalshi<->model
game PAIRING for pm_game_placer (LOC-rail split: placer was 314 lines, over the 300 cap).

RESOLVER-AUTHORITATIVE ID JOIN (rail): identifying WHICH model game a Kalshi row belongs
to must not rest on team-name substring alone when a real ID resolver exists for the
sport. MLB tickers (KXMLBGAME-<date><time><AWAY+HOME abbrev>) resolve via the SAME
ticker-abbrev join the in-game dryrun seam uses -- ingame_id_resolver_mlb.resolve_ticker --
never a guessed substring pairing. A ticker that does not even PARSE as a real MLB game
ticket (e.g. this module's own pre-resolver test fixtures) carries no positive resolver
info, so it degrades to the existing date-gated substring matcher (honest 'no info', same
degrade-on-absence philosophy as pm_game_date_guard's date guard); a ticket that DOES parse
but resolves to 0 or 2+ candidates is an AUTHORITATIVE ambiguity -- honest skip, never a
substring fallback afterward. Sports with no resolver (soccer_intl -- no abbrev-blob
ticket) always take the substring path; run() reports which route a sport used via the
`matcher` field (route_for()) so the fallback is explicit, never silent.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/pm_trading/test_pm_game_placer.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.odds_provider.kalshi_series_spec import ticker_game_date
from scripts.platformkit.pm_trading.pm_game_date_guard import (
    _date_filtered, _match_hits, _norm, _roles_for_candidates,
)

_TIE_TOKENS = frozenset({"tie", "draw"})

# Sports with a real Kalshi-ticker-abbrev ID resolver (route through it, never substring).
# Absent sport -> the existing date-gated substring matcher is the only option.
_RESOLVER_SPORTS = frozenset({"mlb"})


def route_for(sport: Any) -> str:
    """'resolver' or 'substring' -- which game-identity path *sport* uses. Surfaced in
    pm_game_placer.run()'s per-sport stats so the fallback is explicit, never silent."""
    return "resolver" if str(sport or "") in _RESOLVER_SPORTS else "substring"


def group_by_game(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """fetch_inplay rows -> {game_id: {'sides': {side_name: (prob, ticker)}, 'venue': v}}.
    Keeps the most recent prob per side; ignores rows missing a game_id/side/prob.

    MARKET_TYPE FILTER (binding): inplay_kalshi.fetch_inplay now ALSO returns total/spread/
    team_total rows -- their "prob" is P(over line) / P(covers), never a team win-prob, and
    their "side" is not a team name. This placer devigs {side: prob} pairs as a two/three-way
    MONEYLINE book (placements_from_game), so a non-moneyline row must never enter the group
    -- it would either fail team-name matching (harmless) or, worse, silently pollute a game's
    side set. Filtered to market_type=="moneyline"; a row missing market_type (older cached
    shape / non-Kalshi venue) is treated as moneyline for back-compat.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        mt = r.get("market_type")
        if mt is not None and str(mt) != "moneyline":
            continue
        gid = str(r.get("game_id") or "").strip()
        side = str(r.get("side") or "").strip()
        prob = None
        try:
            prob = float(r.get("prob"))
        except (TypeError, ValueError):
            prob = None
        if not gid or not side or prob is None or not (0.0 < prob < 1.0):
            continue
        g = out.setdefault(gid, {"sides": {}, "venue": str(r.get("venue") or "kalshi"),
                                  # PHANTOM-MATCHUP FIX: the scheduled date embedded in the
                                  # Kalshi event ticker itself (gid IS the event_ticker) --
                                  # None when unparseable (degrades to no date filtering,
                                  # never a false-positive reject; see match_model_game).
                                  "date": ticker_game_date(gid)})
        g["sides"][side] = (prob, str(r.get("ticker") or ""))
    return out


def _split_sides(sides: Dict[str, Any]) -> Tuple[List[str], Optional[float]]:
    """Return (team_side_names, tie_prob). Tie/draw side is pulled out of the field."""
    teams: List[str] = []
    tie_prob: Optional[float] = None
    for name, (prob, _t) in sides.items():
        if _norm(name) in _TIE_TOKENS:
            tie_prob = prob
        else:
            teams.append(name)
    return teams, tie_prob


def _resolve_mlb_game(ticker: Any, model_games: Sequence[Dict[str, Any]]
                      ) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """(parsed, game). parsed=False -- *ticker* is not a real Kalshi MLB game ticket, no
    positive resolver info (caller degrades to substring). parsed=True, game=None -- a real
    ticket that the resolver could NOT uniquely bind against *model_games* (0 or 2+
    candidates); authoritative ambiguity, honest skip, never substring afterward.
    parsed=True, game=<dict> -- the UNIQUE model_games entry the ticker's away+home abbrev
    blob resolves to. CALLER MUST pass an already kalshi_date-filtered *model_games* (see
    match_hits) -- the abbrev blob alone identifies the TEAMS, never WHICH date's game; an
    MLB series (same two teams, adjacent dates) would otherwise single-hit bind to whichever
    date happens to be on the board."""
    from scripts.platformkit.ingame import ingame_id_resolver_mlb as _resolver
    if _resolver.parse_kalshi_mlb_ticker(ticker) is None:
        return False, None
    resolved = _resolver.resolve_ticker(ticker, candidates=list(model_games))
    if resolved is None:
        return True, None
    home, away = resolved.get("home"), resolved.get("away")
    game = next((g for g in model_games
                 if g.get("home") == home and g.get("away") == away), None)
    return True, game


def match_hits(team_sides: Sequence[str], model_games: Sequence[Dict[str, Any]], *,
              kalshi_date: Optional[Any] = None, ticker: Optional[str] = None,
              sport: Optional[str] = None) -> List[Dict[str, Any]]:
    """Every model-game candidate for one Kalshi game's two team sides. Routes through the
    authoritative resolver when *sport* has one and *ticker* parses as a real ticket for it
    (currently mlb); otherwise the date-gated substring matcher in pm_game_date_guard (see
    module docstring for the fallback rules).

    DATE GATE (binding, R1 blocker fix): the resolver identifies WHICH TEAMS a ticker is
    for; it does NOT know WHICH DATE's game that is (an MLB series plays the same two teams
    on adjacent dates). *model_games* is therefore restricted to *kalshi_date* candidates
    (_date_filtered, the SAME gate the substring path uses) BEFORE the resolver runs, so a
    0-or-2+-candidate result after that restriction is an honest skip, never a bind to a
    same-teams game on the wrong date."""
    if len(team_sides) != 2:
        return []
    if sport in _RESOLVER_SPORTS and ticker:
        parsed, hit = _resolve_mlb_game(ticker, _date_filtered(model_games, kalshi_date))
        if parsed:
            return _roles_for_candidates(team_sides, [hit]) if hit is not None else []
    return _match_hits(team_sides, model_games, kalshi_date=kalshi_date)


def match_model_game(team_sides: Sequence[str], model_games: Sequence[Dict[str, Any]],
                     *, kalshi_date: Optional[Any] = None, ticker: Optional[str] = None,
                     sport: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Find the model game whose {home,away} uniquely map to the two Kalshi team sides.
    Returns the model rec with an added side->role map, or None on 0 or 2+ candidates
    (unique-hit-only; ambiguity is an honest skip, never a guessed pairing)."""
    hits = match_hits(team_sides, model_games, kalshi_date=kalshi_date, ticker=ticker,
                      sport=sport)
    return hits[0] if len(hits) == 1 else None


__all__ = ["group_by_game", "match_hits", "match_model_game", "route_for"]
