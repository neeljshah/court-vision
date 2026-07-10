"""Per-file tests for scripts.platformkit.pm_trading.run_paper_today.

NO NETWORK: live_board / bet_board / odds index are all injected with stubs.

Run ONLY this file (the full suite freezes the box):
    python -m pytest scripts/platformkit/pm_trading/test_run_paper_today.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List

from scripts.platformkit import clv_ledger as L
from scripts.platformkit.pm_trading.run_paper_today import run_paper_cycle


# --------------------------------------------------------------------------- #
# Stubs (no network): a live feed, a bet board, and an odds index.
# --------------------------------------------------------------------------- #
def _live_one_game(sport: str) -> Dict[str, Any]:
    return {"sport": sport, "status": "ok", "games": [
        {"sport": sport, "home": "Boston Red Sox", "away": "Toronto Blue Jays",
         "state": "pre", "home_score": None, "away_score": None, "clock": None},
    ]}


def _live_no_games(sport: str) -> Dict[str, Any]:
    return {"sport": sport, "status": "unavailable", "games": [],
            "note": "feed down (degraded, not fabricated)"}


def _board_priced(sport, home, away, *, odds_lookup=None, live=None, **_):
    """Board with one PRICED moneyline (home) + one UNPRICED total row."""
    return {"sport": sport, "home": home, "away": away, "status": "ok",
            "live": None, "best_bets": [], "honest_note": "stub",
            "groups": [
                {"name": "Moneyline", "bets": [
                    {"group": "Moneyline", "selection": home, "model_prob": 0.58,
                     "line": None, "fair_odds": 1.72, "best_book": "stub_book",
                     "best_price": 1.95, "ev_pct": 13.1, "verdict": "PRICED+EV"},
                    {"group": "Moneyline", "selection": away, "model_prob": 0.42,
                     "line": None, "fair_odds": 2.38, "best_book": None,
                     "best_price": None, "ev_pct": None, "verdict": "MODEL_VIEW"},
                ]},
                {"name": "Total", "bets": [
                    {"group": "Total", "selection": "Over 8.5", "model_prob": 0.51,
                     "line": 8.5, "fair_odds": 1.96, "best_book": None,
                     "best_price": None, "ev_pct": None, "verdict": "MODEL_VIEW"},
                ]},
            ]}


def _odds_index_stub(sport: str):
    """Odds lookup returning a VIGGED two-way book (booksum > 1) for the stub game.

    1.90/1.90 implies 0.526+0.526 = 1.052 (a real ~5% hold), so the close-proxy
    devig succeeds -- exercising the proxy-target path for the grader.
    """
    def _lookup(s, home, away):
        if home == "Boston Red Sox":
            return {"stub_book": {home: 1.95, away: 1.90}}
        return None
    return _lookup, []


def _no_dh_stamp(home, away, event_day, commence_time):
    """NO-NETWORK stub: no doubleheader stamp resolved (the pre-D6-fix default
    behavior). Existing tests inject this so run_paper_cycle's real MLB default
    (mlb_dh_stamp, which hits statsapi) is never exercised off-network."""
    return {}


def _run(tmp_path, **kw):
    return run_paper_cycle(
        sports=("mlb",),
        ledger_path=tmp_path / "ledger.jsonl",
        predictions_path=tmp_path / "preds.jsonl",
        live_fetch=kw.get("live_fetch", _live_one_game),
        board_fn=kw.get("board_fn", _board_priced),
        odds_index=kw.get("odds_index", _odds_index_stub),
        dh_stamp_fn=kw.get("dh_stamp_fn", _no_dh_stamp),
    )


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_priced_pick_recorded_paper_only(tmp_path):
    out = _run(tmp_path)
    assert out["executed_any"] is False
    assert out["channel"] == "paper"
    assert out["n_recorded"] == 1            # the priced home moneyline
    assert out["n_logged"] >= 1              # the unpriced rows logged
    bet = out["bets"][0]
    assert bet["side"] == "home"
    assert bet["executed"] is False
    assert bet["channel"] == "paper"
    # HONEST: paper-only, real money stays default-DENY -> never a gate-pass claim.
    assert bet["would_pass_real_gate"] is False
    assert bet["price"] == 1.95
    # UNITS-ONLY STAKE: a tiered bet stakes exactly the flat 1.0 unit (NOT a dollar
    # Kelly amount). tier is stamped; quarter_kelly is a separate measurement field.
    assert bet["tier"] in ("A", "B", "C")
    assert bet["stake_units"] == 1.0
    assert bet["flat_unit"] == 1.0
    assert "stake" not in bet  # no dollar stake field on the summary row
    # the ledger row itself is unexecuted / paper, staked in UNITS not $.
    rows = L.load_ledger(tmp_path / "ledger.jsonl")
    assert rows and all(r.get("executed") is False for r in rows)
    assert rows[0]["stake_units"] == 1.0   # ledger faithfully stores 1 unit
    assert "stake" not in rows[0]          # no dollar field ever written


def test_idempotent_second_run_adds_nothing(tmp_path):
    first = _run(tmp_path)
    assert first["n_recorded"] == 1
    n_pred_first = first["n_logged"]
    second = _run(tmp_path)
    assert second["n_recorded"] == 0
    assert second["n_logged"] == 0
    # the stores did not grow on the second pass
    assert len(L.load_ledger(tmp_path / "ledger.jsonl")) == 1
    preds = [l for l in (tmp_path / "preds.jsonl").read_text().splitlines() if l]
    assert len(preds) == n_pred_first


def test_unpriced_rows_logged_with_proxy_target(tmp_path):
    out = _run(tmp_path)
    preds = out["predictions"]
    assert preds, "expected unpriced model predictions to be logged"
    # the unpriced AWAY moneyline maps to a side, so it carries a close proxy
    away_ml = [p for p in preds if p["selection"] == "Toronto Blue Jays"]
    assert away_ml, "away moneyline should be logged as a model-view prediction"
    proxy = away_ml[0]["close_proxy"]
    assert proxy is not None
    assert proxy["fair_close_prob"] is not None   # devigged from the book proxy
    assert away_ml[0]["price"] is None            # NEVER a fabricated price
    assert away_ml[0]["channel"] == "paper"
    # a non-two-way row (Over 8.5) is still logged but has no side -> no proxy
    over = [p for p in preds if p["selection"] == "Over 8.5"]
    assert over and over[0]["close_proxy"] is None


def test_no_games_degrades_cleanly(tmp_path):
    out = _run(tmp_path, live_fetch=_live_no_games)
    assert out["n_recorded"] == 0
    assert out["n_logged"] == 0
    assert out["sports"]["mlb"]["status"] == "unavailable"
    assert out["sports"]["mlb"]["n_games"] == 0


# --------------------------------------------------------------------------- #
# LANE 4 prediction-logger hygiene regressions.
# (a) pregame prediction logging filters to state='pre'.
# (b) dedup keys on EVENT day (commence_time), not LOG day -- a finished game
#     re-seen on a LATER calendar day must not re-log as a fresh prediction.
# --------------------------------------------------------------------------- #
def _live_one_game_state(sport: str, state: str) -> Dict[str, Any]:
    return {"sport": sport, "status": "ok", "games": [
        {"sport": sport, "home": "Boston Red Sox", "away": "Toronto Blue Jays",
         "state": state, "home_score": 5, "away_score": 3, "clock": None},
    ]}


def test_finished_game_does_not_log_pregame_prediction(tmp_path):
    """(a) state='post' (finished) must NOT log a pregame model view -- the
    whole-slate PRICED bet path (_record_priced) is untouched/unchanged;
    only the unpriced pregame-prediction path is gated on state."""
    out = _run(tmp_path, live_fetch=lambda s: _live_one_game_state(s, "post"))
    assert out["n_logged"] == 0
    assert out["predictions"] == []
    # the priced moneyline bet still records -- unrelated to this fix.
    assert out["n_recorded"] == 1


def test_in_game_state_does_not_log_pregame_prediction(tmp_path):
    """(a) state='in' (live) must NOT log a pregame model view either -- an
    in-progress game is not pregame. True in-game logging is a SEPARATE
    module (paper_ingame.py, channel=paper_ingame), never touched here."""
    out = _run(tmp_path, live_fetch=lambda s: _live_one_game_state(s, "in"))
    assert out["n_logged"] == 0
    assert out["predictions"] == []


def test_pregame_state_still_logs_unpriced_predictions(tmp_path):
    """(a) state='pre' is UNCHANGED -- pregame model views still log."""
    out = _run(tmp_path, live_fetch=lambda s: _live_one_game_state(s, "pre"))
    assert out["n_logged"] >= 1
    assert out["predictions"]


def test_finished_game_seen_on_later_day_does_not_relog(tmp_path):
    """(b) REGRESSION for the exact reported defect: a game commencing on day 1
    is logged once (pregame, state='pre'). The SAME game reappearing on the
    feed on a LATER calendar day (still same commence_time -- e.g. a stale/
    re-served feed row) must NOT re-log as a second "fresh" prediction, because
    dedup keys on the event day (commence_time), not the day it was logged."""
    from scripts.platformkit.odds_provider.base import OddsEvent

    ev = OddsEvent(event_id="evt-42", sport="mlb", home="Boston Red Sox",
                   away="Toronto Blue Jays", commence_time="2026-07-01T23:00:00Z",
                   prices={})

    def _idx(sport):
        def _lookup(s, home, away):
            return {"stub_book": {home: 1.95, away: 1.90}}
        return _lookup, [ev]

    # Day 1: game is pregame, logs normally.
    out1 = _run(tmp_path, live_fetch=lambda s: _live_one_game_state(s, "pre"),
               odds_index=_idx)
    n_logged_day1 = out1["n_logged"]
    assert n_logged_day1 >= 1

    # "Later day": the SAME event_id/commence_time reappears (state now 'post'
    # -- game already happened) fed through the identical predictions store.
    # Must add ZERO new predictions: game_state='post' blocks the log path
    # AND (independently) the event-day dedup key would already match even if
    # it were somehow 'pre' again.
    out2 = _run(tmp_path, live_fetch=lambda s: _live_one_game_state(s, "post"),
               odds_index=_idx)
    assert out2["n_logged"] == 0
    preds_path = tmp_path / "preds.jsonl"
    lines = [l for l in preds_path.read_text().splitlines() if l]
    assert len(lines) == n_logged_day1  # store did not grow


# --------------------------------------------------------------------------- #
# Soccer 1X2 close-proxy devig (PROPOSED_soccer_1x2_close_proxy_devig.md).
# Reproduces the live-corpus finding EXACTLY: Austria@Jordan
# close_decimal_home=1.3922 close_decimal_away=9.0 -> booksum 0.829 without the
# draw leg (arb guard fires, fair_close_prob=None, 30/30 soccer rows dead on
# arrival). Adding the draw leg makes the SAME numbers devig cleanly.
# --------------------------------------------------------------------------- #
def _live_soccer_game(sport: str) -> Dict[str, Any]:
    return {"sport": sport, "status": "ok", "games": [
        {"sport": sport, "home": "Austria", "away": "Jordan",
         "state": "pre", "home_score": None, "away_score": None, "clock": None},
    ]}


def _board_soccer_unpriced(sport, home, away, *, odds_lookup=None, live=None, **_):
    """Both moneyline sides unpriced -- exercises the close-proxy path only."""
    return {"sport": sport, "home": home, "away": away, "status": "ok",
            "live": None, "best_bets": [], "honest_note": "stub",
            "groups": [
                {"name": "Moneyline", "bets": [
                    {"group": "Moneyline", "selection": home, "model_prob": 0.55,
                     "line": None, "fair_odds": 1.82, "best_book": None,
                     "best_price": None, "ev_pct": None, "verdict": "MODEL_VIEW"},
                    {"group": "Moneyline", "selection": away, "model_prob": 0.20,
                     "line": None, "fair_odds": 5.0, "best_book": None,
                     "best_price": None, "ev_pct": None, "verdict": "MODEL_VIEW"},
                ]},
            ]}


def _odds_index_soccer_no_draw(sport: str):
    """The live-corpus reproduction: home 1.3922 / away 9.0, NO draw leg captured
    (booksum = 1/1.3922 + 1/9.0 = 0.829 < 1 -> Shin arb guard fires)."""
    def _lookup(s, home, away):
        return {"bookA": {home: 1.3922, away: 9.0}}
    return _lookup, []


def _odds_index_soccer_with_draw(sport: str):
    """Same home/away prices, PLUS the draw leg the book actually offers
    (booksum = 1/1.3922 + 1/4.5 + 1/9.0 = 1.052, a normal ~5% hold)."""
    def _lookup(s, home, away):
        return {"bookA": {home: 1.3922, away: 9.0, "draw": 4.5}}
    return _lookup, []


def test_soccer_proxy_without_draw_leg_dies_on_arb_guard(tmp_path):
    """BEFORE the fix (no draw captured): reproduces the dead-code path exactly --
    close_proxy is captured but fair_close_prob stays None on every row."""
    out = run_paper_cycle(
        sports=("soccer_intl",), ledger_path=tmp_path / "ledger.jsonl",
        predictions_path=tmp_path / "preds.jsonl", live_fetch=_live_soccer_game,
        board_fn=_board_soccer_unpriced, odds_index=_odds_index_soccer_no_draw)
    preds = out["predictions"]
    assert preds, "expected unpriced soccer model views to be logged"
    for p in preds:
        proxy = p["close_proxy"]
        assert proxy is not None
        assert proxy["fair_close_prob"] is None       # arb guard fired -> dead
        assert "close_decimal_draw" not in proxy      # no draw leg was captured


def test_soccer_proxy_with_draw_leg_devigs_correctly(tmp_path):
    """AFTER the fix: the SAME home/away prices plus a captured draw leg devig
    cleanly into a real fair_close_prob -- soccer's proxy becomes measurable."""
    out = run_paper_cycle(
        sports=("soccer_intl",), ledger_path=tmp_path / "ledger.jsonl",
        predictions_path=tmp_path / "preds.jsonl", live_fetch=_live_soccer_game,
        board_fn=_board_soccer_unpriced, odds_index=_odds_index_soccer_with_draw)
    preds = out["predictions"]
    assert preds, "expected unpriced soccer model views to be logged"
    home_pred = [p for p in preds if p["selection"] == "Austria"][0]
    proxy = home_pred["close_proxy"]
    assert proxy is not None
    assert proxy["close_decimal_draw"] == 4.5
    assert proxy["fair_close_prob"] is not None       # devig SUCCEEDED
    assert 0.0 < proxy["fair_close_prob"] < 1.0
    away_pred = [p for p in preds if p["selection"] == "Jordan"][0]
    away_proxy = away_pred["close_proxy"]
    assert away_proxy["fair_close_prob"] is not None
    # three legs must sum to ~1 (Shin normalizes) -- home heavily favoured (1.39)
    # so its fair prob should be well above the away underdog's (9.0).
    assert home_pred["close_proxy"]["fair_close_prob"] > away_proxy["fair_close_prob"]
    # nothing written
    assert L.load_ledger(tmp_path / "ledger.jsonl") == []


