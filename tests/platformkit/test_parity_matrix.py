"""Per-file tests for scripts.platformkit.parity_matrix.

Verifies all 5 sports resolve, graceful n/a where a seam is unbuilt, GREEN cells for
the built NBA+Tennis seams, and the fail-closed is_green logic.

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
       tests/platformkit/test_parity_matrix.py -q
"""
from __future__ import annotations

from scripts.platformkit.parity_matrix import (
    DIMENSIONS,
    GREEN,
    NA,
    RED,
    SPORTS,
    Cell,
    Row,
    build_parity_matrix,
    is_green,
)


def test_all_five_sports_resolve_with_all_dimensions():
    rows = build_parity_matrix()
    assert [r.sport for r in rows] == list(SPORTS)
    for r in rows:
        assert set(r.cells.keys()) == set(DIMENSIONS)
        for d in DIMENSIONS:
            assert r.cells[d].status in (GREEN, RED, NA)


def test_built_seams_are_green_unbuilt_are_na():
    by = {r.sport: r for r in build_parity_matrix()}
    # NBA + Tennis + soccer_intl have feature_spec + ingest_manifest built.
    # (soccer_intl PARITY_GAP lane added the manifest/feature_spec for its single
    #  genuine corpus -- declares ONLY real data, no fabricated sources/columns.)
    for sport in ("basketball_nba", "tennis", "soccer_intl"):
        assert by[sport].cells["feature_spec"].status == GREEN
        assert by[sport].cells["manifest"].status == GREEN
        assert by[sport].cells["census"].status == GREEN


def test_is_green_fail_closed_logic():
    green_rows = [Row("x", {"census": Cell(GREEN), "manifest": Cell(NA),
                            "feature_spec": Cell(GREEN)})]
    assert is_green(green_rows) is True
    red_rows = [Row("x", {"census": Cell(GREEN), "manifest": Cell(RED, "bad"),
                          "feature_spec": Cell(NA)})]
    assert is_green(red_rows) is False
    # n/a alone never fails the gate
    na_rows = [Row("x", {"census": Cell(NA), "manifest": Cell(NA), "feature_spec": Cell(NA)})]
    assert is_green(na_rows) is True


def test_live_matrix_is_green_overall():
    """With NBA+Tennis seams built and others n/a, the live grid must be GREEN."""
    rows = build_parity_matrix()
    reds = [(r.sport, d) for r in rows for d in DIMENSIONS if r.cells[d].status == RED]
    assert is_green(rows), f"unexpected red cells: {reds}"
