"""Per-file test for scripts.platformkit.bestbets.prop_cards.

Run: cd /c/Users/neelj/nba-ai-system && \
     python -m pytest scripts/platformkit/bestbets/test_prop_cards.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone

import scripts.platformkit.bestbets.prop_cards as pc


def _edge(**kw):
    base = {
        "player": "Test Player", "matched_name": "Test Player",
        "match": "A vs B", "team": "A", "stat": "Shots", "line": 1.5,
        "model_p_over": 0.62, "model_lam": 2.1, "side": "over",
        "reliable": True, "ev_flag": "ok", "edge_basis": "model_view",
        "tier": "MODEL_VIEW", "as_of": "2026-06-21", "source": "underdog",
        "calibration": "marginal",
    }
    base.update(kw)
    return base


def _patch_board(monkeypatch, edges_by_sport):
    def fake_board(sport, **_kw):
        return {"status": "ok", "edges": edges_by_sport.get(sport, [])}
    monkeypatch.setattr(
        "scripts.platformkit.prop_edge.build_prop_board", fake_board
    )


_NOW = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc).timestamp()


def test_model_only_card_has_no_edge(monkeypatch):
    _patch_board(monkeypatch, {"soccer_intl": [_edge()], "mlb": []})
    cards = pc.build_prop_cards(now=_NOW)
    assert len(cards) == 1
    c = cards[0]
    assert c["market_type"] == "prop"
    assert c["model_only"] is True
    assert c["edge_claimed"] is False
    assert c["market_prob"] is None
    assert c["edge_vs_market"] is None
    assert c["line"] == 1.5
    assert c["prop_player"] == "Test Player"
    assert c["prop_stat"] == "Shots"
    assert c["proj"] == 2.1
    # model_prob = p_over for an OVER side
    assert abs(c["model_prob"] - 0.62) < 1e-9


def test_priced_card_has_edge(monkeypatch):
    e = _edge(edge_basis="ev_vs_priced", fair_over=0.55, fair_under=0.45)
    _patch_board(monkeypatch, {"soccer_intl": [e], "mlb": []})
    cards = pc.build_prop_cards(now=_NOW)
    assert len(cards) == 1
    c = cards[0]
    assert c["model_only"] is False
    # edge_claimed is ALWAYS False even for a priced card -- edge_vs_market is a
    # LABELLED probability divergence, never a $-edge / beat-the-close claim.
    assert c["edge_claimed"] is False
    assert c["market_prob"] == 0.55
    # edge = model_prob(0.62) - market_prob(0.55)
    assert abs(c["edge_vs_market"] - 0.07) < 1e-9


def test_every_card_edge_claimed_false(monkeypatch):
    # Repo-wide invariant: NO served prop card may claim an edge. Mix of
    # model-only AND priced edges -> edge_claimed must be False on EVERY card.
    priced = _edge(player="Priced", edge_basis="ev_vs_priced",
                   fair_over=0.55, fair_under=0.45)
    model = _edge(player="ModelOnly")
    under = _edge(player="Under", side="under", model_p_over=0.7)
    _patch_board(monkeypatch, {"soccer_intl": [priced, model, under], "mlb": []})
    cards = pc.build_prop_cards(now=_NOW)
    assert len(cards) == 3
    for c in cards:
        assert c["edge_claimed"] is False, c["prop_player"]
    # bounded/served path too
    served, _ = pc.build_bounded_prop_cards(now=_NOW, cap=50)
    assert served
    for c in served:
        assert c["edge_claimed"] is False, c["prop_player"]


def test_under_side_inverts_model_prob(monkeypatch):
    e = _edge(side="under", model_p_over=0.7)
    _patch_board(monkeypatch, {"soccer_intl": [e], "mlb": []})
    cards = pc.build_prop_cards(now=_NOW)
    assert len(cards) == 1
    assert abs(cards[0]["model_prob"] - 0.3) < 1e-9
    assert cards[0]["side"] == "under"


def test_stale_board_dropped(monkeypatch):
    # as_of strictly before today (UTC) -> past event -> dropped.
    e = _edge(as_of="2026-06-18")
    _patch_board(monkeypatch, {"soccer_intl": [e], "mlb": []})
    cards = pc.build_prop_cards(now=_NOW)
    assert cards == []


def test_today_boundary_uses_et_not_utc():
    """At 8pm ET the UTC clock has rolled to the next date; _today_for must bucket on
    the ET day (the earlier date), matching the paper/ + producer convention."""
    # 2026-06-21 20:30 ET == 2026-06-22 00:30 UTC (EDT, UTC-4).
    utc_after_midnight = datetime(2026, 6, 22, 0, 30, tzinfo=timezone.utc).timestamp()
    assert pc._today_for(utc_after_midnight) == "2026-06-21"  # ET day, not UTC 06-22


def test_et_evening_event_not_dropped_as_stale(monkeypatch):
    """A tonight's-ET event (as_of = ET day) must NOT be dropped just because the UTC
    clock has already rolled past midnight to the next date."""
    utc_after_midnight = datetime(2026, 6, 22, 0, 30, tzinfo=timezone.utc).timestamp()
    e = _edge(as_of="2026-06-21")  # the live ET slate
    _patch_board(monkeypatch, {"soccer_intl": [e], "mlb": []})
    cards = pc.build_prop_cards(now=utc_after_midnight)
    assert len(cards) == 1  # kept: ET 'today' == 2026-06-21, not stale


def test_yesterday_et_event_still_dropped(monkeypatch):
    """A genuinely past ET event (as_of before the ET day) is still dropped."""
    utc_after_midnight = datetime(2026, 6, 22, 0, 30, tzinfo=timezone.utc).timestamp()
    e = _edge(as_of="2026-06-20")  # a day before the ET 'today' (2026-06-21)
    _patch_board(monkeypatch, {"soccer_intl": [e], "mlb": []})
    assert pc.build_prop_cards(now=utc_after_midnight) == []


def test_unreliable_dropped_by_default(monkeypatch):
    e = _edge(reliable=False, ev_flag="uncalibrated_thin")
    _patch_board(monkeypatch, {"soccer_intl": [e], "mlb": []})
    assert pc.build_prop_cards(now=_NOW) == []
    # but kept when reliable_only=False
    kept = pc.build_prop_cards(now=_NOW, reliable_only=False)
    assert len(kept) == 1


def test_unavailable_when_no_edges(monkeypatch):
    _patch_board(monkeypatch, {"soccer_intl": [], "mlb": []})
    assert pc.build_prop_cards(now=_NOW) == []


def test_board_status_not_ok_yields_no_cards(monkeypatch):
    def fake_board(sport, **_kw):
        return {"status": "no_data: missing", "edges": [_edge()]}
    monkeypatch.setattr(
        "scripts.platformkit.prop_edge.build_prop_board", fake_board
    )
    assert pc.build_prop_cards(now=_NOW) == []


def test_never_raises_on_board_exception(monkeypatch):
    def boom(sport, **_kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(
        "scripts.platformkit.prop_edge.build_prop_board", boom
    )
    assert pc.build_prop_cards(now=_NOW) == []


# ---------------------------------------------------------------------------
# P0-1: served prop cards carry a REAL, resolvable game_id (the View-detail link).
# The id MUST equal the upstream game's game_id (the SAME source the v1 detail
# board uses) and must NEVER be fabricated when no game resolves.
# ---------------------------------------------------------------------------

def _patch_edge_view(monkeypatch, games_by_sport):
    """Stub frontend.edge_api.build_edge_view -- the SAME source the v1 detail board
    uses -- so prop cards resolve their underlying game's REAL game_id."""
    import frontend.edge_api as _ea

    def fake_view(sport, **_kw):
        return {"status": "ok", "games": games_by_sport.get(sport, [])}
    monkeypatch.setattr(_ea, "build_edge_view", fake_view)


