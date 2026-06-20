"""slate_dead_market_filter -- drop dead/stale markets from the :8098 slate payload.

QA-ISSUE-1 (the :8098 board): a soccer_intl slate game (game_id=558934, a
Polymarket binary contract home='Yes' / away='No', tipoff ~11 months past,
market_prob ~0.0005) was served with ev=683.2 -- a fabricated-edge magnitude
against a RESOLVED/dead market. The :8099 bestbets board already gates this via
scripts.platformkit.bestbets.board_sanitizer; the :8098 slate builder had NO
such gate. This module applies the SAME criteria to the slate path.

It does NOT duplicate the drop logic: it adapts a slate "game" (nested
markets/edges) to the flat card shape board_sanitizer understands and reuses
board_sanitizer._should_drop. A game is dropped when it is a binary 'Yes/No'
contract, its tipoff is in the past, or its market_prob is dead/degenerate.
Within a surviving game, individual dead/stale EDGE rows are also scrubbed so an
EV is NEVER emitted against a resolved market.

RAILS:
  - Pure: no network, no global state; reads the wall clock only for the
    stale-tipoff check (a UTC `now` is injectable for deterministic tests).
  - Returns a NEW payload; never mutates the input dict / nested lists.
  - ASCII only; <= 300 LOC; no $ / ROI / PnL field added.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from scripts.platformkit.bestbets import board_sanitizer as _bs


def _game_as_card(game: Dict[str, Any]) -> Dict[str, Any]:
    """Adapt a slate game to the flat card shape board_sanitizer understands.

    matchup is rendered "<away> vs <home>" so a Polymarket binary game
    (home='Yes', away='No') matches the 'yes vs no' / 'no vs yes' token. Only
    GAME-level signals (binary matchup + stale tipoff) are carried here; per-EDGE
    dead/degenerate market_prob is handled by the edge scrub so one junk edge
    cannot sink a game that also carries a legitimate market.
    """
    home = str(game.get("home") or "")
    away = str(game.get("away") or "")
    return {
        "matchup": "%s vs %s" % (away, home),
        "tipoff": game.get("tipoff"),
        "game_datetime": game.get("tipoff"),
        "market_prob": None,
        "edge_vs_market": None,
        "best_odds": None,
    }


def _edge_is_dead(edge: Dict[str, Any], now: datetime) -> bool:
    """A single edge row is dead when its market_prob is at/below the dead floor.

    Reuses board_sanitizer thresholds so an EV is never emitted against a
    resolved/degenerate market even inside an otherwise-live game.
    """
    if not isinstance(edge, dict):
        return True
    mp = edge.get("market_prob")
    return _bs._market_dead(mp) or _bs._market_prob_degenerate(mp)


def _binary_yes_no(home: str, away: str) -> bool:
    """True when the game is a Polymarket-style Yes/No binary (either ordering)."""
    pair = {home.strip().lower(), away.strip().lower()}
    return pair == {"yes", "no"}


def sanitize_slate(
    payload: Dict[str, Any],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return a NEW slate payload with dead/stale-market games + edges removed.

    Drop a GAME when board_sanitizer._should_drop fires on its card view OR it is
    an explicit Yes/No binary contract. Within a surviving game, scrub any edge
    whose market_prob is dead/degenerate. Non-dict payloads / missing 'games'
    pass through unchanged (defensive; never raises).
    """
    if not isinstance(payload, dict):
        return payload
    games = payload.get("games")
    if not isinstance(games, list):
        return payload
    if now is None:
        now = datetime.now(tz=timezone.utc)

    kept: List[Dict[str, Any]] = []
    n_dropped = 0
    for game in games:
        if not isinstance(game, dict):
            n_dropped += 1
            continue
        home = str(game.get("home") or "")
        away = str(game.get("away") or "")
        card = _game_as_card(game)
        # GAME-level drop: explicit Yes/No binary, or matchup token, or stale tipoff.
        if (_binary_yes_no(home, away)
                or _bs._is_non_sports_binary(card["matchup"])
                or _bs._tipoff_in_past(card, now=now)):
            n_dropped += 1
            continue
        # Surviving game: scrub dead/degenerate individual edges.
        edges = game.get("edges")
        if isinstance(edges, list):
            clean_edges = [e for e in edges if not _edge_is_dead(e, now)]
            if len(clean_edges) != len(edges):
                game = dict(game)
                game["edges"] = clean_edges
        kept.append(game)

    out = dict(payload)
    out["games"] = kept
    if n_dropped:
        out["dead_market_dropped"] = n_dropped
    return out


__all__ = ["sanitize_slate"]
