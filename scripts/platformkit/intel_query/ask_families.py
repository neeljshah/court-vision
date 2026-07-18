"""Family answer formatters + dispatch hooks for ask.py's ask().

Split out of ask.py to respect the <=300 LOC/file rail (ask.py was already
over -- same motivation as ask_index.py's split from the TOP_N fast path).
Behavior-preserving move only: no logic/signature changes. Every function
here is either called directly by ask.py's ask() dispatcher (top_n /
entity_lookup / provenance / gate_verdict answer formatters) or is a
"try this specialized composer first" hook (_try_best_x / _try_shooter_profile)
that ask() calls before falling through to families.classify's dispatch.

ask.py re-exports the small set of these names external callers/tests use
(FAMILY_BEST, FAMILY_SHOOTER_PROFILE, _try_shooter_profile) so
`from scripts.platformkit.intel_query.ask import X` keeps working unchanged.
"""
from __future__ import annotations

import re
from typing import Any

from scripts.platformkit.intel_query import ask_index
from scripts.platformkit.intel_query.ask import _ascii_name, _claim_evidence, _unanswerable
from scripts.platformkit.intel_query.families import (
    FAMILY_ENTITY_LOOKUP,
    FAMILY_GATE_VERDICT,
    FAMILY_PROVENANCE,
    FAMILY_TOP_N,
    gate_verdict_match_score,
    match_gate_verdict_candidates,
)

# ONE-CONCLUSION composer family: "who is the best shooter" (singular,
# all-factors-weighed) is a DIFFERENT question from "top 5 best shooters"
# (a ranking list, already routed to FAMILY_TOP_N by families.classify).
# Checked BEFORE the existing family dispatch so it never disturbs top_n's
# "best shooters" plural/top-N phrasing. Only "shooter" is wired v1 --
# _BEST_ASPECT_ALIASES maps a recognized alias phrase to a compose_best()
# aspect key; an unrecognized "best X" phrase falls through to the existing
# families.classify dispatch unchanged.
FAMILY_BEST = "best"
_BEST_ASPECT_ALIASES: dict[str, str] = {"shooter": "shooter", "shooters": "shooter"}
_BEST_SINGLE_RE = re.compile(r"\bbest\s+(shooter|shooters)\b", re.IGNORECASE)
_TOP_N_ANYWHERE_RE = re.compile(r"\btop\s*[- ]?\s*\d+\b", re.IGNORECASE)

# SHOOTER TRAIT PROFILE family: "what kind of shooter is X?" is a VECTOR
# question (multi-axis profile), not a ranking/scalar question -- routed to
# compose_profile(), which assembles per-axis VERIFIED claims and never
# collapses them into one score. Checked before families.classify (same
# pattern as FAMILY_BEST above).
FAMILY_SHOOTER_PROFILE = "shooter_profile"
_PROFILE_RE = re.compile(
    r"\bwhat kind of shooter is\s+(?P<name>[A-Za-z][A-Za-z .'\-]*?)\s*\??\s*$"
    r"|\bshooter profile (?:for|of)\s+(?P<name2>[A-Za-z][A-Za-z .'\-]*?)\s*\??\s*$",
    re.IGNORECASE,
)


def _filter_by_hints(rows: list[dict[str, Any]], parsed) -> list[dict[str, Any]]:
    # Per-file schema tolerance: a claims row from a store this lane hasn't
    # seen yet might be missing "criteria" entirely -- treat that as "does
    # not match this hint" rather than KeyError-ing the whole ask() call.
    #
    # BUG FIX: families.classify's metric_hints alias dict has no synonym
    # for phrasings like "free throw percentage", so metric_hints can come
    # back EMPTY for a real, answerable metric -- and an empty metric_hints
    # used to skip metric filtering entirely, letting an unrelated claim
    # (wrong metric, wrong entity type) win by recency. ask_index's
    # extract_metric_synonym covers the phrasings that exist in the actual
    # claim corpus; entity_key_matches rejects a claim whose entity_key
    # (player vs team) contradicts a question that names an entity type
    # unambiguously ("players" must never be answered by a team claim).
    metric_synonym = ask_index.extract_metric_synonym(parsed.raw)
    entity_type = ask_index.question_entity_type(parsed.raw)
    allowed_metrics = set(parsed.metric_hints)
    if metric_synonym is not None:
        allowed_metrics.add(metric_synonym)
    candidates = rows
    if allowed_metrics:
        candidates = [r for r in candidates if r.get("criteria", {}).get("metric") in allowed_metrics]
    if parsed.window_hint:
        candidates = [r for r in candidates if r.get("criteria", {}).get("window") == parsed.window_hint]
    candidates = [
        r for r in candidates
        if ask_index.entity_key_matches(
            r.get("criteria", {}).get("entity_key"), entity_type, r.get("claim_id", ""))
    ]
    return candidates


