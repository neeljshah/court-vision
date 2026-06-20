"""Per-file tests for scripts.platformkit.clv_ledger.

Run ONLY this file (full suite freezes the box):
    python -m pytest scripts/platformkit/test_clv_ledger.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.clv_ledger import (
    append_settlement,
    clv_summary,
    compute_clv,
    load_ledger,
    record_bet,
    settle_closing_line,
)


def test_clv_positive_when_better_number_than_close():
    # Bet HOME at 2.50 (implied 0.40). Close has home a clear favourite
    # (home 1.80 / away 2.20) -> fair home prob well above 0.40 -> we got a
    # BETTER NUMBER than the close -> positive CLV.
    out = compute_clv("home", 2.50, 1.80, 2.20)
    assert out["taken_p"] == 0.40
    assert out["fair_close"] > 0.40
    assert out["clv_pct"] > 0.0
    assert out["beat_close"] is True


def test_clv_negative_when_worse_number_than_close():
    # Bet HOME at 1.50 (implied ~0.667) but home CLOSES as an underdog
    # (home 2.50 / away 1.55) -> fair home prob well below 0.667 -> worse
    # number than the close -> negative CLV.
    out = compute_clv("home", 1.50, 2.50, 1.55)
    assert out["taken_p"] > out["fair_close"]
    assert out["clv_pct"] < 0.0
    assert out["beat_close"] is False


def test_away_side_uses_away_fair_prob():
    # Symmetry: betting AWAY should read the away fair prob.
    home = compute_clv("home", 2.00, 1.80, 2.20)
    away = compute_clv("away", 2.00, 1.80, 2.20)
    # fair_home + fair_away devig to ~1.0
    assert abs(home["fair_close"] + away["fair_close"] - 1.0) < 1e-6


def test_append_only_two_records_two_lines(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    r1 = record_bet("nba", "Knicks @ Spurs", "home", "FanDuel", 2.50,
                    model_prob=0.55, stake=10.0, path=ledger)
    r2 = record_bet("mlb", "Yankees @ Sox", "away", "DraftKings", 1.90,
                    model_prob=0.52, stake=5.0, path=ledger)
    assert r1["status"] == "open" and r2["status"] == "open"
    assert r1["executed"] is False
    lines = [ln for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2  # append-only: two records => two lines
    # Settling appends a THIRD line; the open rows are untouched.
    settled = settle_closing_line(r1, 1.80, 2.20)
    append_settlement(settled, path=ledger)
    lines = [ln for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 3
    # original open row still present and still "open"
    rows = [json.loads(ln) for ln in lines]
    open_rows = [r for r in rows if r["status"] == "open"]
    assert len(open_rows) == 2


def test_settle_fields_and_clv_sign(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    bet = record_bet("nba", "A @ B", "home", "FanDuel", 2.50, path=ledger)
    settled = settle_closing_line(bet, 1.80, 2.20)
    assert settled["status"] == "settled"
    assert settled["clv_pct"] > 0.0
    assert settled["beat_close"] is True
    assert settled["closing_decimal_home"] == 1.80
    assert "fair_close_prob" in settled and "taken_implied_prob" in settled


def test_summary_math(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    # Two NBA bets: one beats the close, one does not. One MLB bet that beats it.
    b1 = record_bet("nba", "A @ B", "home", "FD", 2.50, path=ledger)
    b2 = record_bet("nba", "C @ D", "home", "FD", 1.50, path=ledger)
    b3 = record_bet("mlb", "E @ F", "home", "DK", 2.50, path=ledger)
    append_settlement(settle_closing_line(b1, 1.80, 2.20), path=ledger)   # +CLV
    append_settlement(settle_closing_line(b2, 2.50, 1.55), path=ledger)   # -CLV
    append_settlement(settle_closing_line(b3, 1.80, 2.20), path=ledger)   # +CLV

    summary = clv_summary(load_ledger(ledger))
    assert summary["n_bets"] == 3              # only settled rows counted
    # 2 of 3 beat the close
    assert abs(summary["pct_beat_close"] - (100.0 * 2 / 3)) < 1e-3
    # mean over the three clv_pct values
    rows = [r for r in load_ledger(ledger) if r.get("status") == "settled"]
    expected_mean = sum(float(r["clv_pct"]) for r in rows) / 3
    assert abs(summary["mean_clv_pct"] - round(expected_mean, 6)) < 1e-4
    # by-sport breakdown
    assert summary["by_sport"]["nba"]["n"] == 2
    assert summary["by_sport"]["mlb"]["n"] == 1
    assert abs(summary["by_sport"]["mlb"]["pct_beat_close"] - 100.0) < 1e-6


def test_empty_summary():
    s = clv_summary([])
    assert s["n_bets"] == 0
    assert s["pct_beat_close"] is None
    assert s["by_sport"] == {}


# --- M4 lock-guarded write retrofit -----------------------------------------

def test_record_bet_funnels_through_locked_append_row(tmp_path, monkeypatch):
    """record_bet must write via clv_ledger_io.append_row (the locked primitive),
    not its own open('a'). We spy on append_row and assert it received the exact
    open-row dict and the same target path."""
    import scripts.platformkit.clv_ledger_io as io_mod

    seen = []
    real = io_mod.append_row

    def spy(row, *, path=None):
        seen.append((dict(row), path))
        return real(row, path=path)

    monkeypatch.setattr(io_mod, "append_row", spy)
    ledger = tmp_path / "clv_ledger.jsonl"
    rec = record_bet("nba", "A @ B", "home", "FD", 2.50, stake=7.0, path=ledger)
    assert len(seen) == 1
    seen_row, seen_path = seen[0]
    assert seen_path == ledger
    # row shape unchanged: the dict handed to append_row IS the stored record.
    assert seen_row == rec
    on_disk = [json.loads(ln) for ln in
               ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert on_disk == [rec]


def test_append_settlement_funnels_through_locked_append_row(tmp_path, monkeypatch):
    import scripts.platformkit.clv_ledger_io as io_mod

    seen = []
    real = io_mod.append_row

    def spy(row, *, path=None):
        seen.append((dict(row), path))
        return real(row, path=path)

    monkeypatch.setattr(io_mod, "append_row", spy)
    ledger = tmp_path / "clv_ledger.jsonl"
    bet = record_bet("nba", "A @ B", "home", "FD", 2.50, path=ledger)
    settled = settle_closing_line(bet, 1.80, 2.20)
    out = append_settlement(settled, path=ledger)
    # second append_row call is the settled twin (first was the open record).
    assert len(seen) == 2
    seen_row, seen_path = seen[1]
    assert seen_path == ledger
    assert seen_row == settled == out


def test_write_falls_back_when_lock_layer_broken(tmp_path, monkeypatch):
    """If clv_ledger_io.append_row raises, the row must still land via the
    original direct-write fallback (placing/grading never breaks)."""
    import scripts.platformkit.clv_ledger_io as io_mod

    def boom(row, *, path=None):
        raise RuntimeError("lock layer down")

    monkeypatch.setattr(io_mod, "append_row", boom)
    ledger = tmp_path / "clv_ledger.jsonl"
    rec = record_bet("nba", "A @ B", "home", "FD", 2.50, stake=3.0, path=ledger)
    on_disk = [json.loads(ln) for ln in
               ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert on_disk == [rec]  # fallback wrote the identical row
