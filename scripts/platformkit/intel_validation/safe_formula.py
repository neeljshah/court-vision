"""Whitelist-only expression grammar for recomputing a claim's ranking metric.

Supports: column names, integer/float literals, + - * / (), and a small set
of whitelisted numpy-free functions (abs, min, max) applied to columns.
ALSO supports a per-group AGGREGATE grammar (evaluate_group_formula):
sum(col), mean(col), count(col), count_distinct(col) plus arithmetic on
those -- used by the claims contract's criteria.aggregate.derived exprs.
Deliberately NOT python eval() of arbitrary code -- every AST node type is
checked against an allowlist before any evaluation happens.
"""
from __future__ import annotations

import ast
import functools
import operator
from typing import Any

import numpy as np
import pandas as pd

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_ALLOWED_FUNCS = {"abs", "min", "max"}


class FormulaError(ValueError):
    """Raised when a formula uses a non-whitelisted construct or references
    an unknown column."""


def _check_columns(formula: str, columns: set[str]) -> None:
    """Pre-parse pass: confirm every Name node in the formula is either a
    known column or a whitelisted function, before any evaluation happens."""
    tree = ast.parse(formula, mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id not in columns and node.id not in _ALLOWED_FUNCS:
                raise FormulaError(f"unknown identifier in formula: {node.id!r}")
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
                raise FormulaError("only abs()/min()/max() calls are allowed in formulas")
        elif isinstance(
            node,
            (
                ast.Expression,
                ast.BinOp,
                ast.UnaryOp,
                ast.Constant,
                ast.Load,
                ast.Name,
                ast.Call,
            ),
        ):
            continue
        elif isinstance(node, tuple(_ALLOWED_BINOPS.keys())) or isinstance(
            node, tuple(_ALLOWED_UNARYOPS.keys())
        ):
            continue
        else:
            raise FormulaError(f"disallowed syntax in formula: {type(node).__name__}")


def _eval_node(node: ast.AST, row: dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, row)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise FormulaError(f"disallowed constant type: {type(node.value).__name__}")
    if isinstance(node, ast.Name):
        if node.id in row:
            return row[node.id]
        raise FormulaError(f"unknown identifier: {node.id!r}")
    if isinstance(node, ast.BinOp):
        op = _ALLOWED_BINOPS.get(type(node.op))
        if op is None:
            raise FormulaError(f"disallowed operator: {type(node.op).__name__}")
        return op(_eval_node(node.left, row), _eval_node(node.right, row))
    if isinstance(node, ast.UnaryOp):
        op = _ALLOWED_UNARYOPS.get(type(node.op))
        if op is None:
            raise FormulaError(f"disallowed unary operator: {type(node.op).__name__}")
        return op(_eval_node(node.operand, row))
    if isinstance(node, ast.Call):
        fname = node.func.id  # validated in _check_columns
        args = [_eval_node(a, row) for a in node.args]
        if fname == "abs":
            return abs(args[0])
        if fname == "min":
            return min(args)
        if fname == "max":
            return max(args)
        raise FormulaError(f"disallowed function: {fname}")
    raise FormulaError(f"disallowed syntax node: {type(node).__name__}")


_AGG_FUNCS = {"sum", "mean", "count", "count_distinct"}


def _eval_agg_node(node: ast.AST, grouped: Any, columns: set[str]) -> Any:
    """Recursive whitelist evaluation of a per-group AGGREGATE expression.
    Column names may appear ONLY as the single argument of an aggregate
    function call -- a bare column reference is ambiguous per-group and is
    rejected (fails closed)."""
    if isinstance(node, ast.Expression):
        return _eval_agg_node(node.body, grouped, columns)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise FormulaError(f"disallowed constant type: {type(node.value).__name__}")
    if isinstance(node, ast.BinOp):
        op = _ALLOWED_BINOPS.get(type(node.op))
        if op is None:
            raise FormulaError(f"disallowed operator: {type(node.op).__name__}")
        return op(
            _eval_agg_node(node.left, grouped, columns),
            _eval_agg_node(node.right, grouped, columns),
        )
    if isinstance(node, ast.UnaryOp):
        op = _ALLOWED_UNARYOPS.get(type(node.op))
        if op is None:
            raise FormulaError(f"disallowed unary operator: {type(node.op).__name__}")
        return op(_eval_agg_node(node.operand, grouped, columns))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _AGG_FUNCS:
            raise FormulaError(
                "only sum()/mean()/count()/count_distinct() calls are allowed "
                "in aggregate expressions"
            )
        if len(node.args) != 1 or node.keywords or not isinstance(node.args[0], ast.Name):
            raise FormulaError("aggregate functions take exactly one bare column name")
        col = node.args[0].id
        if col not in columns:
            raise FormulaError(f"unknown column in aggregate expression: {col!r}")
        series = grouped[col]
        fname = node.func.id
        if fname == "sum":
            return series.sum()
        if fname == "mean":
            return series.mean()
        if fname == "count":
            return series.count()
        return series.nunique()
    raise FormulaError(f"disallowed syntax in aggregate expression: {type(node).__name__}")


def evaluate_group_formula(formula: str, df: pd.DataFrame, group_by: str) -> pd.Series:
    """Evaluate a whitelisted AGGREGATE expression once per `group_by` group.

    Grammar: sum(col), mean(col), count(col), count_distinct(col), numeric
    literals, + - * / and parentheses. Returns a Series indexed by the
    `group_by` key. Raises FormulaError on any non-whitelisted construct,
    bare column reference, or unknown column (fails closed)."""
    if group_by not in df.columns:
        raise FormulaError(f"group_by column not present: {group_by!r}")
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as e:
        raise FormulaError(f"unparseable aggregate expression: {e}") from e
    result = _eval_agg_node(tree, df.groupby(group_by), set(df.columns))
    if not isinstance(result, pd.Series):
        raise FormulaError("aggregate expression must aggregate at least one column")
    return result


def evaluate_formula(formula: str, df: pd.DataFrame) -> pd.Series:
    """Evaluate `formula` row-wise over `df` using only whitelisted columns
    and operators. Raises FormulaError on any non-whitelisted construct or
    unknown column reference (fails closed, not silently)."""
    columns = set(df.columns)
    _check_columns(formula, columns)
    tree = ast.parse(formula, mode="eval")

    def _row_eval(row: pd.Series) -> float:
        return _eval_node(tree, row.to_dict())

    return df.apply(_row_eval, axis=1)


def _eval_node_vectorized(node: ast.AST, cols: dict[str, pd.Series]) -> Any:
    """SAME grammar/allowlist as `_eval_node`, but the namespace binds whole
    column Series instead of one row's scalars -- every op (+ - * / abs)
    already vectorizes unchanged over a Series. The ONLY divergence is
    min()/max(): Python's builtin min/max does pairwise `<` comparison, which
    on a Series returns an elementwise bool Series (ambiguous truth value,
    raises) instead of picking the smaller Series -- so those two dispatch
    through `functools.reduce(np.minimum/np.maximum, args)` here instead,
    which is elementwise-correct for Series, Series+scalar, and scalar+scalar
    alike. Identical numeric results to the row-wise path in every case."""
    if isinstance(node, ast.Expression):
        return _eval_node_vectorized(node.body, cols)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise FormulaError(f"disallowed constant type: {type(node.value).__name__}")
    if isinstance(node, ast.Name):
        if node.id in cols:
            return cols[node.id]
        raise FormulaError(f"unknown identifier: {node.id!r}")
    if isinstance(node, ast.BinOp):
        op = _ALLOWED_BINOPS.get(type(node.op))
        if op is None:
            raise FormulaError(f"disallowed operator: {type(node.op).__name__}")
        return op(_eval_node_vectorized(node.left, cols), _eval_node_vectorized(node.right, cols))
    if isinstance(node, ast.UnaryOp):
        op = _ALLOWED_UNARYOPS.get(type(node.op))
        if op is None:
            raise FormulaError(f"disallowed unary operator: {type(node.op).__name__}")
        return op(_eval_node_vectorized(node.operand, cols))
    if isinstance(node, ast.Call):
        fname = node.func.id  # validated in _check_columns
        args = [_eval_node_vectorized(a, cols) for a in node.args]
        if fname == "abs":
            return abs(args[0])
        if fname == "min":
            return functools.reduce(np.minimum, args)
        if fname == "max":
            return functools.reduce(np.maximum, args)
        raise FormulaError(f"disallowed function: {fname}")
    raise FormulaError(f"disallowed syntax node: {type(node).__name__}")


def evaluate_formula_vectorized(formula: str, df: pd.DataFrame) -> pd.Series:
    """Evaluate `formula` ONCE over the whole frame (column-Series ops) instead
    of once per row. SAME whitelist grammar, SAME `_check_columns` gate, SAME
    numeric result as `evaluate_formula` -- proven by the parity test in
    test_claims_validator.py. Only the binding differs (Series vs per-row
    dict); no new expressiveness, no forked grammar."""
    columns = set(df.columns)
    _check_columns(formula, columns)
    tree = ast.parse(formula, mode="eval")
    cols = {c: df[c] for c in columns}
    result = _eval_node_vectorized(tree, cols)
    if not isinstance(result, pd.Series):
        # a formula with no column reference (pure literal) evaluates to one
        # scalar; broadcast to match evaluate_formula's one-value-per-row contract.
        result = pd.Series(result, index=df.index, dtype="float64")
    return result
