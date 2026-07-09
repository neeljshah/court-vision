"""Per-file test for scripts.platformkit.interaction_factory.replicate_batch2b.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/interaction_factory/test_replicate_batch2b.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.interaction_factory import replicate_batch2b as REPL


def test_verdict_rule():
    assert REPL.verdict_for(0.23, {"effect": 0.30, "p": 0.0001, "n": 3000}) == "REPLICATED"
    assert REPL.verdict_for(0.23, {"effect": 0.10, "p": 0.20, "n": 300}) == "FAILED_REPLICATION_POWER_ANNOTATED"
    assert REPL.verdict_for(0.23, {"effect": -0.10, "p": 0.001, "n": 3000}) == "KILLED"
    assert REPL.verdict_for(0.23, None) == "NOT_TESTABLE"


def test_alpha_is_flat_bonferroni_k6():
    assert abs(REPL.ALPHA - (0.05 / 6.0)) < 1e-12


def test_mlb_entity_class_parsed_from_candidate_id():
    cid = "mlb_pa_attr_x_archetype::BB_rate__x__K_avoidance::class=low_scoring_grinder::retest_builder_available_2b"
    assert REPL._mlb_entity_class(cid) == "low_scoring_grinder"
    assert REPL._mlb_entity_class("tennis_match_asof_self_cross::a__x__b") is None


def test_tennis_is_replication_blocked_never_a_fake_pass(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    b0_rows = [
        {"candidate_id": "tennis_match_asof_self_cross::diff_1st_in_asof__x__diff_ace_rate_asof",
         "template_id": "tennis_match_asof_self_cross", "verdict": "SURVIVES_PREREG_PROVISIONAL",
         "attr_a": "diff_1st_in_asof", "attr_b": "diff_ace_rate_asof",
         "effect": -0.0261, "p": 0.0113, "n": 29181},
    ]
    for r in b0_rows:
        ledger.write_text(json.dumps(r) + "\n", encoding="ascii")

    monkeypatch.setattr(REPL, "_mlb_build", lambda year: None)  # no mlb survivor in this ledger slice
    verdicts_path = tmp_path / "verdicts.json"
    monkeypatch.setattr(REPL, "VERDICTS_PATH", verdicts_path)

    out = REPL.replicate(ledger_path=ledger)
    assert len(out) == 1
    assert out[0]["verdict"] == "REPLICATION_BLOCKED"
    assert out[0]["effect"] is None and out[0]["n"] == 0  # never a fabricated fit

    persisted = [json.loads(l) for l in ledger.read_text(encoding="ascii").splitlines()]
    assert len(persisted) == 2  # discovery row untouched + one appended replication row
    assert persisted[0] == b0_rows[0]
    assert persisted[1]["replication_of"] == b0_rows[0]["candidate_id"]

    saved = json.loads(verdicts_path.read_text(encoding="ascii"))
    assert saved[b0_rows[0]["candidate_id"]]["verdict"] == "REPLICATION_BLOCKED"


def test_mlb_source_missing_is_not_testable_not_a_crash(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    b0_rows = [
        {"candidate_id": "mlb_pa_attr_x_archetype::BB_rate__x__K_avoidance::class=low_scoring_grinder::retest_builder_available_2b",
         "template_id": "mlb_pa_attr_x_archetype", "verdict": "SURVIVES_PREREG_PROVISIONAL",
         "attr_a": "BB_rate", "attr_b": "K_avoidance", "effect": 0.2330, "p": 2.2e-05, "n": 5108},
    ]
    for r in b0_rows:
        ledger.write_text(json.dumps(r) + "\n", encoding="ascii")

    monkeypatch.setattr(REPL, "_mlb_build", lambda year: None)
    verdicts_path = tmp_path / "verdicts.json"
    monkeypatch.setattr(REPL, "VERDICTS_PATH", verdicts_path)

    out = REPL.replicate(ledger_path=ledger)
    assert len(out) == 1
    assert out[0]["verdict"] == "NOT_TESTABLE"
    assert out[0]["entity_class"] == "low_scoring_grinder"
