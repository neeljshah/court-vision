"""tests/test_clv.py - tier2-7 (loop 5).

Six tests for src.betting.clv + scripts.clv_report.

Synthetic fixtures only - never hits the live scraper or NBA API.
"""
from __future__ import annotations

import csv
import io
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.betting import clv as clv_mod  # noqa: E402
from scripts import clv_report  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixture helpers.                                                            #
# --------------------------------------------------------------------------- #
LINE_FIELDS = ["captured_at", "book", "game_id", "player_id", "player_name",
               "team", "stat", "line", "over_price", "under_price",
               "market_status"]

LEDGER_FIELDS = [
    "bet_id", "placed_at", "game_id", "player_id", "player", "team",
    "stat", "line", "side", "book", "american_odds", "stake",
    "model_pred", "model_prob", "model_edge", "kelly_pct",
    "status", "settled_at", "actual_stat", "profit_loss", "bankroll_after",
]


def _write_lines(tmpdir, date_str, book_short, rows):
    path = os.path.join(tmpdir, f"{date_str}_{book_short}.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LINE_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in LINE_FIELDS})
    return path


def _write_ledger(tmpdir, rows):
    path = os.path.join(tmpdir, "pnl_ledger.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LEDGER_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def _snap(ts, player, stat, line, over=-110, under=-110, book="draftkings",
          pid="", gid=""):
    return {
        "captured_at":   ts,
        "book":          book,
        "game_id":       gid,
        "player_id":     pid,
        "player_name":   player,
        "team":          "",
        "stat":          stat,
        "line":          str(line),
        "over_price":    str(over),
        "under_price":   str(under),
        "market_status": "open",
    }


def _bet(bet_id="b1", player="Foo Bar", stat="pts", line=24.5, side="OVER",
         book="DK", odds=-110, placed_at=None, status="won", stake=10.0,
         pnl=9.09, pid="100"):
    placed_at = placed_at or "2026-05-24T17:30:00"
    return {
        "bet_id":        bet_id,
        "placed_at":     placed_at,
        "game_id":       "0022500001",
        "player_id":     pid,
        "player":        player,
        "team":          "BOS",
        "stat":          stat,
        "line":          str(line),
        "side":          side,
        "book":          book,
        "american_odds": str(odds),
        "stake":         str(stake),
        "status":        status,
        "settled_at":    "2026-05-24T22:30:00",
        "actual_stat":   "26",
        "profit_loss":   f"{pnl:+.2f}",
        "bankroll_after": "1009.09",
    }


# --------------------------------------------------------------------------- #
# Test 1: find_closing_line returns the SNAPSHOT-CLOSEST-to-tip row.          #
# --------------------------------------------------------------------------- #
def test_find_closing_line_picks_closest_to_target(tmp_path):
    lines_dir = str(tmp_path)
    # placed_at = 17:30, asof becomes 18:00, target = 17:30. We expect the
    # 17:35 snapshot to win (closest to 17:30 target while < 18:00 deadline).
    snaps = [
        _snap("2026-05-24T15:00:00", "Foo Bar", "pts", 24.0, over=-115, pid="100"),
        _snap("2026-05-24T17:35:00", "Foo Bar", "pts", 23.5, over=-120, pid="100"),
        _snap("2026-05-24T17:55:00", "Foo Bar", "pts", 23.0, over=-130, pid="100"),
        # A row AFTER asof (18:00) must be ignored even if it'd be "closest".
        _snap("2026-05-24T18:05:00", "Foo Bar", "pts", 22.5, over=-140, pid="100"),
    ]
    _write_lines(lines_dir, "2026-05-24", "draftkings", snaps)
    asof = datetime(2026, 5, 24, 18, 0, 0)
    res = clv_mod.find_closing_line(
        book="DK", game_id="0022500001", player_id="100",
        stat="pts", side="OVER", asof=asof, lines_dir=lines_dir,
        player_name="Foo Bar",
    )
    assert res is not None
    cline, codds = res
    # 17:35 has line 23.5 / -120 and is closest to 17:30 (asof - 30 min).
    assert cline == 23.5
    assert codds == -120


# --------------------------------------------------------------------------- #
# Test 2: returns None when no snapshot is in the 30-min window before tip.   #
# --------------------------------------------------------------------------- #
def test_find_closing_line_none_when_window_empty(tmp_path):
    lines_dir = str(tmp_path)
    # Only a snapshot AFTER tip, and one too old (> 24 h before tip).
    snaps = [
        _snap("2026-05-22T17:35:00", "Foo Bar", "pts", 24.0, over=-110, pid="100"),  # >24h old
        _snap("2026-05-24T19:10:00", "Foo Bar", "pts", 23.0, over=-110, pid="100"),  # after asof
    ]
    _write_lines(lines_dir, "2026-05-24", "draftkings", snaps)
    asof = datetime(2026, 5, 24, 19, 0, 0)
    res = clv_mod.find_closing_line(
        book="DK", game_id="0022500001", player_id="100",
        stat="pts", side="OVER", asof=asof, lines_dir=lines_dir,
        player_name="Foo Bar",
    )
    assert res is None


# --------------------------------------------------------------------------- #
# Test 3: compute_clv POSITIVE when placement implies higher prob than close. #
# --------------------------------------------------------------------------- #
def test_compute_clv_positive_when_beat_close():
    # OVER 24.5 at -110 (placement_implied = 0.524).
    # Closing OVER 23.5 at -130 (closing_implied = 0.565). Closing is shorter price.
    # clv_line = placed - closing = 24.5 - 23.5 = +1.0 (good for OVER bettor).
    # clv_percent = closing_prob - placed_prob = +0.041 (positive = beat close).
    bet = {"side": "OVER", "line": "24.5", "american_odds": "-110"}
    res = clv_mod.compute_clv(bet, closing_line=23.5, closing_odds=-130)
    assert res["clv_line"] == 1.0
    assert res["clv_percent"] is not None and res["clv_percent"] > 0
    assert res["beat_close"] is True


# --------------------------------------------------------------------------- #
# Test 4: compute_clv NEGATIVE when bet was wrong-priced at placement.        #
# --------------------------------------------------------------------------- #
def test_compute_clv_negative_when_lost_to_close():
    # OVER 24.5 at -130 (placement_implied = 0.565).
    # Closing OVER 25.5 at -110 (closing_implied = 0.524). Closing is longer price.
    # clv_line = 24.5 - 25.5 = -1.0 (bad for OVER bettor - close moved against).
    # clv_percent = 0.524 - 0.565 = -0.041 (negative = lost to close).
    bet = {"side": "OVER", "line": "24.5", "american_odds": "-130"}
    res = clv_mod.compute_clv(bet, closing_line=25.5, closing_odds=-110)
    assert res["clv_line"] == -1.0
    assert res["clv_percent"] is not None and res["clv_percent"] < 0
    assert res["beat_close"] is False


# --------------------------------------------------------------------------- #
# Test 5: enrich_pnl_with_clv handles missing close gracefully.               #
# --------------------------------------------------------------------------- #
def test_enrich_handles_missing_close(tmp_path):
    lines_dir = str(tmp_path / "lines"); os.makedirs(lines_dir, exist_ok=True)
    ledger_dir = str(tmp_path / "ledger"); os.makedirs(ledger_dir, exist_ok=True)
    out_path = str(tmp_path / "out_clv.csv")

    # One bet WITH a matching snapshot, one bet WITHOUT.
    snaps = [
        _snap("2026-05-24T17:35:00", "Foo Bar", "pts", 23.5, over=-120, pid="100"),
    ]
    _write_lines(lines_dir, "2026-05-24", "draftkings", snaps)
    bets = [
        _bet(bet_id="b1", player="Foo Bar", stat="pts", line=24.5,
             placed_at="2026-05-24T17:30:00", pid="100"),
        _bet(bet_id="b2", player="Nobody", stat="reb", line=8.5,
             placed_at="2026-05-24T17:30:00", pid="999"),
    ]
    ledger = _write_ledger(ledger_dir, bets)
    rows = clv_mod.enrich_pnl_with_clv(
        pnl_path=ledger, lines_dir=lines_dir, out_path=out_path,
    )
    assert len(rows) == 2

    by_id = {r["bet_id"]: r for r in rows}
    # b1 has a close; b2 does not.
    assert by_id["b1"]["closing_line"] != ""
    assert by_id["b1"]["clv_percent"] != ""
    assert by_id["b2"]["closing_line"] == ""
    assert by_id["b2"]["clv_percent"] == ""
    assert "no closing snapshot" in by_id["b2"]["notes"]

    # File round-trip.
    with open(out_path, encoding="utf-8") as fh:
        rt = list(csv.DictReader(fh))
    assert len(rt) == 2
    assert "clv_percent" in rt[0]


# --------------------------------------------------------------------------- #
# Test 6: CLI summary format matches spec.                                    #
# --------------------------------------------------------------------------- #
def test_clv_report_cli_format(tmp_path):
    lines_dir = str(tmp_path / "lines"); os.makedirs(lines_dir, exist_ok=True)
    ledger_dir = str(tmp_path / "ledger"); os.makedirs(ledger_dir, exist_ok=True)
    out_path = str(tmp_path / "out_clv.csv")

    snaps = [
        _snap("2026-05-24T17:35:00", "Foo Bar", "pts", 23.5, over=-120, pid="100"),
        _snap("2026-05-24T17:35:00", "Baz Quux", "reb", 8.5, over=-105, pid="101"),
    ]
    _write_lines(lines_dir, "2026-05-24", "draftkings", snaps)
    # Use placed_at = today minus a few minutes so it falls inside the
    # 30d window the CLI defaults to.
    today_iso = datetime.now().replace(microsecond=0).isoformat()
    bets = [
        _bet(bet_id="b1", player="Foo Bar", stat="pts", line=24.5,
             placed_at=today_iso, pid="100", odds=-110, status="won", pnl=9.09),
        _bet(bet_id="b2", player="Baz Quux", stat="reb", line=8.5,
             placed_at=today_iso, pid="101", odds=-110, status="lost", pnl=-10.0),
    ]
    # Ensure the snapshot's captured_at is BEFORE the bet's placed_at + 30min
    # window. Rebuild snaps with timestamps relative to the bets' placed_at.
    bet_dt = datetime.fromisoformat(today_iso)
    # snapshot ~25 min before tip-proxy (placed+30) - inside the 30-min window.
    snap_ts = (bet_dt + timedelta(minutes=5)).replace(microsecond=0).isoformat()
    snaps = [
        _snap(snap_ts, "Foo Bar", "pts", 23.5, over=-120, pid="100"),
        _snap(snap_ts, "Baz Quux", "reb", 8.5, over=-105, pid="101"),
    ]
    # Overwrite the lines file (only one date-book file per scraper run).
    date_str = bet_dt.date().isoformat()
    _write_lines(lines_dir, date_str, "draftkings", snaps)

    ledger = _write_ledger(ledger_dir, bets)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = clv_report.main([
            "--range", "30d", "--by", "stat",
            "--pnl", ledger, "--lines-dir", lines_dir, "--out", out_path,
        ])
    assert rc == 0
    txt = buf.getvalue()

    # Format anchors required by the spec.
    assert "CLV Report - last 30d" in txt
    assert "n_settled:" in txt
    assert "n_with_close_line:" in txt
    assert "mean_clv_percent:" in txt
    assert "beat_close_rate:" in txt
    assert "By stat:" in txt
    # Correlation line only when >=2 settled pairs are usable.
    assert "Correlation" in txt or "settled bets" in txt
