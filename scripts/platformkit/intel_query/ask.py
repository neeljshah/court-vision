"""ask(question) -> dict, answering ONLY from VERIFIED claims (mission spine 5).

Deterministic tool surface: an external LLM calls ask() like any other tool.
NO LLM call inside this module -- routing is families.classify (keyword/regex),
and answers come straight from claim rows an INDEPENDENT validator marked
VERIFIED. Sources joined per pair in CLAIM_SOURCE_PAIRS: a validation-summary
JSON (per-claim_id verdict) + the producer claims JSONL it validates (full
claim rows: criteria/ranking or gate_module/verdict, source_files, caveats).

HONEST UNANSWERABLE: no VERIFIED claim covers the question, or the family
can't be classified -> {"answerable": False, "reason": ..., "nearest_supported_families": [...]}.
Never falls back to raw computation; never answers from an UNVERIFIABLE/MISMATCH claim.

CLI:
    python -m scripts.platformkit.intel_query.ask "Who are the top 5 best shooters (composite) in window=last_20?"
    python -m scripts.platformkit.intel_query.ask --demo
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

from scripts.platformkit.intel_query.families import (
    FAMILY_ENTITY_LOOKUP,
    FAMILY_GATE_VERDICT,
    FAMILY_PROVENANCE,
    FAMILY_TOP_N,
    classify,
    describe_families,
    gate_verdict_match_score,
    match_gate_verdict_candidates,
)

# FIT is a compose_fit(player, team)-only family (explicit args, not a
# free-text question routed through families.classify), so it is defined
# here rather than added to families.py's question-classifier enum.
FAMILY_FIT = "fit"

REPO_ROOT = Path(__file__).resolve().parents[3]

# Every known (validation-summary, producer-claims) pair -- a static registry,
# not a directory glob, so ask() only ever reads artifacts this lane verified.
CLAIM_SOURCE_PAIRS: tuple[tuple[Path, Path], ...] = (
    (
        REPO_ROOT / "data" / "frontend" / "ops" / "intel_claims_validation.json",
        REPO_ROOT / "data" / "cache" / "intel_claims" / "nba_shooting_claims.jsonl",
    ),
    (
        REPO_ROOT / "data" / "cache" / "intel_claims" / "nba_quality_claims_validation.json",
        REPO_ROOT / "data" / "cache" / "intel_claims" / "nba_quality_claims.jsonl",
    ),
    (
        REPO_ROOT / "data" / "frontend" / "ops" / "intel_verdict_claims_validation.json",
        REPO_ROOT / "data" / "cache" / "intel_claims" / "gate_verdict_claims.jsonl",
    ),
    (
        REPO_ROOT / "data" / "cache" / "intel_claims" / "tennis_hold_claims_validation.json",
        REPO_ROOT / "data" / "cache" / "intel_claims" / "tennis_hold_claims.jsonl",
    ),
    (
        REPO_ROOT / "data" / "cache" / "intel_claims" / "mlb_pitcher_claims_validation.json",
        REPO_ROOT / "data" / "cache" / "intel_claims" / "mlb_pitcher_claims.jsonl",
    ),
    (
        REPO_ROOT / "data" / "cache" / "intel_claims" / "soccer_intl_strength_claims_validation.json",
        REPO_ROOT / "data" / "cache" / "intel_claims" / "soccer_intl_strength_claims.jsonl",
    ),
    (
        REPO_ROOT / "data" / "cache" / "intel_claims" / "tennis_h2h_index_claims_validation.json",
        REPO_ROOT / "data" / "cache" / "intel_claims" / "tennis_h2h_index_claims.jsonl",
    ),
    (
        REPO_ROOT / "data" / "cache" / "intel_claims" / "nba_fit_ingredient_claims_validation.json",
        REPO_ROOT / "data" / "cache" / "intel_claims" / "nba_fit_ingredient_claims.jsonl",
    ),
)

# claim_id of each fit-ingredient claim compose_fit() joins -- a static
# registry (not a glob) so compose_fit only ever reads claims this lane
# named, matching the CLAIM_SOURCE_PAIRS pattern above.
_FIT_ARCHETYPE_CLAIM_ID = "nba_fit_archetype_profile_current"
_FIT_SCHEME_CLAIM_ID = "nba_fit_team_scheme_identity_current"
_FIT_VACANCY_CLAIM_ID = "nba_fit_role_vacancy_by_team_posgroup_current"

# Words a SCOUTING fit answer must never contain -- compose_fit() is a
# descriptive composition of three VERIFIED ingredient claims, never a
# prediction (no-edge-claims rule).
_FORBIDDEN_FIT_WORDS = ("predict", "will improve", "expected gain", "edge")

VERIFIED = "VERIFIED"


def _ascii_name(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="ascii", errors="strict") as f:
        return json.load(f)


def _display_path(path: Path) -> str:
    """Repo-relative string when possible, else the raw path (fixtures
    live under a tmp_path outside REPO_ROOT)."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with open(path, "r", encoding="ascii", errors="strict") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_verified_claims() -> dict[str, dict[str, Any]]:
    """{claim_id: claim_row} for every claim_id whose validator verdict is
    exactly VERIFIED. A claim_id absent from (or non-VERIFIED in) its
    validation summary is NOT included -- MISMATCH/UNVERIFIABLE stays
    invisible to ask()."""
    verified: dict[str, dict[str, Any]] = {}
    for validation_path, claims_path in CLAIM_SOURCE_PAIRS:
        summary = _load_json(validation_path)
        if not summary:
            continue
        verified_ids = {
            d["claim_id"] for d in summary.get("details", []) if d.get("verdict") == VERIFIED
        }
        if not verified_ids:
            continue
        for row in _load_jsonl(claims_path):
            cid = row.get("claim_id")
            if cid in verified_ids:
                row = dict(row)
                row["_validator_source"] = _display_path(validation_path)
                row["_producer_source"] = _display_path(claims_path)
                verified[cid] = row
    return verified


