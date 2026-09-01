"""Per-file test for gap_ledger (per-file tests ONLY -- a full pytest run freezes the box)."""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.gap_ledger import (HARNESS_MISSING, MEASURED, NO_BENCHMARK, QUEUED,
                                            build, classify, counts, load_cells, render_markdown)


def test_cells_parse_and_have_required_columns():
    rows = load_cells()
    assert rows, "gap_ledger_cells.tsv parsed to zero rows"
    for r in rows:
        for col in ("sport", "question", "regime", "benchmark_kind"):
            assert r.get(col), f"row missing {col}: {r}"


def test_classify_covers_the_four_states(tmp_path: Path):
    repo = tmp_path
    (repo / "real.py").write_text("", encoding="utf-8")
    assert classify({"harness": "real.py", "benchmark_kind": "close"}, repo) == MEASURED
    assert classify({"harness": "gone.py", "benchmark_kind": "close"}, repo) == HARNESS_MISSING
    assert classify({"harness": "", "benchmark_kind": "close"}, repo) == QUEUED
    assert classify({"harness": "", "benchmark_kind": "none"}, repo) == NO_BENCHMARK


def test_declared_harnesses_exist_on_disk():
    """The ledger must not drift from the repo -- a stale path silently fakes coverage."""
    broken = [r for r in build() if r["status"] == HARNESS_MISSING]
    assert not broken, f"declared harnesses missing: {[r['harness'] for r in broken]}"


def test_absence_is_visible():
    """The whole point: unmeasured cells must survive into the report, not be dropped."""
    rows = build()
    c = counts(rows)
    assert c[QUEUED] + c[NO_BENCHMARK] > 0, "ledger shows no gaps at all -- suspicious"
    md = render_markdown(rows)
    assert NO_BENCHMARK in md and "need a benchmark" in md
    assert len([ln for ln in md.splitlines() if ln.startswith("| ")]) >= len(rows)
