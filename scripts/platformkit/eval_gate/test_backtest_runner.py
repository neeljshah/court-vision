"""Focused smoke tests for the frozen odds-corpus backtest runner."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import pytest

from scripts.platformkit.eval_gate.backtest_runner import (
    canonical_ledger_path, run_backtest,
)


def _corpus(root: Path) -> None:
    base = root / "data" / "domains" / "basketball_nba"
    base.mkdir(parents=True)
    odds, games = [], []
    for i in range(60):
        date = f"2025-{'10' if i < 31 else '11'}-{i % 31 + 1:02d}"
        favorite = i % 2 == 0
        odds.append({"date": date, "home_team": f"H{i}", "away_team": f"A{i}",
                     "home_ml": -400 if favorite else 400, "away_ml": 400 if favorite else -400})
        games.append({"game_id": f"g{i}", "date": date, "home_team": f"H{i}", "away_team": f"A{i}",
                      "home_win": int(favorite)})
    pd.DataFrame(odds).to_parquet(base / "odds.parquet", index=False)
    pd.DataFrame(games).to_parquet(base / "games.parquet", index=False)


def test_reference_verdicts_and_cumulative_charge(tmp_path: Path):
    _corpus(tmp_path)
    ledger = tmp_path / "fwer.jsonl"
    common = dict(sport="basketball_nba", start="2025-10-01", end="2025-11-30", repo=tmp_path,
                  ledger_path=ledger, allow_noncanonical_ledger=True)
    echo = run_backtest("scripts.platformkit.eval_gate.backtest_runner:close_echo", **common,
                        allow_reference_close_echo=True)
    uniform = run_backtest("scripts.platformkit.eval_gate.backtest_runner:uniform_half", **common)
    assert echo["verdict"] == "MATCH"
    assert echo["scores"]["model_brier"] == echo["scores"]["close_brier"]
    assert uniform["verdict"] == "BEHIND"
    assert uniform["fwer"]["k_cumulative"] == 2


def test_current_row_is_redacted(tmp_path: Path, monkeypatch):
    _corpus(tmp_path)
    probe = tmp_path / "probe.py"
    probe.write_text("def predict(train, test, select_inside):\n    assert 'outcome' not in test\n    assert 'devig_close_prob' not in test\n    return 0.5\n", encoding="ascii")
    monkeypatch.syspath_prepend(str(tmp_path))
    report = run_backtest("probe:predict", "basketball_nba", "2025-10-01", "2025-11-30",
                          repo=tmp_path, ledger_path=tmp_path / "guard.jsonl",
                          allow_noncanonical_ledger=True)
    assert report["n_games"] == 60


def test_s40b_rt3_noncanonical_ledger_is_refused_before_it_is_created(tmp_path: Path):
    """RT-3: any --ledger path was accepted and CREATED, so a charged run outside the
    main repo started a fresh K. Measured before the fix: k_cumulative=1 -> dm_alpha
    0.050000 against 0.003846 at the canonical K=13 -- a 13x looser per-test bar."""
    _corpus(tmp_path)
    scratch = tmp_path / "scratch" / "backtest_fwer.jsonl"
    with pytest.raises(ValueError, match="non-canonical ledger"):
        run_backtest("scripts.platformkit.eval_gate.backtest_runner:uniform_half",
                     "basketball_nba", "2025-10-01", "2025-11-30",
                     repo=tmp_path, ledger_path=scratch)
    assert not scratch.exists()          # refused BEFORE the charge created it
    # the escape hatch is explicit, and the report says which ledger K came from.
    report = run_backtest("scripts.platformkit.eval_gate.backtest_runner:uniform_half",
                          "basketball_nba", "2025-10-01", "2025-11-30",
                          repo=tmp_path, ledger_path=scratch, allow_noncanonical_ledger=True)
    assert report["fwer"]["ledger_canonical"] is False
    assert canonical_ledger_path().name == "backtest_fwer.jsonl"
    assert canonical_ledger_path().parent.as_posix().endswith("data/cache/eval_gate")