def _claim_evidence(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": row["claim_id"],
        "source_files": row.get("source_files", []),
        "as_of": row.get("computed_at"),
        "validator_verdict": VERIFIED,
        "validator_source": row.get("_validator_source"),
        "producer_source": row.get("_producer_source"),
    }


def _unanswerable(reason: str, question: str) -> dict[str, Any]:
    return {
        "answerable": False,
        "question": question,
        "reason": reason,
        "nearest_supported_families": describe_families(),
    }


def _filter_by_hints(rows: list[dict[str, Any]], parsed) -> list[dict[str, Any]]:
    candidates = rows
    if parsed.metric_hints:
        candidates = [r for r in candidates if r["criteria"].get("metric") in parsed.metric_hints]
    if parsed.window_hint:
        candidates = [r for r in candidates if r["criteria"].get("window") == parsed.window_hint]
    return candidates


def _answer_top_n(parsed, question: str, verified: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ranking_claims = [r for r in verified.values() if r.get("kind") == "ranking"]
    candidates = _filter_by_hints(ranking_claims, parsed)
    if not candidates:
        return _unanswerable(
            "no VERIFIED ranking claim matches the requested metric/window", question
        )
    row = max(candidates, key=lambda r: r.get("computed_at", ""))  # most-recent tie-break
    ranking = [dict(r) for r in row.get("ranking", [])]
    for r in ranking:
        if "player_name" in r:
            r["player_name"] = _ascii_name(str(r["player_name"]))
    ranking = ranking[:parsed.top_n or 10]
    return {
        "answerable": True, "question": question, "family": FAMILY_TOP_N,
        "answer": {
            "metric": row["criteria"].get("metric"), "window": row["criteria"].get("window"),
            "ranking": ranking, "n_considered": row.get("n_considered"),
            "n_excluded_below_floor": row.get("n_excluded_below_floor"),
            "caveats": row.get("caveats", []),
        },
        "evidence": [_claim_evidence(row)],
    }


def _answer_entity_lookup(parsed, question: str, verified: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not parsed.entity_name:
        return _unanswerable("could not extract a player/entity name from the question", question)
    name_key = parsed.entity_name.strip().lower()
    ranking_claims = [r for r in verified.values() if r.get("kind") == "ranking"]
    candidates = _filter_by_hints(ranking_claims, parsed)
    hits = []
    for row in candidates:
        for r in row.get("ranking", []):
            if _ascii_name(str(r.get("player_name", ""))).strip().lower() == name_key:
                hits.append((row, r))
    if not hits:
        return _unanswerable(
            f"no VERIFIED ranking claim has an entry for entity_name={parsed.entity_name!r} "
            "(the entity may exist but did not clear the claim's min_sample floor)",
            question,
        )
    answers = [
        {
            "metric": row["criteria"].get("metric"), "window": row["criteria"].get("window"),
            "rank": r["rank"], "value": r["value"], "n": r.get("n"),
        }
        for row, r in hits
    ]
    evidence = [_claim_evidence(row) for row, _r in hits]
    return {
        "answerable": True, "question": question, "family": FAMILY_ENTITY_LOOKUP,
        "answer": {"entity_name": parsed.entity_name, "rankings": answers},
        "evidence": evidence,
    }


def _answer_provenance(parsed, question: str, verified: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not parsed.claim_id or parsed.claim_id not in verified:
        return _unanswerable(
            "no VERIFIED claim_id was named (or recognized) in the question", question
        )
    row = verified[parsed.claim_id]
    return {
        "answerable": True, "question": question, "family": FAMILY_PROVENANCE,
        "answer": {
            "claim_id": row["claim_id"], "question_answered_by_claim": row.get("question"),
            "criteria": row.get("criteria"), "n_considered": row.get("n_considered"),
            "n_excluded_below_floor": row.get("n_excluded_below_floor"),
            "caveats": row.get("caveats", []),
        },
        "evidence": [_claim_evidence(row)],
    }


def _answer_gate_verdict(parsed, question: str, verified: dict[str, dict[str, Any]]) -> dict[str, Any]:
    # Deterministic ranking (score DESC, claim_id ASC). If 2+ candidates tie
    # the top score with DIFFERENT verdicts, report ambiguity honestly.
    candidates = match_gate_verdict_candidates(parsed, verified)
    if not candidates:
        return _unanswerable(
            "no VERIFIED gate-verdict claim matches this question's topic", question
        )
    row = candidates[0]
    if len(candidates) > 1:
        top_score = gate_verdict_match_score(parsed, row)
        tied = [c for c in candidates if gate_verdict_match_score(parsed, c) == top_score]
        distinct_verdicts = {c.get("verdict") for c in tied}
        if len(tied) > 1 and len(distinct_verdicts) > 1:
            return {
                "answerable": True,
                "question": question,
                "family": FAMILY_GATE_VERDICT,
                "note": "multiple matching verdicts with equal match score -- ambiguous topic",
                "candidates": [c.get("claim_id") for c in tied],
            }
    return {
        "answerable": True, "question": question, "family": FAMILY_GATE_VERDICT,
        "answer": {
            "gate_module": row.get("gate_module"), "verdict": row.get("verdict"),
            "primary_number": row.get("primary_number"), "corpus_ids": row.get("corpus_ids", []),
            "planted_null_passed": row.get("planted_null_passed"),
            "edge_claimed": row.get("edge_claimed", False), "verdict_file": row.get("verdict_file"),
            "caveats": row.get("caveats", []),
        },
        "evidence": [_claim_evidence(row)],
    }


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
    verified = load_verified_claims()
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
            "no market/$ claim."
        ),
    }
    text_blob = json.dumps(answer).lower()
    for word in _FORBIDDEN_FIT_WORDS:
        if word in text_blob:
            return _fit_unanswerable(
                player, team, "forbidden_word_guard",
                f"composed answer would contain forbidden predictive word {word!r} -- refusing",
            )

    return {
        "answerable": True, "family": FAMILY_FIT, "player": _ascii_name(player), "team": team,
        "answer": answer,
        "evidence": [_claim_evidence(archetype_claim), _claim_evidence(scheme_claim),
                     _claim_evidence(vacancy_claim)],
    }


def ask(question: str) -> dict[str, Any]:
    """Answer `question` ONLY from VERIFIED claims. Never guesses, never
    computes from raw data, never uses an UNVERIFIABLE/MISMATCH claim."""
    verified = load_verified_claims()
    parsed = classify(question)

    if parsed.family is None:
        return _unanswerable(
            "question did not match a supported family (top_n / entity_lookup / "
            "provenance / gate_verdict)",
            question,
        )
    if not verified:
        return _unanswerable("no VERIFIED claims are currently available", question)

    if parsed.family == FAMILY_TOP_N:
        return _answer_top_n(parsed, question, verified)
    if parsed.family == FAMILY_ENTITY_LOOKUP:
        return _answer_entity_lookup(parsed, question, verified)
    if parsed.family == FAMILY_PROVENANCE:
        return _answer_provenance(parsed, question, verified)
    if parsed.family == FAMILY_GATE_VERDICT:
        return _answer_gate_verdict(parsed, question, verified)
    return _unanswerable("unreachable family branch", question)  # pragma: no cover


_DEMO_QUESTIONS = (
    "Who are the top 5 best shooters (composite) in window=last_20?",
    "Where does Isaiah Joe rank on composite in window=last_20?",
    "How do you know? Show the evidence for nba_shooting_composite_last_20.",
    "What did the tennis surface gate find?",
    "What is the weather in Boston tomorrow?",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ask-anything over VERIFIED intel claims")
    parser.add_argument("question", nargs="?", default=None)
    parser.add_argument("--demo", action="store_true", help="run 3 answerable + 1 unanswerable proof questions")
    args = parser.parse_args(argv)

    if args.demo or not args.question:
        questions = _DEMO_QUESTIONS[:2] + _DEMO_QUESTIONS[-2:]
        for q in questions:
            result = ask(q)
            print(f"Q: {q}")
            print(json.dumps(result, indent=2))
            print()
        return 0

    result = ask(args.question)
    print(json.dumps(result, indent=2))
    return 0 if result.get("answerable") else 1


if __name__ == "__main__":
    sys.exit(main())
