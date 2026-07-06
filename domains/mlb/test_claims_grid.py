"""Drift-guard + grammar-parse tests for domains/mlb/claims_grid.py.

claims_grid.py must stay logic-free (spec sec 1); this test file is the ONLY
place that imports safe_formula's real parser to check the grid's dim
formulas actually parse, and the ONLY place that reads the real parquet to
confirm no declared column is a phantom. Per-file only (bash-cwd-prefix rule).

Run: python -m pytest domains/mlb/test_claims_grid.py -q
"""
from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

from domains.mlb.claims_grid import GRID
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
    string, e.g. 'sum(pts)' -> {'pts'}, '2*(sum(fga)+0.44*sum(fta))' ->
    {'fga', 'fta'}. Reuses stdlib ast (the same module safe_formula.py itself
    parses with) rather than a hand-rolled regex."""
    tree = ast.parse(expr, mode="eval")
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def test_grid_shape_sane() -> None:
    assert GRID["sport"] == "mlb"
    assert len(GRID["families"]) >= 1
    for fam in GRID["families"]:
        assert fam["dims"], f"{fam['family']}: no dims declared"
        assert fam["windows"], f"{fam['family']}: no windows declared"


def test_every_window_type_has_a_required_floor() -> None:
    """Spec sec 1: floors REQUIRED per window; a window with no matching floor
    entry is a spec violation (fail-closed), not a silent gap. This grid's
    windows are all named career_to_date (no season/year column on the real
    source -- see claims_grid.py docstring), so window_type is always
    'career' per the factory's own _window_type lookup (claims_factory.py:
    81-87: only names starting with 'career' map to the 'career' bucket)."""
    for fam in GRID["families"]:
        floors = fam["floors"]
        assert floors, f"{fam['family']}: floors dict missing entirely"
        for window in fam["windows"]:
            name = window["name"]
            window_type = "career" if name == "career_to_date" else "season"
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


def test_every_window_filter_column_exists_on_declared_source() -> None:
    """A window's filter dict (e.g. {'is_pitcher': False}) references a real
    column too -- the factory's _slice_rows raises FactoryError on a missing
    filter column (claims_factory.py:99-100), but that is a runtime failure
    at generation time; this test catches the same drift BEFORE generation."""
    for fam in GRID["families"]:
        real_cols = _real_columns(fam["source"])
        for window in fam["windows"]:
            for col in (window.get("filter") or {}):
                assert col in real_cols, (
                    f"{fam['family']}: window {window['name']!r} filter references "
                    f"phantom column {col!r} not present on {fam['source']}"
                )


def test_every_dim_formula_parses_against_real_columns() -> None:
    """THE grammar-parse check: build criteria.formula the same way the
    factory will (f"({num})/({den})") and run it through safe_formula's real
    evaluate_group_formula against a real, tiny slice of the actual on-disk
    parquet -- any unknown column or disallowed syntax raises FormulaError.
    Slices the head(200) rather than head(50) like the NBA precedent because
    player_gamelogs.parquet mixes batter/pitcher rows -- a plain head(50) can
    land entirely on one is_pitcher value for a given family's dims, so this
    reads enough rows that both mlb_batter_rate and mlb_pitcher_rate exercise
    real non-null numerator/denominator columns for their respective dims."""
    for fam in GRID["families"]:
        path = REPO_ROOT / fam["source"]
        df = pd.read_parquet(path).head(200).copy()  # tiny real-schema fixture, per rails
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


def test_grid_module_has_zero_imports_beyond_future() -> None:
    """claims_grid.py must never import the factory (spec sec 1: 'the config
    never imports the factory'). Static check on the source text."""
    src = (REPO_ROOT / "domains" / "mlb" / "claims_grid.py").read_text(encoding="ascii")
    import_lines = [ln for ln in src.splitlines() if ln.strip().startswith(("import ", "from "))]
    assert import_lines == ["from __future__ import annotations"], (
        f"claims_grid.py must be import-free except __future__.annotations; found: {import_lines}"
    )


def test_batter_and_pitcher_windows_are_disjoint_via_is_pitcher_filter() -> None:
    """mlb_batter_rate and mlb_pitcher_rate share ONE source but must never
    double-count a player: their window filters must be the exact complement
    on is_pitcher (False vs True), never both-True/both-False/missing."""
    fam_by_name = {f["family"]: f for f in GRID["families"]}
    batter_filter = fam_by_name["mlb_batter_rate"]["windows"][0]["filter"]
    pitcher_filter = fam_by_name["mlb_pitcher_rate"]["windows"][0]["filter"]
    assert batter_filter == {"is_pitcher": False}
    assert pitcher_filter == {"is_pitcher": True}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