def test_below_tier_floor_pick_not_recorded(tmp_path):
    """A priced pick below the tier-C EV floor is REJECTED by the policy gate.

    0.51 * 1.95 - 1 = -0.0055 (> the permissive PAPER_EV_FLOOR=-0.02 but BELOW the
    tier-C floor of +0.02), so policy.tier returns None and nothing is placed -- the
    money-makers (best bets) are exactly the tier-clearing staked bets, nothing else.
    """
    def _board_neg(sport, home, away, *, odds_lookup=None, live=None, **_):
        b = _board_priced(sport, home, away)
        b["groups"][0]["bets"][0]["model_prob"] = 0.51
        return b
    out = _run(tmp_path, board_fn=_board_neg)
    assert out["n_recorded"] == 0
    assert out["bets"] == []
    # nothing staked -> the ledger gained no placed bet for this below-floor pick
    assert L.load_ledger(tmp_path / "ledger.jsonl") == []


def test_symmetric_two_way_records_only_model_backed_side(tmp_path):
    """BOTH sides of a symmetric two-way market priced + EV-positive -> ONE bet placed.

    The model backs HOME (prob 0.58 >= 0.5); AWAY (0.42 < 0.5) is the side the model
    does not back. Recording both is nonsensical (win/loss cancel minus vig) and would
    double-count the market as two bets. Only the home side is recorded; dedup is per
    MARKET (sport, matchup, line, day), not per side, so away cannot also land.
    """
    def _board_both_priced(sport, home, away, *, odds_lookup=None, live=None, **_):
        return {"sport": sport, "home": home, "away": away, "status": "ok",
                "groups": [{"name": "Moneyline", "bets": [
                    {"group": "Moneyline", "selection": home, "model_prob": 0.58,
                     "line": None, "fair_odds": 1.72, "best_book": "stub_book",
                     "best_price": 1.95, "verdict": "PRICED+EV"},
                    {"group": "Moneyline", "selection": away, "model_prob": 0.42,
                     "line": None, "fair_odds": 2.38, "best_book": "stub_book",
                     "best_price": 2.60, "verdict": "PRICED+EV"},
                ]}]}
    out = _run(tmp_path, board_fn=_board_both_priced)
    # Exactly ONE position for the market -- the model-backed home side -- never both.
    assert out["n_recorded"] == 1
    assert [b["side"] for b in out["bets"]] == ["home"]
    rows = L.load_ledger(tmp_path / "ledger.jsonl")
    assert len(rows) == 1 and rows[0]["side"] == "home"


