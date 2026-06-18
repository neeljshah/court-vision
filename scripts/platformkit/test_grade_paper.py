"""Per-file tests for scripts.platformkit.grade_paper (no network).

Run ONLY this file (full suite freezes the box):
    python -m pytest scripts/platformkit/test_grade_paper.py -q

Canned open bets + canned FINAL scores via an injected fetch_finals. Covers:
moneyline win/loss both directions, CLV sign (beat close positive), append-only,
idempotency, summary math, and not-final -> skipped (pending, never fabricated).
"""
from __future__ import annotations

import json

from scripts.platformkit.clv_ledger import load_ledger, record_bet
from scripts.platformkit.grade_paper import (
    grade_one,
    grade_open_bets,
    grade_summary,
)


# --------------------------------------------------------------------------- #
# Canned ESPN-scoreboard-shaped feeds (what live_board.todays_live_games returns).
# --------------------------------------------------------------------------- #
def _game(home, home_abbr, away, away_abbr, hs, as_, state="post"):
    return {"sport": "mlb", "home": home, "home_abbr": home_abbr,
            "away": away, "away_abbr": away_abbr, "state": state,
            "home_score": hs, "away_score": as_}


def _fetch_factory(games_by_sport):
    def _fetch(sport):
        return {"sport": sport, "status": "ok", "games": games_by_sport.get(sport, [])}
    return _fetch


# --------------------------------------------------------------------------- #
# grade_one: pure win/loss + P&L + CLV.
# --------------------------------------------------------------------------- #
def test_grade_one_home_win_and_loss():
    g = _game("New York Mets", "NYM", "Cincinnati Reds", "CIN", 5, 3)
    home_bet = {"sport": "mlb", "matchup": "CIN @ NYM", "side": "home",
                "taken_decimal": 2.0, "stake": 10.0, "ts": "t1"}
    away_bet = {**home_bet, "side": "away", "ts": "t2"}
    sh = grade_one(home_bet, g)
    sa = grade_one(away_bet, g)
    # home scored more -> home win, away loss
    assert sh["outcome"] == "win" and sh["pnl"] == 10.0   # (2.0-1)*10
    assert sa["outcome"] == "loss" and sa["pnl"] == -10.0
    assert sh["executed"] is False and sa["executed"] is False
    assert sh["graded"] is True


def test_grade_one_away_win_other_direction():
    # away team scores more -> away bet wins, home bet loses (opposite direction)
    g = _game("New York Mets", "NYM", "Cincinnati Reds", "CIN", 2, 7)
    away_bet = {"sport": "mlb", "matchup": "CIN @ NYM", "side": "away",
                "taken_decimal": 1.5, "stake": 20.0, "ts": "t3"}
    home_bet = {**away_bet, "side": "home", "ts": "t4"}
    assert grade_one(away_bet, g)["outcome"] == "win"
    assert grade_one(away_bet, g)["pnl"] == 10.0          # (1.5-1)*20
    assert grade_one(home_bet, g)["outcome"] == "loss"


def test_grade_one_draw_is_push():
    g = _game("A", "AAA", "B", "BBB", 1, 1)
    bet = {"sport": "soccer_intl", "matchup": "A vs B", "side": "home",
           "taken_decimal": 2.0, "stake": 10.0, "ts": "t5"}
    s = grade_one(bet, g)
    assert s["outcome"] == "push" and s["pnl"] == 0.0


def test_grade_one_clv_sign_beat_close_positive():
    # Bet HOME at 2.50 (implied 0.40); proxy close 1.80/2.20 -> fair home >> 0.40
    # => better number than close => positive CLV (sign matches clv_ledger).
    g = _game("Home", "HHH", "Away", "AAA", 4, 2)
    bet = {"sport": "mlb", "matchup": "Away @ Home", "side": "home",
           "taken_decimal": 2.50, "stake": 10.0, "ts": "t6",
           "last_decimal_home": 1.80, "last_decimal_away": 2.20}
    s = grade_one(bet, g)
    assert s["clv_pct"] > 0.0
    assert s["beat_close"] is True
    assert s["clv_is_proxy"] is True   # used last-observed price -> labelled proxy


def test_grade_one_no_close_grades_winloss_only():
    g = _game("Home", "HHH", "Away", "AAA", 4, 2)
    bet = {"sport": "mlb", "matchup": "Away @ Home", "side": "home",
           "taken_decimal": 2.0, "stake": 10.0, "ts": "t7"}
    s = grade_one(bet, g)
    assert s["outcome"] == "win"
    assert s["clv_pct"] is None        # no price -> no CLV, win/loss only


