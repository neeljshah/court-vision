"""scripts.platformkit.omni.claims_intake -- P2 intake contract for new claims.

A proposal must (a) cite >=1 supporting claim_id -- except type='mechanism'
proposals, which bootstrap a claim tree and are exempt -- and (b) not collide
with an already-ledgered negative/meta claim in the same (sport, topic)
scope. Failing either bounces the proposal instead of ledgering it.

INVARIANTS: stdlib + claims_ledger only. <=300 LOC. ASCII stdout. No $/edge
claims.
"""
from __future__ import annotations

from scripts.platformkit.omni import claims_ledger

_COLLISION_TYPES = ("negative", "meta")


def _find_collision(sport: str, topic: str, base_dir=None) -> str | None:
    """First ledgered negative/meta claim_id in the same (sport, topic) scope, if any."""
    df = claims_ledger.query(sport=sport, topic=topic, base_dir=base_dir)
    if df.empty:
        return None
    hit = df[df["type"].isin(_COLLISION_TYPES)]
    if hit.empty:
        return None
    return str(hit.iloc[0]["claim_id"])


def intake_proposal(proposal: dict, base_dir=None) -> dict:
    """Adjudicate + (if accepted) ledger *proposal*.

    proposal keys mirror claims_ledger.add_claim's claim dict, plus an
    optional 'supporting_claim_ids' list. Returns:
        {"verdict": "ACCEPTED", "claim_id": ...}
        {"verdict": "BOUNCED", "reason": ..., "collision_claim_id": ... | None}
    """
    ctype = proposal.get("type", "")
    supporting = proposal.get("supporting_claim_ids") or []
    if ctype != "mechanism" and not supporting:
        return {
            "verdict": "BOUNCED",
            "reason": "no supporting claim_id cited (required unless type=mechanism)",
            "collision_claim_id": None,
        }

    scope = proposal.get("scope") or {}
    sport = scope.get("sport", "")
    topic = proposal.get("topic", "")
    collision = _find_collision(sport, topic, base_dir=base_dir)
    if collision is not None:
        return {
            "verdict": "BOUNCED",
            "reason": f"collides with ledgered {_COLLISION_TYPES} claim in same (sport, topic) scope",
            "collision_claim_id": collision,
        }

    links = dict(proposal.get("links") or {})
    if supporting:
        links["parent_claims"] = sorted(set(links.get("parent_claims", []) + list(supporting)))
    claim = {**proposal, "links": links}
    claim_id = claims_ledger.add_claim(claim, base_dir=base_dir)
    return {"verdict": "ACCEPTED", "claim_id": claim_id}


__all__ = ["intake_proposal"]