def _format_top_n_answer(parsed, question: str, row: dict[str, Any]) -> dict[str, Any]:
    """Shared formatter: BOTH the index fast path and the full-load slow
    path call this on their winning row, so the two can never drift in
    answer SHAPE -- only in how the winning row was found."""
    ranking = [dict(r) for r in row.get("ranking", [])]
    for r in ranking:
        if "player_name" in r:
            r["player_name"] = _ascii_name(str(r["player_name"]))
    ranking = ranking[:parsed.top_n or 10]
    return {
        "answerable": True, "question": question, "family": FAMILY_TOP_N,
        "answer": {
            "metric": row.get("criteria", {}).get("metric"), "window": row.get("criteria", {}).get("window"),
            "ranking": ranking, "n_considered": row.get("n_considered"),
            "n_excluded_below_floor": row.get("n_excluded_below_floor"),
            "caveats": row.get("caveats", []),
        },
        "evidence": [_claim_evidence(row)],
    }


def _answer_top_n(parsed, question: str, verified: dict[str, dict[str, Any]]) -> dict[str, Any]:
    # UNANSWERABLE-over-wrong-answer: a top-N question whose metric resolved
    # to NOTHING (no families.py alias, no ask_index synonym) must never be
    # answered by whatever unrelated claim is most recent -- that recency
    # guess IS the reported bug. Entity lookups are exempt: metric-less
    # "where does <name> rank" legitimately searches every ranking claim.
    if not parsed.metric_hints and ask_index.extract_metric_synonym(parsed.raw) is None:
        return _unanswerable(
            "could not map the requested metric to any known claims metric "
            "(no alias or synonym matched) -- refusing to guess", question
        )
    ranking_claims = [r for r in verified.values() if r.get("kind") == "ranking"]
    candidates = _filter_by_hints(ranking_claims, parsed)
    if not candidates:
        return _unanswerable(
            "no VERIFIED ranking claim matches the requested metric/window", question
        )
    row = max(candidates, key=lambda r: r.get("computed_at", ""))  # most-recent tie-break
    return _format_top_n_answer(parsed, question, row)


def _answer_entity_lookup(parsed, question: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """`candidates` is the caller's pre-assembled row list (index fast-path
    hits + any residual full-load rows for families lacking a fresh index)
    -- this function only does the final name-match + answer/evidence
    assembly, so the index fast path and the full-load fallback (see
    ask()'s FAMILY_ENTITY_LOOKUP branch) can never drift in answer SHAPE."""
    if not parsed.entity_name:
        return _unanswerable("could not extract a player/entity name from the question", question)
    name_key = parsed.entity_name.strip().lower()
    hits = []
    for row in candidates:
        for r in row.get("ranking", []):
            # NAME-KEYED stores (e.g. nba_referee_crew_ft: entity_key=
            # "entity_id" but the entity_id VALUE is the official's name,
            # not a numeric id) carry no "player_name" field at all -- only
            # checking that one key silently dropped every such row. Same
            # fallback chain claims_resolver._norm_row already uses for
            # display; applied here too so a named entity actually matches.
            row_name = r.get("player_name") or r.get("entity_name") or r.get("entity_id") or ""
            if _ascii_name(str(row_name)).strip().lower() == name_key:
                hits.append((row, r))
    if not hits:
        return _unanswerable(
            f"no VERIFIED ranking claim has an entry for entity_name={parsed.entity_name!r} "
            "(the entity may exist but did not clear the claim's min_sample floor)",
            question,
        )
    answers = [
        {
            "metric": row.get("criteria", {}).get("metric"), "window": row.get("criteria", {}).get("window"),
            "rank": r.get("rank"), "value": r.get("value"), "n": r.get("n"),
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


def _try_best_x(question: str) -> dict[str, Any] | None:
    """Minimal hook for the ONE-CONCLUSION composer: a singular "best <X>"
    question (not "top N best <X>", which stays FAMILY_TOP_N) with a wired
    aspect alias routes to compose_best(); anything else returns None so
    ask() falls through to its existing family dispatch unchanged."""
    text = question or ""
    if _TOP_N_ANYWHERE_RE.search(text):
        return None
    m = _BEST_SINGLE_RE.search(text)
    if not m:
        return None
    aspect = _BEST_ASPECT_ALIASES.get(m.group(1).lower())
    if aspect is None:
        return None
    from scripts.platformkit.intel_query.compose_best import compose_best  # local import: avoid import cycle

    result = compose_best(aspect)
    result["family"] = FAMILY_BEST
    result["question"] = question
    return result


def _try_shooter_profile(question: str) -> dict[str, Any] | None:
    """"what kind of shooter is <name>" / "shooter profile for <name>" ->
    compose_profile(name); anything else returns None so ask() falls through
    to the existing family dispatch unchanged."""
    m = _PROFILE_RE.search(question or "")
    if not m:
        return None
    name = (m.group("name") or m.group("name2") or "").strip()
    if not name:
        return None
    from scripts.platformkit.intel_query.compose_profile import compose_profile  # local: avoid import cycle

    result = compose_profile(name)
    result["family"] = FAMILY_SHOOTER_PROFILE
    result["question"] = question
    result["answerable"] = result.get("status") == "OK"
    return result
