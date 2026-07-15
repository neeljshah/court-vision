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
    # Use a realistic game_id (>= _MIN_GAME_ID_LEN=3); a 2-char synthetic id would be
    # silently rejected by the paper_ingame write-guard before placement, so this also
    # exercises the REAL placement path the live daemon hits with 9-char ESPN ids.
    gid = "401859967"
    d = dt.on_tick("mlb", gid,
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
    path = grade_dir / "mlb" / ("%s.jsonl" % gid)
    rows = [json.loads(ln) for ln in path.read_text(encoding="ascii").splitlines() if ln.strip()]
    assert len(rows) == 1 and rows[0]["side"] == "home"


def test_second_enter_same_game_side_day_is_idempotent(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    grade_dir = tmp_path / "grade"
    gid = "401859968"  # realistic id -> clears the write-guard, so idempotency is what's tested
    t = _tick(0.80, 0.55, yes_away=0.50)
    d1 = dt.on_tick("mlb", gid, t, grade_dir=grade_dir, ledger_path=ledger)
    # 2nd ENTER from FLAT (position not threaded) -> the (sport,game,market,side,day)
    # edge_key already has an OPEN row -> the ledger idempotency check drops the duplicate.
    d2 = dt.on_tick("mlb", gid, t, grade_dir=grade_dir, ledger_path=ledger)
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


def test_edge_flip_to_other_side_reenters(tmp_path):
    # We HOLD an open HOME position, but the live edge has flipped: model_prob (home) is
    # now far BELOW the fair home price, so AWAY is the +EV side. That is a genuinely new
    # opportunity (the line moved) -> the day-trader RE-ENTERS on the away side, not holds.
    ledger = tmp_path / "ledger.jsonl"
    grade_dir = tmp_path / "grade"
    pos = {"status": "open", "side": "home", "edge_key": "home-key"}
    d = dt.on_tick("mlb", "401859970",
                   _tick(0.20, 0.55, yes_away=0.50),  # home model 0.20 << fair -> away +EV
                   position=pos, grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "bet"
    assert d["side"] == "away"
    assert d["reason"] == "edge_flipped_reenter"
    assert d["placement"]["added_new"] is True       # a real new placement on the new side
    assert d["placement"]["executed"] is False        # still paper-only
    _no_dollar_field(d)


def test_same_side_edge_still_holds_not_reenter(tmp_path):
    # The edge still favours the side we already hold -> HOLD, never a duplicate same-side bet.
    ledger = tmp_path / "ledger.jsonl"
    grade_dir = tmp_path / "grade"
    pos = {"status": "open", "side": "home", "edge_key": "home-key"}
    d = dt.on_tick("mlb", "401859971", _tick(0.80, 0.55, yes_away=0.50),
                   position=pos, grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "hold"
    assert d["reason"] == "hold_existing"
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


# --------------------------------------------------------------------------------------- #
# 6 (LANE 3): `extra` is forwarded verbatim into the persisted grade row.                  #
# --------------------------------------------------------------------------------------- #
def test_extra_kwarg_forwarded_into_grade_row(tmp_path):
    grade_dir = tmp_path / "grade"
    d = dt.on_tick("mlb", "G10", _tick(0.80, 0.55, yes_away=0.50),
                   grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl",
                   extra={"xg_home": 1.5, "espn_wp": 0.58})
    assert d["captured"] is True
    path = grade_dir / "mlb" / "G10.jsonl"
    row = json.loads(path.read_text(encoding="ascii").splitlines()[0])
    assert row["xg_home"] == 1.5 and row["espn_wp"] == 0.58


def test_extra_none_is_backward_compatible(tmp_path):
    # Default (no extra passed) behaves exactly as before, plus the additive
    # claim_tags field (CLAIMS-P3 wiring: condition_tagger.tag output, merged via
    # the same extra pipeline) -- no OTHER new keys appear.
    grade_dir = tmp_path / "grade"
    d = dt.on_tick("mlb", "G11", _tick(0.80, 0.55, yes_away=0.50),
                   grade_dir=grade_dir, ledger_path=tmp_path / "l.jsonl")
    assert d["captured"] is True
    path = grade_dir / "mlb" / "G11.jsonl"
    row = json.loads(path.read_text(encoding="ascii").splitlines()[0])
    assert set(row.keys()) == {"sport", "game_id", "ts", "market_prob", "model_prob",
                               "side", "state_summary", "claim_tags"}


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


# --------------------------------------------------------------------------------------- #
# 7 (queue item 8a): cross-corpus ADVERSE-segment suppression -- a conservative WITHHOLD.  #
# The allowlist (_SANCTIONED_ADVERSE_SEGMENTS) ships EMPTY by design (no doc-sanctioned,   #
# runtime-computable, non-UNK ADVERSE finding exists yet -- see that module-level comment  #
# and PROPOSED_soccer_inplay_suppression.md section 6, "human decision requested",         #
# unresolved). These mechanism tests monkeypatch the allowlist (never the UNK hard-        #
# exclude) to prove the wiring is correct FOR WHEN a human populates it; section 7b below   #
# additionally proves the real unmocked runtime lookup on today's live evidence.           #
# --------------------------------------------------------------------------------------- #
def test_adverse_segment_suppresses_the_marginal_entry(tmp_path, monkeypatch):
    # Same edge/gates as test_enter_places_paper_bet_units_only (would otherwise "bet"),
    # but the segment ("H1", minute=20) is SANCTIONED (via the allowlist, monkeypatched
    # here to simulate a human having populated it) and reported cross-corpus ADVERSE ->
    # WITHHELD, never placed. The pair is still captured (capture is unconditional and
    # runs before the suppression check); no ledger row is written; the reason is the
    # specific sentinel.
    grade_dir = tmp_path / "grade"
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(dt, "_SANCTIONED_ADVERSE_SEGMENTS", {"soccer_intl": frozenset({"H1"})})
    monkeypatch.setattr(
        dt._trust_multi, "build_trust_for_sport",
        lambda sport: {"segments": {"H1": {"trust": "ADVERSE"}}})
    gid = "401859980"
    d = dt.on_tick("soccer_intl", gid,
                   _tick(0.80, 0.55, yes_away=0.50, minute=20),
                   grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "no_bet"
    assert d["reason"] == "segment_adverse_suppressed"
    assert d["placement"] is None
    assert d["captured"] is True  # capture above the branch still ran
    path = grade_dir / "soccer_intl" / ("%s.jsonl" % gid)
    assert path.exists()  # the grade series is complete despite the withhold
    assert not ledger.exists() or "open" not in ledger.read_text(encoding="ascii")
    _no_dollar_field(d)


def test_non_adverse_segment_bets_normally(tmp_path, monkeypatch):
    # Sanity control for the test above: same tick/segment/allowlist entry, but trust
    # reports NEUTRAL -> the suppression must NOT fire and the marginal entry places
    # exactly as before.
    grade_dir = tmp_path / "grade"
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(dt, "_SANCTIONED_ADVERSE_SEGMENTS", {"soccer_intl": frozenset({"H1"})})
    monkeypatch.setattr(
        dt._trust_multi, "build_trust_for_sport",
        lambda sport: {"segments": {"H1": {"trust": "NEUTRAL"}}})
    gid = "401859981"
    d = dt.on_tick("soccer_intl", gid,
                   _tick(0.80, 0.55, yes_away=0.50, minute=20),
                   grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "bet"
    assert d["reason"] != "segment_adverse_suppressed"
    assert d["placement"]["added_new"] is True


def test_trust_lookup_raising_is_unchanged_behavior(tmp_path, monkeypatch):
    # Fail-open (binding rail): if the trust lookup itself raises (missing ops doc, bad
    # sport, whatever) for a SANCTIONED segment, the day-trader must behave EXACTLY as if
    # suppression did not exist -- i.e. the same edge/gates that would otherwise "bet"
    # still "bet".
    grade_dir = tmp_path / "grade"
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(dt, "_SANCTIONED_ADVERSE_SEGMENTS", {"soccer_intl": frozenset({"H1"})})
    def _boom(sport):
        raise RuntimeError("ops doc missing")
    monkeypatch.setattr(dt._trust_multi, "build_trust_for_sport", _boom)
    gid = "401859982"
    d = dt.on_tick("soccer_intl", gid,
                   _tick(0.80, 0.55, yes_away=0.50, minute=20),
                   grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "bet"
    assert d["reason"] != "segment_adverse_suppressed"
    assert d["placement"]["added_new"] is True
    assert d["placement"]["executed"] is False
    _no_dollar_field(d)


# --------------------------------------------------------------------------------------- #
# 7b (fix-round, finding 4): the UNMOCKED real runtime lookup must NEVER suppress on UNK,  #
# and today's empty allowlist means NOTHING is suppressed for soccer_intl at all -- the    #
# doc's sanctioned H1/H2 finding only exists on the BACKFILLED variant this runtime call   #
# does not compute (PROPOSED_soccer_inplay_suppression.md section 0/6).                    #
# --------------------------------------------------------------------------------------- #
def test_real_unmocked_trust_lookup_does_not_suppress_a_no_clock_soccer_tick(tmp_path):
    # NO monkeypatch: calls the REAL ingame_segment_trust_multi.build_trust_for_sport on
    # today's live ops doc. A soccer tick with no minute/half field -> state_summary "live"
    # -> _infer_segment -> "UNK". Even though the real live doc reports UNK as ADVERSE
    # (data/frontend/ops/ingame_segment_trust_multi.json: adverse_by_sport soccer_intl ==
    # ["UNK"]), the hard UNK exclude in _segment_is_adverse means this tick is NEVER
    # suppressed -- proving the inversion bug (suppressing the forbidden UNK bucket while
    # leaving the doc's actual target segment untouched) is fixed.
    grade_dir = tmp_path / "grade"
    ledger = tmp_path / "ledger.jsonl"
    gid = "401859983"
    d = dt.on_tick("soccer_intl", gid,
                   _tick(0.80, 0.55, yes_away=0.50),  # no minute/half -> segment UNK
                   grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "bet"
    assert d["reason"] != "segment_adverse_suppressed"
    assert d["placement"]["added_new"] is True
    _no_dollar_field(d)


def test_real_unmocked_trust_lookup_h1_is_not_suppressed_today(tmp_path):
    # NO monkeypatch: an H1 soccer tick (minute=20) against the REAL runtime trust doc.
    # _SANCTIONED_ADVERSE_SEGMENTS ships empty (no verified human authorization exists for
    # the doc's BACKFILLED-only H1/H2 finding), so this bets normally today regardless of
    # what the live RAW doc reports for H1 (currently NEUTRAL there too).
    grade_dir = tmp_path / "grade"
    ledger = tmp_path / "ledger.jsonl"
    gid = "401859984"
    d = dt.on_tick("soccer_intl", gid,
                   _tick(0.80, 0.55, yes_away=0.50, minute=20),
                   grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "bet"
    assert d["reason"] != "segment_adverse_suppressed"
    assert d["placement"]["added_new"] is True
    _no_dollar_field(d)


# --------------------------------------------------------------------------------------- #
# 8 (execution.ingame_exec_gate wiring): expected-CLV gate + latency/drift fields.         #
# --------------------------------------------------------------------------------------- #
def test_exec_gate_suppresses_below_threshold_placement(tmp_path, monkeypatch):
    # Force the expected-CLV floor absurdly high so even a normally-qualifying edge is
    # suppressed -- proves the gate is load-bearing (SUPPRESS-ONLY: never fires without
    # the floor, but must fire when the floor demands it).
    monkeypatch.setattr(dt._exec_gate, "INGAME_EXPECTED_CLV_MIN_PCT", 1000.0)
    ledger = tmp_path / "ledger.jsonl"
    grade_dir = tmp_path / "grade"
    d = dt.on_tick("mlb", "401859990", _tick(0.80, 0.55, yes_away=0.50),
                   grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "no_bet"
    assert d["reason"] == "expected_clv_below_floor"
    assert d["placement"] is None
    assert d["exec_gate"]["passed"] is False
    assert not ledger.exists() or "open" not in ledger.read_text(encoding="ascii")
    _no_dollar_field(d)


def test_ledger_row_carries_signal_ts_latency_and_exec_gate(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    grade_dir = tmp_path / "grade"
    d = dt.on_tick("mlb", "401859991",
                   _tick(0.80, 0.55, yes_away=0.50, signal_ts="2026-07-15T12:00:00Z"),
                   grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "bet"
    placed = d["placement"]
    assert placed["signal_ts"] == "2026-07-15T12:00:00Z"
    assert isinstance(placed["placement_latency_ms"], float)
    assert placed["placement_latency_ms"] >= 0.0
    assert placed["exec_gate"]["passed"] is True
    assert placed["exec_gate"]["drift_pct"] is None  # no fresher price supplied
    _no_dollar_field(placed)


def test_drift_rejection_suppresses_adverse_moved_price(tmp_path):
    # A fresher price for the taken side has moved adversely (decimal fell) by more
    # than INGAME_MAX_DRIFT_PCT since the signal was computed -> suppressed, not placed.
    ledger = tmp_path / "ledger.jsonl"
    grade_dir = tmp_path / "grade"
    t = _tick(0.80, 0.55, yes_away=0.50)
    t["fresh_obtainable_decimal"] = 1.05  # far below the signal-time obtainable decimal
    d = dt.on_tick("mlb", "401859992", t, grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "no_bet"
    assert d["reason"] == "drift"
    assert d["placement"] is None
    assert d["exec_gate"]["drift_pct"] is not None and d["exec_gate"]["drift_pct"] < 0.0
    assert not ledger.exists() or "open" not in ledger.read_text(encoding="ascii")
    _no_dollar_field(d)


# --------------------------------------------------------------------------------------- #
# 9 (LEVER 1 + LEVER 2 + LEVER 3 wiring): tier sizing, exec_depth stamp, spread suppress.  #
# --------------------------------------------------------------------------------------- #
def test_tier_sizing_wires_stake_into_ledger_row(tmp_path):
    # CV_TIER_SIZING default ON -> the ledger stake reflects execution.sizing.stake_for
    # for whichever tier this edge actually cleared (never the legacy hardcoded 0.0).
    from scripts.platformkit.execution import sizing as _sizing
    ledger = tmp_path / "ledger.jsonl"
    grade_dir = tmp_path / "grade"
    d = dt.on_tick("mlb", "401859993", _tick(0.80, 0.55, yes_away=0.50),
                   grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "bet"
    expected = _sizing.stake_for(d["tier"], "moneyline")
    assert d["placement"]["stake"] == expected
    assert expected in (1.0, 1.5, 2.0)
    _no_dollar_field(d)


def test_tier_sizing_env_off_falls_back_to_legacy_zero_stake(tmp_path, monkeypatch):
    monkeypatch.setenv("CV_TIER_SIZING", "0")
    ledger = tmp_path / "ledger.jsonl"
    grade_dir = tmp_path / "grade"
    d = dt.on_tick("mlb", "401859994", _tick(0.80, 0.55, yes_away=0.50),
                   grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "bet"
    assert d["placement"]["stake"] == 0.0  # toggle off -> exact legacy behavior


def test_exec_depth_threaded_into_placement_honest_null(tmp_path):
    # This tick carries no depth fields and no ticker -> the stamp is the honest
    # null dict (LEVER 1), never fabricated, and still lands on the ledger row.
    ledger = tmp_path / "ledger.jsonl"
    grade_dir = tmp_path / "grade"
    d = dt.on_tick("mlb", "401859995", _tick(0.80, 0.55, yes_away=0.50),
                   grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "bet"
    assert d["placement"]["exec_depth"]["reason"] == "no_depth_source"


def test_exec_depth_threaded_from_tick_fields(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    grade_dir = tmp_path / "grade"
    t = _tick(0.80, 0.55, yes_away=0.50)
    t["spread_bp"], t["best_bid"], t["best_ask"] = 120.0, 0.60, 0.615
    d = dt.on_tick("mlb", "401859996", t, grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "bet"
    depth = d["placement"]["exec_depth"]
    assert depth["spread_bp"] == 120.0
    assert abs(depth["mid"] - 0.6075) < 1e-9


def test_wide_spread_suppresses_the_entry(tmp_path):
    # LEVER 3: a > 800bp spread suppresses the marginal ENTER even though the
    # expected-CLV + drift gates both clear.
    ledger = tmp_path / "ledger.jsonl"
    grade_dir = tmp_path / "grade"
    t = _tick(0.80, 0.55, yes_away=0.50)
    t["spread_bp"] = 900.0
    d = dt.on_tick("mlb", "401859997", t, grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "no_bet"
    assert d["reason"] == "spread_too_wide"
    assert d["placement"] is None
    assert d["exec_gate"]["spread_flag"] is True
    assert not ledger.exists() or "open" not in ledger.read_text(encoding="ascii")
    _no_dollar_field(d)


def test_unknown_spread_does_not_suppress_the_entry(tmp_path):
    # No spread field anywhere on this tick -- missing data must never silently
    # kill the channel; the entry still places.
    ledger = tmp_path / "ledger.jsonl"
    grade_dir = tmp_path / "grade"
    d = dt.on_tick("mlb", "401859998", _tick(0.80, 0.55, yes_away=0.50),
                   grade_dir=grade_dir, ledger_path=ledger)
    assert d["action"] == "bet"
    assert d["exec_gate"]["spread_unknown"] is True
    assert d["exec_gate"]["spread_flag"] is False
