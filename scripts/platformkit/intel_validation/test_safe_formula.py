"""Per-file tests for safe_formula's vectorized evaluator (spec sec 3, batch
validation). `evaluate_formula_vectorized` must return IDENTICAL numeric
results to the row-wise `evaluate_formula` -- same whitelist grammar, same
AST allowlist, only the binding (Series vs per-row dict) differs.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/intel_validation/test_safe_formula.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.intel_validation.safe_formula import (
    FormulaError,
    evaluate_formula,
    evaluate_formula_vectorized,
)


@pytest.fixture
def df() -> pd.DataFrame:
    return pd.DataFrame({
        "pts": [30.0, 20.0, 25.0, 10.0],
        "reb": [10.0, 5.0, 8.0, 12.0],
        "fga": [20.0, 15.0, 18.0, 8.0],
        "fta": [5.0, 2.0, 3.0, 1.0],
    })


@pytest.mark.parametrize(
    "formula",
    [
        "pts + reb",
        "pts - reb",
        "pts * 2",
        "pts / fga",
        "(pts + reb) / fga",
        "pts / (2 * (fga + 0.44 * fta))",  # real TS%-shaped formula
        "abs(pts - reb)",
        "min(pts, reb)",
        "max(pts, reb)",
        "min(pts, reb, fga)",  # 3-arg reduce path
        "-pts",
        "2 + 3",  # pure literal, no column reference
    ],
)
def test_vectorized_matches_row_wise(df, formula):
    row_wise = evaluate_formula(formula, df)
    vectorized = evaluate_formula_vectorized(formula, df)
    assert list(vectorized) == pytest.approx(list(row_wise))
    assert len(vectorized) == len(df)


def test_vectorized_rejects_unknown_column(df):
    with pytest.raises(FormulaError):
        evaluate_formula_vectorized("pts + nonexistent_col", df)


def test_vectorized_rejects_disallowed_syntax(df):
    with pytest.raises(FormulaError):
        evaluate_formula_vectorized("__import__('os')", df)


def test_vectorized_min_max_elementwise_not_series_picking(df):
    """Regression guard: builtin min()/max() on a list of pandas Series
    raises ValueError (ambiguous truth value) instead of comparing
    elementwise -- the vectorized evaluator must dispatch through
    functools.reduce(np.minimum/np.maximum) instead, proven here against
    hand-computed expected values (not just cross-checked vs row-wise)."""
    result_min = evaluate_formula_vectorized("min(pts, reb)", df)
    result_max = evaluate_formula_vectorized("max(pts, reb)", df)
    assert list(result_min) == [10.0, 5.0, 8.0, 10.0]
    assert list(result_max) == [30.0, 20.0, 25.0, 12.0]
