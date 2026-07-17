"""Per-file test for scripts.platformkit.answers.coverage_stress.

Small and monkeypatch-only -- two fake rows through a fake resolve_fn (no
real resolver_registry import, no real bank load) proving rollup math, crash
isolation, and the written report's shape. The full 176-row bank run is the
pod's job, not this laptop's (RAM discipline).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/answers/test_coverage_stress.py -q
"""
from __future__ import annotations

from scripts.platformkit.answers import coverage_stress as C

_BANK = [
    {"q": "win probability Lakers vs Celtics", "sport": "nba", "kind": "prediction", "expects_answer": True},
    {"q": "this one blows up", "sport": "nba", "kind": "stat", "expects_answer": True},
]


def _fake_resolve(query, sport):
    if query == "win probability Lakers vs Celtics":
        return {"status": "ok", "category": "prediction_winprob"}
    raise RuntimeError("boom")


def test_run_rollup_math_and_crash_capture():
    report = C.run(_BANK, resolve_fn=_fake_resolve)

    assert report["n_rows"] == 2
    assert report["n_expects_answer_true"] == 2
    assert report["n_expects_answer_true_ok"] == 1
    assert report["coverage_rate"] == 0.5

    row_ok, row_err = report["rows"]
    assert row_ok["status"] == "ok" and row_ok["category"] == "prediction_winprob"
    assert row_err["status"] == "error"
    assert "resolve() raised" in row_err["note_head"]
    assert "boom" in row_err["note_head"]

    assert report["per_sport"]["nba"]["n"] == 2
    assert report["per_sport"]["nba"]["ok"] == 1
    assert report["per_sport"]["nba"]["error"] == 1

    assert report["per_category"]["prediction_winprob"]["ok"] == 1
    assert report["per_category"]["(uncategorized)"]["error"] == 1

    assert len(report["gaps"]) == 1
    assert report["gaps"][0]["q"] == "this one blows up"
    assert report["gaps"][0]["status"] == "error"


def test_expects_answer_false_row_never_counted_toward_coverage():
    bank = [
        {"q": "betting edge on Lakers", "sport": "nba", "kind": "prediction", "expects_answer": False},
    ]
    report = C.run(bank, resolve_fn=lambda q, s: {"status": "refused", "category": "edge_language"})
    assert report["n_expects_answer_true"] == 0
    assert report["coverage_rate"] is None
    assert report["gaps"] == []
    assert report["per_sport"]["nba"]["refused"] == 1


def test_write_report_atomic(tmp_path):
    out = tmp_path / "coverage_stress_report.json"
    C.write_report({"as_of": "x", "n_rows": 0}, out_path=out)
    assert out.exists()
    assert not out.with_suffix(".json.tmp").exists()


def test_load_bank_reads_jsonl(tmp_path):
    p = tmp_path / "bank.jsonl"
    p.write_text(
        '{"q": "a", "sport": "nba", "kind": "stat", "expects_answer": true}\n'
        "\n"
        '{"q": "b", "sport": "mlb", "kind": "stat", "expects_answer": false}\n',
        encoding="utf-8",
    )
    rows = C.load_bank(p)
    assert len(rows) == 2
    assert rows[0]["q"] == "a" and rows[1]["sport"] == "mlb"
