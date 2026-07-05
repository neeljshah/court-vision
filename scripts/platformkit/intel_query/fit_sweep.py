"""compose_fit_sweep(top_n) -> dict, the read-only query surface for the
LeBron fit SWEEP claim (nba_fit_sweep_lebron_james_current) -- a
league-wide ranking of team fits, joined against the 3 fit-ingredient
claims (archetype profile, team scheme identity, role vacancy) plus the
fit-validity gate's REJECT verdict, so the sweep is never presented
without its own validity caveat inline.

Reads ONLY VERIFIED claims via ask.load_verified_claims() (same package,
same fail-closed contract as ask.compose_fit). Absent/non-VERIFIED sweep
claim -> honest unanswerable, never a partial/silent composition.

CLI:
    python -m scripts.platformkit.intel_query.fit_sweep [--top N]
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from scripts.platformkit.intel_query import ask

# Read-only: this lane only ever GETS this claim_id, never produces it.
_SWEEP_CLAIM_ID = "nba_fit_sweep_lebron_james_current"

_INGREDIENT_CLAIM_IDS = (
    ask._FIT_ARCHETYPE_CLAIM_ID,
    ask._FIT_SCHEME_CLAIM_ID,
    ask._FIT_VACANCY_CLAIM_ID,
)

FAMILY_FIT_SWEEP = "fit_sweep"

# Cites the pre-registered fit-validity gate's REJECT verdict (see
# ask.py's _FIT_VALIDITY_CLAIM_ID / data/domains/nba/fit_validity_gate_verdict.json)
# inline in EVERY sweep answer, so the ranking never implies a forecast it
# does not have. Wording deliberately avoids ask._FORBIDDEN_FIT_WORDS
# ("is NOT a forecast of", not "does not predict").
_SCOUTING_CAVEAT = (
    "SCOUTING ONLY: the fit-validity gate returned REJECT on 2026-07-05 "
    "(fit score is NOT a forecast of post-move performance; n=417 moves, "
    "5 folds, both planted nulls died)."
)


def _unanswerable(missing_ingredient: str, reason: str) -> dict[str, Any]:
    return {
        "answerable": False,
        "family": FAMILY_FIT_SWEEP,
        "missing_ingredient": missing_ingredient,
        "reason": reason,
    }


def _ascii_fold_row(row: dict[str, Any]) -> dict[str, Any]:
    """ASCII-fold every string value in a ranking row (team codes,
    archetype/scheme tags, etc.) -- schema-agnostic, matches ask.py's
    _ascii_name usage elsewhere without hardcoding a field allowlist."""
    folded = dict(row)
    for key, value in folded.items():
        if isinstance(value, str):
            folded[key] = ask._ascii_name(value)
    return folded


def compose_fit_sweep(top_n: int = 10) -> dict[str, Any]:
    """Join the VERIFIED LeBron fit-sweep ranking claim with its 3
    ingredient claims + the fit-validity gate verdict into one read-only,
    honest-caveated composition.

    Fail-closed: the sweep claim missing or not VERIFIED -> honest
    unanswerable naming missing_ingredient="sweep_claim". A composed
    answer that would contain a forbidden predictive word (see
    ask._FORBIDDEN_FIT_WORDS) is refused the same way, naming
    missing_ingredient="forbidden_word_guard".
    """
    verified = ask.load_verified_claims()
    sweep_claim = verified.get(_SWEEP_CLAIM_ID)
    if not sweep_claim:
        return _unanswerable(
            "sweep_claim",
            f"claim {_SWEEP_CLAIM_ID!r} is not currently VERIFIED/available",
        )

    ranking = [_ascii_fold_row(r) for r in sweep_claim.get("ranking", [])]
    top_fits = ranking[: top_n or 10]
    unanswerable_teams = [
        ask._ascii_name(t) if isinstance(t, str) else t
        for t in sweep_claim.get("unanswerable_teams", [])
    ]

    answer = {
        "scouting_caveat": _SCOUTING_CAVEAT,
        "declared_weights": sweep_claim.get("declared_weights", {}),
        "top_fits": top_fits,
        "unanswerable_teams": unanswerable_teams,
        "caveats": sweep_claim.get("caveats", []),
    }

    text_blob = json.dumps(answer).lower()
    for word in ask._FORBIDDEN_FIT_WORDS:
        if word in text_blob:
            return _unanswerable(
                "forbidden_word_guard",
                f"composed answer would contain forbidden predictive word {word!r} -- refusing",
            )

    evidence = [ask._claim_evidence(sweep_claim)]
    for claim_id in _INGREDIENT_CLAIM_IDS:
        ingredient = verified.get(claim_id)
        if ingredient:
            evidence.append(ask._claim_evidence(ingredient))
    gate_claim = verified.get(ask._FIT_VALIDITY_CLAIM_ID)
    if gate_claim:
        evidence.append(ask._claim_evidence(gate_claim))

    return {
        "answerable": True,
        "family": FAMILY_FIT_SWEEP,
        "player": "LeBron James",
        "answer": answer,
        "evidence": evidence,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="read-only query surface for the LeBron fit SWEEP claim"
    )
    parser.add_argument("--top", type=int, default=10, help="number of top fits to include")
    args = parser.parse_args(argv)

    result = compose_fit_sweep(args.top)
    print(json.dumps(result, indent=2))  # ensure_ascii=True default keeps stdout ASCII-safe
    return 0 if result.get("answerable") else 1


if __name__ == "__main__":
    sys.exit(main())
