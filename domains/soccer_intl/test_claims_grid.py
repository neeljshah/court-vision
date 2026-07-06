"""Drift-guard + grammar-parse tests for domains/soccer_intl/claims_grid.py.

claims_grid.py must stay logic-free (spec sec 1); this test file is the ONLY
place that imports safe_formula's real parser to check the grid's dim
formulas actually parse, and the ONLY place that reads the real parquet to
confirm no declared column is a phantom. Mirrors
domains/basketball_nba/test_claims_grid.py exactly; window-type-bucket
mapping is generalized (not NBA's season_2024_25-shaped names) since this
grid ships a single career_to_date window, no "season_*"-named window.
Per-file only (bash-cwd-prefix rule).

Run: python -m pytest domains/soccer_intl/test_claims_grid.py -q
"""
from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

from domains.soccer_intl.claims_grid import GRID
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
    """Bare-Name identifiers referenced anywhere in an agg-grammar expression
    string, e.g. 'sum(miles_flown_in)' -> {'miles_flown_in'}. Reuses stdlib
    ast (the same module safe_formula.py itself parses with)."""
    tree = ast.parse(expr, mode="eval")
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def _window_type(name: str) -> str:
    """Same classification rule the real factory uses
    (claims_factory.py:81-87, `_window_type`): a name starting with "career"
    is type "career", everything else defaults to "season". Reimplemented
    here (not imported) so this test never depends on the factory module --
    the grid config's OWN drift guard must stand on its own per spec sec 1."""
    return "career" if name.startswith("career") else "season"


def test_grid_shape_sane() -> None:
    assert GRID["sport"] == "soccer_intl"
    assert len(GRID["families"]) >= 1
    for fam in GRID["families"]:
        assert fam["dims"], f"{fam['family']}: no dims declared"
        assert fam["windows"], f"{fam['family']}: no windows declared"


def test_every_window_type_has_a_required_floor() -> None:
    """Spec sec 1: floors REQUIRED per window; a window with no matching floor
    entry is a spec violation (fail-closed), not a silent gap."""
    for fam in GRID["families"]:
        floors = fam["floors"]
        assert floors, f"{fam['family']}: floors dict missing entirely"
        for window in fam["windows"]:
            name = window["name"]
            window_type = _window_type(name)
            assert window_type in floors, (
                f"{fam['family']}: window {name!r} has no {window_type!r} floor entry"
            )
            assert floors[window_type], f"{fam['family']}: {window_type!r} floor is empty"
        if fam.get("context_splits"):
            assert "split" in floors, f"{fam['family']}: has context_splits but no 'split' floor"
            assert floors["split"], f"{fam['family']}: 'split' floor is empty"


_AGG_FUNC_NAMES = {"sum", "mean", "count", "count_distinct"}


def test_every_dim_column_exists_on_declared_source() -> None:
    """Drift guard: a phantom column (declared in agg.num/agg.den but absent
    from the real on-disk parquet) is a review FAIL per spec sec 1."""
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
    """THE grammar-parse check: build criteria.formula the same way the
    factory will (f"({num})/({den})") and run it through safe_formula's real
    evaluate_group_formula against a real, tiny slice of the actual on-disk
    parquet -- any unknown column or disallowed syntax raises FormulaError."""
    for fam in GRID["families"]:
        path = REPO_ROOT / fam["source"]
        df = pd.read_parquet(path).head(50).copy()  # tiny real-schema fixture, per rails
        group_by = fam["entity_key"]
        for dim in fam["dims"]:
            num = dim["agg"]["num"]
            den = dim["agg"]["den"]
            formula = f"({num})/({den})"
            try:
                result = evaluate_group_formula(formula, df, group_by)
            except FormulaError as e:  # pragma: no cover - failure path asserted below
                pytest.fail(f"{fam['family']}.{dim['metric']}: formula {formula!r} failed to parse: {e}")
            assert not result.empty, f"{fam['family']}.{dim['metric']}: formula produced no groups"


def test_floor_column_is_row_unique_within_entity_group() -> None:
    """soccer_intl-SPECIFIC guard (the reason this grid drops the
    tournament-grain family entirely, per the module docstring): the
    factory's floor mechanism is count_distinct(floor_col) PER ENTITY GROUP
    (claims_factory.py:132), which only counts true row volume if the floor
    column is row-unique WITHIN that group. This test proves match_row
    satisfies that on the REAL data (count == nunique per team, i.e.
    count_distinct never undercounts) -- catching the exact drift class
    that sank the dropped comp_goals_rate family before it can ship silently
    mis-gated or mis-labeled."""
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
                    f"within every {group_by!r} group ({len(mismatched)} groups mismatch) "
                    f"-- count_distinct({floor_col!r}) would undercount true row volume"
                )


def test_deterministic_no_duplicate_metric_names_within_family() -> None:
    """claim_id is family__entity__metric__window (spec sec 2) -- a duplicate
    metric name within one family would silently collide claim_ids."""
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


def test_window_filters_use_exact_match_only() -> None:
    """The real factory's `_slice_rows` (claims_factory.py:96-107) supports
    ONLY exact-equality filters (`out[out[col] == val]`) -- no range/`_gte`
    operator exists. A window filter value must be a plain scalar (or the
    filter dict empty), never a dict/list that implies a range operator this
    grid config would silently fail to apply as intended."""
    for fam in GRID["families"]:
        for window in fam["windows"]:
            filt = window.get("filter") or {}
            for col, val in filt.items():
                assert isinstance(val, (str, int, float, bool)), (
                    f"{fam['family']}: window {window['name']!r} filter[{col!r}]={val!r} "
                    f"is not a plain scalar -- the factory only supports exact equality"
                )


def test_grid_module_has_zero_imports_beyond_future() -> None:
    """claims_grid.py must never import the factory (spec sec 1: 'the config
    never imports the factory'). Static check on the source text."""
    src = (REPO_ROOT / "domains" / "soccer_intl" / "claims_grid.py").read_text(encoding="ascii")
    import_lines = [ln for ln in src.splitlines() if ln.strip().startswith(("import ", "from "))]
    assert import_lines == ["from __future__ import annotations"], (
        f"claims_grid.py must be import-free except __future__.annotations; found: {import_lines}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
