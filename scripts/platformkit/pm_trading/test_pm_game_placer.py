"""Per-file test for pm_game_placer -- paper-trade Kalshi/Polymarket GAME markets.

Run ONLY this file (the full suite freezes the box):
    python -m pytest scripts/platformkit/pm_trading/test_pm_game_placer.py -q
"""
from __future__ import annotations

import json
from datetime import date

from scripts.platformkit.pm_trading import pm_game_placer as G


def _kalshi_rows():
    # MLB 2-way: model is "Toronto Blue Jays" @ "Houston Astros" -- Kalshi uses cities.
    return [
        {"sport": "mlb", "game_id": "KX-HOUTOR", "venue": "kalshi",
         "side": "Houston", "ticker": "KX-HOUTOR-HOU", "prob": 0.40},
        {"sport": "mlb", "game_id": "KX-HOUTOR", "venue": "kalshi",
         "side": "Toronto", "ticker": "KX-HOUTOR-TOR", "prob": 0.55},
    ]


def _model_games(sport):
    # our model strongly favors Houston (home) -> edge vs the 0.40 Kalshi price.
    return [{"sport": "mlb", "game_id": "401999", "home": "Houston Astros",
             "away": "Toronto Blue Jays",
             "pregame_probs": {"home_ml": 0.62, "away_ml": 0.38}}]


def test_group_by_game():
    g = G.group_by_game(_kalshi_rows())
    assert "KX-HOUTOR" in g
    assert set(g["KX-HOUTOR"]["sides"]) == {"Houston", "Toronto"}


def test_group_by_game_filters_out_non_moneyline_rows():
    # A total/spread/team_total row must NEVER enter the win-prob side set: its "prob" is
    # P(over line), not a team win-prob, and mixing it in would corrupt the devig.
    rows = _kalshi_rows() + [
        {"sport": "mlb", "game_id": "KX-HOUTOR", "venue": "kalshi",
         "market_type": "total", "side": "Over 8.5 runs scored",
         "ticker": "KXMLBTOTAL-x-9", "prob": 0.74},
        {"sport": "mlb", "game_id": "KX-HOUTOR", "venue": "kalshi",
         "market_type": "spread", "side": "Houston wins by over 3.5 runs",
         "ticker": "KXMLBSPREAD-x-HOU4", "prob": 0.31},
    ]
    g = G.group_by_game(rows)
    assert set(g["KX-HOUTOR"]["sides"]) == {"Houston", "Toronto"}  # unchanged by the extra rows


def test_group_by_game_row_missing_market_type_is_back_compat_moneyline():
    rows = [{"sport": "mlb", "game_id": "KX-X", "venue": "kalshi",
             "side": "Home", "ticker": "KX-X-H", "prob": 0.5}]
    g = G.group_by_game(rows)
    assert "KX-X" in g and "Home" in g["KX-X"]["sides"]


def test_name_matches_city_to_fullname():
    assert G._name_matches("Houston", "Houston Astros")
    assert G._name_matches("Toronto", "Toronto Blue Jays")
    assert not G._name_matches("Houston", "Toronto Blue Jays")


def test_name_matches_world_cup_country_aliases():
    # Kalshi vs model national-team naming variants must bridge...
    assert G._name_matches("South Korea", "Korea Republic")
    assert G._name_matches("Czechia", "Czech Republic")
    assert G._name_matches("USA", "United States")
    assert G._name_matches("IR Iran", "Iran")
    assert G._name_matches("Turkiye", "Turkey")
    # ...but distinct nations must NOT cross-match (Congo vs DR Congo) and a country must
    # not substring-match an unrelated one.
    assert not G._name_matches("Congo", "Congo DR")
    assert not G._name_matches("South Korea", "South Africa")


def test_world_cup_game_matches_with_alias():
    # South Africa (home) vs South Korea (away); Kalshi lists "Korea Republic".
    model = [{"home": "South Africa", "away": "South Korea",
              "pregame_probs": {"home": 0.5, "away": 0.5}}]
    m = G.match_model_game(["South Africa", "Korea Republic"], model)
    assert m is not None
    assert m["_roles"]["South Africa"] == "home"
    assert m["_roles"]["Korea Republic"] == "away"