def test_prop_card_carries_real_upstream_game_id(monkeypatch):
    # 'Uruguay vs Cape Verde' must resolve to the SAME real game_id the v1 board
    # exposes for that game -- never empty, never fabricated.
    game = {"game_id": "760450", "home": "Uruguay", "away": "Cape Verde"}
    _patch_edge_view(monkeypatch, {"soccer_intl": [game]})
    e = _edge(match="Uruguay vs Cape Verde")
    _patch_board(monkeypatch, {"soccer_intl": [e], "mlb": []})
    cards = pc.build_prop_cards(now=_NOW, sports=("soccer_intl",))
    assert len(cards) == 1
    assert cards[0]["game_id"] == "760450"  # matches the upstream game exactly


def test_prop_card_resolves_regardless_of_home_away_order(monkeypatch):
    # MLB uses 'Away @ Home'; the team-pair index is unordered, so an 'A @ B' match
    # still resolves to the game the v1 board stores as home=B, away=A.
    game = {"game_id": "1631929388", "home": "Kansas City Royals",
            "away": "St. Louis Cardinals"}
    _patch_edge_view(monkeypatch, {"mlb": [game]})
    e = _edge(match="St. Louis Cardinals @ Kansas City Royals", stat="Hits")
    _patch_board(monkeypatch, {"mlb": [e], "soccer_intl": []})
    cards = pc.build_prop_cards(now=_NOW, sports=("mlb",))
    assert len(cards) == 1
    assert cards[0]["game_id"] == "1631929388"


