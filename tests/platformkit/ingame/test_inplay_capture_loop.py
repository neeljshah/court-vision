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
