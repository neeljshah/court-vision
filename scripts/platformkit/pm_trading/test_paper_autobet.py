"""Per-file tests for scripts.platformkit.pm_trading.paper_autobet.

Run ONLY this file (the full suite freezes the box):
    python -m pytest scripts/platformkit/pm_trading/test_paper_autobet.py -q
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.platformkit import clv_ledger as L
from scripts.platformkit.pm_trading.paper_autobet import (
    AutoBetConfig,
    EdgeCandidate,
    _kelly_fraction_decimal,
    run_slate,
    size_stake,
)

# Banned dollar-connoting keys per honesty rails.
_BANNED_KEYS = re.compile(r"(pnl|profit|dollar|\$)", re.IGNORECASE)


def _ledger(tmp_path) -> Path:
    return tmp_path / "ledger.jsonl"


def test_kelly_fraction_zero_when_no_edge():
    # model 0.40 at 1.95 (implied ~0.513) -> negative edge -> 0 fraction.
    assert _kelly_fraction_decimal(0.40, 1.95) == 0.0
    # model 0.60 at 1.95 -> positive edge -> positive fraction.
    assert _kelly_fraction_decimal(0.60, 1.95) > 0.0


def test_size_stake_kelly_clamped_and_skips_negative_ev():
    cfg = AutoBetConfig(bankroll=10_000.0, sizing="kelly", kelly_cap=0.05,
                        max_stake=1_000.0)
    pos = EdgeCandidate("nba", "A@B", "home", 1.95, 0.58)
    neg = EdgeCandidate("nba", "C@D", "away", 2.50, 0.30)
    s = size_stake(pos, cfg)
    assert 0.0 < s <= 0.05 * cfg.bankroll  # never above the kelly cap dollars
    assert size_stake(neg, cfg) == 0.0     # -EV -> no stake


def test_flat_sizing_uses_unit_stake():
    cfg = AutoBetConfig(sizing="flat", unit_stake=250.0, max_stake=1_000.0)
    cand = EdgeCandidate("nba", "A@B", "home", 1.95, 0.58)
    assert size_stake(cand, cfg) == 250.0


def test_run_slate_records_paper_only_and_updates_clv(tmp_path):
    path = _ledger(tmp_path)
    slate = [
        EdgeCandidate("nba", "BOS@NYK", "home", 1.95, 0.58,
                      closing_decimal_home=1.80, closing_decimal_away=2.10),
        EdgeCandidate("nba", "LAL@DEN", "away", 2.50, 0.30,
                      closing_decimal_home=1.50, closing_decimal_away=2.70),
    ]
    out = run_slate(slate, AutoBetConfig(bankroll=10_000.0), path=path)

    # honesty invariants
    assert out["executed_any"] is False
    assert out["channel"] == "paper"
    # one +EV recorded+settled, one -EV skipped
    assert out["n_recorded"] == 1
    assert out["n_settled"] == 1
    # CLV summary updated from the paper bet
    summ = out["clv_summary"]
    assert summ["n_bets"] == 1
    assert summ["mean_clv_pct"] is not None
    # we took a better number than the close -> positive CLV, beat == True
    assert summ["pct_beat_close"] == 100.0
    rec_row = [b for b in out["bets"] if b["status"] == "settled"][0]
    assert rec_row["beat_close"] is True
    assert rec_row["clv_pct"] > 0.0


def test_every_ledger_row_is_unexecuted(tmp_path):
    path = _ledger(tmp_path)
    slate = [EdgeCandidate("nba", "A@B", "home", 1.95, 0.58,
                           closing_decimal_home=1.80, closing_decimal_away=2.10)]
    run_slate(slate, AutoBetConfig(), path=path)
    rows = L.load_ledger(path)
    assert rows, "expected at least one ledger row"
    # the open row AND the settled twin must both be executed=False, paper-channel
    for r in rows:
        assert r.get("executed") is False
        assert r.get("channel", "paper") == "paper"


def test_total_exposure_cap_trims_the_slate(tmp_path):
    path = _ledger(tmp_path)
    # three identical +EV flat-100 bets but a $150 total cap -> only $150 staked.
    slate = [
        EdgeCandidate("nba", "G%d@H%d" % (i, i), "home", 1.95, 0.58)
        for i in range(3)
    ]
    cfg = AutoBetConfig(sizing="flat", unit_stake=100.0,
                        max_total_exposure=150.0)
    out = run_slate(slate, cfg, path=path)
    assert out["staked_total"] <= 150.0 + 1e-9
    # first full 100, second trimmed to 50, third no room
    assert out["n_recorded"] == 2


# ---------------------------------------------------------------------------
# BE-D acceptance tests: normalized stake_units, no-dollar ledger rows
# ---------------------------------------------------------------------------

def test_recorded_rows_stake_units_in_band(tmp_path):
    """Every ledger row must have stake_units in [0, 10], not raw dollars.

    With default unit_size=$100 and a $1000 kelly cap, the worst case is 10u.
    Old code passed raw dollars (e.g. ~382), which violates the invariant.
    """
    path = _ledger(tmp_path)
    # Large bankroll so Kelly sizing produces dollars well above 10.
    cfg = AutoBetConfig(bankroll=100_000.0, sizing="kelly",
                        kelly_cap=0.05, max_stake=5_000.0,
                        unit_size=100.0)
    slate = [
        EdgeCandidate("nba", "BOS@NYK", "home", 1.95, 0.58,
                      closing_decimal_home=1.80, closing_decimal_away=2.10),
        EdgeCandidate("nba", "MIL@PHX", "home", 1.90, 0.60),
    ]
    run_slate(slate, cfg, path=path)
    rows = L.load_ledger(path)
    open_rows = [r for r in rows if r.get("status") == "open"]
    assert open_rows or any(r.get("status") == "settled" for r in rows), \
        "expected at least one recorded row"
    for r in rows:
        su = r.get("stake_units")
        if su is not None:
            assert 0.0 <= float(su) <= 10.0, (
                "stake_units out of 0-10 band: %r (raw dollars leak?)" % su
            )


def test_skipped_rows_have_stake_units_zero(tmp_path):
    """Skipped (no-edge, exposure-cap) bet rows must carry stake_units=0.0."""
    path = _ledger(tmp_path)
    slate = [
        # -EV -> skipped_no_edge
        EdgeCandidate("nba", "LAL@DEN", "away", 2.50, 0.30),
        # +EV, but cap=0 -> skipped_exposure_cap
        EdgeCandidate("nba", "BOS@NYK", "home", 1.95, 0.58),
    ]
    cfg = AutoBetConfig(sizing="flat", unit_stake=100.0, max_total_exposure=0.0)
    out = run_slate(slate, cfg, path=path)
    for b in out["bets"]:
        if "skipped" in b.get("status", ""):
            assert b.get("stake_units") == 0.0, (
                "skipped row must have stake_units=0.0, got %r" % b
            )
    # No rows should be recorded when cap is 0.
    assert out["n_recorded"] == 0


def test_no_dollar_keys_in_ledger_rows(tmp_path):
    """No ledger row may carry a key containing pnl/profit/dollar/$.

    This guards the /api/paper/trail endpoint: trail rows are built directly
    from ledger rows, so a banned key here would surface as a dollar field.
    """
    path = _ledger(tmp_path)
    slate = [
        EdgeCandidate("nba", "BOS@NYK", "home", 1.95, 0.58,
                      closing_decimal_home=1.80, closing_decimal_away=2.10),
    ]
    run_slate(slate, AutoBetConfig(), path=path)
    rows = L.load_ledger(path)
    assert rows, "expected ledger rows"
    for r in rows:
        for key in r.keys():
            assert not _BANNED_KEYS.search(key), (
                "banned dollar-connoting key %r found in ledger row" % key
            )


def test_flat_sizing_units_matches_unit_size(tmp_path):
    """Flat-sizing with unit_stake=100, unit_size=100 -> stake_units=1.0.

    This is the canonical calibration check: $100 stake / $100 per unit = 1u.
    """
    path = _ledger(tmp_path)
    cfg = AutoBetConfig(sizing="flat", unit_stake=100.0,
                        max_stake=1_000.0, unit_size=100.0)
    slate = [EdgeCandidate("nba", "A@B", "home", 1.95, 0.58)]
    out = run_slate(slate, cfg, path=path)
    assert out["n_recorded"] == 1
    rows = L.load_ledger(path)
    open_rows = [r for r in rows if r.get("status") == "open"]
    assert open_rows, "expected one open ledger row"
    assert open_rows[0]["stake_units"] == pytest.approx(1.0, abs=1e-5), (
        "flat $100 / unit_size $100 should record as 1.0 unit"
    )


def test_kelly_sizing_units_never_exceed_band_max(tmp_path):
    """Kelly sizing with a large bankroll must still record <= 10 units."""
    path = _ledger(tmp_path)
    # Bankroll so large that kelly_cap*bankroll >> max_stake >> 10*unit_size.
    cfg = AutoBetConfig(bankroll=1_000_000.0, sizing="kelly",
                        kelly_cap=0.05, max_stake=50_000.0,
                        unit_size=100.0)
    slate = [EdgeCandidate("nba", "BOS@NYK", "home", 1.95, 0.58)]
    run_slate(slate, cfg, path=path)
    rows = L.load_ledger(path)
    for r in rows:
        su = r.get("stake_units")
        if su is not None:
            assert float(su) <= 10.0, (
                "stake_units exceeds band max 10: %r" % su
            )