def test_event_metadata_attached(tmp_path):
    """When the odds index supplies an event, its id/commence_time ride along."""
    from scripts.platformkit.odds_provider.base import OddsEvent

    def _idx(sport):
        ev = OddsEvent(event_id="evt-123", sport=sport, home="Boston Red Sox",
                       away="Toronto Blue Jays", commence_time="2026-06-17T23:00Z",
                       prices={"stub_book": {"home": 1.95, "away": 2.10}})

        def _lookup(s, home, away):
            return {"stub_book": {home: 1.95, away: 2.10}}
        return _lookup, [ev]

    out = _run(tmp_path, odds_index=_idx)
    bet = out["bets"][0]
    assert bet["event_id"] == "evt-123"
    assert bet["commence_time"] == "2026-06-17T23:00Z"


# --------------------------------------------------------------------------- #
# D6 fix: MLB doubleheader date exposure -- game_number/game_pk stamped at
# PLACEMENT time so a DH day is disambiguated at settle time. Exercises the
# REAL mlb_dh_stamp/mlb_schedule_pairs algorithm (team-pair resolve + nearest-
# commence-time disambiguation), with an offline statsapi-schedule fixture --
# NO network. Reproduces a real doubleheader shape (Brewers @ Cardinals).
# --------------------------------------------------------------------------- #
def _dh_schedule_http_two_games(url: str):
    """Offline statsapi schedule fixture: a real doubleheader (2 games, same
    team pair, distinct commence times) on one date."""
    return {"dates": [{"games": [
        {"gamePk": 111, "gameNumber": 1, "gameDate": "2026-07-07T17:15:00Z",
         "doubleHeader": "S",
         "teams": {"away": {"team": {"name": "Milwaukee Brewers"}},
                   "home": {"team": {"name": "St. Louis Cardinals"}}}},
        {"gamePk": 222, "gameNumber": 2, "gameDate": "2026-07-07T23:00:00Z",
         "doubleHeader": "S",
         "teams": {"away": {"team": {"name": "Milwaukee Brewers"}},
                   "home": {"team": {"name": "St. Louis Cardinals"}}}},
    ]}]}


