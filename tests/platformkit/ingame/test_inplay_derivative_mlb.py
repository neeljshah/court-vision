"""Per-file tests for the MLB in-play totals/run-line derivative channel:
mlb_deriv_align (pure alignment), inplay_derivative_mlb (capture+gate+place),
mlb_deriv_settle (settlement).

OFFLINE + deterministic: fetch/state/surface/finals are all injected -- no
network, no real Kalshi feed, no real corpus predictor. Ledger + grade dir are
tmp_path. Covers: exact-line alignment, interpolation between adjacent
computed lines, no-extrapolation skip, over/under side handling, divergence
suppression, idempotent placement, push/void settle.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_inplay_derivative_mlb.py -q
"""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit import clv_ledger as clv
from scripts.platformkit.ingame import inplay_derivative_mlb as deriv
from scripts.platformkit.ingame import mlb_deriv_align as align
from scripts.platformkit.ingame import mlb_deriv_settle as settle


# --------------------------------------------------------------------------------------- #
# mlb_deriv_align -- pure alignment                                                       #
# --------------------------------------------------------------------------------------- #

_SURFACE = {
    "over_6.5": 0.85, "over_7.5": 0.75, "over_8.5": 0.55, "over_9.5": 0.35, "over_10.5": 0.20,
    "rl_home_minus15": 0.60, "rl_away_plus15": 0.40,
}


def test_interp_exact_grid_line():
    assert align.interp_over_prob(_SURFACE, 8.5) == 0.55


def test_interp_between_adjacent_lines():
    # halfway between 7.5 (0.75) and 8.5 (0.55) -> 0.65
    got = align.interp_over_prob(_SURFACE, 8.0)
    assert abs(got - 0.65) < 1e-9


def test_interp_never_extrapolates_below_grid():
    assert align.interp_over_prob(_SURFACE, 5.5) is None


def test_interp_never_extrapolates_above_grid():
    assert align.interp_over_prob(_SURFACE, 11.5) is None


def test_align_total_over_side():
    tick = {"market_type": "total", "line": 8.5, "prob": 0.50, "side": "Over 8.5"}
    out = align.align_tick(tick, _SURFACE, "New York Yankees", "Boston Red Sox")
    assert out["logical_side"] == "over"
    assert out["model_prob"] == 0.55
    assert out["market_prob"] == 0.50


def test_align_total_under_side_flips_model_prob():
    tick = {"market_type": "total", "line": 8.5, "prob": 0.45, "side": "Under 8.5"}
    out = align.align_tick(tick, _SURFACE, "New York Yankees", "Boston Red Sox")
    assert out["logical_side"] == "under"
    assert abs(out["model_prob"] - (1.0 - 0.55)) < 1e-9


def test_align_total_no_coverage_outside_grid():
    tick = {"market_type": "total", "line": 12.5, "prob": 0.5, "side": "Over 12.5"}
    assert align.align_tick(tick, _SURFACE, "NYY", "BOS") is None


def test_align_spread_home_side_match():
    tick = {"market_type": "spread", "line": 1.5, "prob": 0.55, "side": "Yankees"}
    out = align.align_tick(tick, _SURFACE, "New York Yankees", "Boston Red Sox")
    assert out["logical_side"] == "home_favorite"
    assert out["model_prob"] == 0.60


def test_align_spread_away_side_match():
    tick = {"market_type": "spread", "line": 1.5, "prob": 0.45, "side": "Red Sox"}
    out = align.align_tick(tick, _SURFACE, "New York Yankees", "Boston Red Sox")
    assert out["logical_side"] == "away_dog"
    assert out["model_prob"] == 0.40


def test_align_spread_wrong_line_no_coverage():
    tick = {"market_type": "spread", "line": 2.5, "prob": 0.5, "side": "Yankees"}
    assert align.align_tick(tick, _SURFACE, "New York Yankees", "Boston Red Sox") is None


def test_align_spread_no_side_match_is_honest_skip():
    tick = {"market_type": "spread", "line": 1.5, "prob": 0.5, "side": "Dodgers"}
    assert align.align_tick(tick, _SURFACE, "New York Yankees", "Boston Red Sox") is None


def test_ticker_team_codes():
    assert align.ticker_team_codes("KXMLBTOTAL-25JUL18NYYBOS") == ("NYY", "BOS")
    assert align.ticker_team_codes("garbage") is None


def test_market_key_and_ledger_side():
    assert align.market_key("total", 8.5, "over") == "total_8.5_over"
    assert align.ledger_side("over") == "home"
    assert align.ledger_side("under") == "away"
    assert align.ledger_side("home_favorite") == "home"
    assert align.ledger_side("away_dog") == "away"


# --------------------------------------------------------------------------------------- #
# mlb_deriv_settle -- pure outcome math                                                   #
# --------------------------------------------------------------------------------------- #

def test_settle_total_over_win():
    assert settle.settle_outcome("total_8.5_over", "home", 5, 4) == "win"  # total=9 > 8.5


def test_settle_total_over_loss():
    assert settle.settle_outcome("total_8.5_over", "home", 4, 3) == "loss"  # total=7 < 8.5


