"""Per-file test: settle-time board_date label is ET, not UTC (LANE C2 fix).

MLB Kalshi tickets are ET-dated. A late ET game finishing after 00:00 UTC (e.g.
03:30 UTC = ~23:00 ET the PREVIOUS day) got board_date stamped as tomorrow in
UTC terms -- the bet_expected_dates guard (26c16bf6) then rejected that night's
own legitimate final until the next as-of pass. Traps the regression at both
the label (today_et_iso) and the end-to-end grade_open_bets settle seam.

Run ONLY this file (full suite freezes the box):
    python -m pytest scripts/platformkit/test_grade_paper_boarddate.py -q
"""
from __future__ import annotations

import datetime as _dt

from scripts.platformkit import grade_paper as _gp
from scripts.platformkit.grade_paper_dates import today_et_iso

_FROZEN_UTC = _dt.datetime(2026, 7, 10, 3, 30, tzinfo=_dt.timezone.utc)


def _game(home, home_abbr, away, away_abbr, hs, as_, state="post"):
    return {"sport": "mlb", "home": home, "home_abbr": home_abbr,
            "away": away, "away_abbr": away_abbr, "state": state,
            "home_score": hs, "away_score": as_}


def _ledger_row(bet_id: str):
    return {"ts": "2026-07-09T20:00:00+00:00", "sport": "mlb",
            "matchup": "Colorado @ San Francisco", "side": "home",
            "taken_book": "kalshi", "taken_decimal": 2.0, "stake_units": 1.0,
            "status": "open", "executed": False, "market": "moneyline",
            "market_type": "moneyline", "bet_id": bet_id}


def test_today_et_iso_is_previous_day_at_0330_utc():
    # (a) board date label = the ET date, not the UTC date (which would be 07-10)
    assert today_et_iso(_FROZEN_UTC) == "2026-07-09"


def test_late_final_on_ticket_date_passes_wrong_date_still_rejects(tmp_path, monkeypatch):
    monkeypatch.setattr(_gp, "_today_et_iso", lambda: "2026-07-09")
    games = {"mlb": [_game("San Francisco Giants", "SF", "Colorado Rockies", "COL", 8, 2)]}

    def _fetch(sport):
        return {"sport": sport, "status": "ok", "games": games.get(sport, [])}

    # (b) a final for a game ticketed on THAT ET date passes the guard
    ledger_ok = tmp_path / "ok.jsonl"
    ledger_ok.write_text(
        __import__("json").dumps(_ledger_row("pm|kalshi|KXMLBGAME-26JUL091400COLSF|home")) + "\n",
        encoding="utf-8")
    out_ok = _gp.grade_open_bets(ledger_ok, None, fetch_finals=_fetch)
    assert out_ok["n_settled_now"] == 1 and out_ok["n_pending"] == 0

    # (c) a final ticketed for a DIFFERENT date still rejects
    ledger_bad = tmp_path / "bad.jsonl"
    ledger_bad.write_text(
        __import__("json").dumps(_ledger_row("pm|kalshi|KXMLBGAME-26JUL111400COLSF|home")) + "\n",
        encoding="utf-8")
    out_bad = _gp.grade_open_bets(ledger_bad, None, fetch_finals=_fetch)
    assert out_bad["n_settled_now"] == 0 and out_bad["n_pending"] == 1