def test_prop_card_game_id_empty_not_fabricated_when_unresolvable(monkeypatch):
    # No matching game on the served edge board -> game_id stays '' (link disabled).
    # NEVER a fabricated / invented id.
    _patch_edge_view(monkeypatch, {"soccer_intl": []})
    e = _edge(match="Nowhere FC vs Phantom United")
    _patch_board(monkeypatch, {"soccer_intl": [e], "mlb": []})
    cards = pc.build_prop_cards(now=_NOW, sports=("soccer_intl",))
    assert len(cards) == 1
    assert cards[0]["game_id"] == ""  # honest empty; webapp link guard disables it


def test_game_id_index_never_raises_on_bad_edge_view(monkeypatch):
    # A broken edge view must degrade to '' game_ids, never crash the board.
    import frontend.edge_api as _ea

    def boom(sport, **_kw):
        raise RuntimeError("edge view exploded")
    monkeypatch.setattr(_ea, "build_edge_view", boom)
    e = _edge(match="Uruguay vs Cape Verde")
    _patch_board(monkeypatch, {"soccer_intl": [e], "mlb": []})
    cards = pc.build_prop_cards(now=_NOW, sports=("soccer_intl",))
    assert len(cards) == 1
    assert cards[0]["game_id"] == ""


def test_no_dollar_fields(monkeypatch):
    _patch_board(monkeypatch, {"soccer_intl": [_edge()], "mlb": []})
    cards = pc.build_prop_cards(now=_NOW)
    banned = {"dollar_pnl", "pnl_usd", "usd", "pnl", "roi", "profit", "bankroll"}
    for c in cards:
        assert not (banned & set(c.keys()))
        assert c["units"] == 1.0  # UNITS not $


# ---------------------------------------------------------------------------
# Bounded / ranked served set
# ---------------------------------------------------------------------------

def _many_edges(n, prefix="Player", **kw):
    out = []
    for i in range(n):
        e = _edge(player="%s %d" % (prefix, i), **kw)
        out.append(e)
    return out


def _card_dict(player, sport="mlb"):
    # A minimal served model-only CARD (not an edge) for the synth-only helpers.
    return {
        "sport": sport, "market_type": "prop", "prop_player": player,
        "prop_stat": "Hits", "line": 1.5, "side": "over", "model_prob": 0.55,
        "proj": 1.6, "market_prob": None, "edge_vs_market": None, "units": 1.0,
        "model_only": True, "edge_claimed": False, "reliable": True,
        "calibration": "marginal", "confidence": 0.55, "status": "pregame",
    }


def test_bounded_caps_model_only_and_counts_n_more(monkeypatch):
    # 120 model-only soccer edges; cap=50 keeps 50 + reports 70 more.
    _patch_board(monkeypatch, {"soccer_intl": _many_edges(120), "mlb": []})
    cards, n_more = pc.build_bounded_prop_cards(now=_NOW, cap=50)
    served = [c for c in cards if c["sport"] == "soccer_intl"]
    assert len(served) == 50
    assert n_more["soccer_intl"] == 70