def test_settle_total_under_win():
    assert settle.settle_outcome("total_8.5_under", "away", 3, 3) == "win"  # total=6 < 8.5


def test_settle_total_integer_line_push():
    assert settle.settle_outcome("total_8.0_over", "home", 5, 3) == "push"  # total=8 == 8.0


def test_settle_spread_home_favorite_covers():
    assert settle.settle_outcome("spread_1.5_home_favorite", "home", 5, 2) == "win"  # diff=3


def test_settle_spread_home_favorite_fails_to_cover():
    assert settle.settle_outcome("spread_1.5_home_favorite", "home", 4, 3) == "loss"  # diff=1


def test_settle_spread_away_dog_covers():
    assert settle.settle_outcome("spread_1.5_away_dog", "away", 4, 3) == "win"  # diff=1 < 2


def test_settle_bad_market_string_is_none():
    assert settle.settle_outcome("moneyline_home", "home", 5, 4) is None


# --------------------------------------------------------------------------------------- #
# inplay_derivative_mlb.poll_once -- offline capture + gate + place                       #
# --------------------------------------------------------------------------------------- #

_TICKS = [
    {"sport": "mlb", "game_id": "KXMLBTOTAL-25JUL18NYYBOS", "venue": "kalshi",
     "market_type": "total", "side": "Over 8.5", "ticker": "KXMLBTOTAL-25JUL18NYYBOS-T8.5",
     "prob": 0.50, "line": 8.5, "ts": "2026-07-18T00:00:00Z", "phase": "in_play"},
    {"sport": "mlb", "game_id": "KXMLBSPREAD-25JUL18NYYBOS", "venue": "kalshi",
     "market_type": "spread", "side": "Yankees", "ticker": "KXMLBSPREAD-25JUL18NYYBOS-S1.5",
     "prob": 0.50, "line": 1.5, "ts": "2026-07-18T00:00:00Z", "phase": "in_play"},
]

_STATE = {"home_display": "New York Yankees", "away_display": "Boston Red Sox",
         "home_score": 3, "away_score": 2, "inning": 6, "half": "top"}


def _fetch_stub(sport):
    return list(_TICKS)


def _state_stub(sport, ticks, gid, nowdt, cache):
    return dict(_STATE)


def _surface_stub(home, away, hs, aws, inning, half):
    return dict(_SURFACE)


def test_poll_once_captures_and_places_both_markets(tmp_path):
    grade_dir = tmp_path / "grade"
    ledger_path = tmp_path / "ledger.jsonl"
    hb = deriv.poll_once(fetch_fn=_fetch_stub, state_fn=_state_stub, surface_fn=_surface_stub,
                         grade_dir=grade_dir, ledger_path=ledger_path,
                         heartbeat_path=tmp_path / "hb.json")
    assert hb["n_captured"] == 2
    assert hb["n_bets"] == 2  # both markets clear the strict floor (large synthetic edges)
    assert hb["edge_claimed"] is False
    assert hb["executed"] is False

    rows = clv.load_ledger(ledger_path)
    open_rows = [r for r in rows if r.get("status") == "open"]
    assert len(open_rows) == 2
    markets = {r["market"] for r in open_rows}
    assert "total_8.5_over" in markets
    assert "spread_1.5_home_favorite" in markets
    for r in open_rows:
        assert r["side"] in ("home", "away")
        assert r["executed"] is False
        assert r["taken_decimal"] > 1.0


def test_poll_once_capture_always_runs_even_without_a_bet(tmp_path):
    """A tick that clears alignment but not the EV gate still gets a capture row."""
    tiny_edge_ticks = [
        {"sport": "mlb", "game_id": "KXMLBTOTAL-25JUL18NYYBOS", "venue": "kalshi",
         "market_type": "total", "side": "Over 8.5",
         "ticker": "KXMLBTOTAL-25JUL18NYYBOS-T8.5",
         "prob": 0.549, "line": 8.5, "ts": "2026-07-18T00:00:00Z", "phase": "in_play"},
    ]
    hb = deriv.poll_once(fetch_fn=lambda s: tiny_edge_ticks, state_fn=_state_stub,
                         surface_fn=_surface_stub, grade_dir=tmp_path / "grade",
                         ledger_path=tmp_path / "ledger.jsonl",
                         heartbeat_path=tmp_path / "hb.json")
    assert hb["n_captured"] == 1
    assert hb["n_bets"] == 0
    assert sum(hb["skip_by_reason"].values()) >= 1


def test_poll_once_no_coverage_line_is_skipped_not_captured(tmp_path):
    out_of_range = [
        {"sport": "mlb", "game_id": "KXMLBTOTAL-25JUL18NYYBOS", "venue": "kalshi",
         "market_type": "total", "side": "Over 20.5",
         "ticker": "KXMLBTOTAL-25JUL18NYYBOS-T20.5",
         "prob": 0.10, "line": 20.5, "ts": "2026-07-18T00:00:00Z", "phase": "in_play"},
    ]
    hb = deriv.poll_once(fetch_fn=lambda s: out_of_range, state_fn=_state_stub,
                         surface_fn=_surface_stub, grade_dir=tmp_path / "grade",
                         ledger_path=tmp_path / "ledger.jsonl",
                         heartbeat_path=tmp_path / "hb.json")
    assert hb["n_captured"] == 0
    assert hb["skip_by_reason"].get("no_coverage_or_no_side_match") == 1


