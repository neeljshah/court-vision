"""Per-file tests for scripts.platformkit.pm_trading.paper_autobet.

Run ONLY this file (the full suite freezes the box):
    python -m pytest scripts/platformkit/pm_trading/test_paper_autobet.py -q
"""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit import clv_ledger as L
from scripts.platformkit.pm_trading.paper_autobet import (
    AutoBetConfig,
    EdgeCandidate,
    _kelly_fraction_decimal,
    run_slate,
    size_stake,
)


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
