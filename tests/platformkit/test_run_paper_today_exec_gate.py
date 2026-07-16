"""Per-file test: the pregame exec-quality gate wiring in run_paper_today (F1).

Proves the mission contract:
  (a) a placed pregame row carries an exec_gate dict + placement_latency_ms
      (m44 exec-evidence reader now sees pregame rows as gated).
  (b) a gate exception NEVER blocks the placement -- the row is still recorded,
      ungated, with an exec_gate_error note (crash-safety: m1_paper never crashes).
  (c) a below-expected-CLV-floor row is SUPPRESSED (mirrors the in-game block).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
       tests/platformkit/test_run_paper_today_exec_gate.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

from scripts.platformkit.pm_trading.run_paper_today import run_paper_cycle
import scripts.platformkit.pm_trading.run_paper_today as mod


def _live(sport):
    return {"status": "ok", "games": [
        {"home": "SAS", "away": "NYK", "status": "scheduled"}]}


def _noop_odds(sport):
    return (lambda *a, **k: None), []


def _board_fn_factory(model_prob: float, price: float):
    # selection must equal the home team name (side_of maps by team name, not
    # "home"/"away") so the row routes to the PRICED bet path, not prediction-log.
    row = {"group": "pregame", "selection": "SAS",
           "model_prob": model_prob, "best_price": price,
           "best_book": "espn", "line": None, "fair_odds": None}

    def _board_fn(sp, home, away, **kw):
        return {"status": "ok", "home": home, "away": away,
                "best_bets": [row], "groups": [{"bets": [row]}]}
    return _board_fn


def _read_ledger(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip()]


def test_placed_row_carries_exec_gate_and_latency(tmp_path):
    # model_prob=0.70, price=1.60 -> expected_clv_pct=(1.60*0.70-1)*100=12.0 >= 1.0
    ledger = tmp_path / "ledger.jsonl"
    out = run_paper_cycle(
        sports=["nba"], ledger_path=ledger, predictions_path=tmp_path / "p.jsonl",
        live_fetch=_live, board_fn=_board_fn_factory(0.70, 1.60),
        odds_index=_noop_odds)
    assert out["n_recorded"] == 1
    rows = _read_ledger(ledger)
    assert len(rows) == 1
    r = rows[0]
    assert isinstance(r["exec_gate"], dict) and r["exec_gate"]["passed"] is True
    assert r["exec_gate"]["expected_clv_pct"] >= 1.0
    assert isinstance(r["placement_latency_ms"], (int, float))
    assert "exec_gate_error" not in r


def test_gate_exception_still_records_ungated(tmp_path):
    ledger = tmp_path / "ledger.jsonl"

    def _boom(**kw):
        raise RuntimeError("boom")

    with patch.object(mod._exec_gate, "gate", _boom):
        out = run_paper_cycle(
            sports=["nba"], ledger_path=ledger,
            predictions_path=tmp_path / "p.jsonl", live_fetch=_live,
            board_fn=_board_fn_factory(0.70, 1.60), odds_index=_noop_odds)
    assert out["n_recorded"] == 1  # gate error must NOT lose the row
    r = _read_ledger(ledger)[0]
    assert r.get("exec_gate_error") == "RuntimeError"
    assert "exec_gate" not in r  # ungated on error
    assert isinstance(r["placement_latency_ms"], (int, float))


def test_below_expected_clv_floor_suppressed(tmp_path):
    # A bet that CLEARS the EV floor + policy tier (0.70*1.60-1 = +0.12, tier A) is
    # still SUPPRESSED when its expected_clv_pct (=12.0) is below the exec floor --
    # proving the gate blocks (mirror in-game). We raise the threshold above the tier
    # floor here because, at the default 1.0%, the policy tier-C floor (ev>=0.02 =
    # 2.0%) always dominates, so the block is an additional lower net that never
    # independently fires under the current policy config (documented in the module).
    ledger = tmp_path / "ledger.jsonl"
    with patch.object(mod, "_PREGAME_EXPECTED_CLV_MIN_PCT", 50.0):
        out = run_paper_cycle(
            sports=["nba"], ledger_path=ledger, predictions_path=tmp_path / "p.jsonl",
            live_fetch=_live, board_fn=_board_fn_factory(0.70, 1.60),
            odds_index=_noop_odds)
    assert out["n_recorded"] == 0
    assert not ledger.exists() or _read_ledger(ledger) == []
