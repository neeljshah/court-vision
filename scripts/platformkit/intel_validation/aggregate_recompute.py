"""Window slicing + per-group derived-column recompute for the claims contract.

Executes the contract-extension fields on a claim's criteria:
    criteria.window_spec  -- {"kind": "season"|"last_n_games", ...} declares how
                             to slice the raw source rows, mechanically.
    criteria.aggregate    -- {"group_by": <col>, "derived": {<name>: <agg expr>}}
                             declares per-group derived columns (e.g. games,
                             fga_pg) via the whitelist aggregate grammar in
                             safe_formula (sum/mean/count/count_distinct +
                             arithmetic). criteria.formula is evaluated under
                             the SAME grammar to produce the metric (_value).

No import of any producer module -- this is the independent validator lane.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from scripts.platformkit.intel_validation.safe_formula import (
    FormulaError,
    evaluate_group_formula,
)


def apply_window_spec(df: pd.DataFrame, window_spec: dict[str, Any], group_by: str) -> pd.DataFrame:
    """Slice raw rows per the declared, mechanically-reproducible window.

    kind == "season":       keep rows where window_spec.season_col == season.
    kind == "last_n_games": sort by window_spec.order_by, keep the LAST n rows
                            per `group_by` group (most recent n games played).
    """
    kind = window_spec.get("kind")
    if kind == "season":
        col = window_spec.get("season_col") or "season"
        if col not in df.columns:
            raise FormulaError(f"window_spec season_col not present: {col!r}")
        return df[df[col] == window_spec.get("season")]
    if kind == "last_n_games":
        n = window_spec.get("n")
        order_by = window_spec.get("order_by")
        if not n or not order_by:
            raise FormulaError("window_spec last_n_games requires n and order_by")
        if order_by not in df.columns:
            raise FormulaError(f"window_spec order_by column not present: {order_by!r}")
        return df.sort_values(order_by).groupby(group_by, group_keys=False).tail(int(n))
    raise FormulaError(f"unknown window_spec kind: {kind!r}")


def recompute_aggregate(df: pd.DataFrame, criteria: dict[str, Any]) -> pd.DataFrame:
    """Window-slice raw rows, then build the per-group derived table.

    Returns one row per group_by value with every criteria.aggregate.derived
    column plus `_value` = criteria.formula, all evaluated under the whitelist
    aggregate grammar. min_sample floors are NOT applied here -- the caller
    applies them to the returned DERIVED columns."""
    aggregate = criteria["aggregate"]
    group_by = aggregate.get("group_by")
    if not group_by:
        raise FormulaError("aggregate.group_by missing")
    if group_by not in df.columns:
        raise FormulaError(f"aggregate.group_by column not present: {group_by!r}")
    window_spec = criteria.get("window_spec")
    if window_spec:
        df = apply_window_spec(df, window_spec, group_by)
    if df.empty:
        raise FormulaError("no rows after window_spec slicing")
    parts: dict[str, pd.Series] = {}
    for name, expr in (aggregate.get("derived") or {}).items():
        parts[name] = evaluate_group_formula(expr, df, group_by)
    parts["_value"] = evaluate_group_formula(criteria["formula"], df, group_by)
    return pd.DataFrame(parts).reset_index()