def test_poll_once_no_live_state_is_honest_skip(tmp_path):
    hb = deriv.poll_once(fetch_fn=_fetch_stub, state_fn=lambda *a, **k: None,
                         surface_fn=_surface_stub, grade_dir=tmp_path / "grade",
                         ledger_path=tmp_path / "ledger.jsonl",
                         heartbeat_path=tmp_path / "hb.json")
    assert hb["n_captured"] == 0
    assert hb["skip_by_reason"].get("no_live_state") == 2


def test_poll_once_idempotent_second_tick_same_day_no_duplicate(tmp_path):
    grade_dir = tmp_path / "grade"
    ledger_path = tmp_path / "ledger.jsonl"
    kwargs = dict(fetch_fn=_fetch_stub, state_fn=_state_stub, surface_fn=_surface_stub,
                 grade_dir=grade_dir, ledger_path=ledger_path, heartbeat_path=tmp_path / "hb.json")
    deriv.poll_once(**kwargs)
    deriv.poll_once(**kwargs)
    rows = clv.load_ledger(ledger_path)
    open_rows = [r for r in rows if r.get("status") == "open"]
    assert len(open_rows) == 2  # NOT 4 -- idempotent by (sport,game_id,market,side,day)


def test_poll_once_divergence_suppresses_placement_but_still_captures(tmp_path, monkeypatch):
    """A model-vs-market gap beyond INGAME_MAX_DIVERGENCE suppresses the bet."""
    from scripts.platformkit.execution import ingame_exec_gate as gate
    monkeypatch.setattr(gate, "INGAME_MAX_DIVERGENCE", 0.01, raising=False)
    hb = deriv.poll_once(fetch_fn=_fetch_stub, state_fn=_state_stub, surface_fn=_surface_stub,
                         grade_dir=tmp_path / "grade", ledger_path=tmp_path / "ledger.jsonl",
                         heartbeat_path=tmp_path / "hb.json")
    assert hb["n_captured"] == 2
    assert hb["n_bets"] == 0
    assert hb["skip_by_reason"].get("divergence_stale_quote", 0) >= 1


# --------------------------------------------------------------------------------------- #
# mlb_deriv_settle.settle_open_bets -- end-to-end settle off an injected finals feed      #
# --------------------------------------------------------------------------------------- #

def test_settle_open_bets_end_to_end(tmp_path):
    grade_dir = tmp_path / "grade"
    ledger_path = tmp_path / "ledger.jsonl"
    deriv.poll_once(fetch_fn=_fetch_stub, state_fn=_state_stub, surface_fn=_surface_stub,
                    grade_dir=grade_dir, ledger_path=ledger_path,
                    heartbeat_path=tmp_path / "hb.json")

    def _finals_stub(sport):
        return [{"sport": "mlb", "game_id": "espn123", "home": "New York Yankees",
                 "away": "Boston Red Sox", "home_score": 6, "away_score": 3}]

    summary = settle.settle_open_bets(ledger_path=ledger_path, grade_dir=grade_dir,
                                      finals_fn=_finals_stub)
    assert summary["n_settled"] == 2
    rows = clv.load_ledger(ledger_path)
    settled = [r for r in rows if r.get("status") == "settled"]
    assert len(settled) == 2
    for r in settled:
        assert r["executed"] is False
        assert r["outcome"] in ("win", "loss", "push")
    # total_8.5_over: 6+3=9 > 8.5 -> win. spread_1.5_home_favorite: diff=3 -> win.
    by_market = {r["market"]: r for r in settled}
    assert by_market["total_8.5_over"]["outcome"] == "win"
    assert by_market["spread_1.5_home_favorite"]["outcome"] == "win"

    # idempotent: settling again is a no-op (already settled)
    summary2 = settle.settle_open_bets(ledger_path=ledger_path, grade_dir=grade_dir,
                                       finals_fn=_finals_stub)
    assert summary2["n_settled"] == 0
    rows2 = clv.load_ledger(ledger_path)
    assert len([r for r in rows2 if r.get("status") == "settled"]) == 2


def test_settle_open_bets_no_final_match_is_pending(tmp_path):
    grade_dir = tmp_path / "grade"
    ledger_path = tmp_path / "ledger.jsonl"
    deriv.poll_once(fetch_fn=_fetch_stub, state_fn=_state_stub, surface_fn=_surface_stub,
                    grade_dir=grade_dir, ledger_path=ledger_path,
                    heartbeat_path=tmp_path / "hb.json")
    summary = settle.settle_open_bets(ledger_path=ledger_path, grade_dir=grade_dir,
                                      finals_fn=lambda s: [])
    assert summary["n_settled"] == 0
    assert summary["n_pending"] == 2
