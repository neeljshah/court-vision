"""Tests for scripts.platformkit.omni.claims_ledger + claims_intake.

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_claims_ledger.py -q
"""
from __future__ import annotations

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import claims_intake as ci


def _claim(statement, sport="nba", topic="minutes", ctype="effect", **extra):
    return {
        "statement": statement,
        "type": ctype,
        "scope": {"sport": sport, "entity_ids": extra.pop("entity_ids", ["jokic"])},
        "topic": topic,
        **extra,
    }


def test_add_and_query_by_entity_topic(tmp_path):
    claim_id = cl.add_claim(_claim("jokic minutes rise in clutch", topic="minutes"), base_dir=tmp_path)
    out = cl.query(entity="jokic", topic="minutes", base_dir=tmp_path)
    assert len(out) == 1
    assert out.iloc[0]["claim_id"] == claim_id
    assert out.iloc[0]["sport"] == "nba"


def test_set_lifecycle_journals_and_rebuilds(tmp_path):
    claim_id = cl.add_claim(_claim("stmt a"), base_dir=tmp_path)
    cl.set_lifecycle(claim_id, "accepted", review={"judge": "fable"}, base_dir=tmp_path)
    out = cl.query(base_dir=tmp_path)
    row = out[out["claim_id"] == claim_id].iloc[0]
    assert row["lifecycle"] == "accepted"
    assert "fable" in row["review_json"]
    # journal has 2 events; parquet reflects the latest state (1 row)
    journal_lines = (tmp_path / "journal.jsonl").read_text().strip().splitlines()
    assert len(journal_lines) == 2
    assert len(out) == 1


def test_flag_downstream_flags_children(tmp_path):
    grandchild = _claim("grandchild effect", topic="grand")
    grandchild_id = cl.add_claim(grandchild, base_dir=tmp_path)
    child_claim = _claim("child effect")
    child_claim["links"] = {"child_claims": [grandchild_id]}
    child_id = cl.add_claim(child_claim, base_dir=tmp_path)
    parent_claim = _claim("parent mechanism", ctype="mechanism")
    parent_claim["links"] = {"child_claims": [child_id]}
    parent_id = cl.add_claim(parent_claim, base_dir=tmp_path)

    cl.set_lifecycle(parent_id, "rejected", base_dir=tmp_path)
    flagged = cl.flag_downstream(parent_id, base_dir=tmp_path)

    assert set(flagged) == {child_id, grandchild_id}
    out = cl.query(base_dir=tmp_path).set_index("claim_id")
    assert out.loc[child_id, "lifecycle"] == "flagged"
    assert out.loc[grandchild_id, "lifecycle"] == "flagged"


def test_intake_bounces_on_collision_and_accepts_cited(tmp_path):
    neg_id = cl.add_claim(_claim("no minutes effect found", sport="mlb", topic="fatigue", ctype="negative"),
                           base_dir=tmp_path)

    bounced = ci.intake_proposal(
        {"statement": "new fatigue claim", "type": "effect", "topic": "fatigue",
         "scope": {"sport": "mlb"}, "supporting_claim_ids": [neg_id]},
        base_dir=tmp_path,
    )
    assert bounced["verdict"] == "BOUNCED"
    assert bounced["collision_claim_id"] == neg_id

    ok = ci.intake_proposal(
        {"statement": "distinct claim", "type": "effect", "topic": "usage",
         "scope": {"sport": "mlb"}, "supporting_claim_ids": [neg_id]},
        base_dir=tmp_path,
    )
    assert ok["verdict"] == "ACCEPTED"
    row = cl.query(base_dir=tmp_path)
    row = row[row["claim_id"] == ok["claim_id"]].iloc[0]
    assert neg_id in row["links_json"]


def test_intake_bounces_without_citation_unless_mechanism(tmp_path):
    no_cite = ci.intake_proposal(
        {"statement": "uncited claim", "type": "effect", "topic": "x", "scope": {"sport": "nba"}},
        base_dir=tmp_path,
    )
    assert no_cite["verdict"] == "BOUNCED"

    mech = ci.intake_proposal(
        {"statement": "bootstrap mechanism", "type": "mechanism", "topic": "x", "scope": {"sport": "nba"}},
        base_dir=tmp_path,
    )
    assert mech["verdict"] == "ACCEPTED"


def test_journal_rebuild_roundtrip_lossless(tmp_path):
    id1 = cl.add_claim(_claim("stmt 1", topic="t1"), base_dir=tmp_path)
    id2 = cl.add_claim(_claim("stmt 2", topic="t2", sport="mlb"), base_dir=tmp_path)
    cl.set_lifecycle(id1, "replicated", base_dir=tmp_path)

    before = cl.query(base_dir=tmp_path).sort_values("claim_id").reset_index(drop=True)
    (tmp_path / "claims.parquet").unlink()  # force a rebuild from journal alone
    after = cl.rebuild_parquet(tmp_path).sort_values("claim_id").reset_index(drop=True)

    assert before.equals(after)
    assert set(after["claim_id"]) == {id1, id2}
    assert after[after["claim_id"] == id1].iloc[0]["lifecycle"] == "replicated"
