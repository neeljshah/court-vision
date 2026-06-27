"""Per-file tests for ingame.inplay_grade_run -- the LIVE in-play GRADE harness (Lane G).

OFFLINE + deterministic: the in-play series is an INJECTED fixture and every callback is
INJECTED (no network, no Kalshi, no predictor corpus). Covers the binding contracts:

  1. LEAK-FREE: model_fn is only ever handed history_so_far = series[:i+1] -- it NEVER sees
     series[i+1:] (a spy records the max index it could observe and asserts it equals i).
  2. SINGLE GAME -> INSUFFICIENT_DATA by design (a few ticks < MIN_TICKS, variance not signal).
  3. A constructed MANY-tick favorable series (model leads the market toward the close) ->
     the gate's HONEST verdict BEAT; a market-follow model on the same series NEVER beats.
  4. ALIGNMENT: misaligned / None-prob ticks are SKIPPED (counted), never 0-filled / faked.
  5. NO $ in the output; CLV is in probability space (mean_clv present, no roi/pnl/stake/$).
  6. make_mlb_model_fn is leak-free + corpus-free with an injected predictor stub, and returns
     None (skip) when no synchronized state exists for a tick.
  7. run_live_once with an injected fetch_fn + naive model -> never BEAT (no fake edge).

Run: python -m pytest tests/platformkit/ingame/test_inplay_grade_run.py -q
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.platformkit.ingame import inplay_grade_run as gr


# --------------------------------------------------------------------------------------- #
# fixtures                                                                                 #
# --------------------------------------------------------------------------------------- #
def _ts(i: int) -> str:
    base = datetime(2026, 6, 18, 1, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=60 * i)
    return base.strftime("%Y-%m-%dT%H:%M:%SZ")


def _tick(i: int, prob: float, *, side: str = "home", gid: str = "MLB-G1") -> dict:
    return {
        "sport": "mlb", "game_id": gid, "venue": "kalshi",
        "market_type": "moneyline", "side": side, "ticker": gid,
        "prob": prob, "ts": _ts(i), "phase": "in_play",
    }


def _drift_series(n: int, start: float = 0.50, end: float = 0.65) -> list:
    """A HOME-side market that drifts start->end (closes at end)."""
    out = []
    for i in range(n):
        frac = i / (n - 1) if n > 1 else 0.0
        out.append(_tick(i, start + (end - start) * frac))
    return out


# --------------------------------------------------------------------------------------- #
# 1. LEAK-FREE: model_fn never sees series[i+1:].                                          #
# --------------------------------------------------------------------------------------- #
def test_model_fn_never_sees_future_ticks():
    series = _drift_series(12)
    seen_violation = {"future": False}

    def _spy(tick, history):
        # history must be series[:i+1] -- its last tick is THIS tick, and it must not contain
        # any tick whose ts is strictly after this tick's ts.
        this_ts = str(tick["ts"])
        if history[-1]["ts"] != this_ts:
            seen_violation["future"] = True
        if any(str(h["ts"]) > this_ts for h in history):
            seen_violation["future"] = True
        return float(tick["prob"])  # market-follow (irrelevant here; we only check leakage)

    gr.grade_inplay_series(series, _spy)
    assert seen_violation["future"] is False


# --------------------------------------------------------------------------------------- #
# 2. single game -> INSUFFICIENT_DATA.                                                     #
# --------------------------------------------------------------------------------------- #
def test_single_game_few_ticks_is_insufficient_data():
    series = _drift_series(5)  # 4 scored < MIN_TICKS (8)
    out = gr.grade_inplay_series(series, lambda t, h: min(1.0, float(t["prob"]) + 0.05))
    assert out["verdict"] == "INSUFFICIENT_DATA", out
    assert out["n_input"] == 5
    assert out["n_aligned"] == 5
    assert out["edge_claimed"] is False


def test_empty_series_is_insufficient_data():
    out = gr.grade_inplay_series([], lambda t, h: 0.5)
    assert out["verdict"] == "INSUFFICIENT_DATA"
    assert out["n_input"] == 0 and out["n_aligned"] == 0


# --------------------------------------------------------------------------------------- #
# 3. favorable many-tick series -> the gate's honest verdict BEAT; market-follow never.    #
# --------------------------------------------------------------------------------------- #
def test_leading_model_beats_on_many_tick_favorable_series():
    # Market drifts 0.50 -> 0.65 (closes 0.65); model LEADS it up (+0.05) at every tick.
    series = _drift_series(12, 0.50, 0.65)
    out = gr.grade_inplay_series(series, lambda t, h: min(1.0, float(t["prob"]) + 0.05))
    assert out["verdict"] == "BEAT", out
    assert out["mean_clv"] > 0
    assert out["hit_rate"] > 0.5
    assert out["n_ticks_scored"] == 11  # final close tick excluded
    assert out["side"] == "home"
    assert out["edge_claimed"] is False


def test_market_follow_model_never_beats():
    series = _drift_series(12, 0.50, 0.65)
    out = gr.grade_inplay_series(series, lambda t, h: float(t["prob"]))  # zero edge every tick
    assert out["verdict"] in ("MATCH", "INSUFFICIENT_DATA"), out
    assert out["verdict"] != "BEAT"


def test_none_model_prob_scores_as_no_lean_never_beats():
    # A model that can NEVER price a tick (always None) -> every tick falls back to market-follow
    # -> no lean -> can never beat. n_skipped_model counts the misses honestly.
    series = _drift_series(12, 0.50, 0.65)
    out = gr.grade_inplay_series(series, lambda t, h: None)
    assert out["verdict"] != "BEAT"
    assert out["n_skipped_model"] == 11  # final close tick is not scored


# --------------------------------------------------------------------------------------- #
# 4. ALIGNMENT: misaligned / None-prob ticks are skipped, never faked.                    #
# --------------------------------------------------------------------------------------- #
def test_invalid_prob_ticks_are_skipped_not_filled():
    series = _drift_series(10)
    series.append(_tick(10, 1.5))     # out of [0,1]
    series.append(_tick(11, None))    # missing
    series.append({"prob": 0.5})      # malformed (no ts etc) -> still has valid prob...
    out = gr.grade_inplay_series(series[:12], lambda t, h: float(t["prob"]))
    # the 1.5 and None ticks are dropped; 10 valid drift ticks remain.
    assert out["n_input"] == 12
    assert out["n_aligned"] == 10
    assert out["n_skipped_align"] == 2


def test_side_fn_drops_non_home_ticks():
    home = _drift_series(8)
    away = [_tick(i, 0.4, side="away") for i in range(8, 12)]
    series = home + away
    out = gr.grade_inplay_series(
        series, lambda t, h: float(t["prob"]),
        side_fn=lambda t: str(t.get("side")) == "home")
    assert out["n_aligned"] == 8
    assert out["n_skipped_align"] == 4


# --------------------------------------------------------------------------------------- #
# 5. NO $ in output; CLV in probability space.                                             #
# --------------------------------------------------------------------------------------- #
def test_no_dollar_fields_in_output():
    out = gr.grade_inplay_series(_drift_series(12), lambda t, h: float(t["prob"]) + 0.02)
    assert "mean_clv" in out  # CLV reported (probability space)
    forbidden = ("roi", "pnl", "dollars", "stake", "usd", "profit", "edge_pct", "ev")
    for k in out:
        assert k.lower() not in forbidden, k
    assert out["edge_claimed"] is False


# --------------------------------------------------------------------------------------- #
# 6. make_mlb_model_fn is leak-free + corpus-free with an injected predictor stub.         #
# --------------------------------------------------------------------------------------- #
class _StubPredictor:
    """Stub predictor: predict_live returns P(home) = a simple monotone fn of the score, NEVER
    reading any tick beyond what state_fn supplies (which itself is leak-free)."""
    def __init__(self):
        self.calls = []

    def predict_live(self, home, away, inning, half, home_runs, away_runs):
        self.calls.append((inning, half, home_runs, away_runs))
        lead = home_runs - away_runs
        p = 0.5 + 0.05 * lead
        return {"p_home_win": min(1.0, max(0.0, p))}


def test_make_mlb_model_fn_uses_injected_predictor_and_state():
    stub = _StubPredictor()

    # state_fn derives state from the tick INDEX in history (leak-free: index = len(history)-1).
    def _state_fn(tick, history):
        i = len(history) - 1
        return {"inning": 1 + i // 3, "half": "top", "home_runs": i, "away_runs": 0}

    model_fn = gr.make_mlb_model_fn("NYY", "BOS", _state_fn, predictor=stub)
    series = _drift_series(12)
    out = gr.grade_inplay_series(series, model_fn)
    # The stub priced every scored tick (no model skips) and the model led upward -> BEAT-eligible.
    assert out["n_skipped_model"] == 0
    assert len(stub.calls) == 11  # one per scored tick (final close excluded)
    assert out["verdict"] in ("BEAT", "MATCH", "BEHIND")  # a real gate verdict, not a crash
    assert out["edge_claimed"] is False


def test_make_mlb_model_fn_skips_tick_with_no_state():
    stub = _StubPredictor()
    model_fn = gr.make_mlb_model_fn("NYY", "BOS",
                                    lambda tick, history: None,  # no synchronized state ever
                                    predictor=stub)
    out = gr.grade_inplay_series(_drift_series(12), model_fn)
    assert out["n_skipped_model"] == 11  # every scored tick fell back (no fake number)
    assert out["verdict"] != "BEAT"
    assert stub.calls == []  # predictor never called when state is absent


# --------------------------------------------------------------------------------------- #
# 7. run_live_once with injected fetch_fn + naive model -> never BEAT (no fake edge).      #
# --------------------------------------------------------------------------------------- #
def test_run_live_once_offline_naive_never_beats():
    series = _drift_series(12)
    out = gr.run_live_once("KXMLBGAME-FAKE", fetch_fn=lambda *a, **k: series)
    assert out["market_ref"] == "KXMLBGAME-FAKE"
    assert out["verdict"] != "BEAT"  # naive market-follow can never beat
    assert out["n_aligned"] == 12


def test_run_live_once_fetch_failure_is_insufficient_data():
    def _boom(*a, **k):
        raise RuntimeError("network down")
    out = gr.run_live_once("KXMLBGAME-FAKE", fetch_fn=_boom)
    assert out["verdict"] == "INSUFFICIENT_DATA"
    assert out["n_input"] == 0