def test_bounded_keeps_all_priced(monkeypatch):
    # 60 priced edges + 60 model-only; cap=10 -> ALL 60 priced + 10 model-only.
    priced = _many_edges(60, edge_basis="ev_vs_priced", fair_over=0.5,
                          fair_under=0.5)
    model = _many_edges(60, prefix="Model")
    _patch_board(monkeypatch, {"soccer_intl": priced + model, "mlb": []})
    cards, n_more = pc.build_bounded_prop_cards(now=_NOW, cap=10)
    priced_cards = [c for c in cards if not c["model_only"]]
    model_cards = [c for c in cards if c["model_only"]]
    assert len(priced_cards) == 60      # ALL priced bets survive
    assert len(model_cards) == 10       # model-only capped
    assert n_more["soccer_intl"] == 50


def test_bounded_ranks_reliable_calibrated_first(monkeypatch):
    weak = _edge(player="Weak", calibration="weak", reliable=True,
                 model_p_over=0.55)
    marg = _edge(player="Marg", calibration="marginal", reliable=True,
                 model_p_over=0.55)
    _patch_board(monkeypatch, {"soccer_intl": [weak, marg], "mlb": []})
    cards, _ = pc.build_bounded_prop_cards(now=_NOW, cap=1)
    served = [c for c in cards if c["sport"] == "soccer_intl"]
    assert len(served) == 1
    assert served[0]["prop_player"] == "Marg"  # marginal outranks weak


def test_bounded_never_raises_on_board_exception(monkeypatch):
    def boom(sport, **_kw):
        raise RuntimeError("boom")
    monkeypatch.setattr("scripts.platformkit.prop_edge.build_prop_board", boom)
    # synthesis fallback must also not save us here (board raises) -> ([], {}).
    import scripts.platformkit.bestbets.prop_cards_bounded as pcb
    monkeypatch.setattr(pcb, "_synth_lines_for_sport",
                        lambda *a, **k: [object()])
    cards, n_more = pc.build_bounded_prop_cards(now=_NOW)
    assert cards == []
    assert n_more == {}


# ---------------------------------------------------------------------------
# ALWAYS-FRESH model-only fallback (the 429 robustness fix)
# ---------------------------------------------------------------------------

def _synth_edge(player, sport="mlb"):
    # A SYNTHESIZED model-only edge: no price (edge_basis model_view), reliable.
    return _edge(player=player, source="model_only_synth", edge_basis="model_view",
                 reliable=True, ev_flag="ok")


def _patch_synth(monkeypatch, edges_by_sport):
    """Make the synthesis path return canned MODEL-ONLY edges WITHOUT a parquet/feed:
    a synth board returns the edges, and _synth_lines_for_sport returns a non-empty
    sentinel list so the fallback proceeds (lines are passed straight to that board).
    """
    import scripts.platformkit.bestbets.prop_cards_bounded as pcb

    # Feed 429 -> _capped_lines yields nothing usable (no real on-disk cache leak).
    monkeypatch.setattr(pc, "_capped_lines", lambda sport, max_lines: None)

    def fake_board(sport, lines_source=None, **_kw):
        # model-only synthesis passes lines_source; feed path passes None.
        if lines_source is not None:
            return {"status": "ok", "edges": edges_by_sport.get(sport, [])}
        return {"status": "ok", "edges": []}  # feed 429 -> no priced/model edges
    monkeypatch.setattr("scripts.platformkit.prop_edge.build_prop_board", fake_board)
    monkeypatch.setattr(pcb, "_synth_lines_for_sport",
                        lambda sport, as_of, n: [object()])  # non-empty -> proceed


def test_model_only_flows_when_feed_429s(monkeypatch):
    # Feed path yields ZERO edges (429). Synthesis fallback supplies model-only cards.
    _patch_synth(monkeypatch, {"mlb": [_synth_edge("Synth Bat")], "soccer_intl": []})
    cards, n_more = pc.build_bounded_prop_cards(now=_NOW, sports=("mlb",))
    assert len(cards) == 1
    c = cards[0]
    assert c["model_only"] is True
    assert c["edge_claimed"] is False
    assert c["market_prob"] is None and c["edge_vs_market"] is None
    assert c["prop_player"] == "Synth Bat"
    assert c["best_book"] == "model_only_synth"


