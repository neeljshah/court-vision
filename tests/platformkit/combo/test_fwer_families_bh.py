"""S14 -- the within-family BH bar, and proof the global K bar did not move.

Run ONLY this file: python -m pytest tests/platformkit/combo/test_fwer_families_bh.py -q
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from scripts.platformkit.combo.fwer_budget import (
    DEFAULT_Q, across_families, bh_within_family, cumulative_k, eps_eff, min_corpora_eff)
from scripts.platformkit.eval_gate.backtest_runner import _charge_ledger
from scripts.platformkit.eval_gate.deflated_metrics import deflated_p
from scripts.platformkit.eval_gate.ledger import load_fwer

PLANTED_NULLS = 200
SEED = 20260903
MAX_DISCOVERIES = 10
REAL_LEDGER = Path("data/cache/eval_gate/backtest_fwer.jsonl")


def planted_nulls(n: int = PLANTED_NULLS, seed: int = SEED) -> list:
    return [float(p) for p in np.random.default_rng(seed).uniform(0.0, 1.0, size=n)]


def test_two_hundred_planted_nulls_yield_at_most_ten_discoveries():
    nulls = planted_nulls()
    result = bh_within_family(nulls, q=DEFAULT_Q)
    assert result.n == PLANTED_NULLS and result.q == 0.05
    assert result.n_discoveries <= MAX_DISCOVERIES, result.n_discoveries
    assert len(result.rejected) == PLANTED_NULLS and len(result.adjusted) == PLANTED_NULLS


def test_all_null_family_yields_no_discovery():
    assert bh_within_family([0.2, 0.4, 0.6, 0.8, 0.95]).n_discoveries == 0


def test_bh_returns_results_in_input_order_not_sorted_order():
    result = bh_within_family([0.9, 1e-6, 0.8])
    assert result.rejected == (False, True, False)
    assert result.threshold == pytest.approx(1e-6)


def test_bh_rejects_bad_inputs():
    for bad in ([], [0.5, 1.4], [-0.1]):
        with pytest.raises(ValueError):
            bh_within_family(bad)
    with pytest.raises(ValueError):
        bh_within_family([0.5], q=0.0)


def test_across_families_is_the_canonical_deflation():
    for p, n in ((0.01, 5), (0.5, 10), (0.02, 1), (0.001, 37)):
        assert across_families(p, n) == deflated_p(p, n)


def test_the_global_k_bar_did_not_move(tmp_path):
    """B10 / Q3: eps_eff, min_corpora_eff and cumulative_k are byte-for-byte the old ones,
    and charging a tmp ledger still walks k_cumulative 1,2,3 with the new module imported."""
    assert eps_eff(0.05, 20) == 0.05 / 20
    assert min_corpora_eff(4, 8) == 4 and min_corpora_eff(2, 8) == 2
    assert cumulative_k(13, 1) == 14
    ledger = tmp_path / "backtest_fwer.jsonl"
    before = [_charge_ledger(ledger, "s14:probe%d" % i, "nba", "2024-01-01", "2024-02-01")
              for i in range(3)]
    assert [row["k_cumulative"] for row in before] == [1, 2, 3]
    # exercise the S14 additions between the two reads
    bh_within_family(planted_nulls())
    across_families(0.01, 37)
    after = _charge_ledger(ledger, "s14:probe3", "nba", "2024-01-01", "2024-02-01")
    assert after["k_cumulative"] == 4
    rows = load_fwer(ledger)
    assert [r["k_cumulative"] for r in rows] == [1, 2, 3, 4]
    assert all(r["family"] is None and r["k_family"] is None for r in rows)


def test_the_real_charge_ledger_is_never_touched():
    """NON-TAUTOLOGY guard: no test in this file may write the production ledger."""
    if not REAL_LEDGER.exists():
        pytest.skip("production ledger absent in this clone")
    digest = hashlib.sha256(REAL_LEDGER.read_bytes()).hexdigest()
    bh_within_family(planted_nulls())
    across_families(0.01, 37)
    assert hashlib.sha256(REAL_LEDGER.read_bytes()).hexdigest() == digest


def test_no_historical_row_carries_a_family(tmp_path):
    """Condition (i): the frozen spec predates the first family-relative trial. A legacy
    row reads back with family=None, so nothing recorded so far can be re-priced by family."""
    ledger = tmp_path / "legacy.jsonl"
    ledger.write_text(json.dumps({"at": "2026-09-01T00:00:00+00:00", "predictor": "legacy",
                                  "sport": "nba", "start": "2024-01-01", "end": "2024-02-01",
                                  "k_cumulative": 14}) + "\n", encoding="ascii")
    rows = load_fwer(ledger)
    assert rows[0]["family"] is None and rows[0]["k_family"] is None
