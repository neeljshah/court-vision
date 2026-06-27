"""Tests for ingame_prop_trader -- the in-game player-prop paper trader.

Fully offline: live games, boxscore, prop prices and the pregame distribution are all
injected, so we pin the reprice->devig->edge->tier->record pipeline + idempotency + the
no-fabrication skips without any network. Uses the REAL repricer / devig / policy so the
gate matches production (no parallel math).
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.bestbets.prop_settler_mlb import _norm
from scripts.platformkit.ingame import ingame_prop_trader as T


class _Prop:
    def __init__(self, player, stat, line, over_price, under_price, source="draftkings"):
        self.player, self.stat, self.line = player, stat, line
        self.over_price, self.under_price, self.source = over_price, under_price, source


def _provider(props):
    class _P:
        def fetch_props(self, sport):
            return props
    return _P()


def _live_one():
    return [{"game_pk": "777", "home": "New York Mets", "away": "Chicago Cubs",
             "frac_elapsed": 0.5, "state": "In Progress"}]


def _box_with(player, batting):
    smap = {_norm(player): (batting, {})}
    return lambda pk: smap


def _dist(player, stat, lam, model="poisson"):
    return {(_norm(player), stat): (lam, model)}


def test_places_a_clear_ingame_prop_edge(tmp_path):
    ledger = tmp_path / "clv.jsonl"
    # Pete Alonso already has 1 hit; line 1.5; pregame lam 1.6; half the game gone.
    # reprice P(>1.5) ~= 0.55; DK over 2.5 / under 1.5 devigs fair_over ~0.375 -> edge ~0.18.
    props = [_Prop("Pete Alonso", "Hits", 1.5, 2.5, 1.5)]
    out = T.run("mlb", ledger_path=ledger, prop_provider=_provider(props),
                dist=_dist("Pete Alonso", "Hits", 1.6),
                live_games_fn=_live_one,
                box_fn=_box_with("Pete Alonso", {"hits": 1}), min_tier="C")
    assert out["status"] == "ok"
    assert out["placed"] == 1, out
    rows = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
    r = rows[0]
    assert r["channel"] == "paper_ingame_prop" and r["market_type"] == "prop"
    assert r["prop_player"] == "Pete Alonso" and r["prop_stat"] == "Hits"
    assert r["prop_side"] == "over" and r["ingame"] is True
    assert r["realized_so_far"] == 1.0 and 0.0 < r["model_prob"] < 1.0
    assert r["executed"] is False and r["edge_claimed"] is False
    assert r["edge"] > 0.0


def test_vig_gate_skips_when_edge_below_vig(tmp_path, monkeypatch):
    # SAME prop that places at the default gate (edge ~0.18, vig ~0.067). Raise the
    # vig-edge multiplier so the required margin (5 * 0.067 = 0.33) exceeds the edge:
    # the juice-eater is now skipped -- the in-game-prop CLV-bleed fix.
    monkeypatch.setattr(T, "_VIG_EDGE_MULT", 5.0)
    ledger = tmp_path / "clv.jsonl"
    props = [_Prop("Pete Alonso", "Hits", 1.5, 2.5, 1.5)]
    out = T.run("mlb", ledger_path=ledger, prop_provider=_provider(props),
                dist=_dist("Pete Alonso", "Hits", 1.6), live_games_fn=_live_one,
                box_fn=_box_with("Pete Alonso", {"hits": 1}), min_tier="C")
    assert out["status"] == "ok"
    assert out["placed"] == 0, out          # edge does not clear the (scaled) vig
    assert not ledger.exists() or not ledger.read_text().strip()


def test_vig_gate_skips_market_wider_than_max_vig(tmp_path, monkeypatch):
    # SAME placing prop, but clamp _MAX_VIG below this two-way's hold (~0.067): a market
    # this wide is too uncertain to trust -> skip regardless of edge.
    monkeypatch.setattr(T, "_MAX_VIG", 0.01)
    ledger = tmp_path / "clv.jsonl"
    props = [_Prop("Pete Alonso", "Hits", 1.5, 2.5, 1.5)]
    out = T.run("mlb", ledger_path=ledger, prop_provider=_provider(props),
                dist=_dist("Pete Alonso", "Hits", 1.6), live_games_fn=_live_one,
                box_fn=_box_with("Pete Alonso", {"hits": 1}), min_tier="C")
    assert out["status"] == "ok"
    assert out["placed"] == 0, out          # market too wide -> skipped
    assert not ledger.exists() or not ledger.read_text().strip()


def test_idempotent_no_double_place(tmp_path):
    ledger = tmp_path / "clv.jsonl"
    props = [_Prop("Pete Alonso", "Hits", 1.5, 2.5, 1.5)]
    kw = dict(ledger_path=ledger, prop_provider=_provider(props),
              dist=_dist("Pete Alonso", "Hits", 1.6), live_games_fn=_live_one,
              box_fn=_box_with("Pete Alonso", {"hits": 1}), min_tier="C")
    assert T.run("mlb", **kw)["placed"] == 1
    assert T.run("mlb", **kw)["placed"] == 0  # same position -> not re-recorded
    rows = [l for l in ledger.read_text().splitlines() if l.strip()]
    assert len(rows) == 1


def test_skips_player_not_in_a_live_game(tmp_path):
    ledger = tmp_path / "clv.jsonl"
    props = [_Prop("Ghost Player", "Hits", 1.5, 2.5, 1.5)]
    out = T.run("mlb", ledger_path=ledger, prop_provider=_provider(props),
                dist=_dist("Ghost Player", "Hits", 1.6), live_games_fn=_live_one,
                box_fn=_box_with("Pete Alonso", {"hits": 1}), min_tier="C")
    assert out["placed"] == 0


def test_skips_unknown_stat_and_missing_dist(tmp_path):
    ledger = tmp_path / "clv.jsonl"
    # unknown stat (no boxscore field) + a prop with no pregame distribution
    props = [_Prop("Pete Alonso", "Anytime Touchdown", 0.5, 2.0, 1.8),
             _Prop("Pete Alonso", "Hits", 1.5, 2.5, 1.5)]
    out = T.run("mlb", ledger_path=ledger, prop_provider=_provider(props),
                dist={}, live_games_fn=_live_one,
                box_fn=_box_with("Pete Alonso", {"hits": 1}), min_tier="C")
    assert out["placed"] == 0


def test_no_live_games_places_nothing(tmp_path):
    ledger = tmp_path / "clv.jsonl"
    out = T.run("mlb", ledger_path=ledger, prop_provider=_provider([]),
                dist={}, live_games_fn=lambda: [], box_fn=lambda pk: {})
    assert out["placed"] == 0 and out["reason"] == "no live games"


def test_frac_outside_band_skips(tmp_path):
    ledger = tmp_path / "clv.jsonl"
    late = [{"game_pk": "777", "home": "NYM", "away": "CHC", "frac_elapsed": 0.97}]
    props = [_Prop("Pete Alonso", "Hits", 1.5, 2.5, 1.5)]
    out = T.run("mlb", ledger_path=ledger, prop_provider=_provider(props),
                dist=_dist("Pete Alonso", "Hits", 1.6), live_games_fn=lambda: late,
                box_fn=_box_with("Pete Alonso", {"hits": 1}), min_tier="C")
    assert out["placed"] == 0


def test_unmapped_sport_is_unsupported(tmp_path):
    out = T.run("nba", ledger_path=tmp_path / "x.jsonl")
    assert out["status"] == "unsupported" and out["placed"] == 0


# --- soccer / World Cup path (keyless ESPN keyEvents realized state) -------------
def _soccer_live():
    return [{"game_pk": "900001", "home": "Brazil", "away": "Scotland",
             "frac_elapsed": 0.4, "state": "in"}]


def _soccer_box(player, goals=0.0, assists=0.0, cards=0.0):
    smap = {_norm(player): {"Goals": float(goals), "Assists": float(assists),
                            "Cards": float(cards)}}
    return lambda pk: smap


def test_soccer_places_a_goals_edge(tmp_path):
    ledger = tmp_path / "clv.jsonl"
    # Vinicius o0.5 Goals; pregame lam 1.2; 40% gone, 0 so far -> reprice ~0.51;
    # DK over 2.6 / under 1.55 devigs fair_over ~0.37 -> over edge ~0.14.
    props = [_Prop("Vinicius Junior", "Goals", 0.5, 2.6, 1.55, source="underdog")]
    out = T.run("soccer_intl", ledger_path=ledger, prop_provider=_provider(props),
                dist=_dist("Vinicius Junior", "Goals", 1.2),
                live_games_fn=_soccer_live, box_fn=_soccer_box("Vinicius Junior"),
                min_tier="C")
    assert out["status"] == "ok" and out["placed"] == 1, out
    r = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()][0]
    assert r["sport"] == "soccer_intl" and r["channel"] == "paper_ingame_prop"
    assert r["market_type"] == "prop" and r["prop_stat"] == "Goals"
    assert r["prop_side"] == "over" and r["edge"] > 0.0
    assert r["executed"] is False and r["edge_claimed"] is False


def test_soccer_skips_unreadable_shots_stat(tmp_path):
    ledger = tmp_path / "clv.jsonl"
    # Shots / SOT are NOT per-player readable keyless -> is_known_stat False -> no fab 0.
    props = [_Prop("Vinicius Junior", "Shots On Target", 0.5, 2.6, 1.55)]
    out = T.run("soccer_intl", ledger_path=ledger, prop_provider=_provider(props),
                dist=_dist("Vinicius Junior", "Shots On Target", 1.2),
                live_games_fn=_soccer_live, box_fn=_soccer_box("Vinicius Junior"),
                min_tier="C")
    assert out["placed"] == 0


def test_soccer_default_market_source_is_clean_no_op(tmp_path):
    # No live two-way WC prop source is wired -> the default provider returns unavailable
    # for soccer, so a live match places nothing (honest no-op, never a fabricated line).
    out = T.run("soccer_intl", ledger_path=tmp_path / "clv.jsonl",
                live_games_fn=_soccer_live, box_fn=_soccer_box("Vinicius Junior"))
    assert out["placed"] == 0 and out["status"] == "no_prices"
