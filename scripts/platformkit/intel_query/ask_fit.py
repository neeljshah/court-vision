"""FAMILY_FIT: compose_fit(player, team), a SCOUTING composition of 3
VERIFIED fit-ingredient claims (archetype profile, team scheme identity,
role vacancy) -- descriptive only, never predictive.

Split out of ask.py to respect the <=300 LOC/file rail. compose_fit calls
back into ask.load_verified_claims / ask.pairs_for_claim_stores (imported
directly, not re-implemented) so a test that monkeypatches
scripts.platformkit.intel_query.ask.CLAIM_SOURCE_PAIRS still changes what
compose_fit sees -- those two functions physically live in ask.py and read
CLAIM_SOURCE_PAIRS as ask.py's own module global, so calling them (from
here or from ask.py itself) observes the same monkeypatched value.
"""
from __future__ import annotations

import json
from typing import Any

from scripts.platformkit.intel_query.ask import (
    _ascii_name,
    _claim_evidence,
    load_verified_claims,
    pairs_for_claim_stores,
)

# FIT is a compose_fit(player, team)-only family (explicit args, not a
# free-text question routed through families.classify), so it is defined
# here rather than added to families.py's question-classifier enum.
FAMILY_FIT = "fit"

# claim_id of each fit-ingredient claim compose_fit() joins -- a static
# registry (not a glob) so compose_fit only ever reads claims this lane
# named, matching the CLAIM_SOURCE_PAIRS pattern in ask.py.
_FIT_ARCHETYPE_CLAIM_ID = "nba_fit_archetype_profile_current"
_FIT_SCHEME_CLAIM_ID = "nba_fit_team_scheme_identity_current"
_FIT_VACANCY_CLAIM_ID = "nba_fit_role_vacancy_by_team_posgroup_current"

# compose_fit joins claims from exactly these two stores (3 ingredient claims
# + the validity gate verdict). A bare load_verified_claims() would whole-load
# EVERY store including nba_player_box_rate (2.8GB / 59k VERIFIED rows) -- the
# same footgun as the 6.1GB compose_matchup incident -- so scope like
# compose_best/_profile do (pairs_for_claim_stores).
_FIT_CLAIM_STORES = ("nba_fit_ingredient_claims.jsonl", "gate_verdict_claims.jsonl")

# PROGRAM v3 closure: the pre-registered fit-validity gate's REJECT verdict
# (does scheme fit predict post-move performance? -- see
# data/domains/nba/fit_validity_gate_verdict.json, read-only truth, never
# regenerated here) is cited inline in every compose_fit() answer so the
# SCOUTING composition never implies validity it does not have.
_FIT_VALIDITY_CLAIM_ID = "nba_fit_validity_gate_verdict"

# Words a SCOUTING fit answer must never contain -- compose_fit() is a
# descriptive composition of three VERIFIED ingredient claims, never a
# prediction (no-edge-claims rule).
_FORBIDDEN_FIT_WORDS = ("predict", "will improve", "expected gain", "edge")


def _find_by_key(rows: list[dict[str, Any]], key: str, name_key: str) -> dict[str, Any] | None:
    """First ranking entry whose `key` field ASCII-folds/lowercases to
    name_key. name_key is already normalized by the caller."""
    for r in rows:
        if key in r and _ascii_name(str(r[key])).strip().lower() == name_key:
            return r
    return None


def _fit_unanswerable(player: str, team: str, missing_ingredient: str, reason: str) -> dict[str, Any]:
    return {
        "answerable": False,
        "family": FAMILY_FIT,
        "player": _ascii_name(player),
        "team": team,
        "missing_ingredient": missing_ingredient,
        "reason": _ascii_name(reason),
    }