def test_priced_props_still_flow_when_feed_works(monkeypatch):
    # Feed available: priced edges flow via the normal (feed) path. Synthesis only
    # ever ADDS model-only cards; it never duplicates priced ones.
    import scripts.platformkit.bestbets.prop_cards_bounded as pcb
    priced = _edge(player="Priced", edge_basis="ev_vs_priced",
                   fair_over=0.55, fair_under=0.45)

    # Neutralize the on-disk line cache so the feed path goes through the board
    # directly (lines_source=None), keeping the test deterministic.
    monkeypatch.setattr(pc, "_capped_lines", lambda sport, max_lines: None)

    def fake_board(sport, lines_source=None, **_kw):
        if lines_source is not None:  # synthesis path -> only a model-only card
            return {"status": "ok", "edges": [_synth_edge("SynthAdd", sport)]}
        return {"status": "ok", "edges": [priced] if sport == "mlb" else []}
    monkeypatch.setattr("scripts.platformkit.prop_edge.build_prop_board", fake_board)
    monkeypatch.setattr(pcb, "_synth_lines_for_sport",
                        lambda sport, as_of, n: [object()])
    cards, _ = pc.build_bounded_prop_cards(now=_NOW, sports=("mlb",))
    priced_cards = [c for c in cards if not c["model_only"]]
    assert len(priced_cards) == 1
    assert priced_cards[0]["prop_player"] == "Priced"
    assert priced_cards[0]["edge_claimed"] is False


def test_429_does_not_crash_tick_via_bounded(monkeypatch):
    # A provider 429 surfaces as an empty feed board, never a raise out of bounded.
    import scripts.platformkit.bestbets.prop_cards_bounded as pcb

    monkeypatch.setattr(pc, "_capped_lines", lambda sport, max_lines: None)

    def feed_only_empty(sport, lines_source=None, **_kw):
        return {"status": "ok", "edges": []}
    monkeypatch.setattr("scripts.platformkit.prop_edge.build_prop_board",
                        feed_only_empty)
    # synthesis finds no parquet -> [] (honest empty), still no crash.
    monkeypatch.setattr(pcb, "_synth_lines_for_sport", lambda *a, **k: [])
    cards, n_more = pc.build_bounded_prop_cards(now=_NOW)
    assert cards == []  # honest empty, did not raise
    assert isinstance(n_more, dict)


# ---------------------------------------------------------------------------
# ANTI-FLICKER: pregame_games_exist + build_synth_only_prop_cards (the /bets fix)
# ---------------------------------------------------------------------------

def test_pregame_games_exist_true_when_synth_lines_present(monkeypatch):
    import scripts.platformkit.bestbets.prop_cards_bounded as pcb
    monkeypatch.setattr(pcb, "_synth_lines_for_sport",
                        lambda sport, as_of, n: [object()] if sport == "mlb" else [])
    assert pcb.pregame_games_exist(now=_NOW) is True


def test_pregame_games_exist_false_when_no_synth_lines(monkeypatch):
    import scripts.platformkit.bestbets.prop_cards_bounded as pcb
    monkeypatch.setattr(pcb, "_synth_lines_for_sport", lambda *a, **k: [])
    assert pcb.pregame_games_exist(now=_NOW) is False


def test_pregame_games_exist_never_raises(monkeypatch):
    import scripts.platformkit.bestbets.prop_cards_bounded as pcb

    def boom(*a, **k):
        raise RuntimeError("parquet exploded")
    monkeypatch.setattr(pcb, "_synth_lines_for_sport", boom)
    assert pcb.pregame_games_exist(now=_NOW) is False  # swallowed -> empty slate


def test_build_synth_only_uses_no_feed_and_caps(monkeypatch):
    # build_synth_only_prop_cards must NOT call the external feed path; it only
    # synthesizes model-only cards (capped) -- the honest no-429 fill.
    import scripts.platformkit.bestbets.prop_cards_bounded as pcb
    monkeypatch.setattr(pcb, "_synth_model_only_cards",
                        lambda sport, now, reliable: (
                            [_card_dict("S%d" % i, sport) for i in range(120)]
                            if sport == "mlb" else []))
    cards, n_more = pcb.build_synth_only_prop_cards(now=_NOW, cap=50)
    assert len(cards) == 50
    assert n_more["mlb"] == 70
    assert all(c["model_only"] and not c["edge_claimed"] for c in cards)


def test_build_synth_only_empty_when_no_pregame(monkeypatch):
    import scripts.platformkit.bestbets.prop_cards_bounded as pcb
    monkeypatch.setattr(pcb, "_synth_model_only_cards", lambda *a, **k: [])
    cards, n_more = pcb.build_synth_only_prop_cards(now=_NOW)
    assert cards == [] and n_more == {}  # genuinely empty slate -> honest empty


