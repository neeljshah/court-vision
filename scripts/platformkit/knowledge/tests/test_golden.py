"""Per-file test: the golden recall@5 gate.

Asserts the leak-aware golden set (>=120 rows, >=30/sport, >=15 MEMORY) retrieves
the expected note in the top-5 for >=90% overall and >=85% per sport. Requires a
built index; SKIPS (passes trivially) on a fresh clone without one so the test is
self-contained. Standalone + pytest-discoverable. ASCII.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.knowledge import config, golden  # noqa: E402

_HAS_INDEX = config.CORPUS_PARQUET.exists()


def test_golden_fixture_shape():
    rows = golden.load_golden()
    assert len(rows) >= 120, f"golden set too small: {len(rows)}"
    counts = Counter(r["sport"] for r in rows)
    for sport in ("NBA", "MLB", "Soccer", "Tennis"):
        assert counts[sport] >= 30, f"{sport} has only {counts[sport]} rows"
    assert counts["MEMORY"] >= 15, f"MEMORY has only {counts['MEMORY']} rows"
    # schema sanity
    for r in rows:
        assert set(r) >= {"sport", "query", "expected_note_id"}


def test_no_verbatim_title_leak():
    # Leak-aware discipline: a query must NOT be a verbatim copy of the note's title
    # stem string. We approximate by requiring the query not equal the note stem.
    rows = golden.load_golden()
    for r in rows:
        stem = r["expected_note_id"].split("/")[-1].replace("_", " ")
        assert r["query"].strip().lower() != stem.lower()


def test_recall_at_5_threshold():
    if not _HAS_INDEX:
        print("SKIP recall gate (no index built)")
        return
    rows = golden.load_golden()
    res = golden.evaluate(rows, top_k=5)
    assert res["recall@5"] >= 0.90, f"overall recall@5={res['recall@5']}"
    for sport, s in res["per_sport"].items():
        assert s["recall@5"] >= 0.85, f"{sport} recall@5={s['recall@5']}"


def _run() -> int:
    fails = 0
    for fn in (test_golden_fixture_shape, test_no_verbatim_title_leak,
               test_recall_at_5_threshold):
        try:
            fn()
            print("PASS", fn.__name__)
        except AssertionError as exc:
            fails += 1
            print("FAIL", fn.__name__, exc)
    return fails


if __name__ == "__main__":
    raise SystemExit(_run())