def test_match_model_game_unique():
    m = G.match_model_game(["Houston", "Toronto"], _model_games("mlb"))
    assert m is not None
    assert m["_roles"]["Houston"] == "home" and m["_roles"]["Toronto"] == "away"
    # no-match -> None
    assert G.match_model_game(["Seattle", "Pittsburgh"], _model_games("mlb")) is None


def test_group_by_game_extracts_ticker_date():
    # gid IS the Kalshi event ticker; a real KX*GAME shape embeds the scheduled date.
    rows = [{"sport": "mlb", "game_id": "KXMLBGAME-26JUL10HOUTOR", "venue": "kalshi",
             "side": "Houston", "ticker": "t1", "prob": 0.5}]
    g = G.group_by_game(rows)
    assert g["KXMLBGAME-26JUL10HOUTOR"]["date"] == date(2026, 7, 10)


def test_match_model_game_refuses_cross_date_phantom():
    # PHANTOM-MATCHUP shape (root cause of the 10 bad paper_pm rows): the Kalshi ticker's
    # own date is 2026-07-10, but 'Houston'/'Toronto' only substring-match the 07-09 model
    # game -- a DIFFERENT game on a DIFFERENT date. The date guard must refuse this pairing
    # rather than silently bridge across dates via team-name substring alone.
    model_games = [
        {"sport": "mlb", "game_id": "401001", "home": "Houston Astros",
         "away": "Toronto Blue Jays", "pregame_probs": {"home_ml": 0.55, "away_ml": 0.45},
         "date_candidates": frozenset({date(2026, 7, 9)})},
        {"sport": "mlb", "game_id": "401002", "home": "Houston Astros",
         "away": "Seattle Mariners", "pregame_probs": {"home_ml": 0.60, "away_ml": 0.40},
         "date_candidates": frozenset({date(2026, 7, 10)})},
    ]
    m = G.match_model_game(["Houston", "Toronto"], model_games, kalshi_date=date(2026, 7, 10))
    assert m is None  # no 07-10 model game has Toronto -> honest skip, never the 07-09 game


def test_match_model_game_same_date_places():
    model_games = [
        {"sport": "mlb", "game_id": "401001", "home": "Houston Astros",
         "away": "Toronto Blue Jays", "pregame_probs": {"home_ml": 0.55, "away_ml": 0.45},
         "date_candidates": frozenset({date(2026, 7, 9)})},
    ]
    m = G.match_model_game(["Houston", "Toronto"], model_games, kalshi_date=date(2026, 7, 9))
    assert m is not None and m["_roles"]["Houston"] == "home"


def test_devig_2way_and_3way():
    # 2-way: 0.40 vs 0.55 normalize -> 0.4211
    assert abs(G._devig(0.40, 0.55, None) - 0.40 / 0.95) < 1e-6
    # 3-way: fold tie into the field
    assert abs(G._devig(0.50, 0.30, 0.25) - 0.50 / 1.05) < 1e-6


def test_placements_have_edge_and_units_only():
    g = G.group_by_game(_kalshi_rows())["KX-HOUTOR"]
    g["venue"] = "kalshi"
    placements = G.placements_from_game(g, G.match_model_game(["Houston", "Toronto"],
                                                              _model_games("mlb")))
    assert placements, "expected at least the +EV Houston side to clear the floor"
    home = [p for p in placements if p["side"] == "home"][0]
    # model 0.62 vs devigged market 0.421 -> positive edge
    assert home["model_prob"] == 0.62
    assert home["market_prob"] < home["model_prob"]
    assert home["ev"] > 0
    assert home["tier"] in ("A", "B", "C")
    assert "$" not in json.dumps(home)


def test_run_places_pm_rows_units_only(tmp_path):
    ledger = tmp_path / "l.jsonl"
    out = G.run(("mlb",), ledger_path=ledger, feed_fn=lambda s: _kalshi_rows(),
                model_fn=_model_games, place=True)
    assert out["n_matched"] == 1 and out["n_placed"] >= 1
    rows = [json.loads(ln) for ln in ledger.read_text().splitlines() if ln.strip()]
    assert rows and all(r["is_pm"] is True for r in rows)
    assert all(r["venue"] == "kalshi" and r["channel"] == "paper_pm" for r in rows)
    assert all(r["executed"] is False and r["edge_claimed"] is False for r in rows)
    assert all(r["bet_id"].startswith("pm|kalshi|") for r in rows)
    # honesty: no banned dollar keys on any row
    banned = {"pnl", "roi", "profit", "bankroll", "usd", "dollar"}
    assert not any(k.lower() in banned for r in rows for k in r)


