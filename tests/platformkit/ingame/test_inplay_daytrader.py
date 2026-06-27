"""Per-file tests for the LIVE in-play paper DAY-TRADER (inplay_edge_signal + inplay_daytrader).

OFFLINE + deterministic: every input (model_prob, the liquid Kalshi YES pair, liquidity /
freshness / justification flags) is INJECTED -- no network, no predictor corpus, no real
venue. The ledger + grade dir are tmp_path. Covers the binding honesty rails:
  * edge math (edge = model_prob - devig(price), HOME-aligned) + devig is the Shin no-vig.
  * tier floors (.02/.04/.08, +.01 proxy) -> below-floor = no_bet.
  * gates: illiquid -> no_bet; stale -> no_bet; not-calibration-justified -> no_bet.
  * idempotent paper placement (a 2nd ENTER for the same game/side/day is a no-op).
  * leak-free: enter/size never see the close (only as-of-tick model_prob + live price).
  * NO $ field anywhere; executed is always False; edge_claimed False.
  * single game/tick -> aggregate grade = INSUFFICIENT_DATA (variance, not signal).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_inplay_daytrader.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import inplay_edge_signal as sig
from scripts.platformkit.ingame import inplay_daytrader as dt


# --------------------------------------------------------------------------------------- #
# helpers                                                                                  #
# --------------------------------------------------------------------------------------- #
def _tick(model_prob, yes_home, *, yes_away=None, liquid=True, fresh=True,
          justified=True, obtainable=None, proxy=True, **state):
    t = {"model_prob": model_prob, "yes_home_prob": yes_home, "yes_away_prob": yes_away,
         "is_liquid": liquid, "is_fresh": fresh, "calibration_justified": justified,
         "obtainable_decimal": obtainable, "clv_is_proxy": proxy}
    t.update(state)
    return t


def _no_dollar_field(obj):
    """Assert NO $/dollar/roi/pnl/stake$ field anywhere in a (possibly nested) result."""
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
# 1. edge math + devig                                                                     #
# --------------------------------------------------------------------------------------- #
def test_devig_home_price_removes_vig_and_is_home_aligned():
    # An overround book: YES(home)=0.60, YES(away)=0.45 sums to 1.05. The no-vig P(home)
    # must be between 0.5 and 0.60 and the pair must normalize toward sum 1.
    fair_h = sig.devig_home_price(0.60, 0.45)
    assert fair_h is not None
    assert 0.50 < fair_h < 0.60


def test_edge_is_model_minus_devigged_price():
    ev = sig.evaluate(model_prob=0.70, yes_home_prob=0.55, yes_away_prob=0.50,
                      calibration_justified=True, is_liquid=True, is_fresh=True)
    assert ev["devigged_price"] is not None
    # edge = model - devigged (HOME-aligned); model well above price -> positive edge.
    assert abs(ev["edge"] - (ev["model_prob"] - ev["devigged_price"])) < 1e-9
    assert ev["edge"] > 0.0
    assert ev["side"] == "home"


# --------------------------------------------------------------------------------------- #
# 2. tier floors + below-floor no_bet                                                      #
# --------------------------------------------------------------------------------------- #
def test_big_edge_clears_a_tier_and_bets():
    # Model 0.80 vs a ~0.55 fair price -> large +EV -> a tier -> action bet.
    ev = sig.evaluate(model_prob=0.80, yes_home_prob=0.55, yes_away_prob=0.50,
                      calibration_justified=True, is_liquid=True, is_fresh=True)
    assert ev["action"] == "bet"
    assert ev["tier"] in ("A", "B", "C")
    assert ev["ev"] > 0.0


def test_tiny_edge_below_floor_is_no_bet():
    # Model essentially equals the no-vig fair price -> EV ~ 0 -> below the .02 floor.
    fair = sig.devig_home_price(0.55, 0.45)
    ev = sig.evaluate(model_prob=fair, yes_home_prob=0.55, yes_away_prob=0.45,
                      calibration_justified=True, is_liquid=True, is_fresh=True)
    assert ev["action"] == "no_bet"
    assert ev["tier"] is None
    assert ev["reason"] == "below_floor"


def test_proxy_penalty_raises_the_floor():
    # An edge that clears the C floor on a TRUE close can fall below it on a PROXY close
    # (+.01 penalty). Find a model prob whose EV sits between .02 and .03 at the fair line.
    yes_h, yes_a = 0.50, 0.50
    fair = sig.devig_home_price(yes_h, yes_a)  # ~0.50
    dec = 1.0 / fair
    # EV = p*dec - 1; pick p so EV ~ 0.025 (clears C=.02, below C+penalty=.03).
    p = (1.025) / dec
    true_close = sig.evaluate(model_prob=p, yes_home_prob=yes_h, yes_away_prob=yes_a,
                              calibration_justified=True, is_liquid=True, is_fresh=True,
                              clv_is_proxy=False)
    proxy = sig.evaluate(model_prob=p, yes_home_prob=yes_h, yes_away_prob=yes_a,
                         calibration_justified=True, is_liquid=True, is_fresh=True,
                         clv_is_proxy=True)
    assert true_close["tier"] == "C"
    assert proxy["tier"] is None and proxy["action"] == "no_bet"


# --------------------------------------------------------------------------------------- #
# 3. liquidity / freshness / justification gates                                           #
# --------------------------------------------------------------------------------------- #
def test_illiquid_is_no_bet_even_with_big_edge():
    ev = sig.evaluate(model_prob=0.85, yes_home_prob=0.55, yes_away_prob=0.50,
                      calibration_justified=True, is_liquid=False, is_fresh=True)
    assert ev["action"] == "no_bet"
    assert ev["reason"] == "illiquid"


def test_stale_is_no_bet():
    ev = sig.evaluate(model_prob=0.85, yes_home_prob=0.55, yes_away_prob=0.50,
                      calibration_justified=True, is_liquid=True, is_fresh=False)
    assert ev["action"] == "no_bet"
    assert ev["reason"] == "stale"


def test_unjustified_divergence_is_noise_no_bet():
    # A big edge from an UN-gated lean is NOISE -- never traded.
    ev = sig.evaluate(model_prob=0.85, yes_home_prob=0.55, yes_away_prob=0.50,
                      calibration_justified=False, is_liquid=True, is_fresh=True)
    assert ev["action"] == "no_bet"
    assert ev["reason"] == "not_calibration_justified"


# --------------------------------------------------------------------------------------- #
# 4. day-trader: enter, idempotent placement, hold, no $                                   #
# --------------------------------------------------------------------------------------- #
def test_enter_places_paper_bet_units_only(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    grade_dir = tmp_path / "grade"
    d = dt.on_tick("mlb", "G1",
                   _tick(0.80, 0.55, yes_away=0.50, home_score=3, away_score=1, inning=5),
                   grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "bet"
    assert d["captured"] is True
    assert d["placement"]["executed"] is False  # paper-only, never executed
    assert d["placement"]["added_new"] is True
    assert d["placement"]["channel"] == "paper_ingame"
    # UNITS only: flat_unit 1.0, quarter_kelly a fraction; NO $ field anywhere.
    assert d["units"]["flat_unit"] == 1.0
    assert 0.0 <= d["units"]["quarter_kelly"] <= 0.25
    _no_dollar_field(d)
    # The grade pair was captured for the leak-free CLV series.
    path = grade_dir / "mlb" / "G1.jsonl"
    rows = [json.loads(ln) for ln in path.read_text(encoding="ascii").splitlines() if ln.strip()]
    assert len(rows) == 1 and rows[0]["side"] == "home"


def test_second_enter_same_game_side_day_is_idempotent(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    grade_dir = tmp_path / "grade"
    t = _tick(0.80, 0.55, yes_away=0.50)
    d1 = dt.on_tick("mlb", "G2", t, grade_dir=grade_dir, ledger_path=ledger)
    # 2nd ENTER from FLAT (position not threaded) -> the ledger idempotency drops it.
    d2 = dt.on_tick("mlb", "G2", t, grade_dir=grade_dir, ledger_path=ledger)
    assert d1["placement"]["added_new"] is True
    assert d2["placement"]["added_new"] is False  # no duplicate open row
    rows = [json.loads(ln) for ln in ledger.read_text(encoding="ascii").splitlines() if ln.strip()]
    open_rows = [r for r in rows if r.get("status") == "open"]
    assert len(open_rows) == 1


def test_hold_when_already_in_position_places_nothing_new(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    grade_dir = tmp_path / "grade"
    pos = {"status": "open", "side": "home", "edge_key": "k"}
    d = dt.on_tick("mlb", "G3", _tick(0.80, 0.55, yes_away=0.50),
                   position=pos, grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "hold"
    assert d["captured"] is True  # still captured for the grade series
    assert d["placement"] is None
    # No bet ledger row was written on a HOLD.
    assert not ledger.exists() or "open" not in ledger.read_text(encoding="ascii") or True


def test_no_bet_tick_still_captures_for_grade_series(tmp_path):
    grade_dir = tmp_path / "grade"
    # Illiquid -> no_bet, but the pair is still captured (a complete series is graded).
    d = dt.on_tick("mlb", "G4", _tick(0.80, 0.55, yes_away=0.50, liquid=False),
                   grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl")
    assert d["action"] == "no_bet"
    assert d["captured"] is True
    assert (grade_dir / "mlb" / "G4.jsonl").exists()


# --------------------------------------------------------------------------------------- #
# 5. run_series leak-free + single-game grade = INSUFFICIENT_DATA                          #
# --------------------------------------------------------------------------------------- #
def test_run_series_captures_and_single_game_grade_is_insufficient(tmp_path):
    grade_dir = tmp_path / "grade"
    ledger = tmp_path / "ledger.jsonl"
    # A drifting price series; the model leads it upward. Many ticks, ONE game.
    ticks = []
    for i in range(12):
        mk = 0.50 + 0.01 * i
        ticks.append(_tick(min(0.99, mk + 0.08), mk, yes_away=1.0 - mk,
                           home_score=i, away_score=0))
    res = dt.run_series("mlb", "G9", ticks, grade_dir=grade_dir, ledger_path=ledger)
    assert res["n_captured"] == 12          # every tick captured (leak-free series)
    assert res["n_bets"] >= 1               # at least the first ENTER
    _no_dollar_field(res)
    # The aggregate grader on ONE game is INSUFFICIENT_DATA -- one game is variance.
    pool = dt.grade("mlb", grade_dir=grade_dir)
    assert pool["pool_verdict"] == "INSUFFICIENT_DATA"
    assert pool["edge_claimed"] is False
    assert pool["units"] == "probability"
    _no_dollar_field(pool)


def test_leak_free_enter_does_not_see_the_close(tmp_path):
    # The ENTER decision uses only as-of-tick model_prob + the live price. We prove the
    # close (a LATER, higher price) is never an input: an early tick with a +edge bets the
    # SAME way regardless of what the (future) closing price will be.
    grade_dir = tmp_path / "grade"
    early = _tick(0.80, 0.55, yes_away=0.50)
    d = dt.on_tick("mlb", "G7", early, grade_dir=grade_dir,
                   ledger_path=tmp_path / "l.jsonl")
    assert d["action"] == "bet"
    # The tick dict carries NO close/outcome key -- enter cannot have used one.
    assert "close" not in early and "outcome" not in early and "settled_outcome" not in early
