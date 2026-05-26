"""tests/test_clv_tracker_daemon.py — R16_E8.

Five+ tests covering the real-time CLV tracker daemon:
  1. CLV math correctness for OVER (line moves up = positive CLV)
  2. CLV math direction sign for UNDER (line moves down = positive CLV)
  3. Closing-line capture timing (only fires inside 30-min window)
  4. Vault markdown dashboard refresh
  5. Aggregate computation (mean_clv_pct, pct_positive, by_book)
  6. End-to-end tick wires placed bet -> current snapshot -> CLV row

All synthetic — no NBA API, no live scraper.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR / "scripts"))

import clv_tracker_daemon as ctd  # noqa: E402


UTC = timezone.utc


# --------------------------------------------------------------------------- #
# Helpers to build synthetic fixtures.                                        #
# --------------------------------------------------------------------------- #
def _write_ledger(path: Path, rows):
    fields = [
        "bet_id", "placed_at", "game_id", "player_id", "player", "team",
        "stat", "line", "side", "book", "american_odds", "stake",
        "model_pred", "model_prob", "model_edge", "kelly_pct",
        "status", "settled_at", "actual_stat", "profit_loss", "bankroll_after",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _write_lines(path: Path, rows):
    fields = [
        "captured_at", "book", "game_id", "player_id", "player_name",
        "stat", "line", "over_price", "under_price", "start_time",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _make_bet(**kw):
    base = {
        "bet_id":        "test-bet-1",
        "placed_at":     "2026-05-26T18:00:00+00:00",
        "game_id":       "1631142204",
        "player_id":     "",
        "player":        "Keldon Johnson",
        "team":          "SAS",
        "stat":          "reb",
        "line":          "3.5",
        "side":          "OVER",
        "book":          "pin",
        "american_odds": "157",
        "stake":         "50.00",
        "model_pred":    "4.2",
        "model_prob":    "0.55",
        "model_edge":    "0.05",
        "kelly_pct":     "0.025",
        "status":        "pending",
    }
    base.update(kw)
    return base


def _make_snap(**kw):
    base = {
        "captured_at":  "2026-05-26T19:00:00",
        "book":         "pin",
        "game_id":      "1631142204",
        "player_id":    "",
        "player_name":  "Keldon Johnson",
        "stat":         "reb",
        "line":         "3.5",
        "over_price":   "160",
        "under_price":  "-205",
        "start_time":   "2026-05-27T00:35:00Z",
    }
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# Test 1: OVER math correctness.                                              #
# --------------------------------------------------------------------------- #
def test_compute_realized_clv_over_positive():
    # OVER 3.5; market moves UP to 4.0 — we locked in the LOWER number => +CLV.
    cl, pct = ctd.compute_realized_clv(placed_line=3.5, current_line=4.0, side="OVER")
    assert cl == pytest.approx(0.5)
    assert pct == pytest.approx(0.5 / 3.5, rel=1e-4)


def test_compute_realized_clv_over_negative():
    # OVER 3.5; market moves DOWN to 3.0 — we locked HIGHER number => -CLV.
    cl, pct = ctd.compute_realized_clv(placed_line=3.5, current_line=3.0, side="OVER")
    assert cl == pytest.approx(-0.5)
    assert pct < 0


# --------------------------------------------------------------------------- #
# Test 2: UNDER direction sign.                                               #
# --------------------------------------------------------------------------- #
def test_compute_realized_clv_under_direction():
    # UNDER 3.5; market moves DOWN to 3.0 — we locked the HIGHER number => +CLV.
    cl, pct = ctd.compute_realized_clv(placed_line=3.5, current_line=3.0, side="UNDER")
    assert cl == pytest.approx(0.5)
    assert pct > 0

    # UNDER 3.5; market moves UP to 4.0 — we're worse off => -CLV.
    cl, pct = ctd.compute_realized_clv(placed_line=3.5, current_line=4.0, side="UNDER")
    assert cl == pytest.approx(-0.5)
    assert pct < 0


def test_compute_realized_clv_bad_side_raises():
    with pytest.raises(ValueError):
        ctd.compute_realized_clv(3.5, 4.0, side="MIDDLE")


# --------------------------------------------------------------------------- #
# Test 3: closing-line capture timing.                                        #
# --------------------------------------------------------------------------- #
def test_closing_line_capture_inside_window(tmp_path: Path, monkeypatch):
    pnl = tmp_path / "pnl_ledger.csv"
    lines_dir = tmp_path / "lines"
    clv_out = tmp_path / "pnl_ledger_clv.csv"
    vault_md = tmp_path / "clv_live.md"
    closing_out = tmp_path / "closing_lines.csv"

    # Tip-off in 15 minutes => INSIDE closing window.
    now = datetime(2026, 5, 27, 0, 20, 0, tzinfo=UTC)
    start = (now + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")

    _write_ledger(pnl, [_make_bet()])
    _write_lines(lines_dir / "2026-05-26_pin.csv", [
        _make_snap(captured_at=now.strftime("%Y-%m-%dT%H:%M"),
                   line="3.5", over_price="160", under_price="-205",
                   start_time=start),
    ])

    monkeypatch.setattr(ctd, "_now_utc", lambda: now)
    rpt = ctd.run_tick(pnl, lines_dir, clv_out, vault_md, closing_out)

    assert rpt["closing_lines_captured"] == 1
    assert closing_out.exists()
    with open(closing_out, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert float(rows[0]["closing_line"]) == 3.5
    assert rows[0]["bet_id"] == "test-bet-1"

    # Second tick: closing already logged -> NOT re-captured (idempotent).
    rpt2 = ctd.run_tick(pnl, lines_dir, clv_out, vault_md, closing_out)
    assert rpt2["closing_lines_captured"] == 0


def test_closing_line_NOT_captured_outside_window(tmp_path: Path, monkeypatch):
    pnl = tmp_path / "pnl_ledger.csv"
    lines_dir = tmp_path / "lines"
    clv_out = tmp_path / "pnl_ledger_clv.csv"
    vault_md = tmp_path / "clv_live.md"
    closing_out = tmp_path / "closing_lines.csv"

    # Tip-off in 4 HOURS => OUTSIDE closing window.
    now = datetime(2026, 5, 26, 20, 0, 0, tzinfo=UTC)
    start = (now + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")

    _write_ledger(pnl, [_make_bet()])
    _write_lines(lines_dir / "2026-05-26_pin.csv", [
        _make_snap(captured_at=now.strftime("%Y-%m-%dT%H:%M"), start_time=start),
    ])

    monkeypatch.setattr(ctd, "_now_utc", lambda: now)
    rpt = ctd.run_tick(pnl, lines_dir, clv_out, vault_md, closing_out)

    assert rpt["closing_lines_captured"] == 0
    assert not closing_out.exists() or _empty_csv(closing_out)


def _empty_csv(p: Path) -> bool:
    with open(p, encoding="utf-8") as fh:
        return sum(1 for _ in csv.DictReader(fh)) == 0


# --------------------------------------------------------------------------- #
# Test 4: vault markdown refresh.                                             #
# --------------------------------------------------------------------------- #
def test_vault_markdown_dashboard_refresh(tmp_path: Path, monkeypatch):
    pnl = tmp_path / "pnl_ledger.csv"
    lines_dir = tmp_path / "lines"
    clv_out = tmp_path / "pnl_ledger_clv.csv"
    vault_md = tmp_path / "clv_live.md"
    closing_out = tmp_path / "closing_lines.csv"

    now = datetime(2026, 5, 26, 20, 0, 0, tzinfo=UTC)
    _write_ledger(pnl, [
        _make_bet(bet_id="bet-a", side="OVER",  line="3.5"),
        _make_bet(bet_id="bet-b", side="UNDER", line="3.5", player="Player Two",
                  game_id="1631142205"),
    ])
    # bet-a current line 4.0 (OVER moves up = good)
    # bet-b current line 4.0 (UNDER moves up = bad)
    _write_lines(lines_dir / "2026-05-26_pin.csv", [
        _make_snap(line="4.0", player_name="Keldon Johnson"),
        _make_snap(line="4.0", player_name="Player Two", game_id="1631142205"),
    ])

    monkeypatch.setattr(ctd, "_now_utc", lambda: now)
    rpt = ctd.run_tick(pnl, lines_dir, clv_out, vault_md, closing_out)
    assert rpt["bets_tracked"] == 2

    text = vault_md.read_text(encoding="utf-8")
    assert "Live CLV Dashboard" in text
    assert "Keldon Johnson" in text
    assert "Player Two" in text
    # bet-a should show GREEN (CLV +14.28%) and bet-b RED.
    assert "GREEN" in text
    assert "RED" in text
    # The OVER row should have a positive CLV%.
    assert "+14.29%" in text or "+14.28%" in text


# --------------------------------------------------------------------------- #
# Test 5: aggregate computation.                                              #
# --------------------------------------------------------------------------- #
def test_aggregate_computation(tmp_path: Path):
    clv_csv = tmp_path / "pnl_ledger_clv.csv"
    fields = ctd._CLV_LEDGER_FIELDS
    with open(clv_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        # Three bets: two positive on pin, one negative on bov.
        w.writerow({"bet_id": "b1", "snapshot_time": "2026-05-26T20:00:00", "book": "pin", "clv_pct": 0.05})
        w.writerow({"bet_id": "b1", "snapshot_time": "2026-05-26T20:01:00", "book": "pin", "clv_pct": 0.08})
        w.writerow({"bet_id": "b2", "snapshot_time": "2026-05-26T20:00:00", "book": "pin", "clv_pct": 0.02})
        w.writerow({"bet_id": "b3", "snapshot_time": "2026-05-26T20:00:00", "book": "bov", "clv_pct": -0.03})

    agg = ctd.compute_aggregate(clv_csv)
    # Latest-per-bet: b1=0.08, b2=0.02, b3=-0.03  -> mean = 0.0233...
    assert agg["n_bets_tracked"] == 3
    assert agg["mean_clv_pct"] == pytest.approx((0.08 + 0.02 + -0.03) / 3, rel=1e-3)
    assert agg["pct_positive_clv"] == pytest.approx(2 / 3, rel=1e-3)
    assert "pin" in agg["by_book"] and "bov" in agg["by_book"]
    assert agg["by_book"]["pin"]["n"] == 2
    assert agg["by_book"]["pin"]["mean_clv_pct"] == pytest.approx((0.08 + 0.02) / 2)


def test_aggregate_empty(tmp_path: Path):
    out = ctd.compute_aggregate(tmp_path / "missing.csv")
    assert out["n_bets_tracked"] == 0


# --------------------------------------------------------------------------- #
# Test 6: end-to-end tick — Keldon REB OVER 3.5 @ Pin +157 -> +160.           #
# --------------------------------------------------------------------------- #
def test_end_to_end_keldon_smoke(tmp_path: Path, monkeypatch):
    """Reproduces the R16_E7 smoke-test bet from the acceptance criteria."""
    pnl = tmp_path / "pnl_ledger.csv"
    lines_dir = tmp_path / "lines"
    clv_out = tmp_path / "pnl_ledger_clv.csv"
    vault_md = tmp_path / "clv_live.md"
    closing_out = tmp_path / "closing_lines.csv"

    now = datetime(2026, 5, 26, 19, 0, 0, tzinfo=UTC)
    _write_ledger(pnl, [_make_bet(
        bet_id="keldon-smoke",
        placed_at="2026-05-26T12:27:00+00:00",
        player="Keldon Johnson",
        stat="reb",
        line="3.5",
        side="OVER",
        book="pin",
        american_odds="157",
    )])
    # Latest pin snapshot shows line moved to 3.5@+160 (over odds moved from
    # +157 -> +160; line stayed flat — clv_line=0, but the bet should appear).
    _write_lines(lines_dir / "2026-05-26_pin.csv", [
        _make_snap(captured_at="2026-05-26T12:27", line="3.5", over_price="157"),
        _make_snap(captured_at="2026-05-26T13:08", line="3.5", over_price="160"),
    ])

    monkeypatch.setattr(ctd, "_now_utc", lambda: now)
    rpt = ctd.run_tick(pnl, lines_dir, clv_out, vault_md, closing_out)
    assert rpt["bets_tracked"] == 1
    with open(clv_out, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["bet_id"] == "keldon-smoke"
    assert float(rows[0]["placed_line"]) == 3.5
    assert float(rows[0]["current_line"]) == 3.5
    # Snapshot picked must be the LATEST captured_at (13:08, not 12:27).
    assert rows[0]["snapshot_time"] == "2026-05-26T13:08"

    # Vault dashboard should mention Keldon.
    txt = vault_md.read_text(encoding="utf-8")
    assert "Keldon Johnson" in txt
