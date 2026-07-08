"""Drift-guard + grammar-parse tests for domains/cross_sport_market/claims_grid.py.
Mirrors domains/soccer_intl/test_claims_grid.py exactly (same checks, same
reasoning) -- see that file's docstring for why each check exists.

Run: python -m pytest domains/cross_sport_market/test_claims_grid.py -q
"""
from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

from domains.cross_sport_market.claims_grid import GRID
from scripts.platformkit.intel_validation.safe_formula import (
    FormulaError,
    evaluate_group_formula,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _real_columns(rel_source: str) -> set[str]:
    path = REPO_ROOT / rel_source
    assert path.exists(), f"grid declares a source that does not exist on disk: {rel_source}"
    return set(pd.read_parquet(path).columns)


def _identifiers_in(expr: str) -> set[str]:
    tree = ast.parse(expr, mode="eval")
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def _window_type(name: str) -> str:
    return "career" if name.startswith("career") else "season"


def test_grid_shape_sane() -> None:
    assert GRID["sport"] == "cross_sport_market"
    assert len(GRID["families"]) >= 1
    for fam in GRID["families"]:
        assert fam["dims"], f"{fam['family']}: no dims declared"
        assert fam["windows"], f"{fam['family']}: no windows declared"


def test_every_window_type_has_a_required_floor() -> None:
    for fam in GRID["families"]:
        floors = fam["floors"]
        assert floors, f"{fam['family']}: floors dict missing entirely"
        for window in fam["windows"]:
            window_type = _window_type(window["name"])
            assert window_type in floors, (
                f"{fam['family']}: window {window['name']!r} has no {window_type!r} floor entry"
            )
            assert floors[window_type], f"{fam['family']}: {window_type!r} floor is empty"


_AGG_FUNC_NAMES = {"sum", "mean", "count", "count_distinct"}


def test_every_dim_column_exists_on_declared_source() -> None:
    for fam in GRID["families"]:
        real_cols = _real_columns(fam["source"])
        assert fam["entity_key"] in real_cols, (
            f"{fam['family']}: entity_key {fam['entity_key']!r} not on {fam['source']}"
        )
        for dim in fam["dims"]:
            for side in ("num", "den"):
                expr = dim["agg"][side]
                referenced = _identifiers_in(expr) - _AGG_FUNC_NAMES
                missing = referenced - real_cols
                assert not missing, (
                    f"{fam['family']}.{dim['metric']}.{side} references phantom "
                    f"column(s) {missing} not present on {fam['source']}"
                )


def test_every_dim_formula_parses_against_real_columns() -> None:
    for fam in GRID["families"]:
        path = REPO_ROOT / fam["source"]
        df = pd.read_parquet(path).head(50).copy()
        group_by = fam["entity_key"]
        for dim in fam["dims"]:
            formula = f"({dim['agg']['num']})/({dim['agg']['den']})"
            try:
                result = evaluate_group_formula(formula, df, group_by)
            except FormulaError as e:  # pragma: no cover
                pytest.fail(f"{fam['family']}.{dim['metric']}: formula {formula!r} failed to parse: {e}")
            assert not result.empty, f"{fam['family']}.{dim['metric']}: formula produced no groups"


def test_floor_column_is_row_unique_within_entity_group() -> None:
    for fam in GRID["families"]:
        path = REPO_ROOT / fam["source"]
        df = pd.read_parquet(path)
        group_by = fam["entity_key"]
        for win_type, floor_cols in fam["floors"].items():
            for floor_col in floor_cols:
                g = df.groupby(group_by)[floor_col].agg(["count", "nunique"])
                mismatched = g[g["count"] != g["nunique"]]
                assert mismatched.empty, (
                    f"{fam['family']}: floor column {floor_col!r} is NOT row-unique "
                    f"within every {group_by!r} group ({len(mismatched)} groups mismatch)"
                )


def test_at_least_one_entity_clears_the_floor() -> None:
    """A grid whose floor excludes EVERY entity would still generate an
    (empty) claim -- not a factory bug, but this session's real-coverage
    claim (module docstring) needs at least one bucket to actually survive
    per family, or the family is descriptive theater."""
    for fam in GRID["families"]:
        path = REPO_ROOT / fam["source"]
        df = pd.read_parquet(path)
        group_by = fam["entity_key"]
        floor = next(iter(fam["floors"].values()))
        floor_col, min_n = next(iter(floor.items()))
        counts = df.groupby(group_by)[floor_col].nunique()
        assert (counts >= min_n).any(), (
            f"{fam['family']}: NO entity clears floor {floor_col}>={min_n}"
        )


def test_deterministic_no_duplicate_metric_names_within_family() -> None:
    for fam in GRID["families"]:
        names = [d["metric"] for d in fam["dims"]]
        assert len(names) == len(set(names)), f"{fam['family']}: duplicate metric name(s)"


def test_window_filters_use_exact_match_only() -> None:
    for fam in GRID["families"]:
        for window in fam["windows"]:
            filt = window.get("filter") or {}
            for col, val in filt.items():
                assert isinstance(val, (str, int, float, bool)), (
                    f"{fam['family']}: window {window['name']!r} filter[{col!r}]={val!r} "
                    f"is not a plain scalar"
                )


def test_grid_module_has_zero_imports_beyond_future() -> None:
    src = (REPO_ROOT / "domains" / "cross_sport_market" / "claims_grid.py").read_text(encoding="ascii")
    import_lines = [ln for ln in src.splitlines() if ln.strip().startswith(("import ", "from "))]
    assert import_lines == ["from __future__ import annotations"], (
        f"claims_grid.py must be import-free except __future__.annotations; found: {import_lines}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