def test_synth_gate_fallback_keeps_live_sport_nonempty(monkeypatch):
    # The reliability gate can transiently zero a sport that DOES have games. When the
    # un-gated probe priced cards, _synth_model_only_cards serves the un-gated set so
    # a live pregame sport is never emptied by a boundary jitter.
    import scripts.platformkit.bestbets.prop_cards_bounded as pcb
    monkeypatch.setattr(pcb, "_synth_lines_for_sport",
                        lambda sport, as_of, n: [object()])
    monkeypatch.setattr(pcb, "_recenter_lines", lambda probe, lines: lines)

    def cards_from_lines(sport, lines, *, now=None, reliable_only=True):
        # un-gated (reliable_only=False) -> a card; gated -> empty (boundary jitter).
        return [] if reliable_only else [_card_dict("Boundary", sport)]
    monkeypatch.setattr(pc, "cards_from_lines", cards_from_lines)
    out = pcb._synth_model_only_cards("mlb", _NOW, reliable=True)
    assert len(out) == 1  # served the un-gated card rather than an empty sport


# ---------------------------------------------------------------------------
# m13-circuit fix round 2: circuit_skips must reach the SERVED bounded/synth rows
# (this is the exact dead-provider case the breaker exists for -- BLOCKING finding).
# ---------------------------------------------------------------------------

def _fake_skips(sport, entries_by_sport):
    """A last_circuit_skips() stand-in returning canned SKIPPED_CIRCUIT entries."""
    def _last(sport_arg=None):
        if sport_arg is not None:
            return {sport_arg: list(entries_by_sport.get(sport_arg, []))}
        return {k: list(v) for k, v in entries_by_sport.items()}
    return _last


def test_synth_fallback_carries_real_circuit_skip(monkeypatch):
    # THE BUG: build_bounded_prop_cards synth-fallback path (feed dead -> synthesize
    # from parquet) never stamped circuit_skips, so a SKIPPED_CIRCUIT provider was
    # silently dropped from the served output in exactly the case the breaker exists
    # for. Seed a real skip entry via prop_cards_circuit_io and assert it survives.
    import scripts.platformkit.bestbets.prop_cards_circuit_io as pcio
    skip_entry = {"provider": "prizepicks", "reason": "SKIPPED_CIRCUIT",
                 "since": 1000.0, "last_reason": "403", "consecutive_failures": 3}
    monkeypatch.setattr(pcio, "last_circuit_skips",
                        _fake_skips("mlb", {"mlb": [skip_entry]}))
    _patch_synth(monkeypatch, {"mlb": [_synth_edge("Synth Bat")], "soccer_intl": []})
    cards, _ = pc.build_bounded_prop_cards(now=_NOW, sports=("mlb",))
    assert len(cards) == 1
    c = cards[0]
    assert c["model_only"] is True  # confirms this IS the synth-fallback row
    assert c["circuit_skips"] == [skip_entry]  # never silently dropped


def test_priced_and_feed_model_only_carry_circuit_skips_too(monkeypatch):
    # Non-fallback rows (priced + feed-sourced model-only) already went through
    # build_prop_cards' own stamp; build_bounded_prop_cards must not clobber that
    # with an empty list -- re-stamping with the SAME last-tick skips is a no-op.
    # Includes a model-only edge too so the feed path is non-empty and the synth
    # fallback (a separate, already-covered case) never triggers here.
    import scripts.platformkit.bestbets.prop_cards_circuit_io as pcio
    skip_entry = {"provider": "betmgm", "reason": "SKIPPED_CIRCUIT", "since": 500.0,
                 "last_reason": "400", "consecutive_failures": 3}
    monkeypatch.setattr(pcio, "last_circuit_skips",
                        _fake_skips("mlb", {"mlb": [skip_entry]}))
    priced = _edge(player="Priced", edge_basis="ev_vs_priced",
                   fair_over=0.55, fair_under=0.45)
    model = _edge(player="ModelOnly")
    _patch_board(monkeypatch, {"mlb": [priced, model], "soccer_intl": []})
    cards, _ = pc.build_bounded_prop_cards(now=_NOW, sports=("mlb",))
    assert len(cards) == 2
    for c in cards:
        assert c["circuit_skips"] == [skip_entry]


