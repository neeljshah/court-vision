"""Per-file test for scripts.platformkit.interaction_factory.replicate_nba_form_2026.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/interaction_factory/test_replicate_nba_form_2026.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, eps_eff
from scripts.platformkit.interaction_factory import replicate_nba_form_2026 as REPL


def test_pending_survivors_selects_only_unreplicated_rows_across_both_templates():
    rows = [
        {"candidate_id": "nba_form_self_cross::a__x__b", "template_id": "nba_form_self_cross",
         "verdict": "SURVIVES_PREREG_PROVISIONAL", "attr_a": "a", "attr_b": "b"},
        {"candidate_id": "nba_form_state_conditioner::c__x__d", "template_id": "nba_form_state_conditioner",
         "verdict": "SURVIVES_PREREG_PROVISIONAL", "attr_a": "c", "attr_b": "d"},
        # already replicated -> excluded
        {"candidate_id": "nba_form_self_cross::already_done", "template_id": "nba_form_self_cross",
         "verdict": "SURVIVES_PREREG_PROVISIONAL", "attr_a": "e", "attr_b": "f"},
        {"candidate_id": "repl_of_already_done", "template_id": "nba_form_self_cross",
         "verdict": "REPLICATION_BLOCKED", "replication_of": "nba_form_self_cross::already_done"},
        # different template / non-survivor verdict -> excluded
        {"candidate_id": "other_family::x", "template_id": "nba_shot_attr_x_state",
         "verdict": "SURVIVES_PREREG_PROVISIONAL", "attr_a": "x", "attr_b": "y"},
        {"candidate_id": "nba_form_self_cross::null_one", "template_id": "nba_form_self_cross",
         "verdict": "NULL", "attr_a": "g", "attr_b": "h"},
    ]
    pending = REPL._pending_survivors(rows)
    ids = {r["candidate_id"] for r in pending}
    assert ids == {"nba_form_self_cross::a__x__b", "nba_form_state_conditioner::c__x__d"}


def test_replicate_appends_replication_blocked_for_both_templates_in_one_call(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    discovery_rows = [
        {"candidate_id": "nba_form_self_cross::l5_min__x__l5_ts_pct", "template_id": "nba_form_self_cross",
         "verdict": "SURVIVES_PREREG_PROVISIONAL", "attr_a": "l5_min", "attr_b": "l5_ts_pct",
         "effect": 0.006147, "p": 0.000001, "n": 40000},
        {"candidate_id": "nba_form_state_conditioner::l10_ts_pct__x__clutch_efg",
         "template_id": "nba_form_state_conditioner", "verdict": "SURVIVES_PREREG_PROVISIONAL",
         "attr_a": "l10_ts_pct", "attr_b": "clutch_efg", "effect": 0.004591, "p": 0.003262, "n": 32618},
    ]
    with ledger.open("w", encoding="ascii") as fh:
        for r in discovery_rows:
            fh.write(json.dumps(r) + "\n")

    verdicts_path = tmp_path / "verdicts.json"
    monkeypatch.setattr(REPL, "VERDICTS_PATH", verdicts_path)

    out = REPL.replicate(ledger_path=ledger)
    # ONE call processes ALL pending candidates across BOTH templates.
    assert len(out) == 2
    assert {r["template_id"] for r in out} == {"nba_form_self_cross", "nba_form_state_conditioner"}
    assert {r["verdict"] for r in out} == {"REPLICATION_BLOCKED"}
    assert {r["corpus"] for r in out} == {"unbuildable"}
    assert {r["replication_of"] for r in out} == {r["candidate_id"] for r in discovery_rows}
    # K_DECLARED is the live pending count (2), not a hardcoded family size.
    assert all(r["k_declared"] == 2 for r in out)
    assert all(abs(r["alpha_fwer"] - round(eps_eff(DEFAULT_EPS, 2), 8)) < 1e-9 for r in out)

    persisted = [json.loads(l) for l in ledger.read_text(encoding="ascii").splitlines()]
    assert len(persisted) == 4  # 2 discovery rows untouched + 2 appended replication rows
    assert persisted[0] == discovery_rows[0]
    assert persisted[1] == discovery_rows[1]

    assert verdicts_path.exists()
    saved = json.loads(verdicts_path.read_text(encoding="ascii"))
    for r in discovery_rows:
        assert saved[r["candidate_id"]]["verdict"] == "REPLICATION_BLOCKED"

    # a second call finds nothing pending (both candidates now have a replication_of pointer).
    out2 = REPL.replicate(ledger_path=ledger)
    assert out2 == []
