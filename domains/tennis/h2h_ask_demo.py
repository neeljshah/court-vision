"""ask()-surface demo for the H2H dominance claim (program v2, lane
tennis-h2h-claims). Answers ONE "who owns matchup X vs Y" question straight
from the VERIFIED tennis_h2h_dominance_top50_atp claim, using
scripts.platformkit.intel_query.ask.load_verified_claims() -- the SAME
VERIFIED-only loading path every other ask() family uses. No new question
family is added to families.py/ask.py in this lane (pair-lookup-by-two-names
routing is out of scope here); this is a direct demo of the pair-keyed claim
being answerable through the real verified-claims surface.

CLI:
    python -m domains.tennis.h2h_ask_demo
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

from scripts.platformkit.intel_query.ask import load_verified_claims

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAIM_ID = "tennis_h2h_dominance_top50_atp"
TRANSCRIPT_OUT = REPO_ROOT / "data" / "cache" / "intel_claims" / "tennis_h2h_ask_demo_transcript.json"


def _ascii_name(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def answer_h2h_ownership(p1_name: str, p2_name: str) -> dict[str, Any]:
    """Who owns the matchup <p1_name> vs <p2_name>? Answered ONLY from the
    VERIFIED tennis_h2h_dominance_top50_atp claim's ranking rows -- never
    computed fresh, never falls back to an UNVERIFIABLE/MISMATCH claim."""
    question = f"Who owns the matchup {p1_name} vs {p2_name}?"
    verified = load_verified_claims()
    row = verified.get(CLAIM_ID)
    if row is None:
        return {
            "answerable": False, "question": question,
            "reason": f"claim_id={CLAIM_ID!r} is not currently VERIFIED",
        }

    key = {_ascii_name(p1_name).strip().lower(), _ascii_name(p2_name).strip().lower()}
    hit = None
    for r in row.get("ranking", []):
        names = {_ascii_name(str(r.get("p1_name", ""))).strip().lower(),
                 _ascii_name(str(r.get("p2_name", ""))).strip().lower()}
        if names == key:
            hit = r
            break

    if hit is None:
        return {
            "answerable": False, "question": question,
            "reason": (
                f"no VERIFIED top-{len(row.get('ranking', []))} H2H-dominance row covers this pair "
                "(the pair may exist but did not clear the claim's min_sample floor, or is outside "
                "the top-50 dominance ranks)"
            ),
        }

    owner = hit["p1_name"] if hit["value"] >= 0.5 else hit["p2_name"]
    return {
        "answerable": True,
        "question": question,
        "answer": {
            "owner": owner,
            "pair": [hit["p1_name"], hit["p2_name"]],
            "dominance_metric": row["criteria"]["metric"],
            "dominance_value": hit["value"],
            "meetings": hit["n"],
            "rank_in_top50": hit["rank"],
            "caveats": row.get("caveats", []),
        },
        "evidence": {
            "claim_id": row["claim_id"],
            "source_files": row.get("source_files", []),
            "as_of": row.get("computed_at"),
            "validator_verdict": "VERIFIED",
        },
    }


def main() -> int:
    # Demo pair: the real top-1 dominance pair on the live claims artifact.
    verified = load_verified_claims()
    row = verified.get(CLAIM_ID)
    if not row or not row.get("ranking"):
        print(f"UNANSWERABLE: {CLAIM_ID} not currently VERIFIED with a non-empty ranking")
        return 1
    top = row["ranking"][0]
    result = answer_h2h_ownership(top["p1_name"], top["p2_name"])

    print(json.dumps(result, indent=2))
    TRANSCRIPT_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(TRANSCRIPT_OUT, "w", encoding="ascii", errors="strict") as f:
        json.dump(result, f, indent=2)
    print(f"transcript saved -> {TRANSCRIPT_OUT}")
    return 0 if result.get("answerable") else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
