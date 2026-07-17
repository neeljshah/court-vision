"""Per-file test for scripts.platformkit.answers.qa_bank / qa_runner.

Three layers: (1) bank schema validity (every entry has the required shape,
ids are unique, categories/tiers are legal), (2) runner grading logic against
a fake resolve() so PASS/FAIL/crash-isolation is proven without touching real
data, (3) ONE real-repo SMOKE-tier run against the actual resolver_registry,
asserting n_fail == 0 -- if this fails at authoring time because reality
moved, fix qa_bank.py's expectation to match the new verified truth, never
loosen this assertion.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/answers/test_qa_bank.py -q
"""
from __future__ import annotations

from scripts.platformkit.answers import qa_bank as B
from scripts.platformkit.answers import qa_runner as Q

_LEGAL_STATUS = {"ok", "no_data", "not_supported", "ambiguous", "refused"}


def test_bank_schema_valid():
    assert len(B.QA_BANK) >= 50
    ids = [e["id"] for e in B.QA_BANK]
    assert len(ids) == len(set(ids)), "duplicate id in QA_BANK"
    for e in B.QA_BANK:
        assert e["question"] and isinstance(e["question"], str)
        assert e["sport"] in {"nba", "mlb", "wnba", "tennis", "soccer"}
        assert e["tier"] in {"SMOKE", "FULL"}
        exp = e["expect"]
        assert exp["category"] in B.CATEGORIES
        assert exp["status_one_of"] and set(exp["status_one_of"]) <= _LEGAL_STATUS
        assert isinstance(exp["receipt_required"], bool)
        assert isinstance(exp["must_contain_keys"], list)


def test_bank_covers_12_categories_x_5_sports():
    assert len(B.CATEGORIES) == 12
    assert len(B.SPORTS) == 5
    assert len(B.QA_BANK) == 60


def test_by_tier_smoke_is_cheap_subset_of_full():
    smoke = B.by_tier("SMOKE")
    full = B.by_tier("FULL")
    assert 10 <= len(smoke) <= 20
    assert full == B.QA_BANK
    assert {e["id"] for e in smoke} <= {e["id"] for e in full}


def test_runner_grades_pass_fail_and_isolates_crash(monkeypatch):
    entries = [
        {"id": "a", "question": "q1", "sport": "nba",
         "expect": {"category": "system_map", "status_one_of": ["ok"],
                     "receipt_required": True, "must_contain_keys": ["n_nodes"]}},
        {"id": "b", "question": "q2", "sport": "nba",
         "expect": {"category": "system_map", "status_one_of": ["ok"],
                     "receipt_required": True, "must_contain_keys": ["missing_key"]}},
        {"id": "c", "question": "q3", "sport": "nba",
         "expect": {"category": "system_map", "status_one_of": ["ok"],
                     "receipt_required": True, "must_contain_keys": []}},
    ]
    monkeypatch.setattr(Q._bank, "by_tier", lambda tier: entries)

    def _fake_resolve(question, sport=None, category=None, **kw):
        if question == "q1":
            return {"status": "ok", "category": "system_map", "n_nodes": 5}
        if question == "q2":
            return {"status": "ok", "category": "system_map"}  # missing must_contain_keys
        raise RuntimeError("boom")  # q3 crashes the resolver

    monkeypatch.setattr(Q.R, "resolve", _fake_resolve)
    report = Q.run("SMOKE")
    assert report["n_entries"] == 3 and report["n_run"] == 3
    assert report["n_pass"] == 1 and report["n_fail"] == 2
    fail_ids = {f["id"] for f in report["fails"]}
    assert fail_ids == {"b", "c"}
    assert report["edge_claimed"] is False


def test_write_report_atomic(tmp_path, monkeypatch):
    out = tmp_path / "qa_bank_report.json"
    monkeypatch.setattr(Q, "OUT_PATH", out)
    Q.write_report({"as_of": "x", "n_pass": 1, "n_fail": 0})
    assert out.exists()
    assert not out.with_suffix(".json.tmp").exists()


def test_real_smoke_run_n_fail_zero():
    """The one real-repo call: SMOKE tier through the actual resolver_registry.
    If this fails, verified reality moved -- fix qa_bank.py's expect block for
    the failing id(s), don't weaken this test."""
    report = Q.run("SMOKE")
    assert report["n_run"] == len(B.by_tier("SMOKE"))
    assert report["n_fail"] == 0, report["fails"]