def test_run_is_idempotent(tmp_path):
    ledger = tmp_path / "l.jsonl"
    a = G.run(("mlb",), ledger_path=ledger, feed_fn=lambda s: _kalshi_rows(),
              model_fn=_model_games, place=True)
    b = G.run(("mlb",), ledger_path=ledger, feed_fn=lambda s: _kalshi_rows(),
              model_fn=_model_games, place=True)
    assert b["n_placed"] == 0 and b["n_dup_skipped"] >= a["n_placed"]


def test_implausible_stale_price_is_skipped():
    # A 2% home YES (untraded/stale thin quote) -> market_prob below the band -> NO bet,
    # even though the model disagrees hugely (that fake edge is a data artifact, not real).
    rows = [
        {"sport": "mlb", "game_id": "KX-STALE", "venue": "kalshi",
         "side": "Houston", "ticker": "t1", "prob": 0.02},
        {"sport": "mlb", "game_id": "KX-STALE", "venue": "kalshi",
         "side": "Toronto", "ticker": "t2", "prob": 0.99},
    ]
    g = G.group_by_game(rows)["KX-STALE"]
    g["venue"] = "kalshi"
    placements = G.placements_from_game(g, G.match_model_game(["Houston", "Toronto"],
                                                              _model_games("mlb")))
    assert all(p["market_prob"] >= 0.05 for p in placements)  # the 0.02 side is dropped


def test_et_date_candidates_is_single_exact_date_not_a_two_day_hedge():
    # Real MLB tipoff: 2026-07-10 02:05 UTC == 2026-07-09 21:05 ET (EDT, UTC-4) -- the
    # PREVIOUS calendar day for the SAME game (UTC/ET midnight-rollover). The tightened
    # guard derives exactly ONE ET date (07-09), never a {07-09,07-10} hedge that could
    # ALSO false-positive-match an adjacent real game on 07-10 (R1 residual root cause).
    from scripts.platformkit.pm_trading.pm_game_date_guard import _et_date_candidates
    assert _et_date_candidates("2026-07-10T02:05:00+00:00") == frozenset({date(2026, 7, 9)})
    assert _et_date_candidates(None) == frozenset()


def test_match_model_game_series_adjacent_day_no_false_bind_when_correct_game_missing():
    # MLB SERIES shape: Houston @ Toronto plays both 07-09 and 07-10. The model board is
    # MISSING the 07-09 game (this residual's exact trap); the 07-10 game's date_candidates
    # come from the REAL derivation (_et_date_candidates), not a hard-coded literal, so this
    # exercises the actual fix, not just the containment check.
    from scripts.platformkit.pm_trading.pm_game_date_guard import _et_date_candidates
    model_games = [
        {"sport": "mlb", "game_id": "401099", "home": "Toronto Blue Jays",
         "away": "Houston Astros", "pregame_probs": {"home_ml": 0.5, "away_ml": 0.5},
         "date_candidates": _et_date_candidates("2026-07-10T23:10:00+00:00")},  # ET 07-10
    ]
    m = G.match_model_game(["Houston", "Toronto"], model_games, kalshi_date=date(2026, 7, 9))
    assert m is None  # honest skip -- must NOT single-hit-bind to the adjacent 07-10 game


def test_match_model_game_routes_through_mlb_resolver():
    # Ticker-abbrev ID join (ingame_id_resolver_mlb), never substring: away=TOR home=HOU.
    ticker = "KXMLBGAME-26JUL101810TORHOU"
    model_games = [{"sport": "mlb", "game_id": "402001", "home": "Houston Astros",
                    "away": "Toronto Blue Jays",
                    "pregame_probs": {"home_ml": 0.60, "away_ml": 0.40}}]
    m = G.match_model_game(["Houston", "Toronto"], model_games, ticker=ticker, sport="mlb")
    assert m is not None
    assert m["_roles"]["Houston"] == "home" and m["_roles"]["Toronto"] == "away"


