"""Per-file tests for inplay_status -- the live in-play engine read-out.

Offline: synthetic heartbeat dicts (no daemon, no network). Proves the read-out
honestly separates "bet the live game" from the reasons a game was skipped, and that
a slate of all-future markets renders as "live slate empty", not a failure.

  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/ingame/test_inplay_status.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame import inplay_status as S


def _hb(games, **kw):
    base = {"as_of": "2026-06-30T15:00:00Z", "sports": ["soccer_intl"],
            "n_pairs": sum(1 for g in games if g.get("paired")),
            "n_bets": sum(1 for g in games if g.get("bet")), "games": games}
    base.update(kw)
    return base


def test_one_live_bet_amongst_future_markets():
    # The real WC shape: 1 live game bet + many future Kalshi markets correctly skipped.
    games = [
        {"sport": "soccer_intl", "game_id": "KXWCGAME-CIVNOR", "paired": True,
         "bet": True, "action": "bet", "tier": "C", "model_prob": 0.58,
         "devigged_price": 0.55, "reason": "ok"},
    ] + [
        {"sport": "soccer_intl", "game_id": "KXWCGAME-FUT%d" % i, "paired": False,
         "bet": False, "reason": "no_live_state"} for i in range(12)
    ]
    s = S.summarize(_hb(games))
    assert s["n_games_on_book"] == 13
    assert s["n_bets"] == 1
    assert len(s["bets"]) == 1 and s["bets"][0]["game_id"] == "KXWCGAME-CIVNOR"
    # the 12 future markets are categorized as "not live yet", NOT as an error
    assert s["by_category"]["not live yet (future/pregame on book)"] == 12
    assert s["edge_claimed"] is False and s["executed"] is False


def test_live_no_edge_is_not_a_bet():
    # A live, priced game whose model does not beat the floor is HONESTLY "no edge", not bet.
    games = [{"sport": "soccer_intl", "game_id": "KXWCGAME-X", "paired": True,
              "bet": False, "action": "no_bet", "reason": "below_floor"}]
    s = S.summarize(_hb(games))
    assert s["n_bets"] == 0
    assert "live, priced -- no edge past floor" in s["by_category"]


def test_empty_slate_renders_without_crash():
    s = S.summarize(_hb([]))
    txt = S.render(s)
    assert "BETS PLACED=0" in txt
    assert "live slate is empty" in txt.lower() or "NO bets this tick" in txt


def test_render_shows_the_live_bet():
    games = [{"sport": "soccer_intl", "game_id": "KXWCGAME-CIVNOR", "paired": True,
              "bet": True, "action": "bet", "tier": "C", "model_prob": 0.58,
              "devigged_price": 0.55, "reason": "ok"}]
    txt = S.render(S.summarize(_hb(games)))
    assert "BETS PLACED on live games" in txt
    assert "KXWCGAME-CIVNOR" in txt and "tier=C" in txt
    # UNITS only -- no dollar AMOUNT in the read-out (the "no $" disclaimer prose is fine).
    import re
    assert not re.search(r"\$\s*\d", txt)
