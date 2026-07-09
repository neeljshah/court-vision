"""Per-file test for scripts.platformkit.interaction_factory.knowledge_intake.

Covers: only a CONFIRMED_LOCAL hypothesis with a declared KNOWN_MAPPINGS entry
emits candidates; a NULL/NOT_TESTABLE verdict or an unmapped hypothesis emits
nothing (honest, not an error); emitted candidates carry
hypothesis_source='knowledge' and a candidate_id distinct from the same
attr-pair's blind id (no ledger collision if both ever run).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/interaction_factory/test_knowledge_intake.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.interaction_factory import generator as GEN
from scripts.platformkit.interaction_factory import knowledge_intake as KI


def _write_ledger(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="ascii")


def test_confirmed_mapped_hypothesis_emits_candidates(tmp_path):
    mlb = tmp_path / "mlb_ledger.jsonl"
    nba = tmp_path / "nba_ledger.jsonl"
    _write_ledger(mlb, [{"hypothesis": "contact_quality_persists_split_half", "verdict": "CONFIRMED_LOCAL"}])
    _write_ledger(nba, [])
    cands = KI.knowledge_candidates({"mlb": mlb, "basketball_nba": nba})
    assert len(cands) == 2
    assert all(c.hypothesis_source == "knowledge" for c in cands)
    assert {c.attr_a for c in cands} == {"contact_quality"}
    assert {c.attr_b for c in cands} == {"whiff_rate", "platoon_split"}
    assert all(c.template_id == "mlb_pa_batter_x_pitcher" for c in cands)
    # deterministic id, distinct from the plain blind-enumeration id (no ledger collision).
    assert all(c.candidate_id.endswith("::src=knowledge") for c in cands)


def test_null_or_unmapped_hypothesis_emits_nothing(tmp_path):
    mlb = tmp_path / "mlb_ledger.jsonl"
    nba = tmp_path / "nba_ledger.jsonl"
    _write_ledger(mlb, [
        {"hypothesis": "contact_quality_persists_split_half", "verdict": "NULL_LOCAL"},  # not CONFIRMED
        {"hypothesis": "some_other_confirmed_thing", "verdict": "CONFIRMED_LOCAL"},       # no mapping declared
    ])
    _write_ledger(nba, [{"hypothesis": "b2b_rest_penalty", "verdict": "CONFIRMED_LOCAL"}])  # no mapping declared
    cands = KI.knowledge_candidates({"mlb": mlb, "basketball_nba": nba})
    assert cands == []


def test_mapped_attrs_are_real_registry_members():
    # KNOWN_MAPPINGS must only ever name attrs that actually resolve in the
    # target template's declared sport registry -- never invent one.
    for mappings in KI.KNOWN_MAPPINGS.values():
        for m in mappings:
            tpl = GEN.TEMPLATES[m["template_id"]]
            reg = GEN._registry(tpl["sport"])  # noqa: SLF001 -- registry integrity check
            assert m["attr_a"] in reg
            assert m["attr_b"] in reg