def test_synth_only_prop_cards_carries_circuit_skip(monkeypatch):
    # build_synth_only_prop_cards (the anti-flicker no-feed fill) is ALSO a served
    # path -- it must stamp circuit_skips exactly like the bounded builder.
    import scripts.platformkit.bestbets.prop_cards_bounded as pcb
    import scripts.platformkit.bestbets.prop_cards_circuit_io as pcio
    skip_entry = {"provider": "fanduel", "reason": "SKIPPED_CIRCUIT", "since": 1.0,
                 "last_reason": "timeout", "consecutive_failures": 3}
    monkeypatch.setattr(pcio, "last_circuit_skips",
                        _fake_skips("mlb", {"mlb": [skip_entry]}))
    monkeypatch.setattr(pcb, "_synth_model_only_cards",
                        lambda sport, now, reliable: (
                            [_card_dict("S1", sport)] if sport == "mlb" else []))
    cards, _ = pcb.build_synth_only_prop_cards(now=_NOW, sports=("mlb",))
    assert len(cards) == 1
    assert cards[0]["circuit_skips"] == [skip_entry]


def test_no_skip_recorded_yields_empty_circuit_skips_list(monkeypatch):
    # Honest default: a sport with no breaker activity carries [], never omitted.
    import scripts.platformkit.bestbets.prop_cards_circuit_io as pcio
    monkeypatch.setattr(pcio, "last_circuit_skips", _fake_skips("mlb", {}))
    _patch_synth(monkeypatch, {"mlb": [_synth_edge("Clean")], "soccer_intl": []})
    cards, _ = pc.build_bounded_prop_cards(now=_NOW, sports=("mlb",))
    assert len(cards) == 1
    assert cards[0]["circuit_skips"] == []


# ---------------------------------------------------------------------------
# REGRESSION (m13-breaker-bypass, wave-34): when _capped_lines() yields no source
# (feed empty + no on-disk cache -- e.g. all default providers circuit-OPEN),
# _board_edges() previously fell through to a BARE build_prop_board(sport) call,
# which re-derives cfg.default_providers() with NO breaker filter inside
# prop_edge.py -- re-dispatching live HTTP calls to providers the breaker just
# opened. The fix routes that fallback through an EXPLICIT breaker-filtered
# providers list so a circuit-OPEN provider can never be re-dispatched this way.
# ---------------------------------------------------------------------------

def test_no_capped_lines_fallback_uses_breaker_filtered_providers(monkeypatch):
    import scripts.platformkit.bestbets.prop_cards_circuit_io as pcio

    # Feed empty + no cache -> _capped_lines returns None (the exact bypass trigger).
    monkeypatch.setattr(pc, "_capped_lines", lambda sport, max_lines: None)

    calls = []

    def fake_board(sport, **kw):
        calls.append((sport, kw))
        return {"status": "ok", "edges": []}
    monkeypatch.setattr("scripts.platformkit.prop_edge.build_prop_board", fake_board)

    class _FakeProvider:
        name = "fake_survivor"

    filtered_calls = []

    def fake_breaker_filtered(sport):
        filtered_calls.append(sport)
        return [_FakeProvider()]
    monkeypatch.setattr(pcio, "breaker_filtered_providers", fake_breaker_filtered)

    pc.build_prop_cards(now=_NOW, sports=("mlb",), max_lines_per_sport=2500)

    # build_prop_board must have been called via the breaker-filtered helper
    # (never bare / with no providers kwarg at all).
    assert filtered_calls == ["mlb"]
    assert len(calls) == 1
    sport_arg, kwargs = calls[0]
    assert sport_arg == "mlb"
    assert "providers" in kwargs
    assert [getattr(p, "name", None) for p in kwargs["providers"]] == ["fake_survivor"]
    # lines_source must NOT be set on this fallback path (it's the providers path).
    assert kwargs.get("lines_source") is None


