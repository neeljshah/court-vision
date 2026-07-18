"""Per-file test for the MEASUREMENT-ONLY in-play capture daemon (W4).

OFFLINE + deterministic: every chain (live_state, predict_live model, the liquid Kalshi
fetch, the FINAL-games feed) is INJECTED -- no network, no predictor corpus, no real venue.
grade_dir / ledger / heartbeat are tmp_path. Covers the binding rails:
  * one bounded cycle CAPTURES a (model_prob, devigged-price) pair carrying the PROVEN prior
    (p0_source=PRIOR -> calibration_justified True) -> a paper UNIT decision is taken.
  * on FINAL the held-out home_win LABEL is stamped (W3) so the OUTCOME arm can fire.
  * the heartbeat advances + is written (stale-never-green), measurement_only / executed False.
  * INERT / measurement-only: NO $ field anywhere; edge_claimed False; no flag flipped.
  * a BASE-fallback state (no pregame prior) is captured for the series but NEVER traded.
  * bounded serve_forever ALWAYS stops (max_ticks) with an injected clock (no real sleep).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_inplay_capture_loop.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import inplay_capture_loop as loop


# --------------------------------------------------------------------------------------- #
# injected offline chains                                                                  #
# --------------------------------------------------------------------------------------- #
def _state_fn_prior(sport, gid):
    # Live state carrying the PROVEN pregame prior (P1 wire -> p0_source PRIOR).
    return {"sport": sport, "game_id": gid, "home": "DET", "away": "CWS",
            "state_diff": 2.0, "frac_elapsed": 0.4, "p0": 0.58, "p0_source": "PRIOR",
            "status": "Top 5th"}


def _state_fn_base(sport, gid):
    # No pregame snapshot -> BASE_FALLBACK: captured for the series but NOT prior-justified.
    s = _state_fn_prior(sport, gid)
    s.update({"p0": None, "p0_source": "BASE_FALLBACK"})
    return s


def _model_fn(sport, state):
    # As-of-this-tick P(home win) -- a clear +edge vs the 0.55 YES(home) price below.
    return 0.80


def _inplay_fetch(sport):
    # The verified-real KXMLBGAME shape: two liquid team legs (home DET, away CWS).
    return [
        {"sport": sport, "game_id": "KXMLBGAME-26JUN191840CWSDET", "venue": "kalshi",
         "market_type": "moneyline", "side": "DET", "prob": 0.55, "phase": "in_play"},
        {"sport": sport, "game_id": "KXMLBGAME-26JUN191840CWSDET", "venue": "kalshi",
         "market_type": "moneyline", "side": "CWS", "prob": 0.47, "phase": "in_play"},
    ]


def _finals_none(sport):
    return []


def _finals_det_wins(sport):
    # A FINAL game whose grade file we want stamped (home DET won 5-3).
    return [{"sport": sport, "game_id": "KXMLBGAME-26JUN191840CWSDET",
             "event": {"competitions": [{"status": {"type": {"completed": True}},
                                         "competitors": [
                                             {"homeAway": "home", "score": "5"},
                                             {"homeAway": "away", "score": "3"}]}]}}]


def _no_dollar_field(obj):
    banned = {"$", "dollars", "usd", "roi", "pnl", "profit", "edge_dollars", "bankroll_usd"}

    def _walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                assert str(k).lower() not in banned, "banned $ field: %s" % k
                _walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                _walk(v)
    _walk(obj)


# --------------------------------------------------------------------------------------- #
# 0. market_type filter: _yes_pair must never mix a total/spread/team_total row into the   #
#    win-prob pairing (its "prob" is P(over line), never a team win-prob)                  #
# --------------------------------------------------------------------------------------- #
def test_yes_pair_filters_out_non_moneyline_ticks():
    ticks = [
        {"game_id": "KX-G", "side": "DET", "prob": 0.55, "market_type": "moneyline"},
        {"game_id": "KX-G", "side": "CWS", "prob": 0.47, "market_type": "moneyline"},
        {"game_id": "KX-G", "side": "Over 8.5 runs scored", "prob": 0.74,
         "market_type": "total"},
        {"game_id": "KX-G", "side": "DET wins by over 3.5 runs", "prob": 0.31,
         "market_type": "spread"},
    ]
    legs = loop._yes_pair(ticks)
    assert set(legs["KX-G"]) == {"DET", "CWS"}
    assert legs["KX-G"]["DET"] == 0.55 and legs["KX-G"]["CWS"] == 0.47


def test_yes_pair_row_missing_market_type_is_back_compat_moneyline():
    ticks = [{"game_id": "KX-G", "side": "DET", "prob": 0.55}]
    legs = loop._yes_pair(ticks)
    assert legs["KX-G"]["DET"] == 0.55


def test_poll_once_end_to_end_ignores_mixed_market_type_ticks(tmp_path):
    # A live fetch that returns the widened multi-series shape (moneyline + total + spread)
    # must still pair + paper-decide identically to the moneyline-only fixture.
    def _mixed_fetch(sport):
        return _inplay_fetch(sport) + [
            {"sport": sport, "game_id": "KXMLBGAME-26JUN191840CWSDET", "venue": "kalshi",
             "market_type": "total", "side": "Over 8.5 runs scored",
             "ticker": "KXMLBTOTAL-x-9", "prob": 0.74, "phase": "in_play"},
            {"sport": sport, "game_id": "KXMLBGAME-26JUN191840CWSDET", "venue": "kalshi",
             "market_type": "team_total", "side": "DET over 4.5 runs",
             "ticker": "KXMLBTEAMTOTAL-x-DET4", "prob": 0.40, "phase": "in_play"},
        ]

    grade_dir = tmp_path / "grade"
    hb = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                        inplay_fetch_fn=_mixed_fetch, finals_fn=_finals_none,
                        grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    assert hb["n_pairs"] == 1 and hb["n_live"] == 1  # the extra total/team_total rows are inert
    g = hb["games"][0]
    assert g["paired"] is True
    assert g["devigged_price"] is not None and 0.0 < g["devigged_price"] < 1.0


# --------------------------------------------------------------------------------------- #
# 1. one bounded cycle: capture a pair (with the proven prior), paper-decide, no $          #
# --------------------------------------------------------------------------------------- #
def test_one_cycle_captures_pair_with_prior_and_paper_decides(tmp_path):
    grade_dir = tmp_path / "grade"
    hb = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                        inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                        grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    assert hb["n_pairs"] == 1 and hb["n_live"] == 1
    g = hb["games"][0]
    assert g["paired"] is True
    assert g["p0_source"] == "PRIOR"                 # the PROVEN prior, not BASE
    assert g["model_prob"] == 0.80
    assert g["devigged_price"] is not None and 0.0 < g["devigged_price"] < 1.0
    # model (0.80) is well above the ~0.54 devigged price -> a paper ENTER fires.
    assert g["bet"] is True and g["action"] == "bet"
    assert hb["n_bets"] == 1
    # The leak-free grade pair was captured to the per-game file.
    path = grade_dir / "mlb" / "KXMLBGAME-26JUN191840CWSDET.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="ascii").splitlines() if x.strip()]
    assert len(rows) == 1 and rows[0]["side"] == "home"
    assert rows[0]["model_prob"] == 0.80
    # measurement-only honesty rails.
    assert hb["measurement_only"] is True and hb["executed"] is False
    assert hb["edge_claimed"] is False and hb["units"] == "probability"
    _no_dollar_field(hb)


# --------------------------------------------------------------------------------------- #
# 2. on FINAL the held-out home_win label is stamped (W3 -> OUTCOME arm wired)              #
# --------------------------------------------------------------------------------------- #
def test_final_stamps_outcome_label_for_outcome_arm(tmp_path):
    grade_dir = tmp_path / "grade"
    # tick 1: capture a pair. tick 2: same pair + the game is now FINAL -> stamp the label.
    loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                   inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                   grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                   heartbeat_path=tmp_path / "hb.json")
    hb = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                        inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_det_wins,
                        grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    assert hb["n_settled"] == 1
    # The OUTCOME arm reads the settled label via inplay_aggregate_grade._settled_outcome.
    from scripts.platformkit.ingame import inplay_aggregate_grade as agg
    path = grade_dir / "mlb" / "KXMLBGAME-26JUN191840CWSDET.jsonl"
    assert agg._settled_outcome(path) == 1.0          # DET (home) won -> 1
    # The settle row does NOT corrupt the captured model/market pairs.
    from scripts.platformkit.ingame import live_grade as lg
    assert len(lg._load_pairs(path)) == 2             # the 2 paired ticks remain
    _no_dollar_field(hb)


# --------------------------------------------------------------------------------------- #
# 3. a BASE-fallback (no prior) tick is captured but NEVER traded (prior-justified gate)    #
# --------------------------------------------------------------------------------------- #
def test_base_fallback_captures_but_does_not_trade(tmp_path):
    grade_dir = tmp_path / "grade"
    hb = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_base, model_fn=_model_fn,
                        inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                        grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    g = hb["games"][0]
    assert g["paired"] is True                        # still captured for the series
    assert g["bet"] is False                          # NOT prior-justified -> no paper bet
    assert hb["n_bets"] == 0
    assert g["reason"] == "not_calibration_justified"


# --------------------------------------------------------------------------------------- #
# 4. heartbeat advances + is written; bounded serve_forever ALWAYS stops (injected clock)   #
# --------------------------------------------------------------------------------------- #
def test_serve_forever_bounded_stops_and_writes_heartbeat(tmp_path):
    grade_dir = tmp_path / "grade"
    hb_path = tmp_path / "hb.json"
    sleeps = []
    n = loop.serve_forever(interval=5.0, max_ticks=3, clock=lambda s: sleeps.append(s),
                           sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                           inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                           grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                           heartbeat_path=hb_path)
    assert n == 3                                     # bounded run stopped at max_ticks
    # The final tick does NOT sleep (loop breaks first) -> exactly max_ticks-1 sleeps.
    assert len(sleeps) == 2
    hb = json.loads(hb_path.read_text(encoding="ascii"))
    assert hb["measurement_only"] is True and "as_of" in hb
    _no_dollar_field(hb)


# --------------------------------------------------------------------------------------- #
# 5. a down feed yields zero live games + a clean heartbeat (never a fabricated game)       #
# --------------------------------------------------------------------------------------- #
def test_down_feed_zero_games_clean_heartbeat(tmp_path):
    hb = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                        inplay_fetch_fn=lambda s: [], finals_fn=_finals_none,
                        grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    assert hb["n_live"] == 0 and hb["n_pairs"] == 0 and hb["games"] == []
    assert hb["edge_claimed"] is False


# --------------------------------------------------------------------------------------- #
# 6. DEEP enrichment: the resolver's base-out reaches the captured state_summary (the       #
#    fix for the bare "live" series). MLB-only; a non-mlb sport never calls the resolver.   #
# --------------------------------------------------------------------------------------- #
def _deep_fn(gid):
    # The statsapi resolver's deep state for the live game (Bottom 7, runner on 2nd, 1-1).
    return {"inning": 7, "half": "bottom", "outs": 1, "base": 2, "bos": 7,
            "re": 0.664, "count": "1-1", "game_pk": "822960"}


def test_deep_state_flows_into_captured_series(tmp_path):
    grade_dir = tmp_path / "grade"
    hb = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                        inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                        deep_state_fn=_deep_fn,
                        grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    assert hb["n_pairs"] == 1
    path = grade_dir / "mlb" / "KXMLBGAME-26JUN191840CWSDET.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="ascii").splitlines() if x.strip()]
    summ = rows[0]["state_summary"]
    # The deep base-out state DEEPENS the captured series (was a bare "live").
    assert summ != "live"
    for token in ("inning=7", "half=bottom", "outs=1", "base=2",
                  "bos=7", "re=0.664", "count=1-1"):
        assert token in summ


def _soccer_fetch(sport):
    return [
        {"sport": sport, "game_id": "KXWCGAME-26JUN271810ARGAUS", "venue": "kalshi",
         "market_type": "moneyline", "side": "Argentina", "prob": 0.55, "phase": "in_play"},
        {"sport": sport, "game_id": "KXWCGAME-26JUN271810ARGAUS", "venue": "kalshi",
         "market_type": "moneyline", "side": "Australia", "prob": 0.47, "phase": "in_play"},
    ]


def test_deep_enrichment_is_mlb_only(tmp_path):
    # Even with a live soccer game processed, the MLB base-out resolver is NEVER invoked for
    # a non-mlb sport (it would mis-key a soccer ticker). poll_once gates by sport.
    seen = []

    def _spy(gid):
        seen.append(gid)
        return {"inning": 1}

    loop.poll_once(sports=["soccer_intl"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                   inplay_fetch_fn=_soccer_fetch, finals_fn=_finals_none,
                   deep_state_fn=_spy,
                   grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
                   heartbeat_path=tmp_path / "hb.json")
    assert seen == []  # mlb-only gating: soccer never invokes the base-out resolver


def test_default_sports_widened_to_tennis_and_wnba():
    # 2026-07-03: tennis (KXATPMATCH/KXWTAMATCH) + wnba (KXWNBAGAME) capture START --
    # kalshi_series_spec already carried both series; DEFAULT_SPORTS was the only gate
    # keeping them out of the capture daemon. mlb/soccer_intl stay present (additive).
    assert set(loop.DEFAULT_SPORTS) >= {"mlb", "soccer_intl", "tennis", "wnba"}
    # both new sports resolve to a real (series_ticker, market_type) list, never [].
    from scripts.platformkit.odds_provider import kalshi_series_spec as _spec
    assert _spec.series_for("tennis")
    assert _spec.series_for("wnba")


# --------------------------------------------------------------------------------------- #
# 7. LANE 3: npb/kbo widen (capture-only, NO placement -- no live model wired yet)          #
# --------------------------------------------------------------------------------------- #
def test_default_sports_widened_to_npb_and_kbo():
    assert set(loop.DEFAULT_SPORTS) >= {"mlb", "soccer_intl", "tennis", "wnba", "npb", "kbo"}
    from scripts.platformkit.odds_provider import kalshi_series_spec as _spec
    assert _spec.series_for("npb")
    assert _spec.series_for("kbo")


def test_default_sports_widened_to_nba():
    # live_board.live_model_home_prob now has an nba branch (see test_live_board.py's
    # test_live_model_home_prob_nba_*), so nba joins the default roster.
    assert "nba" in loop.DEFAULT_SPORTS


def test_nba_model_fn_wired_no_longer_early_exits(tmp_path, monkeypatch):
    """Exercises the REAL production default model_fn (_default_model_fn ->
    live_board.live_model_home_prob), NOT an injected stub, to prove nba no longer
    early-exits at reason=no_model_prob now that live_board's nba branch + this
    module's DEFAULT_SPORTS are both wired. No network, no real predictor build:
    only the ingame_shadow singleton is monkeypatched to a deterministic stub."""
    from domains.basketball_nba import ingame_shadow as nba_shadow

    class _StubShadow:
        def shadow_prob(self, sport, home, away, state):
            return 0.66

    monkeypatch.setattr(nba_shadow, "get_shadow", lambda: _StubShadow())

    def _nba_state_fn(sport, gid):
        return {"sport": sport, "game_id": gid, "home": "BOS", "away": "LAL",
                "period": 3, "clock": 200.0, "home_score": 62.0, "away_score": 58.0,
                "state_diff": 4.0, "frac_elapsed": 0.55, "p0": 0.6, "p0_source": "PRIOR"}

    def _nba_fetch(sport):
        # probs must sum to >= 1.0 (a real overround) -- 0.55/0.47 mirrors the mlb
        # fixture (_inplay_fetch) above; 0.60/0.38 (sums < 1.0) is a degenerate VOID
        # pair that devig_home_price correctly refuses to price.
        return [
            {"sport": sport, "game_id": "KXNBAGAME-26JAN01BOSLAL", "venue": "kalshi",
             "market_type": "moneyline", "side": "BOS", "prob": 0.55, "phase": "in_play"},
            {"sport": sport, "game_id": "KXNBAGAME-26JAN01BOSLAL", "venue": "kalshi",
             "market_type": "moneyline", "side": "LAL", "prob": 0.47, "phase": "in_play"},
        ]

    grade_dir = tmp_path / "grade"
    hb = loop.poll_once(sports=["nba"], live_state_fn=_nba_state_fn,
                        inplay_fetch_fn=_nba_fetch, finals_fn=_finals_none,
                        grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    g = hb["games"][0]
    assert g["reason"] != "no_model_prob"
    assert g["paired"] is True
    assert g["model_prob"] == 0.66
    assert hb["n_pairs"] == 1
    _no_dollar_field(hb)


def _npb_fetch(sport):
    return [
        {"sport": sport, "game_id": "KXNPBGAME-26JUL050500YOKYAK-YOK", "venue": "kalshi",
         "market_type": "moneyline", "side": "YOK", "prob": 0.55, "phase": "in_play"},
        {"sport": sport, "game_id": "KXNPBGAME-26JUL050500YOKYAK-YOK", "venue": "kalshi",
         "market_type": "moneyline", "side": "YAK", "prob": 0.43, "phase": "in_play"},
    ]


def test_npb_kbo_have_no_model_fn_branch_ticks_still_accrue(tmp_path):
    """Poison-safe path: the PRODUCTION default model_fn (_default_model_fn ->
    live_board.live_model_home_prob) has NO npb/kbo branch, so model_prob is
    honestly None every tick -- _process_game must skip the pair cleanly
    (reason=no_model_prob) WITHOUT raising, and WITHOUT calling on_tick/placing
    any bet. This exercises the REAL default model_fn (no injection) so the
    None-safe dispatch itself is covered, not just a stubbed model_fn."""
    grade_dir = tmp_path / "grade"

    def _npb_state_fn(sport, gid):
        return {"sport": sport, "game_id": gid, "home": "YAK", "away": "YOK",
                "state_diff": 1.0, "frac_elapsed": 0.3, "p0": 0.52,
                "p0_source": "PRIOR", "status": "3rd inning"}

    hb = loop.poll_once(sports=["npb"], live_state_fn=_npb_state_fn,
                        inplay_fetch_fn=_npb_fetch, finals_fn=_finals_none,
                        grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    # ticks + venue prices are seen (games_seen carries the row) but NOTHING pairs/bets.
    assert hb["n_pairs"] == 0 and hb["n_bets"] == 0
    g = hb["games"][0]
    assert g["paired"] is False
    assert g["reason"] == "no_model_prob"
    assert hb["edge_claimed"] is False and hb["executed"] is False
    _no_dollar_field(hb)


def test_kbo_model_fn_none_safe_with_injected_model_fn_matching_production(tmp_path):
    """Same poison-safe contract, but via an explicit model_fn stand-in for
    live_board.live_model_home_prob's real npb/kbo dispatch (always None for
    any sport not in ('mlb','soccer','soccer_intl'))."""
    def _prod_shaped_model_fn(sport, state):
        return None  # mirrors live_model_home_prob's real kbo/npb behavior

    grade_dir = tmp_path / "grade"

    def _kbo_fetch(sport):
        return [
            {"sport": sport, "game_id": "KXKBOGAME-26JUL050500NCDKIA-NCD", "venue": "kalshi",
             "market_type": "moneyline", "side": "NCD", "prob": 0.5, "phase": "in_play"},
            {"sport": sport, "game_id": "KXKBOGAME-26JUL050500NCDKIA-NCD", "venue": "kalshi",
             "market_type": "moneyline", "side": "KIA", "prob": 0.48, "phase": "in_play"},
        ]

    def _kbo_state_fn(sport, gid):
        return {"sport": sport, "game_id": gid, "home": "KIA", "away": "NCD",
                "state_diff": 0.0, "frac_elapsed": 0.1, "p0": 0.5,
                "p0_source": "PRIOR", "status": "1st inning"}

    hb = loop.poll_once(sports=["kbo"], live_state_fn=_kbo_state_fn,
                        model_fn=_prod_shaped_model_fn,
                        inplay_fetch_fn=_kbo_fetch, finals_fn=_finals_none,
                        grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    assert hb["n_pairs"] == 0 and hb["n_bets"] == 0
    assert hb["games"][0]["reason"] == "no_model_prob"


# --------------------------------------------------------------------------------------- #
# 7b. kbo-alias-wire-soak lane: kbo_deep_state_fn is dispatched ONLY for sport=="kbo",       #
#     merges additively onto the coarse KBO state, and its failure never sinks the tick     #
#     (capture-only: no model prob, no dispatch change vs the existing no_model_prob path)  #
# --------------------------------------------------------------------------------------- #
def _kbo_fetch_for_deep():
    return [
        {"sport": "kbo", "game_id": "KXKBOGAME-26JUL050100DOOKIW", "venue": "kalshi",
         "market_type": "moneyline", "side": "KIW", "prob": 0.5, "phase": "in_play"},
        {"sport": "kbo", "game_id": "KXKBOGAME-26JUL050100DOOKIW", "venue": "kalshi",
         "market_type": "moneyline", "side": "DOO", "prob": 0.48, "phase": "in_play"},
    ]


def _kbo_state_fn_for_deep(sport, gid):
    return {"sport": sport, "game_id": gid, "home": "KIWOOM", "away": "DOOSAN",
            "state_diff": 0.0, "frac_elapsed": None, "p0": 0.5,
            "p0_source": "PRIOR", "status": "in progress"}


def test_kbo_deep_state_fn_dispatched_only_for_kbo(tmp_path):
    """kbo_deep_state_fn must NEVER be invoked for a non-kbo sport (mirrors the MLB-only
    gating test): calling it on an mlb ticker would mis-key a Kalshi blob that was never
    a KXKBOGAME series."""
    seen = []

    def _spy(gid):
        seen.append(gid)
        return {"inning": 3}

    loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                   inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                   kbo_deep_state_fn=_spy,
                   grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
                   heartbeat_path=tmp_path / "hb.json")
    assert seen == []  # kbo-only gating: mlb never invokes the kbo relay-state wire


def test_kbo_deep_state_fn_merges_additively_onto_coarse_state(tmp_path):
    """The KBO capture-only enricher's row (inning/half/outs/base_state/...) merges onto
    the coarse live state; the tick still has no model_prob (honest no_model_prob skip,
    unchanged from before this wiring) -- capture-only, no dispatch change."""
    captured_state = {}

    def _prod_shaped_model_fn(sport, state):
        captured_state.update(state)
        return None  # mirrors live_model_home_prob's real npb/kbo dispatch (still None)

    def _deep_row(gid):
        return {"game_id": gid, "inning": 8, "half": "top", "outs": 2,
                "base_state": "-2-", "score_home": 1, "score_away": 5, "count": "1-0"}

    hb = loop.poll_once(sports=["kbo"], live_state_fn=_kbo_state_fn_for_deep,
                        model_fn=_prod_shaped_model_fn,
                        inplay_fetch_fn=lambda s: _kbo_fetch_for_deep(),
                        finals_fn=_finals_none, kbo_deep_state_fn=_deep_row,
                        grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    # Still no_model_prob (unchanged existing behavior) -- this wiring adds NO dispatch.
    assert hb["games"][0]["reason"] == "no_model_prob"
    assert hb["n_pairs"] == 0 and hb["n_bets"] == 0
    # But the deep row DID merge onto the state model_fn received.
    assert captured_state.get("inning") == 8
    assert captured_state.get("base_state") == "-2-"
    assert captured_state.get("score_away") == 5
    _no_dollar_field(hb)


def test_kbo_deep_state_fn_exception_leaves_base_path_untouched(tmp_path):
    """An exploding kbo_deep_state_fn must NEVER sink the tick -- the coarse state still
    reaches model_fn unmodified, exactly as if no enricher were injected at all."""
    captured_state = {}

    def _prod_shaped_model_fn(sport, state):
        captured_state.update(state)
        return None

    def _boom(gid):
        raise RuntimeError("relay down")

    hb = loop.poll_once(sports=["kbo"], live_state_fn=_kbo_state_fn_for_deep,
                        model_fn=_prod_shaped_model_fn,
                        inplay_fetch_fn=lambda s: _kbo_fetch_for_deep(),
                        finals_fn=_finals_none, kbo_deep_state_fn=_boom,
                        grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    assert hb["games"][0]["reason"] == "no_model_prob"
    # The base state (home/away/status) is intact -- the exception never removed it.
    assert captured_state.get("home") == "KIWOOM"
    assert captured_state.get("away") == "DOOSAN"
    assert "inning" not in captured_state  # the boom never contributed a row


# --------------------------------------------------------------------------------------- #
# 7c. kbo-reorder-verify lane: ESPN cannot resolve a KBO live state at all -> the deep      #
#     enricher's dispatch (kbo_deep_state_fn) was otherwise UNREACHABLE for kbo. The        #
#     reorder invokes it fail-open for its capture (disk-append) side effect BEFORE the     #
#     early no_live_state return, WITHOUT changing the returned row: reason stays           #
#     "no_live_state" and no decision field is ever populated (capture-only).               #
# --------------------------------------------------------------------------------------- #
def _no_state_fn(sport, gid):
    return None  # ESPN-keyed lookup miss (the exact seam this reorder targets)


def test_kbo_failed_live_state_still_invokes_deep_fn_once_reason_unchanged(tmp_path, monkeypatch):
    # Force the team-name bridge scan to also miss (mirrors an ESPN-side outage/absence)
    # so the offline test never depends on a real npb/kbo network call.
    monkeypatch.setattr(loop._ls, "live_states", lambda *a, **kw: [])
    calls = []

    def _deep_fn(gid):
        calls.append(gid)
        return {"inning": 4}  # return value is discarded by the reorder -- capture only

    hb = loop.poll_once(sports=["kbo"], live_state_fn=_no_state_fn,
                        model_fn=_model_fn,
                        inplay_fetch_fn=lambda s: _kbo_fetch_for_deep(),
                        finals_fn=_finals_none, kbo_deep_state_fn=_deep_fn,
                        grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    assert calls == ["KXKBOGAME-26JUL050100DOOKIW"]  # deep fn fired exactly once
    g = hb["games"][0]
    assert g["reason"] == "no_live_state"            # row output unchanged
    assert g["paired"] is False and g["bet"] is False  # no decision fields populated
    assert "action" not in g and "model_prob" not in g and "tier" not in g
    assert hb["n_pairs"] == 0 and hb["n_bets"] == 0 and hb["n_live"] == 0
    _no_dollar_field(hb)


def test_kbo_failed_live_state_deep_fn_raising_is_swallowed_identical_output(tmp_path, monkeypatch):
    monkeypatch.setattr(loop._ls, "live_states", lambda *a, **kw: [])

    def _boom(gid):
        raise RuntimeError("relay down")

    hb = loop.poll_once(sports=["kbo"], live_state_fn=_no_state_fn,
                        model_fn=_model_fn,
                        inplay_fetch_fn=lambda s: _kbo_fetch_for_deep(),
                        finals_fn=_finals_none, kbo_deep_state_fn=_boom,
                        grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    # Identical output to the non-raising deep fn case above: the exception never
    # surfaces, reason/paired/bet are unaffected.
    g = hb["games"][0]
    assert g["reason"] == "no_live_state"
    assert g["paired"] is False and g["bet"] is False
    assert hb["n_pairs"] == 0 and hb["n_bets"] == 0


def test_non_kbo_sport_never_invokes_deep_fn_on_failed_live_state_path(tmp_path, monkeypatch):
    # mlb (and every other sport) must NOT get this capture-only hook on the
    # no_live_state path -- it is scoped to sport=="kbo" ONLY, per the sanctioned reorder.
    monkeypatch.setattr(loop._ls, "live_states", lambda *a, **kw: [])
    calls = []

    def _spy(gid):
        calls.append(gid)
        return {"inning": 4}

    hb = loop.poll_once(sports=["mlb"], live_state_fn=_no_state_fn, model_fn=_model_fn,
                        inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                        deep_state_fn=_spy,
                        grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    assert calls == []  # non-kbo sport: the reorder's kbo-only gate never fires
    g = hb["games"][0]
    assert g["reason"] == "no_live_state"


# --------------------------------------------------------------------------------------- #
# 8. LANE 3: wnba shadow field appended after on_tick, poisoned-build -> permanent None,    #
#    decision path untouched.                                                               #
# --------------------------------------------------------------------------------------- #
def test_wnba_shadow_field_present_and_none_safe(tmp_path, monkeypatch):
    # Force the shadow's underlying prober to a KNOWN value via the injected singleton,
    # so this test asserts the WIRE (field present, decision untouched) not the adapter math.
    from scripts.platformkit.ingame import wnba_ingame_shadow as wshadow

    class _Stub:
        def shadow_prob(self, sport, home, away, state):
            return 0.71

    monkeypatch.setattr(wshadow, "get_shadow", lambda: _Stub())

    grade_dir = tmp_path / "grade"
    hb = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                        inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                        grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    g = hb["games"][0]
    # additive field present; decision (bet/action/model_prob) is UNCHANGED by it.
    assert g["model_prob_wnba_shadow"] == 0.71
    assert g["bet"] is True and g["model_prob"] == 0.80


def test_wnba_shadow_poisoned_get_shadow_is_none_never_raises(tmp_path, monkeypatch):
    from scripts.platformkit.ingame import wnba_ingame_shadow as wshadow

    def _raise():
        raise RuntimeError("poisoned build")

    monkeypatch.setattr(wshadow, "get_shadow", _raise)

    grade_dir = tmp_path / "grade"
    hb = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                        inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                        grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    g = hb["games"][0]
    assert g["model_prob_wnba_shadow"] is None
    # decision path fully unaffected by the poisoned shadow prober.
    assert g["bet"] is True and g["model_prob"] == 0.80


# --------------------------------------------------------------------------------------- #
# 8b. mechanism-ladder nba shadow: SECOND, independent nba field alongside model_prob_    #
#     nba_shadow (NBARepricer); additive, never decided on, none-safe.                    #
# --------------------------------------------------------------------------------------- #
def test_nba_ladder_shadow_field_present_and_none_safe(tmp_path, monkeypatch):
    from scripts.platformkit.ingame import nba_logistic_pricer as pricer_mod

    class _StubPricer:
        def price(self, margin, frac_elapsed, prior_prob):
            assert margin == 2.0 and frac_elapsed == 0.4 and prior_prob == 0.58
            return 0.63

    monkeypatch.setattr(pricer_mod, "get_pricer", lambda: _StubPricer())

    grade_dir = tmp_path / "grade"
    hb = loop.poll_once(sports=["nba"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                        inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                        grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    g = hb["games"][0]
    # additive field present; the EXISTING nba shadow field + decision are untouched by it.
    assert g["model_prob_nba_ladder_shadow"] == 0.63
    assert "model_prob_nba_shadow" in g
    assert g["bet"] is True and g["model_prob"] == 0.80


def test_nba_ladder_shadow_poisoned_pricer_is_none_never_raises(tmp_path, monkeypatch):
    from scripts.platformkit.ingame import nba_logistic_pricer as pricer_mod

    def _raise():
        raise RuntimeError("poisoned pricer build")

    monkeypatch.setattr(pricer_mod, "get_pricer", _raise)

    grade_dir = tmp_path / "grade"
    hb = loop.poll_once(sports=["nba"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                        inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                        grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    g = hb["games"][0]
    assert g["model_prob_nba_ladder_shadow"] is None
    assert g["bet"] is True and g["model_prob"] == 0.80


def test_nba_ladder_shadow_non_nba_sport_is_none():
    assert loop._nba_ladder_shadow(
        "mlb", {"state_diff": 2.0, "frac_elapsed": 0.4, "p0": 0.58}) is None


def test_nba_ladder_shadow_missing_p0_is_none():
    assert loop._nba_ladder_shadow(
        "nba", {"state_diff": 2.0, "frac_elapsed": 0.4, "p0": None}) is None


# --------------------------------------------------------------------------------------- #
# LANE 1 enrichment: append-after-decision property (on / off / poisoned)                  #
# --------------------------------------------------------------------------------------- #
def _run_one_tick(tmp_path):
    grade_dir = tmp_path / "grade"
    return loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                          inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                          grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                          heartbeat_path=tmp_path / "hb.json")


def _decision_fields(g):
    return {k: g.get(k) for k in ("bet", "action", "tier", "model_prob", "devigged_price",
                                  "p0_source", "reason", "paired")}


def test_enrichment_fields_present_and_none_safe_with_no_sidecars(tmp_path):
    # No fixture sidecars exist -> every enrichment field is honest None, but the
    # decision output is fully present and identical to the pre-enrichment shape.
    hb = _run_one_tick(tmp_path)
    g = hb["games"][0]
    for key in ("xg_home", "xg_away", "xg_asof_min", "spread_bp", "book_thinness",
               "stale_quote", "espn_wp"):
        assert key in g and g[key] is None
    assert g["bet"] is True and g["model_prob"] == 0.80


def test_enrichment_on_vs_off_decision_output_identical(tmp_path, monkeypatch):
    # "on": facade returns real-looking values. "off": facade returns None (as if no
    # sidecar existed). Either way the decision fields (bet/action/model_prob/etc) must
    # be byte-identical -- enrichment can only ever add measurement fields, never change
    # a decision.
    from scripts.platformkit.ingame import ingame_enrichment as enrich

    class _StubOn:
        def fotmob_xg(self, *a, **kw):
            return {"xg_home": 1.2, "xg_away": 0.4, "xg_asof_min": 55.0}

        def book_depth(self, *a, **kw):
            return {"spread_bp": 80.0, "book_thinness": 20, "stale_quote": False}

        def espn_wp(self, *a, **kw):
            return {"espn_wp": 0.63}

    class _StubOff:
        def fotmob_xg(self, *a, **kw):
            return None

        def book_depth(self, *a, **kw):
            return None

        def espn_wp(self, *a, **kw):
            return None

    monkeypatch.setattr(enrich, "get_facade", lambda: _StubOn())
    hb_on = _run_one_tick(tmp_path / "on")
    g_on = hb_on["games"][0]

    monkeypatch.setattr(enrich, "get_facade", lambda: _StubOff())
    hb_off = _run_one_tick(tmp_path / "off")
    g_off = hb_off["games"][0]

    assert _decision_fields(g_on) == _decision_fields(g_off)
    # the "on" run DOES carry the enriched values (proves the wire fired).
    assert g_on["spread_bp"] == 80.0 and g_on["espn_wp"] == 0.63
    # the "off" run is honest None (proves absence never fabricates a value).
    assert g_off["spread_bp"] is None and g_off["espn_wp"] is None


def test_enrichment_poisoned_facade_never_raises_decision_unaffected(tmp_path, monkeypatch):
    from scripts.platformkit.ingame import ingame_enrichment as enrich

    def _raise():
        raise RuntimeError("poisoned enrichment facade")

    monkeypatch.setattr(enrich, "get_facade", _raise)
    hb = _run_one_tick(tmp_path)
    g = hb["games"][0]
    for key in ("xg_home", "xg_away", "xg_asof_min", "spread_bp", "book_thinness",
               "stale_quote", "espn_wp"):
        assert g.get(key) is None
    # decision path fully unaffected by the poisoned enrichment facade.
    assert g["bet"] is True and g["model_prob"] == 0.80


# --------------------------------------------------------------------------------------- #
# LANE 3 persistence: enrichment now PERSISTS into the grade jsonl row (not just the       #
# ops/heartbeat row) -- additive-only, never changes the decision.                         #
# --------------------------------------------------------------------------------------- #
def test_enrichment_persists_into_grade_row(tmp_path, monkeypatch):
    from scripts.platformkit.ingame import ingame_enrichment as enrich

    class _StubOn:
        def fotmob_xg(self, *a, **kw):
            return None  # mlb tick -- fotmob_xg is soccer_intl-only, expect None either way

        def book_depth(self, *a, **kw):
            return {"spread_bp": 42.0, "book_thinness": 7, "stale_quote": False}

        def espn_wp(self, *a, **kw):
            return {"espn_wp": 0.59}

    monkeypatch.setattr(enrich, "get_facade", lambda: _StubOn())
    grade_dir = tmp_path / "grade"
    hb = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                       inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                       grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                       heartbeat_path=tmp_path / "hb.json")
    assert hb["games"][0]["paired"] is True

    grade_files = list(grade_dir.rglob("*.jsonl"))
    assert grade_files, "a grade row must have been written"
    rows = [json.loads(ln) for ln in grade_files[0].read_text(encoding="ascii").splitlines()
            if ln.strip()]
    assert len(rows) == 1
    row = rows[0]
    # The enrichment fields persisted INTO the grade row (not just the ops heartbeat).
    assert row["spread_bp"] == 42.0 and row["book_thinness"] == 7
    assert row["espn_wp"] == 0.59
    # Core pair/alignment keys are untouched by the additive merge.
    assert row["model_prob"] == 0.80 and row["side"] == "home"
    assert set(row.keys()) >= {"sport", "game_id", "ts", "market_prob", "model_prob",
                               "side", "state_summary", "spread_bp", "book_thinness",
                               "stale_quote", "espn_wp"}


# --------------------------------------------------------------------------------------- #
# MLB IDENTITY fields (mlb_batter_id / mlb_pitcher_id / mlb_pitcher_pitch_count /
# mlb_ondeck_id / mlb_bullpen_used): root-cause fix for MLB MODEL_BEHIND -- the live
# model previously saw only 8 crude score/inning/base-out features, no notion of WHO is
# playing. These fields need no facade/import (unlike xg_home/espn_wp) -- they are read
# straight off `state`, which ingame_id_resolver_mlb's deep_state_fn merge already
# populates in production from the SAME statsapi payload the base-out resolver fetches.
# --------------------------------------------------------------------------------------- #
def _state_fn_identity(sport, gid):
    s = _state_fn_prior(sport, gid)
    s.update({"batter_id": 683002, "pitcher_id": 656492, "pitch_count": 61,
              "ondeck_id": 700000, "bullpen_used": [656492]})
    return s


def test_mlb_identity_fields_persist_into_grade_row(tmp_path):
    grade_dir = tmp_path / "grade"
    hb = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_identity, model_fn=_model_fn,
                        inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                        grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    assert hb["games"][0]["paired"] is True

    grade_files = list(grade_dir.rglob("*.jsonl"))
    assert grade_files, "a grade row must have been written"
    rows = [json.loads(ln) for ln in grade_files[0].read_text(encoding="ascii").splitlines()
            if ln.strip()]
    row = rows[0]
    assert row["mlb_batter_id"] == 683002
    assert row["mlb_pitcher_id"] == 656492
    assert row["mlb_pitcher_pitch_count"] == 61
    assert row["mlb_ondeck_id"] == 700000
    assert row["mlb_bullpen_used"] == [656492]
    # core pairing/decision keys are untouched by the additive identity merge.
    assert row["model_prob"] == 0.80 and row["side"] == "home"


def test_mlb_identity_fields_none_safe_when_unresolved(tmp_path):
    # No batter_id/pitcher_id/etc on state (the resolver never bound this tick, e.g. a
    # doubleheader ambiguity or a pregame gap) -> honest None, never fabricated.
    hb = _run_one_tick(tmp_path)
    g = hb["games"][0]
    for key in ("mlb_batter_id", "mlb_pitcher_id", "mlb_pitcher_pitch_count",
               "mlb_ondeck_id", "mlb_bullpen_used"):
        assert key in g and g[key] is None
    assert g["bet"] is True and g["model_prob"] == 0.80


# --------------------------------------------------------------------------------------- #
# LANE 2: grade-write wedge fix (wave-14, 21.8% truncation). Root cause: mlb_live_model's
# old frac_elapsed>=1.0 guard permanently starved model_fn once a game reached bottom-9th/
# extras (ingame_live_state's MLB frac formula saturates at 1.0 there). Fixed at the model
# layer (see test_mlb_live_model.py); THIS file additionally verifies (a) a per-game
# capture failure is ISOLATED per tick -- the roster is rebuilt fresh from the raw liquid
# legs every poll_once call, so a live game whose grade-write fails once is NEVER
# permanently dropped, the very next tick retries unconditionally -- and (b) the failure
# is now COUNTED into the heartbeat (grade_write_fail_by_reason / grade_write_fail_games)
# so an ops freshness SLA can see per-game grade-write lag instead of silence.
# --------------------------------------------------------------------------------------- #
def test_grade_write_failure_counted_and_isolated_per_tick(tmp_path):
    # model_fn raises on the FIRST tick only (simulates an exception inside the per-game
    # model-prob step, e.g. the old extras-saturation bug) -- captured by _process_game's
    # broad except, never sinks the loop, and the SAME live game is retried next tick.
    calls = {"n": 0}

    def _flaky_model_fn(sport, state):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated per-game grade-write failure")
        return 0.80

    grade_dir = tmp_path / "grade"
    hb1 = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior,
                        model_fn=_flaky_model_fn, inplay_fetch_fn=_inplay_fetch,
                        finals_fn=_finals_none, grade_dir=grade_dir,
                        ledger_path=tmp_path / "l.jsonl", heartbeat_path=tmp_path / "hb.json")
    # tick 1: the game was LIVE (a liquid leg existed) but failed to pair -> counted,
    # never silently dropped from games_seen.
    assert hb1["n_pairs"] == 0
    assert len(hb1["games"]) == 1
    g1 = hb1["games"][0]
    assert g1["paired"] is False
    assert str(g1["reason"]).startswith("error:")
    assert hb1["grade_write_fail_by_reason"]  # non-empty: at least one failure bucketed
    assert sum(hb1["grade_write_fail_by_reason"].values()) == 1
    fail_row = hb1["grade_write_fail_games"][0]
    assert fail_row["sport"] == "mlb" and fail_row["reason"].startswith("error:")

    # tick 2: SAME game_id, no injected failure this time -> retries cleanly and pairs.
    # The roster is rebuilt from legs_by_game every call -- nothing permanently removed it.
    hb2 = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior,
                        model_fn=_flaky_model_fn, inplay_fetch_fn=_inplay_fetch,
                        finals_fn=_finals_none, grade_dir=grade_dir,
                        ledger_path=tmp_path / "l.jsonl", heartbeat_path=tmp_path / "hb.json")
    assert hb2["n_pairs"] == 1
    assert hb2["games"][0]["paired"] is True
    assert hb2["grade_write_fail_by_reason"] == {}  # clean tick -> no failures counted
    assert hb2["grade_write_fail_games"] == []


def test_grade_write_fail_counters_empty_on_clean_run(tmp_path):
    # A fully healthy tick carries the new keys but empty -- additive, never noisy.
    hb = _run_one_tick(tmp_path)
    assert hb["grade_write_fail_by_reason"] == {}
    assert hb["grade_write_fail_games"] == []


def test_grade_write_fail_reason_no_model_prob_counted(tmp_path):
    # The exact wave-14 signature (before this lane's model-layer fix): model_fn returns
    # None every tick (e.g. a still-poisoned corpus) -> reason=no_model_prob, counted, and
    # the game stays visible in games_seen every tick (never vanishes silently).
    grade_dir = tmp_path / "grade"
    hb = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior,
                        model_fn=lambda sport, state: None, inplay_fetch_fn=_inplay_fetch,
                        finals_fn=_finals_none, grade_dir=grade_dir,
                        ledger_path=tmp_path / "l.jsonl", heartbeat_path=tmp_path / "hb.json")
    assert hb["n_pairs"] == 0
    assert hb["games"][0]["reason"] == "no_model_prob"
    assert hb["grade_write_fail_by_reason"] == {"no_model_prob": 1}
    assert hb["grade_write_fail_games"][0]["reason"] == "no_model_prob"


# --------------------------------------------------------------------------------------- #
# LANE 1 (wave-16 fix): Kalshi pacing counters surface in the heartbeat, aggregated across  #
# sports; legacy 1-arg fetch stubs (every pre-existing test's inplay_fetch_fn) still work.  #
# --------------------------------------------------------------------------------------- #
def test_heartbeat_carries_pacing_counters_zero_for_legacy_1arg_fetch_fn(tmp_path):
    # _inplay_fetch (used throughout this file) is a 1-arg stub with no stats kwarg --
    # _call_fetch must fall back to the legacy call cleanly, and the counters read 0
    # (no stats.dict was ever populated), never raising and never breaking the decision.
    hb = _run_one_tick(tmp_path)
    assert hb["n_requests_total"] == 0
    assert hb["n_429_total"] == 0
    assert "cycle_duration_sec" in hb and hb["cycle_duration_sec"] >= 0.0
    g = hb["games"][0]
    assert g["bet"] is True and g["model_prob"] == 0.80  # decision path unaffected


def test_heartbeat_aggregates_stats_from_a_pacing_aware_fetch_fn(tmp_path):
    # A fetch_fn that DOES accept **stats (mirrors _default_inplay_fetch's real
    # signature) has its counters aggregated into the heartbeat across every sport
    # polled this cycle -- two sports here, each contributing its own stats dict.
    def _mlb_fetch(sport, stats=None):
        if stats is not None:
            stats["n_requests"] = 4
            stats["n_429"] = 1
        return _inplay_fetch(sport)

    def _soccer_fetch_stats(sport, stats=None):
        if stats is not None:
            stats["n_requests"] = 3
            stats["n_429"] = 0
        return _soccer_fetch(sport)

    def _fetch_router(sport, stats=None):
        if sport == "mlb":
            return _mlb_fetch(sport, stats=stats)
        return _soccer_fetch_stats(sport, stats=stats)

    def _state_fn_by_sport(sport, gid):
        if sport == "soccer_intl":
            s = _state_fn_prior(sport, gid)
            s.update({"home": "Argentina", "away": "Australia"})
            return s
        return _state_fn_prior(sport, gid)

    grade_dir = tmp_path / "grade"
    hb = loop.poll_once(sports=["mlb", "soccer_intl"], live_state_fn=_state_fn_by_sport,
                        model_fn=_model_fn, inplay_fetch_fn=_fetch_router,
                        finals_fn=_finals_none, grade_dir=grade_dir,
                        ledger_path=tmp_path / "l.jsonl", heartbeat_path=tmp_path / "hb.json")
    assert hb["n_requests_total"] == 7   # 4 (mlb) + 3 (soccer_intl)
    assert hb["n_429_total"] == 1        # only mlb's series 429'd
    assert hb["n_pairs"] == 2            # both sports still pair/decide identically


def test_call_fetch_falls_back_to_legacy_1arg_on_typeerror():
    # Directly exercises _call_fetch's fallback: a fetch_fn that raises TypeError
    # if given a stats kwarg (the exact shape of every pre-existing test stub in
    # this file) must still be called successfully via the 1-arg path.
    def _legacy_fetch(sport):
        return _inplay_fetch(sport)

    result = loop._call_fetch(_legacy_fetch, "mlb", {})
    assert result == _inplay_fetch("mlb")


def test_default_inplay_fetch_passes_stagger_sec_to_fetch_inplay(monkeypatch):
    # The production default fetcher must opt IN to inplay_kalshi's pacing
    # (stagger_sec=REQUEST_STAGGER_SEC) rather than relying on fetch_inplay's own
    # (now zero) default -- this is what actually fixes the burst in production.
    from scripts.platformkit.odds_provider import inplay_kalshi as _ik

    seen_kwargs = {}

    def _spy_fetch_inplay(sport, **kwargs):
        seen_kwargs.update(kwargs)
        return []

    monkeypatch.setattr(_ik, "fetch_inplay", _spy_fetch_inplay)
    loop._default_inplay_fetch("mlb", stats={})
    assert seen_kwargs.get("stagger_sec") == _ik.REQUEST_STAGGER_SEC


# --------------------------------------------------------------------------------------- #
# LANE 4b: optional, fail-open depth-capture hook                                          #
# --------------------------------------------------------------------------------------- #
def test_depth_capture_off_by_default_zero_behavior_change(tmp_path):
    # depth_capture_fn defaults to None -> heartbeat carries depth_capture=None and the
    # existing pairing/decision fields are completely unaffected (regression guard).
    hb = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                        inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                        grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    assert hb["depth_capture"] is None
    assert hb["n_pairs"] == 1


def test_depth_capture_fires_on_first_tick_when_supplied(tmp_path):
    calls = []

    def _depth_fn(sports):
        calls.append(list(sports))
        return {"sports": {s: {"n_rows_written": 3} for s in sports}}

    hb = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                        inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                        depth_capture_fn=_depth_fn, depth_tick_counter={},
                        grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    assert len(calls) == 1 and calls[0] == ["mlb"]
    assert hb["depth_capture"]["sports"]["mlb"]["n_rows_written"] == 3


def test_depth_capture_throttled_to_every_nth_tick(tmp_path):
    # Same counter dict threaded across N+2 manual poll_once calls (mirrors how
    # serve_forever threads it): must fire on call 1 and call N+1, never in between.
    calls = []
    counter: dict = {}

    def _depth_fn(sports):
        calls.append(1)
        return {"ok": True}

    n = loop.DEPTH_CAPTURE_EVERY_N_TICKS
    for _ in range(n + 1):
        loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                       inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                       depth_capture_fn=_depth_fn, depth_tick_counter=counter,
                       grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
                       heartbeat_path=tmp_path / "hb.json")
    # Fires on tick index 0 and tick index n (n+1 calls total spanning indices 0..n).
    assert len(calls) == 2


def test_depth_capture_exception_never_breaks_host_cycle(tmp_path):
    def _boom(sports):
        raise RuntimeError("depth feed exploded")

    hb = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                        inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                        depth_capture_fn=_boom, depth_tick_counter={},
                        grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
                        heartbeat_path=tmp_path / "hb.json")
    # The host cycle's own pairing/decision/heartbeat must be completely unaffected.
    assert hb["depth_capture"] is None
    assert hb["n_pairs"] == 1
    assert hb["n_bets"] >= 0  # decision path ran to completion, no propagated exception
    _no_dollar_field(hb)


def test_maybe_capture_depth_none_fn_is_noop():
    assert loop._maybe_capture_depth(None, ["mlb"], {}) is None


def test_serve_forever_depth_capture_off_by_default(tmp_path):
    # depth_capture=False (default) -> the hook never fires across a multi-tick bounded run,
    # even though a stub is capable of being called (proves the flag actually gates it).
    calls = []

    def _depth_fn(sports):
        calls.append(1)
        return {}

    ticks_run = loop.serve_forever(
        clock=lambda s: None, max_ticks=3, sports=["mlb"],
        live_state_fn=_state_fn_prior, model_fn=_model_fn,
        inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
        depth_capture=False,  # explicit default
        grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
        heartbeat_path=tmp_path / "hb.json")
    assert ticks_run == 3
    assert calls == []


def test_serve_forever_injected_depth_capture_fn_fires_without_flag(tmp_path):
    # An explicitly-injected depth_capture_fn should activate even if the caller left the
    # depth_capture bool at its default -- this is what lets a test/offline stub run without
    # also having to flip a separate flag.
    calls = []

    def _depth_fn(sports):
        calls.append(list(sports))
        return {"ok": True}

    ticks_run = loop.serve_forever(
        clock=lambda s: None, max_ticks=1, sports=["mlb"],
        live_state_fn=_state_fn_prior, model_fn=_model_fn,
        inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
        depth_capture_fn=_depth_fn,
        grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
        heartbeat_path=tmp_path / "hb.json")
    assert ticks_run == 1
    assert calls == [["mlb"]]


def test_serve_forever_depth_capture_true_uses_default_fn(tmp_path, monkeypatch):
    # depth_capture=True with no explicit fn wires up _default_depth_capture, which in turn
    # calls odds_provider.depth_capture.run_capture_pass -- verify that real wiring path
    # (not just the injectable stub path) without hitting the network.
    from scripts.platformkit.odds_provider import depth_capture as _dc

    seen = []

    def _fake_run_capture_pass(sports, **kwargs):
        seen.append(list(sports))
        return {"sports": {}, "n_requests_total": 0, "n_429_total": 0}

    monkeypatch.setattr(_dc, "run_capture_pass", _fake_run_capture_pass)
    ticks_run = loop.serve_forever(
        clock=lambda s: None, max_ticks=1, sports=["mlb"],
        live_state_fn=_state_fn_prior, model_fn=_model_fn,
        inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
        depth_capture=True,
        grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
        heartbeat_path=tmp_path / "hb.json")
    assert ticks_run == 1
    assert seen == [["mlb"]]


# --------------------------------------------------------------------------------------- #
# LANE 2: shadow_history hook -- append-only durable evidence store, fail-open.            #
# --------------------------------------------------------------------------------------- #
def test_shadow_history_hook_writes_rows_after_a_real_tick(tmp_path, monkeypatch):
    # NOTE: no shadow_history monkeypatch needed -- poll_once derives history_dir from
    # heartbeat_path's own parent (see the LANE 2 hook comment in inplay_capture_loop.py),
    # so an injected tmp heartbeat_path automatically isolates this test's shadow rows
    # from the real data/cache/ingame_shadow_history/ path.
    from scripts.platformkit.ingame import wnba_ingame_shadow as wshadow

    class _Stub:
        def shadow_prob(self, sport, home, away, state):
            return 0.71

    monkeypatch.setattr(wshadow, "get_shadow", lambda: _Stub())
    hb = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                       inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                       grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
                       heartbeat_path=tmp_path / "hb.json")
    assert hb["games"][0]["model_prob_wnba_shadow"] == 0.71
    hist_dir = tmp_path / "ingame_shadow_history"
    day_files = list(hist_dir.rglob("*.jsonl"))
    assert day_files, "shadow_history must have appended a row for the shadow-carrying game"
    rec = json.loads(day_files[0].read_text(encoding="utf-8").strip())
    assert rec["model_prob_wnba_shadow"] == 0.71 and rec["sport"] == "mlb"


def test_shadow_history_poisoned_module_never_raises_into_poll_once(tmp_path, monkeypatch):
    from scripts.platformkit.ingame import shadow_history as sh

    def _boom(*a, **kw):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(sh, "append_shadow_rows", _boom)
    hb = loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                       inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                       grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
                       heartbeat_path=tmp_path / "hb.json")
    # the heartbeat write (which happens before the hook) still succeeded, and the
    # decision path is fully unaffected by the poisoned shadow_history module.
    assert hb["games"][0]["bet"] is True and hb["games"][0]["model_prob"] == 0.80
    assert (tmp_path / "hb.json").is_file()


def test_shadow_history_history_dir_isolated_from_real_default_via_heartbeat_path(
        tmp_path, monkeypatch):
    """Regression guard: a test/caller that supplies heartbeat_path but never touches
    shadow_history directly must NOT be able to leak rows into the real
    data/cache/ingame_shadow_history/ default (this bit once: poll_once used to call
    append_shadow_rows with no history_dir override at all)."""
    from scripts.platformkit.ingame import shadow_history as sh
    from scripts.platformkit.ingame import wnba_ingame_shadow as wshadow

    class _Stub:
        def shadow_prob(self, sport, home, away, state):
            return 0.71

    monkeypatch.setattr(wshadow, "get_shadow", lambda: _Stub())
    real_default_before = (sh.DEFAULT_HISTORY_DIR.exists()
                           and list(sh.DEFAULT_HISTORY_DIR.rglob("*.jsonl")))
    loop.poll_once(sports=["mlb"], live_state_fn=_state_fn_prior, model_fn=_model_fn,
                   inplay_fetch_fn=_inplay_fetch, finals_fn=_finals_none,
                   grade_dir=tmp_path / "grade", ledger_path=tmp_path / "l.jsonl",
                   heartbeat_path=tmp_path / "hb.json")
    real_default_after = (sh.DEFAULT_HISTORY_DIR.exists()
                          and list(sh.DEFAULT_HISTORY_DIR.rglob("*.jsonl")))
    assert real_default_after == real_default_before, (
        "poll_once must never write shadow rows to the real DEFAULT_HISTORY_DIR "
        "when a tmp heartbeat_path was supplied")
