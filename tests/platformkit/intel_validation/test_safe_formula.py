"""tests for scripts.platformkit.intel_validation.safe_formula -- the
whitelist-only grammar, including the AGGREGATE extension (sum/mean/count/
count_distinct + arithmetic, evaluated per group). Still no arbitrary eval.

Run ONLY this file:
    python -m pytest tests/platformkit/intel_validation/test_safe_formula.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.intel_validation.safe_formula import (  # noqa: E402
    FormulaError,
    evaluate_formula,
    evaluate_group_formula,
)


def _df() -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": ["a", "a", "b"],
        "game_id": ["g1", "g2", "g1"],
        "pts": [10.0, 20.0, 7.0],
        "fga": [8.0, 12.0, 5.0],
        "fta": [2.0, 4.0, 0.0],
    })


def test_group_sum_arithmetic_ts_pct_shape():
    s = evaluate_group_formula("sum(pts)/(2*(sum(fga)+0.44*sum(fta)))", _df(), "player_id")
    assert s["a"] == pytest.approx(30.0 / (2 * (20.0 + 0.44 * 6.0)))
    assert s["b"] == pytest.approx(7.0 / (2 * (5.0 + 0.0)))


def test_group_mean_count_count_distinct():
    df = _df()
    assert evaluate_group_formula("mean(pts)", df, "player_id")["a"] == pytest.approx(15.0)
    assert int(evaluate_group_formula("count(pts)", df, "player_id")["a"]) == 2
    assert int(evaluate_group_formula("count_distinct(game_id)", df, "player_id")["b"]) == 1


def test_bare_column_rejected_in_aggregate_expression():
    with pytest.raises(FormulaError):
        evaluate_group_formula("pts", _df(), "player_id")
    with pytest.raises(FormulaError):
        evaluate_group_formula("sum(pts) + fga", _df(), "player_id")


def test_non_whitelisted_call_rejected():
    with pytest.raises(FormulaError):
        evaluate_group_formula("__import__('os').system('echo pwned')", _df(), "player_id")
    with pytest.raises(FormulaError):
        evaluate_group_formula("eval(pts)", _df(), "player_id")


def test_unknown_column_and_bad_args_rejected():
    with pytest.raises(FormulaError):
        evaluate_group_formula("sum(nope)", _df(), "player_id")
    with pytest.raises(FormulaError):
        evaluate_group_formula("sum(pts, fga)", _df(), "player_id")
    with pytest.raises(FormulaError):
        evaluate_group_formula("sum(1)", _df(), "player_id")


def test_missing_group_by_and_constant_only_rejected():
    with pytest.raises(FormulaError):
        evaluate_group_formula("sum(pts)", _df(), "team_id")
    with pytest.raises(FormulaError):
        evaluate_group_formula("1 + 2", _df(), "player_id")


def test_rowwise_formula_still_works():
    vals = evaluate_formula("pts + fga", _df())
    assert list(vals) == [18.0, 32.0, 12.0]