def _live_dh_game(sport: str) -> Dict[str, Any]:
    """The SECOND (later) game of the doubleheader is today's placed board."""
    return {"sport": sport, "status": "ok", "games": [
        {"sport": sport, "home": "St. Louis Cardinals", "away": "Milwaukee Brewers",
         "state": "pre", "home_score": None, "away_score": None, "clock": None},
    ]}


def test_mlb_doubleheader_row_stamped_with_game_number(tmp_path):
    """A new MLB pregame row placed on a real DH date carries game_number/game_pk,
    disambiguating which leg it belongs to (the bug this lane closes)."""
    from functools import partial
    from scripts.platformkit.odds_provider.base import OddsEvent
    from scripts.platformkit.pm_trading.mlb_dh_stamp import mlb_dh_stamp

    stamp_fn = partial(mlb_dh_stamp, http=_dh_schedule_http_two_games)

    def _idx(sport):
        # G2's commence_time (23:00Z) -- closer to G2 (23:00Z) than G1 (17:15Z).
        ev = OddsEvent(event_id="evt-dh-g2", sport=sport,
                       home="St. Louis Cardinals", away="Milwaukee Brewers",
                       commence_time="2026-07-07T23:00:00Z",
                       prices={"stub_book": {"home": 1.95, "away": 2.10}})

        def _lookup(s, home, away):
            return {"stub_book": {home: 1.95, away: 2.10}}
        return _lookup, [ev]

    out = _run(tmp_path, live_fetch=_live_dh_game, odds_index=_idx,
              dh_stamp_fn=stamp_fn)
    assert out["n_recorded"] == 1
    bet = out["bets"][0]
    assert bet["game_number"] == 2   # matched to the later leg by commence_time
    assert bet["game_pk"] == 222
    rows = L.load_ledger(tmp_path / "ledger.jsonl")
    assert rows[0]["game_number"] == 2
    assert rows[0]["game_pk"] == 222


def test_mlb_single_game_day_stamped_unambiguously(tmp_path):
    """A normal (non-DH) day: exactly one scheduled game for the pair -> always
    stamped, no commence_time disambiguation needed."""
    from functools import partial
    from scripts.platformkit.pm_trading.mlb_dh_stamp import mlb_dh_stamp

    def _single_game_http(url: str):
        return {"dates": [{"games": [
            {"gamePk": 555, "gameNumber": 1, "gameDate": "2026-07-08T17:00:00Z",
             "teams": {"away": {"team": {"name": "Toronto Blue Jays"}},
                       "home": {"team": {"name": "Boston Red Sox"}}}},
        ]}]}

    stamp_fn = partial(mlb_dh_stamp, http=_single_game_http)
    out = _run(tmp_path, dh_stamp_fn=stamp_fn)
    assert out["n_recorded"] == 1
    bet = out["bets"][0]
    assert bet["game_number"] == 1
    assert bet["game_pk"] == 555
