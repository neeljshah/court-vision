"""Drift-guard + grammar-parse tests for domains/soccer/claims_grid.py.

claims_grid.py must stay logic-free (spec sec 1); this test file is the ONLY
place that imports safe_formula's real parser to check the grid's dim
formulas actually parse, and the ONLY place that reads the real parquet to
confirm no declared column is a phantom. Mirrors domains/basketball_nba/
test_claims_grid.py exactly. Per-file only (bash-cwd-prefix rule).

Run: python -m pytest domains/soccer/test_claims_grid.py -q
"""
from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

from domains.soccer.claims_grid import GRID
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
    """Same classification rule the real factory uses (claims_factory.py
    `_window_type`): a name starting with "career" is type "career",
    everything else defaults to "season"."""
    return "career" if name.startswith("career") else "season"


def test_grid_shape_sane() -> None:
    assert GRID["sport"] == "soccer"
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
        if fam.get("context_splits"):
            assert "split" in floors, f"{fam['family']}: has context_splits but no 'split' floor"
            assert floors["split"], f"{fam['family']}: 'split' floor is empty"


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


def test_every_window_filter_column_exists_on_declared_source() -> None:
    for fam in GRID["families"]:
        real_cols = _real_columns(fam["source"])
        for window in fam["windows"]:
            for col in (window.get("filter") or {}):
                assert col in real_cols, (
                    f"{fam['family']}: window {window['name']!r} filter references "
                    f"phantom column {col!r} not present on {fam['source']}"
                )


def test_every_dim_formula_parses_against_real_columns() -> None:
    for fam in GRID["families"]:
        path = REPO_ROOT / fam["source"]
        if not path.exists():
            pytest.skip(f"source not present in this checkout: {fam['source']}")
        df = pd.read_parquet(path).head(200).copy()  # tiny real-schema fixture, per rails
        group_by = fam["entity_key"]
        for dim in fam["dims"]:
            num, den = dim["agg"]["num"], dim["agg"]["den"]
            formula = f"({num})/({den})"
            try:
                result = evaluate_group_formula(formula, df, group_by)
            except FormulaError as e:  # pragma: no cover - failure path asserted below
                pytest.fail(f"{fam['family']}.{dim['metric']}: formula {formula!r} failed to parse: {e}")
            assert not result.empty, f"{fam['family']}.{dim['metric']}: formula produced no groups"


def test_deterministic_no_duplicate_metric_names_within_family() -> None:
    for fam in GRID["families"]:
        names = [d["metric"] for d in fam["dims"]]
        assert len(names) == len(set(names)), f"{fam['family']}: duplicate metric name(s)"


def test_context_splits_reference_real_columns() -> None:
    for fam in GRID["families"]:
        if not fam.get("context_splits"):
            continue
        real_cols = _real_columns(fam["source"])
        for split in fam["context_splits"]:
            assert split["col"] in real_cols, (
                f"{fam['family']}: context_split col {split['col']!r} not on {fam['source']}"
            )


def test_grid_module_has_zero_imports_beyond_future() -> None:
    src = (REPO_ROOT / "domains" / "soccer" / "claims_grid.py").read_text(encoding="ascii")
    import_lines = [ln for ln in src.splitlines() if ln.strip().startswith(("import ", "from "))]
    assert import_lines == ["from __future__ import annotations"], (
        f"claims_grid.py must be import-free except __future__.annotations; found: {import_lines}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
