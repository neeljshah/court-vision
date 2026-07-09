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
    is_clv_suspect,
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


def test_settle_closing_line_stamps_close_source_venue_when_given(tmp_path):
    # ROOT CAUSE FIX (2026-07-09): the m18 sweep needs close_source/close_venue
    # to reach the SETTLED row so downstream CLV-basis diagnostics can tell a
    # real same-venue Kalshi close from a cross-venue fallback. Optional +
    # additive: omitted entirely when the caller doesn't pass them.
    ledger = tmp_path / "clv_ledger.jsonl"
    bet = record_bet("nba", "A @ B", "home", "kalshi", 2.50, path=ledger)
    settled = settle_closing_line(bet, 1.80, 2.20,
                                   close_source="kalshi", close_venue="kalshi")
    assert settled["close_source"] == "kalshi"
    assert settled["close_venue"] == "kalshi"


def test_settle_closing_line_omits_close_source_venue_by_default():
    bet = {"side": "home", "taken_decimal": 2.50}
    settled = settle_closing_line(bet, 1.80, 2.20)
    assert "close_source" not in settled
    assert "close_venue" not in settled


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
    assert s["median_clv_pct"] is None
    assert s["n_suspect_excluded"] == 0


def test_offmarket_taken_price_is_clv_suspect():
    # A "taken" 12.0 on a game that CLOSED ~pick'em (1.95/1.95) is off-market: no book
    # offered +1100 on a coin flip -> it is a misparsed line, flagged suspect so it
    # never fabricates a fake +CLV. A normal underdog price (3.0 vs a 1.8 close) is NOT
    # suspect (ratio 1.67 < 2.5) -- a real, kept bet.
    assert is_clv_suspect({"side": "away", "taken_decimal": 12.0,
                           "closing_decimal_home": 1.95, "closing_decimal_away": 1.95})
    assert not is_clv_suspect({"side": "home", "taken_decimal": 3.0,
                               "closing_decimal_home": 1.80, "closing_decimal_away": 2.20})
    # Missing the side's close -> cannot judge -> NOT flagged (kept).
    assert not is_clv_suspect({"side": "home", "taken_decimal": 12.0})


def test_summary_excludes_suspect_and_reports_robust_median(tmp_path):
    # Three honest near-pickem bets + ONE off-market garbage row. The garbage row's
    # +497% CLV must NOT inflate the headline mean: it is excluded (n_suspect_excluded=1),
    # n_bets counts only the trustworthy rows, and the median is the robust yardstick.
    ledger = tmp_path / "clv_ledger.jsonl"
    b1 = record_bet("mlb", "A @ B", "home", "FD", 2.00, path=ledger)
    b2 = record_bet("mlb", "C @ D", "away", "FD", 2.00, path=ledger)
    b3 = record_bet("mlb", "E @ F", "home", "FD", 1.95, path=ledger)
    bad = record_bet("mlb", "G @ H", "away", "FD", 12.00, path=ledger)  # off-market
    append_settlement(settle_closing_line(b1, 1.95, 1.95), path=ledger)
    append_settlement(settle_closing_line(b2, 1.95, 1.95), path=ledger)
    append_settlement(settle_closing_line(b3, 1.95, 1.95), path=ledger)
    append_settlement(settle_closing_line(bad, 1.95, 1.95), path=ledger)  # fabricates +CLV

    s = clv_summary(load_ledger(ledger))
    assert s["n_suspect_excluded"] == 1          # the garbage row is flagged + dropped
    assert s["n_bets"] == 3                       # only the 3 trustworthy rows count
    assert s["mean_clv_pct"] < 5.0                # NOT dragged to +100%+ by the garbage
    assert s["median_clv_pct"] is not None
    # The suspect row's clv_pct is real on disk but never reaches the aggregate.
    rows = [r for r in load_ledger(ledger) if r.get("status") == "settled"]
    assert any(float(r["clv_pct"]) > 100.0 for r in rows)  # garbage row IS still on disk


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


def test_record_bet_labels_market_type_when_market_omitted(tmp_path):
    """A game-ML placer that omits market= must still yield a row whose market
    AND market_type are 'moneyline' (the value bet_id already resolves to), never
    an unlabelled '?' that breaks the board / settler / grade summary."""
    ledger = tmp_path / "clv_ledger.jsonl"
    rec = record_bet("mlb", "Rangers @ Blue Jays", "home", "pinnacle", 1.99,
                     model_prob=0.55, event_id="401815912", path=ledger)
    assert rec["market"] == "moneyline"
    assert rec["market_type"] == "moneyline"
    # bet_id already classified it moneyline; the persisted row now matches.
    assert "|moneyline|" in rec["bet_id"]
    on_disk = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert on_disk["market_type"] == "moneyline"


def test_record_bet_preserves_explicit_market(tmp_path):
    """An explicit market= (e.g. 'prop') is preserved on both fields, not coerced."""
    ledger = tmp_path / "clv_ledger.jsonl"
    rec = record_bet("mlb", "A @ B", "home", "DK", 1.90, market="prop", path=ledger)
    assert rec["market"] == "prop"
    assert rec["market_type"] == "prop"


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