def test_no_capped_lines_fallback_never_calls_default_providers_unfiltered(monkeypatch):
    # Even if the breaker helper itself is unavailable (returns None), the fallback
    # must pass an explicit empty providers list -- NEVER omit providers/let
    # build_prop_board fall back to cfg.default_providers() un-gated.
    import scripts.platformkit.bestbets.prop_cards_circuit_io as pcio

    monkeypatch.setattr(pc, "_capped_lines", lambda sport, max_lines: None)
    monkeypatch.setattr(pcio, "breaker_filtered_providers", lambda sport: None)

    calls = []

    def fake_board(sport, **kw):
        calls.append((sport, kw))
        return {"status": "ok", "edges": []}
    monkeypatch.setattr("scripts.platformkit.prop_edge.build_prop_board", fake_board)

    pc.build_prop_cards(now=_NOW, sports=("mlb",), max_lines_per_sport=2500)

    assert len(calls) == 1
    _, kwargs = calls[0]
    assert kwargs.get("providers") == []


# ---------------------------------------------------------------------------
# m13-sport-parallel: build_prop_cards fans out across sports CONCURRENTLY.
# Race-audit -- two sports scored concurrently must produce output IDENTICAL
# to a sequential build, in a fixed (not completion-order) sequence, and one
# sport erroring must not sink the cycle.
# ---------------------------------------------------------------------------

def test_sport_parallel_matches_sequential_output(monkeypatch):
    # soccer_intl sleeps longer than mlb so completion order would put mlb
    # first if the assembly were completion-ordered; the FIXED sports order
    # (soccer_intl, mlb) must still be what comes out. game_id lookup is
    # stubbed out (network call, orthogonal to this fan-out test) so timing
    # reflects ONLY the board-fetch mock.
    import time as _time

    _patch_edge_view(monkeypatch, {})  # no games -> game_id="" for every card

    def fake_board(sport, **_kw):
        _time.sleep(0.05 if sport == "soccer_intl" else 0.01)
        return {"status": "ok", "edges": [_edge(player="P-%s" % sport)]}
    monkeypatch.setattr("scripts.platformkit.prop_edge.build_prop_board", fake_board)

    cards = pc.build_prop_cards(now=_NOW, sports=("soccer_intl", "mlb"))
    assert [c["sport"] for c in cards] == ["soccer_intl", "mlb"]

    # Sequential reference build (call each sport's edges directly, in order).
    seq_cards = []
    for sport in ("soccer_intl", "mlb"):
        edges = pc._board_edges(sport)
        seq_cards.extend(pc._cards_from_edges(edges, sport, pc._today_for(_NOW), True))
    assert cards == seq_cards
    assert pc.last_sport_errors() == {}


def test_sport_parallel_one_sport_error_does_not_sink_cycle(monkeypatch):
    # _board_edges already swallows a build_prop_board raise into an honest
    # empty board (existing, unrelated behavior) -- so to exercise THIS lane's
    # SCORE_ERROR isolation we make the per-sport unit itself raise past that
    # point, via _cards_from_edges (still inside _build_one_sport).
    _patch_board(monkeypatch, {"soccer_intl": [_edge(player="OK")], "mlb": [_edge()]})
    _patch_edge_view(monkeypatch, {})
    real_cards_from_edges = pc._cards_from_edges

    def fake_cards_from_edges(edges, sport, today, reliable_only):
        if sport == "mlb":
            raise RuntimeError("mlb scoring exploded")
        return real_cards_from_edges(edges, sport, today, reliable_only)
    monkeypatch.setattr(pc, "_cards_from_edges", fake_cards_from_edges)

    cards = pc.build_prop_cards(now=_NOW, sports=("soccer_intl", "mlb"))
    assert len(cards) == 1
    assert cards[0]["sport"] == "soccer_intl"
    errors = pc.last_sport_errors()
    assert "mlb" in errors
    assert "SCORE_ERROR" in errors["mlb"]
    assert "soccer_intl" not in errors


def test_sport_parallel_runs_concurrently_not_sequentially(monkeypatch):
    import time as _time

    _patch_edge_view(monkeypatch, {})

    def fake_board(sport, **_kw):
        _time.sleep(0.15)
        return {"status": "ok", "edges": [_edge(player="P-%s" % sport)]}
    monkeypatch.setattr("scripts.platformkit.prop_edge.build_prop_board", fake_board)

    t0 = _time.time()
    cards = pc.build_prop_cards(now=_NOW, sports=("soccer_intl", "mlb"))
    elapsed = _time.time() - t0
    assert len(cards) == 2
    assert elapsed < 0.28  # well under the 0.30s sequential sum
