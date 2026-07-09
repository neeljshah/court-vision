"""Per-file test for scripts.platformkit.autoloop.propose_gate_job (M10).

Acceptance criteria:
1. Dedup vs the ledger: an already-tested candidate_id AND an identity tested
   under a '::src=knowledge' id are never re-proposed.
2. Closed-class refusal: reject-ledger REJECT signals and NULL_LOCAL-mapped
   (template, pair) identities are refused at draw time.
3. K budget: exactly k candidates proposed, round-robin across sports.
4. Wall-clock cap: an over-budget cycle defers remaining template groups.
5. Verdict append shape: the REAL run_batch path appends honest NOT_TESTABLE
   rows with hypothesis_source to the (tmp) ledger.
6. Dry-cycle counter: 3 NOT_TESTABLE-only cycles log EXHAUSTED + rotate.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_propose_gate_job.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.autoloop import propose_gate_job as PGJ
from scripts.platformkit.interaction_factory import generator as GEN

_TPL_COMMON = {"atomic_unit": "match", "outcome": "y", "baseline": "y ~ a + b",
               "pairing": "self_cross", "blocklist_attrs": [], "blocklist_pairs": []}
FAKE_TEMPLATES = {
    "s1_tpl": dict(_TPL_COMMON, sport="s1", left_pool={"static_pool": "s1_pool"},
                   feature_builder="s1_builder_unregistered"),
    "s2_tpl": dict(_TPL_COMMON, sport="s2", left_pool={"static_pool": "s2_pool"},
                   feature_builder="s2_builder_unregistered"),
}
FAKE_POOLS = {"s1_pool": ["a1", "a2", "a3", "a4", "a5"],
              "s2_pool": ["b1", "b2", "b3", "b4", "b5"]}


def _patch_grammar(monkeypatch, templates=None, pools=None):
    monkeypatch.setattr(GEN, "TEMPLATES", templates or FAKE_TEMPLATES)
    monkeypatch.setattr(GEN, "STATIC_POOLS", pools or FAKE_POOLS)


def _paths(tmp_path):
    """(ledger, reject_ledger, knowledge_ledgers) -- all tmp, all absent-ok."""
    return (tmp_path / "factory_ledger.jsonl", tmp_path / "reject.jsonl",
            {"d": tmp_path / "validation_ledger.jsonl"})


def _fake_run_batch(calls, verdict="NULL"):
    def fn(tid, k, cands):
        calls.append((tid, [c.candidate_id for c in cands]))
        return [{"candidate_id": c.candidate_id, "template_id": tid, "attr_a": c.attr_a,
                 "attr_b": c.attr_b, "verdict": verdict,
                 "hypothesis_source": c.hypothesis_source} for c in cands]
    return fn


def _run(tmp_path, monkeypatch, watermarks, calls, **kw):
    _patch_grammar(monkeypatch)
    ledger, reject, know = _paths(tmp_path)
    return PGJ.run_propose_gate(
        watermarks, ledger_path=ledger, reject_ledger_path=reject,
        knowledge_ledgers=know, run_batch_fn=_fake_run_batch(calls, kw.pop("verdict", "NULL")),
        **kw)


def _proposed_pairs(calls):
    return {cid for _tid, cids in calls for cid in cids}


def test_dedup_vs_ledger_identity(tmp_path, monkeypatch):
    ledger, _rj, _kn = _paths(tmp_path)
    rows = [
        {"candidate_id": "s1_tpl::a1__x__a2", "template_id": "s1_tpl",
         "attr_a": "a1", "attr_b": "a2", "verdict": "NULL"},
        # tested under a knowledge-source id: identity dedup must catch the blind twin
        {"candidate_id": "s2_tpl::b1__x__b2::src=knowledge", "template_id": "s2_tpl",
         "attr_a": "b1", "attr_b": "b2", "verdict": "NULL"},
    ]
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="ascii")
    calls: list = []
    out = _run(tmp_path, monkeypatch, {}, calls, k=20)
    proposed = _proposed_pairs(calls)
    assert "s1_tpl::a1__x__a2" not in proposed
    assert not any("b1__x__b2" in c for c in proposed if c.startswith("s2_tpl"))
    assert out["proposed"] > 0  # the rest of the pool still flows


def test_closed_class_refusal(tmp_path, monkeypatch):
    _ledger, reject, know = _paths(tmp_path)
    reject.write_text(json.dumps({"sport": "s1", "signal": "a3", "verdict": "REJECT"}) + "\n",
                      encoding="ascii")
    know["d"].write_text(json.dumps({"hypothesis": "h_null", "verdict": "NULL_LOCAL"}) + "\n",
                         encoding="ascii")
    mappings = {"h_null": [{"template_id": "s2_tpl", "attr_a": "b1", "attr_b": "b3"}]}
    calls: list = []
    out = _run(tmp_path, monkeypatch, {}, calls, k=50, mappings=mappings)
    proposed = _proposed_pairs(calls)
    assert not any("a3" in c for c in proposed if c.startswith("s1_tpl"))  # REJECT signal refused
    assert "s2_tpl::b1__x__b3" not in proposed                             # NULL_LOCAL family refused
    assert out["refused_closed_class"] > 0


def test_k_budget_round_robin(tmp_path, monkeypatch):
    calls: list = []
    out = _run(tmp_path, monkeypatch, {}, calls, k=8)
    proposed = _proposed_pairs(calls)
    assert out["proposed"] == 8 and len(proposed) == 8
    assert sum(1 for c in proposed if c.startswith("s1_tpl")) == 4  # round-robin fairness
    assert sum(1 for c in proposed if c.startswith("s2_tpl")) == 4


def test_wall_clock_cap_defers_groups(tmp_path, monkeypatch):
    ticks = iter([0.0, 5.0, 10000.0, 10001.0])
    calls: list = []
    out = _run(tmp_path, monkeypatch, {}, calls, k=4,
               wall_clock_cap_sec=100.0, clock=lambda: next(ticks))
    assert len(calls) == 1                       # only the first template group ran
    assert len(out["deferred_over_cap"]) == 1    # the second was deferred, not dropped
    assert out["per_template"][calls[0][0]]["status"] == "ran"


def test_verdict_append_shape_real_gate(tmp_path, monkeypatch):
    """Real run_batch path (no injected gate): unregistered builders yield honest
    NOT_TESTABLE rows APPENDED to the ledger, hypothesis_source='blind'."""
    _patch_grammar(monkeypatch)
    ledger, reject, know = _paths(tmp_path)
    out = PGJ.run_propose_gate({}, k=4, ledger_path=ledger,
                               reject_ledger_path=reject, knowledge_ledgers=know)
    assert out["proposed"] == 4 and out["gated_rows"] == 4
    assert out["by_verdict"] == {"NOT_TESTABLE": 4}
    rows = [json.loads(l) for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(rows) == 4
    for r in rows:
        assert r["verdict"] == "NOT_TESTABLE" and r["hypothesis_source"] == "blind"
        assert r["edge_claimed"] is False and isinstance(r["cum_K"], int)
        for key in ("candidate_id", "template_id", "attr_a", "attr_b", "computed_at", "note"):
            assert key in r


def test_dry_cycle_counter_exhausts_and_rotates(tmp_path, monkeypatch):
    templates = {
        "s1_tpl": dict(_TPL_COMMON, sport="s1", left_pool={"static_pool": "s1_pool"},
                       feature_builder="nope"),
        "s1_tplb": dict(_TPL_COMMON, sport="s1", left_pool={"static_pool": "s2_pool"},
                        feature_builder="nope"),
    }
    _patch_grammar(monkeypatch, templates=templates)
    ledger, reject, know = _paths(tmp_path)
    watermarks: dict = {}
    queued: list = []
    calls: list = []
    for _cycle in range(3):
        out = PGJ.run_propose_gate(
            watermarks, k=2, ledger_path=ledger, reject_ledger_path=reject,
            knowledge_ledgers=know, queue_fn=queued.append,
            run_batch_fn=_fake_run_batch(calls, verdict="NOT_TESTABLE"))
    assert out["exhausted_logged"] == ["s1_tpl"]
    assert [q["kind"] for q in queued] == ["POOL_EXHAUSTED"]
    assert watermarks[PGJ.STATE_KEY]["exhausted"] == ["s1_tpl"]
    # cycle 4: the exhausted pool is rotated out; its sibling takes over
    calls.clear()
    PGJ.run_propose_gate(watermarks, k=2, ledger_path=ledger, reject_ledger_path=reject,
                         knowledge_ledgers=know, queue_fn=queued.append,
                         run_batch_fn=_fake_run_batch(calls, verdict="NOT_TESTABLE"))
    assert {tid for tid, _ in calls} == {"s1_tplb"}
