"""Per-file test for scripts.platformkit.omni.escalation_intake.

Acceptance criteria:
1. A synthetic escalated claim (lifecycle=proposed, links.escalate_to_funnel)
   routes to a Stage-A verdict (ACCEPTED/BOUNCED via claims_intake) and the
   parent claim's lifecycle flips to "escalation_screened".
2. A non-escalated proposed claim (no escalate_to_funnel flag) is ignored.
3. Idempotent rerun: a claim already screened (lifecycle no longer
   "proposed") is not reprocessed a second time.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_escalation_intake.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import escalation_intake as ei


def _escalated_claim(base_dir, key="p1"):
    claim = {
        "statement": f"NBA player {key} pts delta under b2b_vs_rest",
        "type": "conditional",
        "scope": {"sport": "nba", "entity_type": "player", "entity_ids": [key], "context": "b2b_vs_rest"},
        "topic": "reactions.b2b_vs_rest",
        "lifecycle": "proposed",
        "effect": {"verdict": "TESTED", "delta": -3.5},
        "evidence": {"p_value": 0.001, "p_adj_bh": 0.01},
        "provenance": {"created_by_lane": "k_sweep_nba_v1"},
        "links": {"escalate_to_funnel": True},
    }
    return cl.add_claim(claim, base_dir=base_dir)


def _non_escalated_claim(base_dir):
    claim = {
        "statement": "NBA player p2 pts delta under home_vs_road",
        "type": "conditional",
        "scope": {"sport": "nba", "entity_type": "player", "entity_ids": ["p2"], "context": "home_vs_road"},
        "topic": "reactions.home_vs_road",
        "lifecycle": "proposed",
        "effect": {"verdict": "TESTED", "delta": 0.4},
        "evidence": {"p_value": 0.6, "p_adj_bh": 0.8},
        "provenance": {"created_by_lane": "k_sweep_nba_v1"},
        "links": {"escalate_to_funnel": False},
    }
    return cl.add_claim(claim, base_dir=base_dir)


def test_escalated_claim_routes_to_stage_a_verdict_and_marks_screened(tmp_path):
    parent_id = _escalated_claim(tmp_path)
    out = ei.run_escalation_intake(base_dir=tmp_path)
    assert out["screened"] == 1
    assert out["results"][0]["parent_claim_id"] == parent_id
    assert out["results"][0]["verdict"] in ("ACCEPTED", "BOUNCED")

    df = cl.query(sport="nba", base_dir=tmp_path)
    row = df[df["claim_id"] == parent_id].iloc[0]
    assert row["lifecycle"] == "escalation_screened"
    review = json.loads(row["review_json"])
    assert review["screen_verdict"] == out["results"][0]["verdict"]


def test_non_escalated_claim_is_ignored(tmp_path):
    _non_escalated_claim(tmp_path)
    out = ei.run_escalation_intake(base_dir=tmp_path)
    assert out["screened"] == 0
    assert out["results"] == []


def test_idempotent_rerun_skips_already_screened(tmp_path):
    _escalated_claim(tmp_path)
    first = ei.run_escalation_intake(base_dir=tmp_path)
    assert first["screened"] == 1
    second = ei.run_escalation_intake(base_dir=tmp_path)
    assert second["screened"] == 0


def test_accepted_verdict_ledgers_a_proposal_claim_citing_parent(tmp_path):
    parent_id = _escalated_claim(tmp_path)
    out = ei.run_escalation_intake(base_dir=tmp_path)
    result = out["results"][0]
    if result["verdict"] == "ACCEPTED":
        df = cl.query(sport="nba", base_dir=tmp_path)
        prop = df[df["claim_id"] == result["claim_id"]].iloc[0]
        links = json.loads(prop["links_json"])
        assert parent_id in links.get("parent_claims", [])
