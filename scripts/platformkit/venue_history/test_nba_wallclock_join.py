"""Tests for scripts.platformkit.venue_history.nba_wallclock_join.
Offline, synthetic fixtures only -- no network, no dependency on real disk
corpora (tmp_path builds a throwaway Kalshi-shaped directory)."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.venue_history import nba_wallclock_join as wj


def _states(ts_margins):
    """[(ts, period, margin)] -> state dicts (score fields derived from margin)."""
    return [{"ts": ts, "period": per, "game_clock_s": 100.0,
             "score_home": max(margin, 0), "score_away": max(-margin, 0), "margin": margin}
            for ts, per, margin in ts_margins]


def _candle(ts_epoch, prob, traded=True):
    return {"ts": ts_epoch, "prob": prob, "traded": traded}


def test_join_backward_no_future_leak() -> None:
    """A candle at T must get the LATEST state with ts<=T -- never a future one."""
    states = _states([(100, 1, 0), (200, 1, 5), (300, 2, 10)])
    candles = [_candle(150, 0.6), _candle(250, 0.7), _candle(350, 0.9)]
    out = wj.join_game_states(states, candles)
    assert list(out["ts"]) == [150, 250, 350]
    # candle150 -> state100 (margin 0), NOT state200 (margin 5, which is in the future)
    assert list(out["margin"]) == [0, 5, 10]


def test_join_drops_candles_before_first_state() -> None:
    states = _states([(200, 1, 3)])
    candles = [_candle(50, 0.5), _candle(250, 0.6)]
    out = wj.join_game_states(states, candles)
    assert list(out["ts"]) == [250]  # the ts=50 pre-tipoff candle has no state -> dropped


def test_join_empty_inputs_never_raises() -> None:
    assert wj.join_game_states([], []).empty
    assert wj.join_game_states(_states([(1, 1, 0)]), []).empty
    assert wj.join_game_states([], [_candle(1, 0.5)]).empty


def test_join_accepts_iso_candle_ts() -> None:
    state_ts = wj._epoch("2026-06-14T11:00:00Z")
    candle_ts = wj._epoch("2026-06-14T11:01:00Z")
    states = _states([(state_ts, 1, 2)])
    candles = [_candle("2026-06-14T11:01:00Z", 0.55)]
    out = wj.join_game_states(states, candles)
    assert len(out) == 1
    assert out.iloc[0]["ts"] == candle_ts
    assert out.iloc[0]["margin"] == 2


def test_assemble_output_int64_dtypes() -> None:
    states = _states([(100, 1, 0), (200, 4, -8)])
    candles = [_candle(150, 0.5), _candle(250, 0.02)]
    joined = wj.join_game_states(states, candles)
    out = wj.assemble_output(joined, game_id=401869406, game_date="2026-04-26",
                             market_ticker="KXNBAGAME-26APR26BOSPHI-PHI", home_win=0)
    for col in ("game_id", "ts", "period", "score_home", "score_away", "margin", "outcome_home_win"):
        assert str(out[col].dtype) == "int64", f"{col} is {out[col].dtype}, want int64"
    assert (out["outcome_home_win"] == 0).all()
    assert (out["game_id"] == 401869406).all()


def test_states_from_payload_uses_wallclock() -> None:
    payload = {"plays": [
        {"wallclock": "2026-04-26T23:06:46Z", "period": {"number": 1}, "clock": {"displayValue": "12:00"},
         "homeScore": 0, "awayScore": 0},
        {"wallclock": "2026-04-27T01:31:25Z", "period": {"number": 4}, "clock": {"displayValue": "0.0"},
         "homeScore": 96, "awayScore": 128},
        {"period": {"number": 2}, "clock": {"displayValue": "6:00"},  # missing wallclock -> skipped
         "homeScore": 40, "awayScore": 40},
    ]}
    states = wj.states_from_payload(payload)
    assert len(states) == 2
    assert states[0]["ts"] < states[1]["ts"]
    assert states[-1]["margin"] == 96 - 128


def _write_side(directory: Path, event_ticker: str, side: str, result: str, candles) -> None:
    doc = {"ticker": f"{event_ticker}-{side}", "event_ticker": event_ticker,
           "series_ticker": "KXNBAGAME", "sport": "nba", "result": result, "candles": candles}
    (directory / f"{event_ticker}-{side}.jsonl").write_text(json.dumps(doc) + "\n", encoding="utf-8")


def test_enumerate_games_splits_tail_at_three(tmp_path: Path) -> None:
    """AWAY+HOME tail (always 6 chars) splits at position 3; home_win comes
    from the HOME-side ticker's own settled result, not any external source."""
    et = "KXNBAGAME-26APR26BOSPHI"
    _write_side(tmp_path, et, "BOS", "yes", [_candle(1, 0.7)])
    _write_side(tmp_path, et, "PHI", "no", [_candle(1, 0.3)])
    games = wj.enumerate_games(tmp_path)
    assert len(games) == 1
    g = games[0]
    assert (g.away, g.home) == ("BOS", "PHI")
    assert g.date == "2026-04-26"
    assert g.home_win == 0  # PHI (home) side resolved "no" -> home lost
    assert g.home_ticker == f"{et}-PHI"


def test_enumerate_games_skips_incomplete_event(tmp_path: Path) -> None:
    """Only one side present (no unique home-side settle) -> honestly excluded."""
    et = "KXNBAGAME-26APR26BOSPHI"
    _write_side(tmp_path, et, "BOS", "yes", [_candle(1, 0.7)])
    games = wj.enumerate_games(tmp_path)
    assert games == []