# --------------------------------------------------------------------------- #
# grade_open_bets: append-only, idempotent, not-final skipped.
# --------------------------------------------------------------------------- #
def test_open_bets_append_only_and_settle(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    record_bet("mlb", "CIN @ NYM", "home", "paper_book", 2.0,
               model_prob=0.55, stake=10.0, path=ledger)
    games = {"mlb": [_game("New York Mets", "NYM", "Cincinnati Reds", "CIN", 6, 3)]}
    out = grade_open_bets(ledger, None, fetch_finals=_fetch_factory(games))
    assert out["n_open"] == 1 and out["n_settled_now"] == 1 and out["n_pending"] == 0
    lines = [ln for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2  # open row untouched + appended settled twin
    rows = [json.loads(ln) for ln in lines]
    assert sum(1 for r in rows if r.get("status") == "open") == 1
    settled = [r for r in rows if r.get("graded")]
    assert len(settled) == 1 and settled[0]["outcome"] == "win"
    assert settled[0]["executed"] is False


def test_open_bets_idempotent_no_double_settle(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    record_bet("mlb", "CIN @ NYM", "home", "paper_book", 2.0, stake=10.0, path=ledger)
    games = {"mlb": [_game("New York Mets", "NYM", "Cincinnati Reds", "CIN", 6, 3)]}
    fetch = _fetch_factory(games)
    grade_open_bets(ledger, None, fetch_finals=fetch)
    out2 = grade_open_bets(ledger, None, fetch_finals=fetch)  # second pass
    assert out2["n_settled_now"] == 0  # already settled -> skipped
    lines = [ln for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2  # still exactly one settled twin, no duplicate


def test_open_bets_not_final_is_pending(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    record_bet("mlb", "CIN @ NYM", "home", "paper_book", 2.0, stake=10.0, path=ledger)
    # game is still in-progress -> NOT final -> must be skipped, never settled
    games = {"mlb": [_game("New York Mets", "NYM", "Cincinnati Reds", "CIN",
                           3, 2, state="in")]}
    out = grade_open_bets(ledger, None, fetch_finals=_fetch_factory(games))
    assert out["n_settled_now"] == 0 and out["n_pending"] == 1
    lines = [ln for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1  # only the open row; nothing fabricated


def test_open_bets_no_matching_game_is_pending(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    record_bet("mlb", "LAD @ SFG", "home", "paper_book", 2.0, stake=10.0, path=ledger)
    games = {"mlb": [_game("New York Mets", "NYM", "Cincinnati Reds", "CIN", 6, 3)]}
    out = grade_open_bets(ledger, None, fetch_finals=_fetch_factory(games))
    assert out["n_pending"] == 1 and out["n_settled_now"] == 0


# --------------------------------------------------------------------------- #
# grade_summary: math + breakdowns.
# --------------------------------------------------------------------------- #
def test_grade_summary_math(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    # 3 paper bets across 2 final games; one home win, one away loss, one mlb win.
    record_bet("mlb", "CIN @ NYM", "home", "paper_book", 2.0, stake=10.0, path=ledger)
    record_bet("mlb", "BOS @ TAM", "home", "paper_book", 2.0, stake=10.0, path=ledger)
    record_bet("nba", "LAL @ BOS", "away", "paper_book", 1.5, stake=10.0, path=ledger)
    games = {
        "mlb": [_game("New York Mets", "NYM", "Cincinnati Reds", "CIN", 6, 3),   # home win
                _game("Tampa Bay Rays", "TAM", "Boston Red Sox", "BOS", 1, 5)],  # home loss
        "nba": [{"sport": "nba", "home": "Boston Celtics", "home_abbr": "BOS",
                 "away": "Los Angeles Lakers", "away_abbr": "LAL", "state": "post",
                 "home_score": 90, "away_score": 110}],  # away win
    }
    grade_open_bets(ledger, None, fetch_finals=_fetch_factory(games))
    s = grade_summary(ledger)
    assert s["n"] == 3 and s["n_decided"] == 3
    # 2 wins (mlb home win + nba away win), 1 loss -> 66.67% hit rate
    assert abs(s["hit_rate"] - (100.0 * 2 / 3)) < 1e-3
    # pnl: +10 (2.0 win) -10 (loss) +5 (1.5 win) = +5 on 30 staked -> ROI 16.67%
    assert abs(s["total_pnl"] - 5.0) < 1e-6
    assert abs(s["paper_roi"] - (100.0 * 5.0 / 30.0)) < 1e-3
    # breakdowns present
    assert s["by_sport"]["mlb"]["n"] == 2 and s["by_sport"]["nba"]["n"] == 1
    assert "moneyline" in s["by_market"]  # default market label


def test_grade_summary_empty(tmp_path):
    out = grade_summary(tmp_path / "does_not_exist.jsonl")
    assert out["n"] == 0
    assert out["hit_rate"] is None and out["by_sport"] == {}