def compose_fit(player: str, team: str) -> dict[str, Any]:
    """Join the 3 VERIFIED fit-ingredient claims (archetype/attribute
    profile, team scheme identity, role vacancy) into one SCOUTING
    composition -- descriptive only, never predictive. If ANY ingredient is
    below its stated floor or absent for this player/team, returns honest
    UNANSWERABLE naming the exact missing ingredient (never guesses, never
    silently composes from a partial join)."""
    verified = load_verified_claims(pairs_for_claim_stores(_FIT_CLAIM_STORES))
    name_key = _ascii_name(player).strip().lower()
    team_key = team.strip().upper()

    archetype_claim = verified.get(_FIT_ARCHETYPE_CLAIM_ID)
    if not archetype_claim:
        return _fit_unanswerable(
            player, team, "archetype_profile",
            f"claim {_FIT_ARCHETYPE_CLAIM_ID!r} is not currently VERIFIED/available",
        )
    profile = _find_by_key(archetype_claim.get("ranking", []), "player_name", name_key)
    if not profile:
        return _fit_unanswerable(
            player, team, "archetype_profile",
            f"{player!r} has no VERIFIED archetype/attribute row (absent from the claim, "
            f"or below its stated minutes floor -- see {_FIT_ARCHETYPE_CLAIM_ID}'s caveats)",
        )

    scheme_claim = verified.get(_FIT_SCHEME_CLAIM_ID)
    if not scheme_claim:
        return _fit_unanswerable(
            team, team, "team_scheme_identity",
            f"claim {_FIT_SCHEME_CLAIM_ID!r} is not currently VERIFIED/available",
        )
    scheme = _find_by_key(scheme_claim.get("ranking", []), "team", team_key.lower())
    if not scheme:
        return _fit_unanswerable(
            player, team, "team_scheme_identity",
            f"team {team!r} has no VERIFIED scheme-identity row in {_FIT_SCHEME_CLAIM_ID}",
        )

    vacancy_claim = verified.get(_FIT_VACANCY_CLAIM_ID)
    if not vacancy_claim:
        return _fit_unanswerable(
            player, team, "role_vacancy",
            f"claim {_FIT_VACANCY_CLAIM_ID!r} is not currently VERIFIED/available",
        )
    posgroup = profile.get("posgroup")
    vacancy_key = f"{team_key}|{posgroup}"
    vacancy = _find_by_key(vacancy_claim.get("ranking", []), "team_posgroup", vacancy_key.lower())
    if not vacancy:
        return _fit_unanswerable(
            player, team, "role_vacancy",
            f"team_posgroup {vacancy_key!r} has no VERIFIED role-vacancy row (thin sample "
            f"-- see {_FIT_VACANCY_CLAIM_ID}'s min_sample floor)",
        )

    answer = {
        "player": _ascii_name(str(profile.get("player_name"))), "team": team_key,
        "archetype_profile": {
            "posgroup": profile.get("posgroup"), "archetype": profile.get("archetype"),
            "creation": profile.get("creation"), "playmaking": profile.get("playmaking"),
            "spacing": profile.get("spacing"), "rim_pressure": profile.get("rim_pressure"),
            "rebounding": profile.get("rebounding"), "rim_protect": profile.get("rim_protect"),
            "perimeter_d": profile.get("perimeter_d"), "self_create": profile.get("self_create"),
            "usage_pct": profile.get("usage_pct"),
        },
        "team_scheme_identity": {
            "dominant_tag": scheme.get("dominant_tag"), "best_scheme": scheme.get("best_scheme"),
            "confidence": scheme.get("confidence"),
        },
        "role_vacancy": {"team_posgroup": vacancy.get("team_posgroup"), "vacancy_share": vacancy.get("value"),
                          "n": vacancy.get("n")},
        "note": (
            "SCOUTING composition of 3 VERIFIED descriptive ingredients -- purely descriptive, "
            "no market/$ claim. Composition is descriptive; the validity gate returned REJECT "
            "on 2026-07-05."
        ),
    }
    text_blob = json.dumps(answer).lower()
    for word in _FORBIDDEN_FIT_WORDS:
        if word in text_blob:
            return _fit_unanswerable(
                player, team, "forbidden_word_guard",
                f"composed answer would contain forbidden predictive word {word!r} -- refusing",
            )

    evidence = [_claim_evidence(archetype_claim), _claim_evidence(scheme_claim),
                _claim_evidence(vacancy_claim)]
    validity_claim = verified.get(_FIT_VALIDITY_CLAIM_ID)
    if validity_claim:
        evidence.append(_claim_evidence(validity_claim))

    return {
        "answerable": True, "family": FAMILY_FIT, "player": _ascii_name(player), "team": team,
        "answer": answer,
        "evidence": evidence,
    }