def test_match_model_game_resolver_refuses_cross_date_phantom():
    # OPUS-JUDGE BLOCKER (c19e9a72 review): a 07-09 ticker resolves the TEAMS via the
    # abbrev-blob resolver, but the model board holds ONLY the SAME-TEAMS 07-10 game (an
    # MLB series shape). Team-abbrev matching alone (the pre-fix resolver path) single-hit
    # binds regardless of date; the resolver path must be gated by kalshi_date exactly like
    # the substring path -- 0 date-satisfying candidates -> honest skip, never a wrong bind.
    ticker = "KXMLBGAME-26JUL091810TORHOU"  # 07-09
    model_games = [{"sport": "mlb", "game_id": "402099", "home": "Houston Astros",
                    "away": "Toronto Blue Jays",
                    "pregame_probs": {"home_ml": 0.60, "away_ml": 0.40},
                    "date_candidates": frozenset({date(2026, 7, 10)})}]  # only 07-10 on board
    m = G.match_model_game(["Houston", "Toronto"], model_games,
                           kalshi_date=date(2026, 7, 9), ticker=ticker, sport="mlb")
    assert m is None  # honest skip -- must NOT bind the 07-09 ticket to the 07-10 game


def test_match_model_game_resolver_places_when_correct_date_present():
    # Same phantom shape, but the CORRECT 07-09 game IS on the board -> resolver path binds.
    ticker = "KXMLBGAME-26JUL091810TORHOU"  # 07-09
    model_games = [{"sport": "mlb", "game_id": "402100", "home": "Houston Astros",
                    "away": "Toronto Blue Jays",
                    "pregame_probs": {"home_ml": 0.60, "away_ml": 0.40},
                    "date_candidates": frozenset({date(2026, 7, 9)})}]
    m = G.match_model_game(["Houston", "Toronto"], model_games,
                           kalshi_date=date(2026, 7, 9), ticker=ticker, sport="mlb")
    assert m is not None and m["_roles"]["Houston"] == "home"


def test_run_end_to_end_refuses_resolver_cross_date_phantom_via_real_path():
    # Reproduces the judge's EXACT scenario through run()'s real call args (event_ticker as
    # game_id + sport='mlb'), not the direct kalshi_date-only entry point the R1 test used --
    # run() always threads ticker=gid/sport=sport, so this is what the live path actually does.
    ticker = "KXMLBGAME-26JUL091810TORHOU"  # 07-09
    rows = [
        {"sport": "mlb", "game_id": ticker, "venue": "kalshi",
         "side": "Houston", "ticker": ticker + "-HOU", "prob": 0.40},
        {"sport": "mlb", "game_id": ticker, "venue": "kalshi",
         "side": "Toronto", "ticker": ticker + "-TOR", "prob": 0.55},
    ]

    def model_only_0710(sport):
        return [{"sport": "mlb", "game_id": "999010", "home": "Houston Astros",
                 "away": "Toronto Blue Jays", "pregame_probs": {"home_ml": 0.62, "away_ml": 0.38},
                 "date_candidates": frozenset({date(2026, 7, 10)})}]

    out = G.run(("mlb",), ledger_path=None, feed_fn=lambda s: rows,
               model_fn=model_only_0710, place=False)
    assert out["by_sport"]["mlb"]["matched"] == 0
    assert out["n_placed"] == 0


def test_match_model_game_resolver_ambiguous_is_honest_skip():
    ticker = "KXMLBGAME-26JUL101810TORHOU"
    model_games = [
        {"sport": "mlb", "game_id": "402001", "home": "Houston Astros", "away": "Toronto Blue Jays"},
        {"sport": "mlb", "game_id": "402002", "home": "Houston Astros", "away": "Toronto Blue Jays"},
    ]
    # two identical-name candidates -> resolver sees 2 abbrev hits -> honest skip, never a guess
    m = G.match_model_game(["Houston", "Toronto"], model_games, ticker=ticker, sport="mlb")
    assert m is None


