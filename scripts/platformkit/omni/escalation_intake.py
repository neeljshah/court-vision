"""scripts.platformkit.omni.escalation_intake -- routes K-sweep escalations
(status=ESCALATED coverage cells / escalate_to_funnel claims) into a funnel
Stage-A proposal, screens it, and records the verdict. Claude-free.

STEP 0 premise check (2026-07-13): the mineable unit is the CLAIM, not the
bare coverage cell -- a coverage cell (k_coverage.load_matrix, status
ESCALATED) carries no statement/effect payload to build a proposal from, it
is only a rollup of its player's escalated claims (k_sweep_nba's own
_STATUS_PRIORITY max over that player's per-condition claims). So this
module's source of truth is: claims_ledger rows with lifecycle=="proposed"
AND links.escalate_to_funnel==True (44 such claims covering 27 distinct
player-level ESCALATED cells, verified 2026-07-13). The coverage-matrix
ESCALATED count is read only as a cross-check in the returned summary.

FUNNEL Stage-A REUSE: funnel.stage_a_screen (scripts.platformkit.
interaction_factory.runner.run_batch under the hood) screens
interaction-factory candidates shaped as attr_a/attr_b template pairs; a
K-sweep escalation is a univariate mechanical split with no such template,
so calling it directly would be a shape mismatch, not real reuse. The
applicable, already-built Stage-A gate for an OUTSIDE-origin proposal is
claims_intake.intake_proposal (P2's own contract: cite a parent claim_id,
bounce on a same-(sport,topic) negative/meta collision, else ledger) --
this literally IS "convert to a funnel Stage-A proposal via claims_intake"
per the task naming, and its ACCEPTED/BOUNCED verdict is the screen verdict
recorded below (mirrors funnel's own SCREEN semantics: BOUNCED == kill,
ACCEPTED == survives to the ledger).

"ESCALATION_SCREENED" MARK: k_coverage.STATUSES is a closed, validated enum
(UNMINED/MINED/INSUFFICIENT_DATA/ESCALATED) in a file this lane does not own
-- adding a fifth literal there is a shared-file edit outside AUTOWIRE's
ownership. lifecycle is a free string field claims_ledger already supports
mutating via set_lifecycle (accepted/rejected/screened/proposed are all
existing free-string values, not an enum), so the PARENT claim's lifecycle
is flipped to "escalation_screened" -- the claim-level analogue of the
task's "mark the cell ESCALATION_SCREENED", using an existing public API
instead of extending a shared enum. This also gives idempotency for free:
the next run's lifecycle=="proposed" query no longer matches a screened row.

INVARIANTS: claims_ledger/claims_intake import only. <=300 LOC. ASCII
stdout. Never writes data/registry/. No $/edge claims.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_omni_escalation_intake.py -q

CLI (runs for real against the live ledger):
  cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.omni.escalation_intake
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, Dict, List, Optional

from scripts.platformkit.omni import claims_intake as CI
from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_coverage as kc

_SCREENED_LIFECYCLE = "escalation_screened"


def _find_escalated_claims(base_dir=None) -> List[dict]:
    """Every lifecycle=='proposed' claim carrying links.escalate_to_funnel."""
    df = cl.query(sport="nba", lifecycle="proposed", base_dir=base_dir)
    out = []
    for _, row in df.iterrows():
        links = json.loads(row["links_json"])
        if links.get("escalate_to_funnel"):
            out.append(row.to_dict())
    return out


def _build_proposal(parent: dict) -> dict:
    scope = json.loads(parent["scope_json"])
    return {
        "statement": f"{parent['statement']} :: funnel escalation intake",
        "type": "effect",
        "supporting_claim_ids": [parent["claim_id"]],
        "scope": scope,
        "topic": parent.get("topic", ""),
        "lifecycle": "proposed",
        "provenance": {"created_by_lane": "omni_escalation_intake",
                       "parent_claim_id": parent["claim_id"]},
        "links": {"escalation_parent": parent["claim_id"]},
    }


def run_escalation_intake(base_dir=None) -> Dict[str, Any]:
    """Screen every un-screened escalated claim exactly once (idempotent:
    reruns skip claims whose lifecycle already flipped off 'proposed')."""
    escalated = _find_escalated_claims(base_dir)
    results: List[dict] = []
    for parent in escalated:
        proposal = _build_proposal(parent)
        verdict = CI.intake_proposal(proposal, base_dir=base_dir)
        review = {"screen_verdict": verdict["verdict"],
                  "proposal_claim_id": verdict.get("claim_id"),
                  "reason": verdict.get("reason")}
        cl.set_lifecycle(parent["claim_id"], _SCREENED_LIFECYCLE, review=review, base_dir=base_dir)
        results.append({"parent_claim_id": parent["claim_id"], "statement": parent["statement"],
                         **verdict})

    escalated_cells = 0
    try:
        matrix = kc.load_matrix(base_dir)
        escalated_cells = int((matrix["status"] == "ESCALATED").sum())
    except FileNotFoundError:
        pass  # no coverage matrix yet -- cross-check is best-effort only

    return {
        "screened": len(results),
        "verdict_counts": dict(Counter(r["verdict"] for r in results)),
        "escalated_cells_cross_check": escalated_cells,
        "results": results,
    }


if __name__ == "__main__":
    out = run_escalation_intake()
    print(f"[escalation_intake] screened: {out['screened']}")
    print(f"[escalation_intake] verdict_counts: {out['verdict_counts']}")
    print(f"[escalation_intake] escalated_cells_cross_check: {out['escalated_cells_cross_check']}")
    for r in out["results"]:
        print(f"[escalation_intake]   {r['parent_claim_id']} -> {r['verdict']} "
              f"({r.get('reason') or r.get('claim_id')})")


__all__ = ["run_escalation_intake"]
