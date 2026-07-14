"""Tests for scripts.platformkit.omni.claim_impact.

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_claim_impact.py -q
"""
from __future__ import annotations

from scripts.platformkit.omni import claim_impact as ci
from scripts.platformkit.omni import claims_ledger as cl


def _claim(statement, topic, lifecycle="accepted", entity_ids=("jokic",), sport="nba"):
    return {
        "statement": statement, "type": "effect",
        "scope": {"sport": sport, "entity_ids": list(entity_ids)},
        "topic": topic, "lifecycle": lifecycle,
    }


def test_observable_fan_out_over_family_map(tmp_path):
    claims_dir, impact_dir = tmp_path / "claims", tmp_path / "impact"
    claim_id = cl.add_claim(_claim("foul trouble cuts minutes", "reactions.high_foul_vs_low_foul"),
                             base_dir=claims_dir)
    df = ci.impact_index(claims_base_dir=claims_dir, base_dir=impact_dir)
    row = df[df["claim_id"] == claim_id]
    assert set(row["market_family"]) == set(ci.FAMILIES_BY_OBSERVABLE["minutes_dist"])
    assert (row["observable"] == "minutes_dist").all()
    assert (row["tier"] == 1).all()


def test_unmapped_topic_counted_not_guessed(tmp_path):
    claims_dir, impact_dir = tmp_path / "claims", tmp_path / "impact"
    claim_id = cl.add_claim(_claim("infra housekeeping row", "reserve_discipline"), base_dir=claims_dir)
    df = ci.impact_index(claims_base_dir=claims_dir, base_dir=impact_dir)
    row = df[df["claim_id"] == claim_id]
    assert len(row) == 1  # no silent multi-guess
    assert row.iloc[0]["observable"] == "unmapped"
    assert row.iloc[0]["market_family"] == ""


def test_tier3_and_rejected_excluded(tmp_path):
    claims_dir, impact_dir = tmp_path / "claims", tmp_path / "impact"
    cl.add_claim(_claim("screened claim", "minutes_dist", lifecycle="screened"), base_dir=claims_dir)
    cl.add_claim(_claim("rejected claim", "minutes_dist", lifecycle="rejected"), base_dir=claims_dir)
    tier2_id = cl.add_claim(_claim("replicated claim", "minutes_dist", lifecycle="replicated"), base_dir=claims_dir)
    df = ci.impact_index(claims_base_dir=claims_dir, base_dir=impact_dir)
    assert set(df["claim_id"]) == {tier2_id}
    assert (df["tier"] == 2).all()


def test_idempotent_rebuild(tmp_path):
    claims_dir, impact_dir = tmp_path / "claims", tmp_path / "impact"
    cl.add_claim(_claim("a claim", "pace"), base_dir=claims_dir)
    first = ci.impact_index(claims_base_dir=claims_dir, base_dir=impact_dir)
    second = ci.impact_index(claims_base_dir=claims_dir, base_dir=impact_dir)
    assert first.sort_values("market_family").reset_index(drop=True).equals(
        second.sort_values("market_family").reset_index(drop=True))


def test_affected_bets_round_trip_by_entity_and_claim(tmp_path):
    claims_dir, impact_dir = tmp_path / "claims", tmp_path / "impact"
    claim_id = cl.add_claim(_claim("jokic foul trouble", "reactions.high_foul_vs_low_foul",
                                    entity_ids=("jokic",)), base_dir=claims_dir)
    ci.impact_index(claims_base_dir=claims_dir, base_dir=impact_dir)

    by_entity = ci.affected_bets(entity_id="jokic", base_dir=impact_dir)
    by_claim = ci.affected_bets(claim_id=claim_id, base_dir=impact_dir)
    assert set(by_entity["market_family"]) == set(by_claim["market_family"])
    assert "props.pts" in set(by_entity["market_family"])


def test_families_for_slate_counts_distinct_claims(tmp_path):
    claims_dir, impact_dir = tmp_path / "claims", tmp_path / "impact"
    cl.add_claim(_claim("claim one", "minutes_dist", entity_ids=("a",)), base_dir=claims_dir)
    cl.add_claim(_claim("claim two", "minutes_dist", entity_ids=("b",)), base_dir=claims_dir)
    ci.impact_index(claims_base_dir=claims_dir, base_dir=impact_dir)

    out = ci.families_for_slate("nba", base_dir=impact_dir)
    row = out[out["market_family"] == "props.pts"]
    assert row.iloc[0]["n_claims"] == 2