def test_match_model_game_unparseable_ticker_degrades_to_substring():
    # A non-KXMLBGAME-shaped id (this test file's own synthetic fixture convention) carries
    # no resolver info -- explicit substring fallback, not a hard failure.
    m = G.match_model_game(["Houston", "Toronto"], _model_games("mlb"),
                           ticker="KX-HOUTOR", sport="mlb")
    assert m is not None and m["_roles"]["Houston"] == "home"


def test_run_reports_matcher_route_per_sport(tmp_path):
    out = G.run(("mlb", "soccer_intl"), ledger_path=tmp_path / "l.jsonl",
               feed_fn=lambda s: [], model_fn=lambda s: [], place=True)
    assert out["by_sport"]["mlb"]["matcher"] == "resolver"
    assert out["by_sport"]["soccer_intl"]["matcher"] == "substring"


def test_outright_no_homeaway_is_skipped(tmp_path):
    # a futures/outright row (single side, no opponent) -> no 2-team match -> no bet.
    rows = [{"sport": "soccer_intl", "game_id": "KX-WC-WINNER", "venue": "kalshi",
             "side": "Spain", "ticker": "KX-SPAIN", "prob": 0.14}]
    out = G.run(("soccer_intl",), ledger_path=tmp_path / "l.jsonl",
                feed_fn=lambda s: rows, model_fn=lambda s: [], place=True)
    assert out["n_placed"] == 0


# --- exec-quality stamps (F1: pregame exec-gate wiring, pm_game_placer twin) -------
def test_run_placed_pm_row_carries_exec_gate_and_latency(tmp_path):
    # model 0.62 vs devigged market ~0.421 -> huge +EV -> clears the 1% exec floor, so
    # the placed paper_pm row must carry an exec_gate dict (passed) + placement_latency_ms,
    # exactly like the in-game / run_paper_today rows the m44 reader counts.
    ledger = tmp_path / "l.jsonl"
    out = G.run(("mlb",), ledger_path=ledger, feed_fn=lambda s: _kalshi_rows(),
                model_fn=_model_games, place=True)
    assert out["n_placed"] >= 1 and out["n_suppressed"] == 0
    rows = [json.loads(ln) for ln in ledger.read_text().splitlines() if ln.strip()]
    assert rows
    r = rows[0]
    assert isinstance(r["exec_gate"], dict) and r["exec_gate"]["passed"] is True
    assert r["exec_gate"]["expected_clv_pct"] >= 1.0
    assert isinstance(r["placement_latency_ms"], (int, float))
    assert "exec_gate_error" not in r


def test_run_gate_exception_still_records_ungated(tmp_path):
    # A gate crash must NEVER lose the placement row: it is recorded ungated with an
    # exec_gate_error note (crash-safety -- m1_paper never dies on a gate error).
    ledger = tmp_path / "l.jsonl"

    def _boom(**kw):
        raise RuntimeError("boom")

    from unittest.mock import patch
    with patch.object(G._exec_gate, "gate", _boom):
        out = G.run(("mlb",), ledger_path=ledger, feed_fn=lambda s: _kalshi_rows(),
                    model_fn=_model_games, place=True)
    assert out["n_placed"] >= 1  # gate error must NOT drop the row
    r = [json.loads(ln) for ln in ledger.read_text().splitlines() if ln.strip()][0]
    assert r.get("exec_gate_error") == "RuntimeError"
    assert "exec_gate" not in r  # ungated on error
    assert isinstance(r["placement_latency_ms"], (int, float))


def test_run_below_exec_floor_suppressed(tmp_path):
    # Raising the exec floor above the candidate's expected-CLV suppresses the placement
    # (mirror the pregame/in-game block); nothing is written.
    ledger = tmp_path / "l.jsonl"
    from unittest.mock import patch
    with patch.object(G, "INGAME_EXPECTED_CLV_MIN_PCT", 1e6):
        out = G.run(("mlb",), ledger_path=ledger, feed_fn=lambda s: _kalshi_rows(),
                    model_fn=_model_games, place=True)
    assert out["n_placed"] == 0 and out["n_suppressed"] >= 1
    assert not ledger.exists() or ledger.read_text().strip() == ""
